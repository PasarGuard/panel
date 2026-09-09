"""Conservative reference checks of rendered preview bodies, without changing them."""

import json
from contextlib import contextmanager
from contextvars import ContextVar

import yaml

_preview_exceptions: ContextVar[list[str] | None] = ContextVar("client_preview_exceptions", default=None)


@contextmanager
def collect_preview_exceptions():
    exceptions: list[str] = []
    token = _preview_exceptions.set(exceptions)
    try:
        yield exceptions
    finally:
        _preview_exceptions.reset(token)


def record_preview_exception(message: str) -> None:
    exceptions = _preview_exceptions.get()
    if exceptions is not None and message not in exceptions:
        exceptions.append(message)


def _objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _tags(value, key="tag"):
    return {item[key] for item in _objects(value) if isinstance(item.get(key), str)}


def diagnose_client_body(content: str | bytes, config_format: str) -> list[str]:
    """Report definite missing references only; this is not a complete core schema validator."""
    if config_format not in {"xray", "sing_box", "clash", "clash_meta"}:
        return []
    try:
        document = yaml.safe_load(content) if config_format in {"clash", "clash_meta"} else json.loads(content)
    except ValueError, TypeError, UnicodeError, yaml.YAMLError:
        return ["Rendered configuration could not be parsed for reference checks."]
    errors: list[str] = []

    def reference(value, known, path, kind):
        if isinstance(value, str) and value and value not in known:
            errors.append(f"{path} references a missing {kind}.")

    if config_format == "xray":
        documents = document if isinstance(document, list) else [document]
        for index, config in enumerate(documents):
            if not isinstance(config, dict):
                continue
            prefix = f"configs[{index}]." if isinstance(document, list) else ""
            outbounds = _tags(config.get("outbounds"))
            routing = config.get("routing")
            if not isinstance(routing, dict):
                continue
            balancers = _tags(routing.get("balancers"))
            for rule_index, rule in enumerate(_objects(routing.get("rules"))):
                path = f"{prefix}routing.rules[{rule_index}]"
                reference(rule.get("outboundTag"), outbounds, f"{path}.outboundTag", "outbound")
                reference(rule.get("balancerTag"), balancers, f"{path}.balancerTag", "balancer")
            for balancer_index, balancer in enumerate(_objects(routing.get("balancers"))):
                selectors = balancer.get("selector")
                if (
                    isinstance(selectors, list)
                    and all(isinstance(value, str) for value in selectors)
                    and not any(tag.startswith(selector) for selector in selectors for tag in outbounds)
                ):
                    errors.append(f"{prefix}routing.balancers[{balancer_index}].selector matches no outbounds.")
                reference(
                    balancer.get("fallbackTag"), outbounds,
                    f"{prefix}routing.balancers[{balancer_index}].fallbackTag", "outbound",
                )
    elif config_format == "sing_box" and isinstance(document, dict):
        outbounds = _tags(document.get("outbounds")) | _tags(document.get("endpoints"))

        def route_rules(rules, path):
            for index, rule in enumerate(_objects(rules)):
                rule_path = f"{path}[{index}]"
                if rule.get("action") in (None, "route"):
                    reference(rule.get("outbound"), outbounds, f"{rule_path}.outbound", "outbound or endpoint")
                if rule.get("type") == "logical":
                    route_rules(rule.get("rules"), f"{rule_path}.rules")

        route = document.get("route")
        if isinstance(route, dict):
            reference(route.get("final"), outbounds, "route.final", "outbound or endpoint")
            route_rules(route.get("rules"), "route.rules")
        for index, outbound in enumerate(_objects(document.get("outbounds"))):
            if outbound.get("type") not in ("selector", "urltest"):
                continue
            members = outbound.get("outbounds")
            if isinstance(members, list):
                if not members:
                    errors.append(f"outbounds[{index}].outbounds has no selectable targets.")
                for member_index, member in enumerate(members):
                    reference(member, outbounds, f"outbounds[{index}].outbounds[{member_index}]", "outbound or endpoint")
    elif config_format in {"clash", "clash_meta"} and isinstance(document, dict):
        policies = _tags(document.get("proxies"), "name") | _tags(document.get("proxy-groups"), "name")
        policies |= {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}
        providers = document.get("proxy-providers")
        providers = set(providers) if isinstance(providers, dict) else set()
        rule_providers = document.get("rule-providers")
        rule_providers = set(rule_providers) if isinstance(rule_providers, dict) else set()
        for index, group in enumerate(_objects(document.get("proxy-groups"))):
            for key, known, kind in (("proxies", policies, "proxy or group"), ("use", providers, "proxy provider")):
                if isinstance(group.get(key), list):
                    for member_index, member in enumerate(group[key]):
                        reference(member, known, f"proxy-groups[{index}].{key}[{member_index}]", kind)
        simple_rules = {
            "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-REGEX", "GEOSITE", "GEOIP",
            "IP-CIDR", "IP-CIDR6", "IP-SUFFIX", "SRC-IP-CIDR", "SRC-PORT", "DST-PORT",
            "IN-PORT", "PROCESS-NAME", "PROCESS-PATH", "PROCESS-NAME-REGEX", "PROCESS-PATH-REGEX",
            "NETWORK", "UID", "IN-TYPE", "IN-USER", "IN-NAME", "RULE-SET",
        }
        rules = document.get("rules")
        for index, rule in enumerate(rules if isinstance(rules, list) else []):
            if not isinstance(rule, str):
                continue
            parts = [part.strip() for part in rule.split(",")]
            if parts[-1] == "no-resolve":
                parts.pop()
            if len(parts) == 2 and parts[0] == "MATCH":
                reference(parts[1], policies, f"rules[{index}].policy", "proxy or group")
            elif len(parts) == 3 and parts[0] in simple_rules:
                reference(parts[2], policies, f"rules[{index}].policy", "proxy or group")
                if parts[0] == "RULE-SET":
                    reference(parts[1], rule_providers, f"rules[{index}].provider", "rule provider")
    return errors
