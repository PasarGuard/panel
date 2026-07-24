import base64
import random
import secrets
from collections import defaultdict
from datetime import UTC, datetime as dt, timedelta

from jdatetime import date as jd

from app.core.hosts import host_manager
from app.db.crud.wireguard import pick_peer_ip_for_inbound
from app.db.models import UserStatus
from app.models.status_emojis import STATUS_EMOJIS
from app.models.subscription import SubscriptionInboundData
from app.models.user import UsersResponseWithInbounds
from app.settings import subscription_settings
from app.subscription.client_templates import subscription_client_templates, subscription_xray_templates
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

SERVER_IP = "127.0.0.1"
SERVER_IPV6 = "[::1]"


def _build_subscription_config(
    config_format: str,
    client_templates: dict[str, str],
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
        "user_agent_template_content": client_templates["USER_AGENT_TEMPLATE"],
        "grpc_user_agent_template_content": client_templates["GRPC_USER_AGENT_TEMPLATE"],
    }

    if config_format == "links":
        return StandardLinks(**common_kwargs)
    if config_format == "clash":
        return ClashConfiguration(
            clash_template_content=client_templates["CLASH_SUBSCRIPTION_TEMPLATE"],
            **common_kwargs,
        )
    if config_format == "clash_meta":
        return ClashMetaConfiguration(
            clash_template_content=client_templates["CLASH_SUBSCRIPTION_TEMPLATE"],
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
    client_templates = await subscription_client_templates()
    xray_template_overrides = await subscription_xray_templates() if config_format == "xray" else None
    conf = _build_subscription_config(config_format, client_templates)
    if conf is None:
        raise ValueError(f'Unsupported format "{config_format}"')

    sub_settings = await subscription_settings()
    custom_variables = get_effective_custom_variables(user, sub_settings.custom_variables)
    format_variables = setup_format_variables(user, sub_settings.custom_variables)

    config = await process_inbounds_and_tags(
        user,
        format_variables,
        conf,
        client_templates,
        xray_template_overrides=xray_template_overrides,
        randomize_order=randomize_order,
        custom_variables=custom_variables,
    )

    if as_base64 and not isinstance(config, bytes):
        config = base64.b64encode(config.encode()).decode()

    return config


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


def _custom_variable_parts(custom_variable) -> tuple[str | None, str]:
    if isinstance(custom_variable, dict):
        key = custom_variable.get("key")
        value = custom_variable.get("value", "")
    else:
        key = getattr(custom_variable, "key", None)
        value = getattr(custom_variable, "value", "")
    return (str(key) if key else None), str(value or "")


def get_effective_custom_variables(
    user: UsersResponseWithInbounds, custom_variables: list | tuple | None = None
) -> list:
    variables = list(custom_variables or [])
    admin_variables = getattr(getattr(user, "admin", None), "custom_variables", None) or []
    variables.extend(admin_variables)
    return variables


def apply_custom_format_variables(format_variables: dict, custom_variables: list | tuple | None = None) -> dict:
    if not custom_variables:
        return format_variables

    custom_keys = {key for key, _ in (_custom_variable_parts(variable) for variable in custom_variables) if key}
    base_variables = defaultdict(
        lambda: "<missing>",
        {key: value for key, value in format_variables.items() if key not in custom_keys},
    )

    for variable in custom_variables:
        key, raw_value = _custom_variable_parts(variable)
        if not key:
            continue
        try:
            format_variables[key] = raw_value.format_map(base_variables)
        except ValueError, KeyError:
            format_variables[key] = raw_value

    return format_variables


def _format_dynamic_value(value, format_variables: dict):
    if isinstance(value, str):
        try:
            return value.format_map(format_variables)
        except ValueError, KeyError:
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


async def filter_hosts(hosts: list[SubscriptionInboundData], user_status: UserStatus) -> list[SubscriptionInboundData]:
    return [host for host in hosts if not host.status or user_status in host.status]


async def process_host(
    inbound: SubscriptionInboundData,
    format_variables: dict,
    inbounds: list[str],
    proxies: dict,
    custom_variables: list | tuple | None = None,
) -> None | tuple[SubscriptionInboundData, dict]:
    """
    Process host data for subscription generation.
    Now only does random selection and user-specific formatting!
    All merging and data preparation is done in hosts.py.
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

    # Update format variables
    format_variables.update({"PROTOCOL": inbound.protocol})
    format_variables.update({"TRANSPORT": inbound.network})
    apply_custom_format_variables(format_variables, custom_variables)

    salt = secrets.token_hex(8)

    sni = ""
    if isinstance(inbound.tls_config.sni, list) and inbound.tls_config.sni:
        sni = random.choice(inbound.tls_config.sni)
    sni = sni.replace("*", salt)

    req_host = ""
    host_list = inbound.transport_config.host
    if isinstance(host_list, list) and host_list:
        req_host = random.choice(host_list)
    req_host = req_host.replace("*", salt)
    req_host = req_host.format_map(format_variables) if req_host else ""

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
    path = inbound.transport_config.path.format_map(format_variables) if inbound.transport_config.path else ""

    # Apply use_sni_as_host override
    if inbound.use_sni_as_host and sni:
        req_host = sni

    # Create a copy of the inbound data with selected random values
    # Deep copy tls_config and transport_config to avoid mutating cached host data
    inbound_copy = inbound.model_copy(
        update={
            "tls_config": inbound.tls_config.model_copy(deep=True),
            "transport_config": inbound.transport_config.model_copy(deep=True),
        }
    )

    # Update TLS config with selected values
    inbound_copy.tls_config.sni = sni
    inbound_copy.tls_config.reality_short_id = reality_sid

    # Update transport config with selected host
    inbound_copy.transport_config.host = req_host
    inbound_copy.transport_config.path = path
    if getattr(inbound_copy.transport_config, "request", None):
        inbound_copy.transport_config.request = _format_dynamic_value(
            inbound_copy.transport_config.request,
            format_variables,
        )
    if getattr(inbound_copy.transport_config, "response", None):
        inbound_copy.transport_config.response = _format_dynamic_value(
            inbound_copy.transport_config.response,
            format_variables,
        )

    # Update address and port with selected values
    inbound_copy.address = address
    inbound_copy.port = port

    return inbound_copy, settings


async def _prepare_download_settings(
    download_data: SubscriptionInboundData,
    format_variables: dict,
    inbounds: list[str],
    proxies: dict,
    client_templates: dict[str, str],
    custom_variables: list | tuple | None,
    conf: StandardLinks
    | XrayConfiguration
    | SingBoxConfiguration
    | ClashConfiguration
    | ClashMetaConfiguration
    | OutlineConfiguration
    | WireGuardConfiguration,
) -> SubscriptionInboundData | dict | None:
    result = await process_host(download_data, format_variables, inbounds, proxies, custom_variables)

    if not result:
        return

    download_copy, _ = result

    if isinstance(download_copy.address, str):
        download_copy.address = download_copy.address.format_map(format_variables)

    if isinstance(conf, StandardLinks):
        xc = XrayConfiguration(
            xray_template_content=client_templates["XRAY_SUBSCRIPTION_TEMPLATE"],
            user_agent_template_content=client_templates["USER_AGENT_TEMPLATE"],
            grpc_user_agent_template_content=client_templates["GRPC_USER_AGENT_TEMPLATE"],
        )
        return xc._download_config(download_copy, link_format=True)

    return download_copy


async def process_inbounds_and_tags(
    user: UsersResponseWithInbounds,
    format_variables: dict,
    conf: StandardLinks
    | XrayConfiguration
    | SingBoxConfiguration
    | ClashConfiguration
    | ClashMetaConfiguration
    | OutlineConfiguration
    | WireGuardConfiguration,
    client_templates: dict[str, str],
    xray_template_overrides: dict[int, str] | None = None,
    randomize_order: bool = False,
    custom_variables: list | tuple | None = None,
) -> str | bytes:
    proxy_settings = user.proxy_settings.dict()
    proxy_settings["_user_id"] = user.id
    hosts = await filter_hosts(list((await host_manager.get_hosts()).values()), user.status)
    if randomize_order and len(hosts) > 1:
        random.shuffle(hosts)

    def _resolve_host_xray_template_content(inbound: SubscriptionInboundData) -> str | None:
        if xray_template_overrides is None:
            return None
        if not isinstance(inbound.subscription_templates, dict):
            return None
        template_id = inbound.subscription_templates.get("xray")
        if not isinstance(template_id, int):
            return None
        return xray_template_overrides.get(template_id)

    for host_data in hosts:
        result = await process_host(host_data, format_variables, user.inbounds, proxy_settings, custom_variables)
        if not result:
            continue

        inbound_copy: SubscriptionInboundData
        inbound_copy, settings = result

        # Format remark and address with user variables
        remark = inbound_copy.remark.format_map(format_variables)
        formatted_address = inbound_copy.address.format_map(format_variables)

        download_settings = getattr(inbound_copy.transport_config, "download_settings", None)
        if download_settings:
            if isinstance(download_settings, SubscriptionInboundData):
                processed_download_settings = await _prepare_download_settings(
                    download_settings,
                    format_variables,
                    user.inbounds,
                    proxy_settings,
                    client_templates,
                    custom_variables,
                    conf,
                )
            else:
                processed_download_settings = download_settings
            if hasattr(inbound_copy.transport_config, "download_settings"):
                inbound_copy.transport_config.download_settings = processed_download_settings

        if isinstance(conf, XrayConfiguration):
            template_content = _resolve_host_xray_template_content(inbound_copy)
            conf.add(
                remark=remark,
                address=formatted_address,
                inbound=inbound_copy,
                settings=settings,
                template_content=template_content,
            )
        else:
            conf.add(
                remark=remark,
                address=formatted_address,
                inbound=inbound_copy,
                settings=settings,
            )

    return conf.render()


def encode_title(text: str) -> str:
    return f"base64:{base64.b64encode(text.encode()).decode()}"
