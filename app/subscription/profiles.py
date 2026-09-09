"""Opt-in full client-profile generators.

The legacy generators intentionally retain their historical behavior.  This
module is only called for an explicitly selected profile template.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

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

    if config_format == "sing_box":
        # The generator refuses a rule set it cannot turn into a source URL. If
        # that refusal only happened at build time the profile would save
        # cleanly and then 422 every subscription fetch bound to it, so the
        # operator would hear about the typo from their users.
        _singbox_rule_sets(_collect_rule_set_tags(profile.routing_rules))
        _singbox_pool_group_labels(profile)


def _singbox_dns_server(server: str, tag: str, detour: str | None) -> dict[str, Any]:
    """Sing-box wants the transport spelled out; Xray infers it from the string."""
    entry: dict[str, Any] = {"tag": tag}
    if server.startswith("https://"):
        # ProfileDns already refused anything urlsplit cannot read, so hostname
        # and port are trustworthy here. `server` has to be the bare host --
        # sing-box resolves it as written, so "dns.example:8443" or a bracketed
        # IPv6 literal there becomes a lookup that always fails.
        parts = urlsplit(server)
        entry.update({"type": "https", "server": parts.hostname})
        if parts.port is not None:
            entry["server_port"] = parts.port
        # A query string belongs to neither field; sing-box sends its own.
        entry["path"] = parts.path
    else:
        entry.update({"type": "udp", "server": server})
    if detour:
        entry["detour"] = detour
    return entry


def _balancer_strategy(profile: SubscriptionProfile) -> dict[str, Any]:
    """Xray reads leastLoad's tuning from a nested `settings` object.

    Without it leastLoad ranks the endpoints and sends everything to the
    winner, so the strategy that is supposed to spread load behaves exactly
    like leastPing. Omitted entirely when unset, to keep the emitted config
    identical for the strategies that ignore it.
    """
    strategy: dict[str, Any] = {"type": profile.balancer_strategy.value}
    if profile.balancer_settings is not None:
        settings = profile.balancer_settings.model_dump(exclude_none=True)
        if settings:
            strategy["settings"] = settings
    return strategy


def _applicable_xray_rules(
    rules: list[dict[str, Any]], generated: set[str], profile: SubscriptionProfile
) -> list[dict[str, Any]]:
    """Drop rules for generated groups this user cannot reach.

    Country and pool groups are created from the endpoints available to one
    user. A missing generated group is therefore expected; an arbitrary name
    remains in the output so validation still reports a typo.
    """
    declared_pools = {f"pg-auto-{pool.id}" for pool in profile.pools}
    return [
        rule
        for rule in rules
        if not (
            isinstance(rule.get("balancerTag"), str)
            and not rule.get("outboundTag")
            and (rule["balancerTag"] in declared_pools or re.fullmatch(r"pg-country-[a-z]{2}", rule["balancerTag"]))
            and rule["balancerTag"] not in generated
        )
    ]


def _resolved_singbox_rule(
    rule: dict[str, Any], reachable: set[str], group_targets: dict[str, str | None]
) -> dict[str, Any] | None:
    """Resolve stable group identifiers and omit known unavailable groups.

    Endpoint display tags remain valid for backwards compatibility. Group
    targets are resolved first, however, so an endpoint remark can never steal
    a route from a declared pool or generated country group.
    """
    target = rule.get("outbound")
    if not isinstance(target, str):
        return rule
    if target in group_targets:
        resolved = group_targets[target]
        if resolved is None:
            return None
        if resolved == target:
            return rule
        result = deepcopy(rule)
        result["outbound"] = resolved
        return result
    if target in reachable:
        return rule
    # Preserve unknown targets so output validation reports the typo.
    return rule


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


# Sing-box matches geo data through rule sets that have to be declared next to
# the rules that name them. Xray reads `geosite:`/`geoip:` straight out of a
# rule, so a profile written for one core has no equivalent for the other.
# The published file is named after the whole tag, so "geosite-netflix" lives
# at .../rule-set/geosite-netflix.srs; the prefix only selects the repository.
SINGBOX_RULE_SET_SOURCES = {
    "geosite": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/{tag}.srs",
    "geoip": "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/{tag}.srs",
}


def _collect_rule_set_tags(rules: list[dict[str, Any]]) -> list[str]:
    """Every rule set named anywhere in the operator's rules, including nested ones."""
    tags: list[str] = []

    def visit(rule: dict[str, Any]) -> None:
        referenced = rule.get("rule_set")
        if isinstance(referenced, str):
            tags.append(referenced)
        elif isinstance(referenced, list):
            tags.extend(tag for tag in referenced if isinstance(tag, str))
        for nested in rule.get("rules", []) or []:
            if isinstance(nested, dict):
                visit(nested)

    for rule in rules:
        if isinstance(rule, dict):
            visit(rule)
    return list(dict.fromkeys(tags))


