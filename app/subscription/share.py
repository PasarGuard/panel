import base64
import random
import secrets
from collections import defaultdict
from copy import deepcopy
from datetime import datetime as dt, timedelta, timezone

from jdatetime import date as jd

from app.core.hosts import host_manager
from app.db.models import UserStatus
from app.models.subscription import SubscriptionInboundData
from app.models.user import UsersResponseWithInbounds
from app.subscription.client_templates import subscription_client_templates, subscription_xray_templates
from app.utils.system import get_public_ip, get_public_ipv6, readable_size

from . import (
    ClashConfiguration,
    ClashMetaConfiguration,
    OutlineConfiguration,
    SingBoxConfiguration,
    StandardLinks,
    WireGuardConfiguration,
    XrayConfiguration,
)

SERVER_IP = get_public_ip()
SERVER_IPV6 = get_public_ipv6()

STATUS_EMOJIS = {
    "active": "✅",
    "expired": "⌛️",
    "limited": "🪫",
    "disabled": "❌",
    "on_hold": "🔌",
}


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

    format_variables = setup_format_variables(user)

    config = await process_inbounds_and_tags(
        user,
        format_variables,
        conf,
        client_templates,
        xray_template_overrides=xray_template_overrides,
        randomize_order=randomize_order,
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


def setup_format_variables(user: UsersResponseWithInbounds) -> dict:
    user_status = user.status
    expire = user.expire
    on_hold_expire_duration = user.on_hold_expire_duration
    now = dt.now(timezone.utc)

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

        if data_left < 0:
            data_left = 0
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

    return format_variables


async def filter_hosts(hosts: list[SubscriptionInboundData], user_status: UserStatus) -> list[SubscriptionInboundData]:
    return [host for host in hosts if not host.status or user_status in host.status]


async def process_host(
    inbound: SubscriptionInboundData, format_variables: dict, inbounds: list[str], proxies: dict
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

    # Handle flow: user settings have priority, fall back to inbound flow
    if "flow" in settings and settings["flow"] == "":
        # User has empty flow, use inbound flow as default
        settings["flow"] = inbound.inbound_flow

    # Update format variables
    format_variables.update({"PROTOCOL": inbound.protocol})
    format_variables.update({"TRANSPORT": inbound.network})

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
    inbound_copy = deepcopy(inbound)

    # Update TLS config with selected values
    inbound_copy.tls_config.sni = sni
    inbound_copy.tls_config.reality_short_id = reality_sid

    # Update transport config with selected host
    inbound_copy.transport_config.host = req_host
    inbound_copy.transport_config.path = path

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
    conf: StandardLinks
    | XrayConfiguration
    | SingBoxConfiguration
    | ClashConfiguration
    | ClashMetaConfiguration
    | OutlineConfiguration
    | WireGuardConfiguration,
) -> SubscriptionInboundData | dict | None:
    result = await process_host(download_data, format_variables, inbounds, proxies)

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
) -> list | str | bytes:
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
        result = await process_host(host_data, format_variables, user.inbounds, proxy_settings)
        if not result:
            continue

        inbound_copy: SubscriptionInboundData
        inbound_copy, settings = result

        # Format remark and address with user variables
        remark = inbound_copy.remark.format_map(format_variables)
        formatted_address = inbound_copy.address.format_map(format_variables)

        download_settings = getattr(inbound_copy.transport_config, "download_settings", None)
        if download_settings:
            processed_download_settings = await _prepare_download_settings(
                download_settings,
                format_variables,
                user.inbounds,
                proxy_settings,
                client_templates,
                conf,
            )
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
