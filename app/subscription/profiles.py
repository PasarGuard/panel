"""Opt-in full client-profile generators.

The legacy generators intentionally retain their historical behavior.  This
module is only called for an explicitly selected profile template.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.models.subscription import SubscriptionInboundData
from app.models.subscription_profile import SubscriptionProfile

from .singbox import SingBoxConfiguration
from .xray import XrayConfiguration


class ProfileValidationError(ValueError):
    """A profile can be saved but is not publishable for this user."""


@dataclass(frozen=True)
class ProfileEndpoint:
    inbound: SubscriptionInboundData
    address: str
    settings: dict[str, Any]
    pool: str
    country: str | None
    priority: int
    exclude_from_auto: bool

    @property
    def machine_key(self) -> str:
        # Host ID and inbound tag are stable across randomized address/port/SNI
        # materialization.  The inbound tag distinguishes multiple endpoints
        # on one host without consulting user-visible remarks.
        host_key = str(self.inbound.host_id or self.inbound.inbound_tag)
        return f"{host_key}\x1f{self.inbound.inbound_tag}\x1f{self.pool}"

    @property
    def source_identity(self) -> str:
        """Hash materialized source data so secrets never appear in tags or logs."""
        canonical_source = json.dumps(
            {"address": self.address, "settings": self.settings},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical_source.encode()).hexdigest()

    @property
    def stable_tie_breaker(self) -> tuple[bool, str, int, str]:
        """Totally order distinct materialized endpoints with the same machine key."""
        return (self.exclude_from_auto, self.country or "", self.priority, self.source_identity)


def load_profile(content: str) -> SubscriptionProfile:
    try:
        return SubscriptionProfile.model_validate_json(content)
    except Exception as exc:
        raise ProfileValidationError(f"Invalid subscription profile: {exc}") from exc


def validate_profile_routing_rules(profile: SubscriptionProfile, config_format: str) -> None:
    """Reject rule shapes that belong to the other client engine before output."""
    for index, rule in enumerate(profile.routing_rules):
        prefix = f"routing_rules[{index}]"
        if config_format == "xray":
            if rule.get("type") != "field":
                raise ProfileValidationError(f"{prefix} must use Xray field-rule type 'field'")
            if not any(isinstance(rule.get(key), str) and rule[key] for key in ("outboundTag", "balancerTag")):
                raise ProfileValidationError(f"{prefix} must set Xray outboundTag or balancerTag")
            continue

        if config_format != "sing_box":
            raise ProfileValidationError(f'Unsupported profile format "{config_format}"')

        rule_type = rule.get("type")
        if rule_type is None:
            if not any(isinstance(rule.get(key), str) and rule[key] for key in ("action", "outbound")):
                raise ProfileValidationError(f"{prefix} must set Sing-box action or outbound")
            continue
        if rule_type != "logical":
            raise ProfileValidationError(f"{prefix} has unsupported Sing-box rule type '{rule_type}'")
        if rule.get("mode") not in ("and", "or") or not isinstance(rule.get("rules"), list):
            raise ProfileValidationError(f"{prefix} logical rule requires mode 'and'/'or' and a rules array")
        if not any(isinstance(rule.get(key), str) and rule[key] for key in ("action", "outbound")):
            raise ProfileValidationError(f"{prefix} logical rule must set Sing-box action or outbound")


def _validate_xray_output_routing(config: dict[str, Any]) -> None:
    outbound_tags = {outbound.get("tag") for outbound in config["outbounds"] if outbound.get("tag")}
    balancer_tags = {balancer.get("tag") for balancer in config["routing"]["balancers"] if balancer.get("tag")}
    for index, rule in enumerate(config["routing"]["rules"]):
        outbound_tag = rule.get("outboundTag")
        balancer_tag = rule.get("balancerTag")
        prefix = f"routing.rules[{index}]"
        if outbound_tag and balancer_tag:
            raise ProfileValidationError(f"{prefix} cannot set both outboundTag and balancerTag")
        if outbound_tag and outbound_tag not in outbound_tags:
            raise ProfileValidationError(f"{prefix}.outboundTag references unknown outbound '{outbound_tag}'")
        if balancer_tag and balancer_tag not in balancer_tags:
            raise ProfileValidationError(f"{prefix}.balancerTag references unknown balancer '{balancer_tag}'")


def _validate_singbox_output_routing(config: dict[str, Any]) -> None:
    target_tags = {outbound.get("tag") for outbound in config["outbounds"] if outbound.get("tag")}
    target_tags.update(endpoint.get("tag") for endpoint in config.get("endpoints", []) if endpoint.get("tag"))

    def validate_rule(rule: dict[str, Any], prefix: str) -> None:
        outbound = rule.get("outbound")
        if outbound and outbound not in target_tags:
            raise ProfileValidationError(f"{prefix}.outbound references unknown outbound '{outbound}'")
        if rule.get("type") == "logical":
            for index, nested_rule in enumerate(rule.get("rules", [])):
                validate_rule(nested_rule, f"{prefix}.rules[{index}]")

    for index, rule in enumerate(config["route"]["rules"]):
        validate_rule(rule, f"route.rules[{index}]")


def endpoint_from_inbound(inbound: SubscriptionInboundData, address: str, settings: dict[str, Any]) -> ProfileEndpoint:
    classification = inbound.profile_classification or {}
    pool = str(classification.get("pool") or "primary").lower()
    country = classification.get("country")
    country = str(country).upper() if country else None
    priority = classification.get("priority")
    return ProfileEndpoint(
        inbound=inbound,
        address=address,
        settings=settings,
        pool=pool,
        country=country,
        priority=int(priority if priority is not None else inbound.priority),
        exclude_from_auto=bool(classification.get("exclude_from_auto", False)),
    )


def _endpoint_tags(endpoints: list[ProfileEndpoint]) -> dict[int, str]:
    """Create deterministic unique tags, even for duplicate endpoint inputs."""
    result: dict[int, str] = {}
    occurrences: defaultdict[str, int] = defaultdict(int)
    for endpoint in sorted(endpoints, key=lambda item: (item.machine_key, item.stable_tie_breaker)):
        digest = hashlib.sha256(endpoint.machine_key.encode()).hexdigest()[:16]
        occurrences[digest] += 1
        # Observatory selectors are prefix based.  A fixed-width occurrence
        # suffix prevents one endpoint tag from selecting a duplicate tag too.
        result[id(endpoint)] = f"pg-proxy-{digest}-{occurrences[digest]:04d}"
    return result


def _retag_xray_outbounds(outbounds: list[dict[str, Any]], tag_map: dict[str, str]) -> list[dict[str, Any]]:
    """Retag Xray references without rewriting endpoint credentials or hosts."""

    def retag_dialer_references(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                retag_dialer_references(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == "dialerProxy" and isinstance(item, str):
                    value[key] = tag_map.get(item, item)
                else:
                    retag_dialer_references(item)

    retagged = deepcopy(outbounds)
    for outbound in retagged:
        outbound["tag"] = tag_map.get(outbound.get("tag"), outbound.get("tag"))
        retag_dialer_references(outbound)
    return retagged


def _grouped_endpoints(
    profile: SubscriptionProfile, endpoints: list[ProfileEndpoint]
) -> dict[str, list[ProfileEndpoint]]:
    enabled_pools = {pool.id for pool in profile.pools if pool.enabled}
    groups: dict[str, list[ProfileEndpoint]] = {pool_id: [] for pool_id in enabled_pools}
    for endpoint in endpoints:
        if endpoint.pool in enabled_pools:
            groups[endpoint.pool].append(endpoint)
    if not groups[profile.default_pool]:
        raise ProfileValidationError(f"Profile has no eligible endpoints in the default pool '{profile.default_pool}'")
    return {pool_id: entries for pool_id, entries in groups.items() if entries}


def _xray_outbounds(endpoint: ProfileEndpoint, tag: str) -> list[dict[str, Any]]:
    builder = XrayConfiguration(xray_template_content='{"outbounds": []}')
    builder.add(
        remark=tag,
        address=endpoint.address,
        inbound=endpoint.inbound,
        settings=endpoint.settings,
    )
    if not builder.config:
        raise ProfileValidationError(
            f"Endpoint '{endpoint.inbound.inbound_tag}' uses a transport or protocol unsupported by Xray profile output"
        )
    outbounds = builder.config[-1]["outbounds"]
    tags = {
        "proxy": tag,
        "dialer": f"pg-dialer-{tag.removeprefix('pg-proxy-')}",
        "dsdialer": f"pg-dsdialer-{tag.removeprefix('pg-proxy-')}",
    }
    return _retag_xray_outbounds(outbounds, tags)


def build_xray_profile(profile: SubscriptionProfile, endpoints: list[ProfileEndpoint]) -> dict[str, Any]:
    groups = _grouped_endpoints(profile, endpoints)
    endpoints = [endpoint for entries in groups.values() for endpoint in entries]
    tags = _endpoint_tags(endpoints)
    outbounds: list[dict[str, Any]] = []
    pool_tags: dict[str, list[str]] = defaultdict(list)
    auto_pool_tags: dict[str, list[str]] = defaultdict(list)
    auto_country_tags: dict[str, list[str]] = defaultdict(list)

    for endpoint in sorted(endpoints, key=lambda item: (item.priority, item.machine_key, item.stable_tie_breaker)):
        tag = tags[id(endpoint)]
        outbounds.extend(_xray_outbounds(endpoint, tag))
        pool_tags[endpoint.pool].append(tag)
        if not endpoint.exclude_from_auto:
            auto_pool_tags[endpoint.pool].append(tag)
        if endpoint.country and not endpoint.exclude_from_auto:
            auto_country_tags[endpoint.country].append(tag)

    balancers: list[dict[str, Any]] = []
    for pool in profile.pools:
        if pool.id not in groups:
            continue
        candidates = auto_pool_tags[pool.id]
        if not candidates:
            if pool.id == profile.default_pool:
                raise ProfileValidationError(
                    f"Profile has no automatic endpoints in the default pool '{profile.default_pool}'"
                )
            continue
        balancer: dict[str, Any] = {
            "tag": f"pg-auto-{pool.id}",
            "selector": candidates,
            "strategy": {"type": "random"},
        }
        if pool.fallback_pool and auto_pool_tags[pool.fallback_pool]:
            # Xray requires fallbackTag to name an outbound, not another
            # balancer/group.  Select the deterministic first endpoint from
            # the declared fallback pool; its own balancer remains available
            # to routing rules as pg-auto-<pool>.
            balancer["fallbackTag"] = auto_pool_tags[pool.fallback_pool][0]
        balancers.append(balancer)
    for country, actor_tags in sorted(auto_country_tags.items()):
        balancers.append(
            {"tag": f"pg-country-{country.lower()}", "selector": actor_tags, "strategy": {"type": "random"}}
        )

    rules = list(profile.routing_rules)
    rules.append({"type": "field", "network": "tcp,udp", "balancerTag": f"pg-auto-{profile.default_pool}"})
    outbounds.extend(
        [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ]
    )
    config = {
        "inbounds": [
            {"tag": "socks-in", "listen": "127.0.0.1", "port": 1080, "protocol": "socks", "settings": {"udp": True}}
        ],
        "outbounds": outbounds,
        "observatory": {
            "subjectSelector": [tag for pool in profile.pools for tag in auto_pool_tags.get(pool.id, [])],
            "probeUrl": profile.health_check.url,
            "probeInterval": profile.health_check.interval,
        },
        "routing": {"domainStrategy": "AsIs", "balancers": balancers, "rules": rules},
    }
    _validate_xray_output_routing(config)
    return config


def _singbox_endpoint(endpoint: ProfileEndpoint, tag: str) -> tuple[str, dict[str, Any]]:
    builder = SingBoxConfiguration(singbox_template_content='{"inbounds": [], "outbounds": []}')
    builder.add(remark=tag, address=endpoint.address, inbound=endpoint.inbound, settings=endpoint.settings)
    if builder.config["outbounds"]:
        return "outbounds", builder.config["outbounds"][0]
    if builder.config.get("endpoints"):
        generated_endpoint = builder.config["endpoints"][0]
        if generated_endpoint.get("type") == "wireguard" and generated_endpoint.get("system") is True:
            # Linux interface names are limited to 15 bytes. Derive a stable,
            # collision-resistant name from the already-stable endpoint tag so
            # multiple WireGuard endpoints never all claim the legacy `wg0`.
            generated_endpoint["name"] = f"wg{hashlib.sha256(tag.encode()).hexdigest()[:12]}"
        return "endpoints", generated_endpoint
    raise ProfileValidationError(
        f"Endpoint '{endpoint.inbound.inbound_tag}' uses a transport or protocol unsupported by Sing-box profile output"
    )


def build_singbox_profile(profile: SubscriptionProfile, endpoints: list[ProfileEndpoint]) -> dict[str, Any]:
    groups = _grouped_endpoints(profile, endpoints)
    endpoints = [endpoint for entries in groups.values() for endpoint in entries]
    tags = _endpoint_tags(endpoints)
    outbounds: list[dict[str, Any]] = []
    singbox_endpoints: list[dict[str, Any]] = []
    pool_tags: dict[str, list[str]] = defaultdict(list)
    auto_pool_tags: dict[str, list[str]] = defaultdict(list)
    country_tags: dict[str, list[str]] = defaultdict(list)
    auto_country_tags: dict[str, list[str]] = defaultdict(list)

    for endpoint in sorted(endpoints, key=lambda item: (item.priority, item.machine_key, item.stable_tie_breaker)):
        tag = tags[id(endpoint)]
        container, generated_endpoint = _singbox_endpoint(endpoint, tag)
        (outbounds if container == "outbounds" else singbox_endpoints).append(generated_endpoint)
        pool_tags[endpoint.pool].append(tag)
        if not endpoint.exclude_from_auto:
            auto_pool_tags[endpoint.pool].append(tag)
        if endpoint.country:
            country_tags[endpoint.country].append(tag)
            if not endpoint.exclude_from_auto:
                auto_country_tags[endpoint.country].append(tag)

    selection_tags: list[str] = []
    for pool in profile.pools:
        if pool.id not in groups:
            continue
        auto_tag = f"pg-auto-{pool.id}"
        automatic_tags = auto_pool_tags[pool.id]
        if not automatic_tags and pool.id == profile.default_pool:
            raise ProfileValidationError(
                f"Profile has no automatic endpoints in the default pool '{profile.default_pool}'"
            )
        if automatic_tags:
            outbounds.append(
                {
                    "type": "urltest",
                    "tag": auto_tag,
                    "outbounds": automatic_tags,
                    "url": profile.health_check.url,
                    "interval": profile.health_check.interval,
                    "tolerance": profile.health_check.tolerance,
                    "idle_timeout": profile.health_check.timeout,
                }
            )
        pool_tag = f"pg-select-{pool.id}"
        outbounds.append(
            {
                "type": "selector",
                "tag": pool_tag,
                "outbounds": ([auto_tag] if automatic_tags else []) + pool_tags[pool.id],
            }
        )
        selection_tags.append(pool_tag)
    for country, actor_tags in sorted(country_tags.items()):
        country_tag = f"pg-country-{country.lower()}"
        auto_country_tag = f"pg-auto-country-{country.lower()}"
        automatic_tags = auto_country_tags[country]
        if automatic_tags:
            outbounds.append(
                {
                    "type": "urltest",
                    "tag": auto_country_tag,
                    "outbounds": automatic_tags,
                    "url": profile.health_check.url,
                    "interval": profile.health_check.interval,
                    "tolerance": profile.health_check.tolerance,
                    "idle_timeout": profile.health_check.timeout,
                }
            )
        outbounds.append(
            {
                "type": "selector",
                "tag": country_tag,
                "outbounds": ([auto_country_tag] if automatic_tags else []) + actor_tags,
            }
        )
        selection_tags.append(country_tag)

    root_selector = f"pg-select-{profile.default_pool}"
    root_choices = list(dict.fromkeys([root_selector, *selection_tags]))
    outbounds.extend(
        [
            {"type": "selector", "tag": "proxy", "outbounds": root_choices},
            {"type": "direct", "tag": "direct"},
        ]
    )
    # Sing-box urltest selects the best member of its own list; it has no native
    # fallbackTag equivalent.  The selector intentionally exposes each pool so
    # clients can choose a fallback without promising strict failover.
    route_rules = list(profile.routing_rules)
    config = {
        "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 1080}],
        "outbounds": outbounds,
        "route": {"rules": route_rules, "final": "proxy"},
    }
    if singbox_endpoints:
        config["endpoints"] = singbox_endpoints
    _validate_singbox_output_routing(config)
    return config