def _singbox_rule_sets(tags: list[str]) -> list[dict[str, Any]]:
    """Declare each referenced rule set as a remote source.

    An undeclared reference is not a soft failure: `sing-box check` accepts the
    config and the client then refuses to start with "rule-set not found", so
    the profile has to emit these or reject the rule outright.
    """
    declared: list[dict[str, Any]] = []
    for tag in tags:
        prefix, _, name = tag.partition("-")
        template = SINGBOX_RULE_SET_SOURCES.get(prefix)
        if template is None or not name:
            raise ProfileValidationError(
                f"rule set '{tag}' cannot be resolved; name it 'geosite-<name>' or 'geoip-<name>'"
            )
        declared.append(
            {
                "type": "remote",
                "tag": tag,
                "format": "binary",
                "url": template.format(tag=tag),
                # download_detour is omitted on purpose: sing-box 1.14 deprecates
                # it and drops it in 1.16, and the default already fetches
                # outside the tunnel, which is what this needs anyway.
                "update_interval": "1d",
            }
        )
    return declared


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


def _ordered_endpoints(profile: SubscriptionProfile, endpoints: list[ProfileEndpoint]) -> list[ProfileEndpoint]:
    """Endpoints that survive pool filtering, in stable publication order."""
    groups = _grouped_endpoints(profile, endpoints)
    flattened = [endpoint for entries in groups.values() for endpoint in entries]
    return sorted(flattened, key=lambda item: (item.priority, item.machine_key, item.stable_tie_breaker))


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


def _xray_outbounds(
    endpoint: ProfileEndpoint, tag: str, client_templates: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    templates = client_templates or {}
    builder = XrayConfiguration(
        xray_template_content='{"outbounds": []}',
        user_agent_template_content=templates.get("USER_AGENT_TEMPLATE"),
        grpc_user_agent_template_content=templates.get("GRPC_USER_AGENT_TEMPLATE"),
    )
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


def build_xray_profile(
    profile: SubscriptionProfile,
    endpoints: list[ProfileEndpoint],
    *,
    client_templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    groups = _grouped_endpoints(profile, endpoints)
    endpoints = _ordered_endpoints(profile, endpoints)
    tags = _endpoint_tags(endpoints)
    outbounds: list[dict[str, Any]] = []
    pool_tags: dict[str, list[str]] = defaultdict(list)
    auto_pool_tags: dict[str, list[str]] = defaultdict(list)
    auto_country_tags: dict[str, list[str]] = defaultdict(list)

    for endpoint in endpoints:
        tag = tags[id(endpoint)]
        outbounds.extend(_xray_outbounds(endpoint, tag, client_templates))
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
            "strategy": _balancer_strategy(profile),
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
            {
                "tag": f"pg-country-{country.lower()}",
                "selector": actor_tags,
                "strategy": _balancer_strategy(profile),
            }
        )

    generated_groups = {balancer["tag"] for balancer in balancers}
    rules = _applicable_xray_rules(profile.routing_rules, generated_groups, profile)
    rules.append({"type": "field", "network": "tcp,udp", "balancerTag": f"pg-auto-{profile.default_pool}"})
    outbounds.extend(
        [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ]
    )
    subject_selector = [tag for pool in profile.pools for tag in auto_pool_tags.get(pool.id, [])]
    config = {
        # Clients hand this file to the core untouched and then dial the local
        # proxy themselves, so the listener has to be where they look for it.
        # A socks-in on port 1080 left tun2socks with nothing to connect to.
        # These match the default Xray subscription template this panel ships,
        # which is the shape the clients are known to accept.
        "inbounds": [
            {
                "tag": "socks",
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                # Without destOverride the core only ever sees IP addresses, so
                # every domain routing rule in the profile silently never matches.
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": False},
                "settings": {"auth": "noauth", "udp": True, "allowTransparent": False},
            },
            {
                "tag": "http",
                "listen": "127.0.0.1",
                "port": 10809,
                "protocol": "http",
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": False},
                "settings": {"auth": "noauth", "udp": True, "allowTransparent": False},
            },
        ],
        "log": {"loglevel": "warning"},
        "dns": {"servers": list(profile.dns.servers)},
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": profile.domain_strategy.value,
            "balancers": balancers,
            "rules": rules,
        },
    }
    if profile.health_check.burst:
        # leastPing/leastLoad need measured latency, which only burstObservatory
        # collects; plain observatory just tracks alive/dead.
        config["burstObservatory"] = {
            "subjectSelector": subject_selector,
            "pingConfig": {
                "destination": profile.health_check.url,
                "interval": profile.health_check.interval,
                "timeout": profile.health_check.probe_timeout,
                "sampling": 3,
            },
        }
    else:
        config["observatory"] = {
            "subjectSelector": subject_selector,
            "probeUrl": profile.health_check.url,
            "probeInterval": profile.health_check.interval,
        }
    _validate_xray_output_routing(config)
    return config


