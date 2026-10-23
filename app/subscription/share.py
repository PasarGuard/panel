import base64
import json
import random
import secrets
from collections import defaultdict
from copy import copy
from dataclasses import dataclass
from datetime import UTC, datetime as dt, timedelta
from functools import cached_property

from jdatetime import date as jd

from app.core.hosts import host_manager
from app.db.crud.wireguard import pick_peer_ip_for_inbound
from app.db.models import UserStatus
from app.models.client_template import TemplateSource
from app.models.status_emojis import STATUS_EMOJIS
from app.models.subscription import SubscriptionInboundData
from app.models.user import UsersResponseWithInbounds
from app.settings import subscription_settings
from app.subscription.client_templates import subscription_client_templates, subscription_xray_templates
from app.subscription.config_cache import (
    get_or_create_sub_config,
    make_sub_config_key,
)
from app.subscription.host_refs import HostRef
from app.templates import render_template_string, render_variables
from app.templates.failures import report_failure, template_ref, variable_ref
from app.templates.pool import subscription_pool
from app.utils.helpers import has_markup_unsafe_chars, has_oversized_format_spec
from app.utils.logger import get_logger
from app.utils.system import readable_size

from . import (
    ClashConfiguration,
    ClashMetaConfiguration,
    OutlineConfiguration,
    SingBoxConfiguration,
    StandardLinks,
    WireGuardConfiguration,
    XrayConfiguration,
)

logger = get_logger("subscription")

SERVER_IP = "127.0.0.1"
SERVER_IPV6 = "[::1]"

# Transports only the Xray JSON format can express.
XRAY_ONLY_NETWORKS = frozenset({"xdrive"})


USER_AGENT_TEMPLATE_KEYS = ("USER_AGENT_TEMPLATE", "GRPC_USER_AGENT_TEMPLATE")
# The client templates each format reads
FORMAT_TEMPLATE_KEYS = {
    "links": USER_AGENT_TEMPLATE_KEYS,
    "clash": (*USER_AGENT_TEMPLATE_KEYS, "CLASH_SUBSCRIPTION_TEMPLATE"),
    "clash_meta": (*USER_AGENT_TEMPLATE_KEYS, "CLASH_SUBSCRIPTION_TEMPLATE"),
    "sing_box": (*USER_AGENT_TEMPLATE_KEYS, "SINGBOX_SUBSCRIPTION_TEMPLATE"),
    "xray": (*USER_AGENT_TEMPLATE_KEYS, "XRAY_SUBSCRIPTION_TEMPLATE"),
    "outline": (),
    "wireguard": (),
}


def _render_if_jinja(content: str, use_jinja: bool, format_variables: dict) -> str:
    return render_template_string(content, format_variables) if use_jinja else content


class TemplateRenderError(Exception):
    """A client template failed to render, or rendered to something that is not JSON."""

    def __init__(self, template_id: int | None):
        super().__init__(f"Client template {template_id} failed to render")
        self.template_id = template_id


def _render_json_template(source: TemplateSource, variables: dict) -> str:
    """Renders a JSON client template. A failure is logged with the template's id and raised: serving a
    subscription without what the template should have added would break clients without anyone noticing."""
    try:
        text = _render_if_jinja(source.content, source.use_jinja, variables)
        if source.use_jinja:
            json.loads(text)
    except Exception as exc:
        report_failure(template_ref(source.id), exc)
        raise TemplateRenderError(source.id) from exc
    return text


def _render_client_templates(client_templates: dict[str, TemplateSource], format_variables: dict) -> dict[str, str]:
    """Render the Jinja2 in the JSON client templates with the user's variables.

    Clash is left alone: it renders last, once it has the proxies (see ClashConfiguration.render).
    """
    rendered: dict[str, str] = {}
    for key, source in client_templates.items():
        if key == "CLASH_SUBSCRIPTION_TEMPLATE":
            rendered[key] = source.content
            continue
        rendered[key] = _render_json_template(source, format_variables)
    return rendered