def _unique_label(label: str, used: set[str]) -> str:
    """Sing-box shows an outbound tag verbatim, so tags double as display names.

    Two pools may legitimately carry the same title, and a tag collision would
    make the config invalid rather than merely confusing, so duplicates get a
    numeric suffix.
    """
    candidate = label
    suffix = 2
    while candidate in used:
        candidate = f"{label} {suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _singbox_pool_group_labels(profile: SubscriptionProfile) -> dict[str, tuple[str, str]]:
    """Validate and allocate stable display tags for all declared pools."""
    labels: dict[str, tuple[str, str]] = {}
    # Reserve country groups even when this particular user has no endpoint in
    # that country. Otherwise an endpoint called "NL" would change from NL to
    # NL 2 as soon as an NL endpoint becomes available, and an old route would
    # silently change meaning.
    used = {"proxy", "direct"}
    for first in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for second in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            country = first + second
            used.update((country, f"{country} · Auto"))

    target_owners: defaultdict[str, set[str]] = defaultdict(set)
    for pool in profile.pools:
        target_owners[pool.id].add(f"pool '{pool.id}'")
        target_owners[f"pg-auto-{pool.id}"].add(f"automatic pool '{pool.id}'")
    for first in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for second in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            country = first + second
            target_owners[f"pg-country-{country.lower()}"].add(f"automatic country '{country}'")
    for target, owners in target_owners.items():
        if len(owners) > 1:
            raise ProfileValidationError(
                f"Generated group target '{target}' is ambiguous between {', '.join(sorted(owners))}"
            )
    machine_targets = set(target_owners)
    for pool in profile.pools:
        selector = pool.title or pool.id
        automatic = f"{selector} · Auto"
        for label in (selector, automatic):
            own_id = label == pool.id
            if label in used or (label in machine_targets and not own_id):
                raise ProfileValidationError(
                    f"Pool '{pool.id}' label '{label}' collides with another generated group or reserved target"
                )
            used.add(label)
        labels[pool.id] = (selector, automatic)
    return labels


def _auto_group_label(pool_or_country: str, *, title: str | None = None, is_country: bool = False) -> str:
    if title:
        return title
    return f"Auto ({pool_or_country.upper()})" if is_country else f"Auto ({pool_or_country})"


def build_xray_profile_configs(
    profile: SubscriptionProfile,
    endpoints: list[ProfileEndpoint],
    *,
    client_templates: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Emit one named Xray config per automatic group.

    Xray has no selector outbound, so a single config cannot offer the user a
    choice between groups: only a routing rule can point at a balancer. Clients
    do let the user pick between whole configs, and the legacy Xray
    subscription already ships a JSON array, so each group is published as its
    own entry instead. `remarks` is what the client displays.
    """
    base = build_xray_profile(profile, endpoints, client_templates=client_templates)
    balancer_tags = {balancer["tag"] for balancer in base["routing"]["balancers"]}

    labels: list[tuple[str, str]] = []
    for pool in profile.pools:
        tag = f"pg-auto-{pool.id}"
        if tag in balancer_tags:
            labels.append((tag, _auto_group_label(pool.id, title=pool.title)))
    for tag in sorted(balancer_tags):
        if tag.startswith("pg-country-"):
            labels.append((tag, _auto_group_label(tag.removeprefix("pg-country-"), is_country=True)))

    configs: list[dict[str, Any]] = []
    for tag, remark in labels:
        config = copy.deepcopy(base)
        # The catch-all rule appended by build_xray_profile is always the last
        # one; repointing it leaves any operator-authored rule ahead of it
        # untouched.
        config["routing"]["rules"][-1]["balancerTag"] = tag
        config["remarks"] = remark
        _validate_xray_output_routing(config)
        configs.append(config)

    if profile.publish_endpoint_configs:
        # A group is not a substitute for picking one server, so every endpoint
        # is published too. These carry no balancer: the catch-all rule names
        # the endpoint's own outbound directly.
        ordered = _ordered_endpoints(profile, endpoints)
        endpoint_tags = _endpoint_tags(ordered)
        for endpoint in ordered:
            config = copy.deepcopy(base)
            endpoint_tag = endpoint_tags[id(endpoint)]
            catch_all = config["routing"]["rules"][-1]
            catch_all.pop("balancerTag", None)
            catch_all["outboundTag"] = endpoint_tag
            # This config offers one server, so it carries no balancer. An
            # operator rule that names one still has to go somewhere: pointing
            # it at this endpoint keeps the rule's own matcher intact and means
            # the traffic it selects stays on the server the user picked.
            # Leaving the reference dangling made the whole subscription fail
            # validation, so a single balancer rule broke every config at once.
            for rule in config["routing"]["rules"]:
                if rule.get("balancerTag"):
                    rule.pop("balancerTag")
                    rule["outboundTag"] = endpoint_tag
            config["routing"]["balancers"] = []
            config.pop("observatory", None)
            config.pop("burstObservatory", None)
            config["remarks"] = endpoint.inbound.remark
            _validate_xray_output_routing(config)
            configs.append(config)
    return configs


def _singbox_endpoint(
    endpoint: ProfileEndpoint, tag: str, client_templates: dict[str, str] | None = None
) -> tuple[str, dict[str, Any]]:
    templates = client_templates or {}
    builder = SingBoxConfiguration(
        singbox_template_content='{"inbounds": [], "outbounds": []}',
        user_agent_template_content=templates.get("USER_AGENT_TEMPLATE"),
        grpc_user_agent_template_content=templates.get("GRPC_USER_AGENT_TEMPLATE"),
    )
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


def build_singbox_profile(
    profile: SubscriptionProfile,
    endpoints: list[ProfileEndpoint],
    *,
    client_templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    groups = _grouped_endpoints(profile, endpoints)
    endpoints = [endpoint for entries in groups.values() for endpoint in entries]
    outbounds: list[dict[str, Any]] = []
    singbox_endpoints: list[dict[str, Any]] = []
    pool_tags: dict[str, list[str]] = defaultdict(list)
    auto_pool_tags: dict[str, list[str]] = defaultdict(list)
    country_tags: dict[str, list[str]] = defaultdict(list)
    auto_country_tags: dict[str, list[str]] = defaultdict(list)
    pool_selector_tags: dict[str, str] = {}
    pool_auto_tags: dict[str, str | None] = {}
    pool_group_labels = _singbox_pool_group_labels(profile)
    # One namespace for endpoints and groups alike: a tag is what the client
    # prints in its server list, and a collision between the two would make the
    # config invalid rather than merely confusing.
    used_labels: set[str] = {"proxy", "direct"}
    for first in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for second in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            country = first + second
            used_labels.update((country, f"{country} · Auto"))
    for selector, automatic in pool_group_labels.values():
        used_labels.update((selector, automatic))

    for endpoint in sorted(endpoints, key=lambda item: (item.priority, item.machine_key, item.stable_tie_breaker)):
        # The machine tag exists so the Xray observatory can match on a prefix.
        # Sing-box has no such requirement and shows the tag to the user, so
        # putting it here meant picking a server from a list of hashes.
        tag = _unique_label(endpoint.inbound.remark, used_labels)
        container, generated_endpoint = _singbox_endpoint(endpoint, tag, client_templates)
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
        pool_tag, auto_tag = pool_group_labels[pool.id]
        if pool.id not in groups:
            pool_auto_tags[pool.id] = None
            continue
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
        else:
            pool_auto_tags[pool.id] = None
        if automatic_tags:
            pool_auto_tags[pool.id] = auto_tag
        pool_selector_tags[pool.id] = pool_tag
        outbounds.append(
            {
                "type": "selector",
                "tag": pool_tag,
                "outbounds": ([auto_tag] if automatic_tags else []) + pool_tags[pool.id],
            }
        )
        selection_tags.append(pool_tag)
    for country, actor_tags in sorted(country_tags.items()):
        country_tag = country.upper()
        auto_country_tag: str | None = f"{country.upper()} · Auto"
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
        else:
            auto_country_tag = None
        outbounds.append(
            {
                "type": "selector",
                "tag": country_tag,
                "outbounds": ([auto_country_tag] if auto_country_tag else []) + actor_tags,
            }
        )
        selection_tags.append(country_tag)

    group_targets: dict[str, str | None] = {}
    for pool in profile.pools:
        selector, automatic = pool_group_labels[pool.id]
        emitted_selector = pool_selector_tags.get(pool.id)
        emitted_auto = pool_auto_tags.get(pool.id)
        for alias in (pool.id, selector):
            group_targets[alias] = emitted_selector
        for alias in (f"pg-auto-{pool.id}", automatic):
            group_targets[alias] = emitted_auto
    for first in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for second in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            country = first + second
            automatic = f"{country} · Auto"
            emitted_selector = country if country in country_tags else None
            emitted_auto = automatic if auto_country_tags.get(country) else None
            group_targets[country] = emitted_selector
            group_targets[automatic] = emitted_auto
            # This is the same canonical country target used by Xray, whose
            # country groups are automatic balancers.
            group_targets[f"pg-country-{country.lower()}"] = emitted_auto

    root_selector = pool_selector_tags[profile.default_pool]
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
    # Everything below mirrors the Sing-box subscription template this panel
    # ships, which is the shape its clients are known to accept. The profile
    # used to emit a bare mixed proxy on 127.0.0.1:1080 and nothing else: no
    # tun for VPN mode to capture traffic, no sniffing so every domain rule
    # silently failed to match, no DNS hijack so queries escaped the tunnel,
    # and no auto_detect_interface, which a device needs to find its real
    # egress instead of routing into itself.
    reachable = {outbound["tag"] for outbound in outbounds} | {entry["tag"] for entry in singbox_endpoints}
    operator_rules = [
        resolved
        for rule in profile.routing_rules
        if (resolved := _resolved_singbox_rule(rule, reachable, group_targets)) is not None
    ]
    route_rules = [
        # Both inbounds, not just the tun: hijack-dns matches on `protocol`, and
        # so does every domain rule below, and only sniffing fills that in. A
        # desktop client dialling the local mixed proxy would otherwise see its
        # domain rules never match and its DNS queries leave the tunnel.
        {"inbound": ["tun-in", "mixed-in"], "action": "sniff"},
        {"protocol": "dns", "action": "hijack-dns"},
        *operator_rules,
    ]
    rule_sets = _singbox_rule_sets(_collect_rule_set_tags(route_rules))
    config = {
        "log": {"level": "warn", "timestamp": False},
        "dns": {
            "servers": [
                # Only the first resolver: `final` names one server and this
                # profile emits no dns.rules, so any further entry would be
                # declared and referenced by nothing. Sing-box has no "try the
                # next one" list -- extra servers are reachable only through a
                # rule that selects them. Xray takes the whole list.
                # Resolving through the proxy keeps queries off the local network.
                _singbox_dns_server(profile.dns.servers[0], "dns-remote", "proxy"),
                # Reaching the servers themselves must not depend on the tunnel.
                {"type": "local", "tag": "dns-local"},
            ],
            "final": "dns-remote",
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": "sing-tun",
                "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
                "auto_route": True,
                "route_exclude_address": [
                    "192.168.0.0/16",
                    "10.0.0.0/8",
                    "169.254.0.0/16",
                    "172.16.0.0/12",
                    "fe80::/10",
                    "fc00::/7",
                ],
            },
            # Kept alongside the tun so a desktop client, or anything that only
            # wants a local proxy, still has somewhere to connect.
            {"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2080},
        ],
        "outbounds": outbounds,
        "route": {
            "rules": route_rules,
            "final": "proxy",
            # Required since sing-box 1.14: without it the client refuses to
            # start at all. Outbound addresses resolve locally on purpose, so
            # reaching the servers never depends on the tunnel being up first.
            "default_domain_resolver": {"server": "dns-local"},
            "auto_detect_interface": True,
            # override_android_vpn is deliberately absent. The shipped template
            # sets it, but Sing-box refuses to start with it anywhere except
            # Android ("initialize network manager: `override_android_vpn` is
            # only supported on Android"), and one profile is served to every
            # platform.
        },
        "experimental": {"cache_file": {"enabled": True, "store_dns": True}},
    }
    if rule_sets:
        config["route"]["rule_set"] = rule_sets
    if singbox_endpoints:
        config["endpoints"] = singbox_endpoints
    _validate_singbox_output_routing(config)
    return config