def _build_subscription_config(
    config_format: str,
    client_templates: dict[str, str],
    format_variables: dict,
    clash_template_ref: str | None = None,
) -> (
    StandardLinks
    | XrayConfiguration
    | SingBoxConfiguration
    | ClashConfiguration
    | ClashMetaConfiguration
    | OutlineConfiguration
    | WireGuardConfiguration
    | None
):
    common_kwargs = {
        "user_agent_template_content": client_templates.get("USER_AGENT_TEMPLATE"),
        "grpc_user_agent_template_content": client_templates.get("GRPC_USER_AGENT_TEMPLATE"),
    }

    if config_format == "links":
        return StandardLinks(**common_kwargs)
    if config_format == "clash":
        return ClashConfiguration(
            clash_template_content=client_templates["CLASH_SUBSCRIPTION_TEMPLATE"],
            format_variables=format_variables,
            template_ref=clash_template_ref,
            **common_kwargs,
        )
    if config_format == "clash_meta":
        return ClashMetaConfiguration(
            clash_template_content=client_templates["CLASH_SUBSCRIPTION_TEMPLATE"],
            format_variables=format_variables,
            template_ref=clash_template_ref,
            **common_kwargs,
        )
    if config_format == "sing_box":
        return SingBoxConfiguration(
            singbox_template_content=client_templates["SINGBOX_SUBSCRIPTION_TEMPLATE"],
            **common_kwargs,
        )
    if config_format == "outline":
        return OutlineConfiguration()
    if config_format == "wireguard":
        return WireGuardConfiguration()
    if config_format == "xray":
        return XrayConfiguration(
            xray_template_content=client_templates["XRAY_SUBSCRIPTION_TEMPLATE"],
            **common_kwargs,
        )
    return None


async def generate_subscription(
    user: UsersResponseWithInbounds,
    config_format: str,
    as_base64: bool,
    randomize_order: bool = False,
) -> str | bytes:
    cache_key = make_sub_config_key(user, config_format, as_base64, randomize_order)

    async def render() -> str | bytes:
        sub_settings = await subscription_settings()
        custom_variables = get_effective_custom_variables(user, sub_settings.custom_variables)
        raw_client_templates = await subscription_client_templates()
        all_hosts = list((await host_manager.get_all_hosts()).values())
        xray_template_overrides = await subscription_xray_templates() if config_format == "xray" else None
        user_agents = tuple(
            source.content if (source := raw_client_templates.get(key)) else None for key in USER_AGENT_TEMPLATE_KEYS
        )
        used_templates = {
            key: raw_client_templates[key] for key in FORMAT_TEMPLATE_KEYS[config_format] if key in raw_client_templates
        }

        def build() -> str | bytes:
            format_variables = setup_format_variables(user, sub_settings.custom_variables)
            preparer = HostPreparer(user, format_variables, custom_variables, all_hosts, user_agents)
            refs = preparer.host_refs()
            template_context = {**format_variables, "hosts": refs}
            client_templates = _render_client_templates(used_templates, template_context)
            clash = raw_client_templates.get("CLASH_SUBSCRIPTION_TEMPLATE")
            clash_template_ref = template_ref(clash.id) if clash else None
            conf = _build_subscription_config(config_format, client_templates, template_context, clash_template_ref)
            if conf is None:
                raise ValueError(f'Unsupported format "{config_format}"')

            return process_inbounds_and_tags(
                user,
                conf,
                client_templates,
                preparer,
                refs,
                xray_template_overrides=xray_template_overrides,
                randomize_order=randomize_order,
            )

        # Jinja is CPU work: it runs in the render pool's threads so it does not block the event loop. Formats with
        # no client template (WireGuard, Outline) and no Jinja variable have none, so a busy pool cannot refuse them.
        if FORMAT_TEMPLATE_KEYS[config_format] or any(_custom_variable_parts(v)[2] for v in custom_variables):
            config = await subscription_pool.run(build)
        else:
            config = build()
        if as_base64 and not isinstance(config, bytes):
            config = base64.b64encode(config.encode()).decode()
        return config

    # Building yields to the render pool, so identical requests that arrive meanwhile share one build instead of
    # each taking a slot of the pool.
    return await get_or_create_sub_config(cache_key, render)


def inject_body_placement(conf: str | bytes, lines: list[str], placement: str, as_base64: bool) -> str | bytes:
    if isinstance(conf, bytes) or not lines:
        return conf

    block = "\n".join(lines)
    if as_base64:
        try:
            decoded = base64.b64decode(conf).decode()
        except ValueError, UnicodeDecodeError:
            return conf
        merged = f"{block}\n{decoded}" if placement == "body_start" else f"{decoded}\n{block}"
        return base64.b64encode(merged.encode()).decode()

    return f"{block}\n{conf}" if placement == "body_start" else f"{conf}\n{block}"


def format_time_left(seconds_left: int) -> str:
    if not seconds_left or seconds_left <= 0:
        return "∞"

    minutes, _ = divmod(seconds_left, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    months, days = divmod(days, 30)

    result = []
    if months:
        result.append(f"{int(months)}m")
    if days:
        result.append(f"{int(days)}d")
    if hours and (days < 7):
        result.append(f"{int(hours)}h")
    if minutes and not (months or days):
        result.append(f"{int(minutes)}m")
    return " ".join(result)


def _custom_variable_parts(custom_variable) -> tuple[str | None, str, bool, str | None]:
    """key, value, use_jinja and the owner (None for the global variables, `admin:<id>` for an admin's)."""
    get = (
        custom_variable.get
        if isinstance(custom_variable, dict)
        else lambda name, default: getattr(custom_variable, name, default)
    )
    key, value, use_jinja, owner = get("key", None), get("value", ""), get("use_jinja", False), get("owner", None)
    return (str(key) if key else None), str(value or ""), bool(use_jinja), owner


def get_effective_custom_variables(
    user: UsersResponseWithInbounds, custom_variables: list | tuple | None = None
) -> list:
    """The global variables, then the admin's, which win on the same key. The admin's carry their owner."""
    variables = list(custom_variables or [])
    admin = getattr(user, "admin", None)
    if admin_variables := getattr(admin, "custom_variables", None):
        owner = f"admin:{getattr(admin, 'id', None) or admin.username}"
        for variable in admin_variables:
            key, value, use_jinja, _ = _custom_variable_parts(variable)
            variables.append({"key": key, "value": value, "use_jinja": use_jinja, "owner": owner})
    return variables


def apply_custom_format_variables(format_variables: dict, custom_variables: list | tuple | None = None) -> dict:
    if not custom_variables:
        return format_variables

    custom_keys = {parts[0] for parts in map(_custom_variable_parts, custom_variables) if parts[0]}
    base_variables = defaultdict(
        lambda: "<missing>",
        {key: value for key, value in format_variables.items() if key not in custom_keys},
    )

    for variable in custom_variables:
        key, raw_value, use_jinja, owner = _custom_variable_parts(variable)
        if not key:
            continue
        try:
            format_variables[key] = render_variables(raw_value, base_variables, use_jinja=use_jinja)
        except (ValueError, KeyError) as exc:
            report_failure(variable_ref(key, owner), exc)
            format_variables[key] = raw_value

    return format_variables


def _format_dynamic_value(value, format_variables: dict):
    if isinstance(value, str):
        if has_oversized_format_spec(value):
            # Formatting would build the padded result first; a value saved before the size check stays raw text
            return value
        try:
            return value.format_map(format_variables)
        except ValueError, KeyError, AttributeError, IndexError, TypeError:
            # A value the variables cannot fill (stray brace, {0}, {X.y}) is kept as it is
            return value
    if isinstance(value, list):
        return [_format_dynamic_value(item, format_variables) for item in value]
    if isinstance(value, dict):
        return {key: _format_dynamic_value(item, format_variables) for key, item in value.items()}
    return value


def setup_format_variables(user: UsersResponseWithInbounds, custom_variables: list | tuple | None = None) -> dict:
    custom_variables = get_effective_custom_variables(user, custom_variables)
    user_status = user.status
    expire = user.expire
    on_hold_expire_duration = user.on_hold_expire_duration
    now = dt.now(UTC)

    admin_username = ""
    if admin_data := user.admin:
        admin_username = admin_data.username

    if user_status != UserStatus.on_hold:
        if expire is not None:
            seconds_left = (expire - now).total_seconds()
            expire_date_obj = expire.date()
            expire_date = expire_date_obj.strftime("%Y-%m-%d")
            jalali_expire_date = jd.fromgregorian(
                year=expire_date_obj.year, month=expire_date_obj.month, day=expire_date_obj.day
            ).strftime("%Y-%m-%d")
            if now < expire:
                days_left = (expire - now).days + 1
                time_left = format_time_left(seconds_left)
            else:
                days_left = "0"
                time_left = "0"

        else:
            days_left = "∞"
            time_left = "∞"
            expire_date = "∞"
            jalali_expire_date = "∞"
    else:
        if on_hold_expire_duration:
            days_left = timedelta(seconds=on_hold_expire_duration).days
            time_left = format_time_left(on_hold_expire_duration)
            expire_date = "-"
            jalali_expire_date = "-"
        else:
            days_left = "∞"
            time_left = "∞"
            expire_date = "∞"
            jalali_expire_date = "∞"

    if user.data_limit:
        data_limit = readable_size(user.data_limit)
        data_left = user.data_limit - user.used_traffic
        usage_Percentage = round((user.used_traffic / user.data_limit) * 100.0, 2)

        data_left = max(data_left, 0)
        data_left = readable_size(data_left)
    else:
        data_limit = "∞"
        data_left = "∞"
        usage_Percentage = "∞"

    status_emoji = STATUS_EMOJIS.get(user.status.value)

    format_variables = defaultdict(
        lambda: "<missing>",
        {
            "SERVER_IP": SERVER_IP,
            "SERVER_IPV6": SERVER_IPV6,
            "USERNAME": user.username,
            "DATA_USAGE": readable_size(user.used_traffic),
            "DATA_LIMIT": data_limit,
            "DATA_LEFT": data_left,
            "DAYS_LEFT": days_left,
            "EXPIRE_DATE": expire_date,
            "JALALI_EXPIRE_DATE": jalali_expire_date,
            "TIME_LEFT": time_left,
            "STATUS_EMOJI": status_emoji,
            "USAGE_PERCENTAGE": usage_Percentage,
            "ADMIN_USERNAME": admin_username,
        },
    )

    return apply_custom_format_variables(format_variables, custom_variables)


def host_matches(host: SubscriptionInboundData, user_status: UserStatus) -> bool:
    """Whether the host's restriction to user statuses lets this user have it."""
    return not host.status or user_status in host.status


def filter_hosts(hosts: list[SubscriptionInboundData], user_status: UserStatus) -> list[SubscriptionInboundData]:
    return [host for host in hosts if not host.is_disabled and host_matches(host, user_status)]


def _prepare_download_settings(
    download_data: SubscriptionInboundData,
    format_variables: dict,
    inbounds: list[str],
    proxies: dict,
    client_templates: dict[str, str] | None,
    custom_variables: list | tuple | None,
) -> SubscriptionInboundData | dict | None:
    """`client_templates` is given for share links, where the download settings become part of the link."""
    result = process_host(download_data, format_variables, inbounds, proxies, custom_variables)

    if not result:
        return

    download_copy, _, variables = result

    if isinstance(download_copy.address, str):
        download_copy.address = _format_dynamic_value(download_copy.address, variables)

    if client_templates is not None:
        xc = XrayConfiguration(
            user_agent_template_content=client_templates.get("USER_AGENT_TEMPLATE"),
            grpc_user_agent_template_content=client_templates.get("GRPC_USER_AGENT_TEMPLATE"),
        )
        return xc._download_config(download_copy, link_format=True)

    return download_copy


def set_host_variables(
    format_variables: dict, inbound: SubscriptionInboundData, custom_variables: list | tuple | None
) -> dict:
    """The variables of one host: its own PROTOCOL and TRANSPORT, then the custom ones that may build on them.

    Returns a new dict, so hosts never see each other's variables.
    """
    variables = copy(format_variables)
    variables.update({"PROTOCOL": inbound.protocol, "TRANSPORT": inbound.network})
    return apply_custom_format_variables(variables, custom_variables)


def process_host(
    inbound: SubscriptionInboundData,
    format_variables: dict,
    inbounds: list[str],
    proxies: dict,
    custom_variables: list | tuple | None = None,
) -> None | tuple[SubscriptionInboundData, dict, dict]:
    """
    Process host data for subscription generation.
    Now only does random selection and user-specific formatting!
    All merging and data preparation is done in hosts.py.

    Returns the host, the user's settings for its protocol, and the host's own variables.
    """

    if inbound.inbound_tag not in inbounds:
        return

    # Get user settings for this protocol
    settings = proxies.get(inbound.protocol)
    if not settings:
        return
    settings = dict(settings)

    # Keep user id accessible for protocol-level dynamic allocation helpers.
    user_id = proxies.get("_user_id")
    if user_id is not None:
        settings["_user_id"] = user_id

    # Each WG interface only gets the user's peer IP from its own subnet.
    if inbound.protocol == "wireguard":
        settings["peer_ips"] = pick_peer_ip_for_inbound(inbound.wireguard_local_address, settings.get("peer_ips") or [])

    format_variables = set_host_variables(format_variables, inbound, custom_variables)

    salt = secrets.token_hex(8)

    sni = ""
    if isinstance(inbound.tls_config.sni, list) and inbound.tls_config.sni:
        sni = random.choice(inbound.tls_config.sni)
    sni = sni.replace("*", salt)
    sni = _format_dynamic_value(sni, format_variables) if sni else ""

    req_host = ""
    host_list = inbound.transport_config.host
    if isinstance(host_list, list) and host_list:
        req_host = random.choice(host_list)
    req_host = req_host.replace("*", salt)
    req_host = _format_dynamic_value(req_host, format_variables) if req_host else ""

    address = ""
    if inbound.address:
        address = random.choice(inbound.address).replace("*", salt)

    # Select random port from list
    port = random.choice(inbound.port) if inbound.port else 0

    # Select random Reality short ID if available
    if inbound.tls_config.reality_short_ids:
        reality_sid = random.choice(inbound.tls_config.reality_short_ids)
    else:
        reality_sid = inbound.tls_config.reality_short_id

    # Format path with variables
    path = (
        _format_dynamic_value(inbound.transport_config.path, format_variables) if inbound.transport_config.path else ""
    )

    # Apply use_sni_as_host override
    if inbound.use_sni_as_host and sni:
        req_host = sni

    # Copy only the nested models we mutate so cached host objects stay intact.
    transport_update: dict = {"host": req_host, "path": path}
    if getattr(inbound.transport_config, "request", None):
        transport_update["request"] = _format_dynamic_value(
            inbound.transport_config.request,
            format_variables,
        )
    if getattr(inbound.transport_config, "response", None):
        transport_update["response"] = _format_dynamic_value(
            inbound.transport_config.response,
            format_variables,
        )
    inbound_copy = inbound.model_copy(
        update={
            "tls_config": inbound.tls_config.model_copy(
                update={"sni": sni, "reality_short_id": reality_sid},
            ),
            "transport_config": inbound.transport_config.model_copy(update=transport_update),
            "address": address,
            "port": port,
        }
    )

    return inbound_copy, settings, format_variables


@dataclass
class PreparedHost:
    """A host with the user's choices made (address, SNI, ...), ready for `conf.add`."""

    inbound: SubscriptionInboundData
    settings: dict
    remark: str
    address: str
    variables: dict  # the host's own, for whatever is rendered for it later


class HostPreparer:
    """The hosts of one request. Each is prepared once, so the entry in the listing and the outbound a template
    embeds through `hosts` agree on the random choices (address, SNI, ...)."""

    def __init__(
        self,
        user: UsersResponseWithInbounds,
        format_variables: dict,
        custom_variables: list | tuple | None,
        hosts: list[SubscriptionInboundData],
        user_agent_templates: tuple[str | None, str | None] = (None, None),
    ):
        self.user_status = user.status
        self.user_inbounds = user.inbounds
        self.proxy_settings = user.proxy_settings.dict()
        self.proxy_settings["_user_id"] = user.id
        self.format_variables = format_variables
        self.custom_variables = custom_variables
        self.hosts = hosts
        self.user_agent_templates = user_agent_templates
        self._prepared: dict[tuple[int, bool], PreparedHost | None] = {}

    @cached_property
    def _builder(self) -> XrayConfiguration:
        return XrayConfiguration(
            user_agent_template_content=self.user_agent_templates[0],
            grpc_user_agent_template_content=self.user_agent_templates[1],
        )

    def prepare(
        self, host: SubscriptionInboundData, client_templates: dict[str, str] | None = None
    ) -> PreparedHost | None:
        """`client_templates` is given for share links, which carry the download settings inside the link."""
        key = (id(host), client_templates is not None)
        if key not in self._prepared:
            self._prepared[key] = self._prepare(host, client_templates)
        return self._prepared[key]

    def _prepare(self, host: SubscriptionInboundData, client_templates: dict[str, str] | None) -> PreparedHost | None:
        result = process_host(
            host, self.format_variables, self.user_inbounds, self.proxy_settings, self.custom_variables
        )
        if not result:
            return None

        inbound_copy, settings, variables = result

        # Format remark and address with user variables
        remark = _format_dynamic_value(inbound_copy.remark, variables)
        formatted_address = _format_dynamic_value(inbound_copy.address, variables)
        if has_markup_unsafe_chars(formatted_address):
            # Never valid, and links print the address unencoded; covers hosts saved before
            # address validation existed and values that came in through a format variable.
            return None

        download_settings = getattr(inbound_copy.transport_config, "download_settings", None)
        if download_settings:
            if isinstance(download_settings, SubscriptionInboundData):
                processed_download_settings = _prepare_download_settings(
                    download_settings,
                    variables,
                    self.user_inbounds,
                    self.proxy_settings,
                    client_templates,
                    self.custom_variables,
                )
            else:
                processed_download_settings = download_settings
            if hasattr(inbound_copy.transport_config, "download_settings"):
                inbound_copy.transport_config.download_settings = processed_download_settings

        return PreparedHost(inbound_copy, settings, remark, formatted_address, variables)

    def host_refs(self) -> list[HostRef]:
        """Every host, disabled ones included, for the `hosts` variable of client templates. A disabled host is not a
        profile of its own but templates may still embed it. One restricted to other user statuses is
        marked, so templates that skip unavailable hosts follow the same rules as the subscription."""
        return [
            HostRef(host, self.remark, self.outbounds, visible=host_matches(host, self.user_status))
            for host in self.hosts
        ]

    def remark(self, host: SubscriptionInboundData) -> str:
        if prepared := self._prepared.get((id(host), False)):
            return prepared.remark
        variables = set_host_variables(self.format_variables, host, self.custom_variables)
        try:
            return _format_dynamic_value(host.remark, variables)
        except ValueError, KeyError, IndexError:
            return host.remark

    def outbounds(self, host: SubscriptionInboundData, tag: str) -> list[dict] | None:
        """None for a host the user has no access to."""
        prepared = self.prepare(host)
        if not prepared:
            return None
        return self._builder.build_outbounds(prepared.address, prepared.inbound, prepared.settings, tag)


def process_inbounds_and_tags(
    user: UsersResponseWithInbounds,
    conf: StandardLinks
    | XrayConfiguration
    | SingBoxConfiguration
    | ClashConfiguration
    | ClashMetaConfiguration
    | OutlineConfiguration
    | WireGuardConfiguration,
    client_templates: dict[str, str],
    preparer: HostPreparer,
    refs: list[HostRef],
    xray_template_overrides: dict[int, TemplateSource] | None = None,
    randomize_order: bool = False,
) -> str | bytes:
    hosts = filter_hosts(preparer.hosts, user.status)
    if randomize_order and len(hosts) > 1:
        random.shuffle(hosts)

    def _resolve_host_xray_template_content(prepared: PreparedHost) -> str | None:
        if xray_template_overrides is None:
            return None
        if not isinstance(prepared.inbound.subscription_templates, dict):
            return None
        template_id = prepared.inbound.subscription_templates.get("xray")
        if not isinstance(template_id, int):
            return None
        override = xray_template_overrides.get(template_id)
        if override is None:
            return None
        return _render_json_template(override, {**prepared.variables, "hosts": refs})

    is_links = isinstance(conf, StandardLinks)
    for host_data in hosts:
        if host_data.network in XRAY_ONLY_NETWORKS and not isinstance(conf, XrayConfiguration):
            # Links, sing-box, Clash and Outline cannot carry these transports.
            continue
        prepared = preparer.prepare(host_data, client_templates if is_links else None)
        if not prepared:
            continue

        kwargs = {
            "remark": prepared.remark,
            "address": prepared.address,
            "inbound": prepared.inbound,
            "settings": prepared.settings,
        }
        if isinstance(conf, XrayConfiguration):
            kwargs["template_content"] = _resolve_host_xray_template_content(prepared)
        conf.add(**kwargs)

    return conf.render()


def encode_title(text: str) -> str:
    return f"base64:{base64.b64encode(text.encode()).decode()}"
