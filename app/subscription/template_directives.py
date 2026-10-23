"""`pasarguard` directives in client templates.

A template may carry a `pasarguard` key that tells the panel which of the user's hosts to put where:
- Xray JSON: top-level `{"mode": "per_host" | "single", "inject": [{"select": {...}, "tag_prefix": "de", "tag_from": "index"}]}`
- Sing-box: inside a `selector`/`urltest` outbound, `{"include_proxies": true, "select": {...}}`
- Clash/Mihomo: inside a `proxy-groups` item, `{include-proxies: true, select: {...}}`

The key is always stripped from the output. Templates without it render exactly as before.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.utils.logger import get_logger

logger = get_logger("template-directives")

DIRECTIVE_KEY = "pasarguard"
SINGBOX_GROUP_TYPES = ("selector", "urltest")


@dataclass(frozen=True, slots=True)
class HostCandidate:
    """What a selector can match a host on. `remark` is the remark after format variables."""

    host_id: int | None
    inbound_tag: str
    remark: str


class HostSelector(BaseModel):
    """Picks hosts the user receives. All given conditions must match; an empty selector matches every host."""

    model_config = ConfigDict(extra="forbid")

    inbound_tags: list[str] | None = None
    inbound_tag_regex: str | None = None
    remark_regex: str | None = None
    host_ids: list[int] | None = None
    # Reserved for host tags (upstream PR #667); rejected until hosts have tags.
    tags: list[str] | None = None

    @field_validator("inbound_tag_regex", "remark_regex")
    @classmethod
    def validate_regex(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid regular expression {value!r}: {exc}") from exc
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        if value:
            raise ValueError("selecting hosts by tags is not supported yet")
        return value

    def matches(self, host: HostCandidate) -> bool:
        if self.inbound_tags is not None and host.inbound_tag not in self.inbound_tags:
            return False
        if self.host_ids is not None and host.host_id not in self.host_ids:
            return False
        if self.inbound_tag_regex is not None and not re.search(self.inbound_tag_regex, host.inbound_tag):
            return False
        return self.remark_regex is None or re.search(self.remark_regex, host.remark) is not None


class XrayInject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    select: HostSelector = Field(default_factory=HostSelector)
    # Index tags default to "proxy-1..n"; remark tags have no prefix unless one is given.
    tag_prefix: str | None = Field(default=None, min_length=1, max_length=64)
    tag_from: Literal["index", "remark"] = "index"


class XrayDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["per_host", "single"] = "per_host"
    inject: list[XrayInject] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_single_has_inject(self):
        if self.mode == "single" and not self.inject:
            raise ValueError('"single" mode needs at least one "inject" entry')
        return self


class GroupDirective(BaseModel):
    """Sing-box selector/urltest outbound or Clash proxy group directive."""

    model_config = ConfigDict(extra="forbid")

    include_proxies: bool = Field(default=True, validation_alias=AliasChoices("include_proxies", "include-proxies"))
    select: HostSelector = Field(default_factory=HostSelector)


# A directive that cannot be parsed at render time selects no hosts.
NOTHING = GroupDirective(include_proxies=True, select=HostSelector(host_ids=[]))


def parse_group_directive(raw: Any, where: str) -> GroupDirective:
    try:
        return GroupDirective.model_validate(raw)
    except ValidationError as exc:
        logger.warning(f"Ignoring invalid pasarguard directive in {where}: {exc}")
        return NOTHING


def parse_xray_directive(raw: Any) -> XrayDirective | None:
    try:
        return XrayDirective.model_validate(raw)
    except ValidationError as exc:
        logger.warning(f"Ignoring invalid pasarguard directive in xray template: {exc}")
        return None


def validate_xray_template_directive(parsed: dict) -> None:
    if DIRECTIVE_KEY in parsed:
        XrayDirective.model_validate(parsed[DIRECTIVE_KEY])


def validate_singbox_template_directives(parsed: dict) -> None:
    if DIRECTIVE_KEY in parsed:
        raise ValueError('"pasarguard" is only allowed inside selector/urltest outbounds')
    for outbound in parsed.get("outbounds") or []:
        if not isinstance(outbound, dict) or DIRECTIVE_KEY not in outbound:
            continue
        if outbound.get("type") not in SINGBOX_GROUP_TYPES:
            raise ValueError(
                f'"pasarguard" is only allowed inside selector/urltest outbounds (found in {outbound.get("tag")!r})'
            )
        GroupDirective.model_validate(outbound[DIRECTIVE_KEY])


def validate_clash_template_directives(parsed: Any) -> None:
    if not isinstance(parsed, dict):
        return
    for group in parsed.get("proxy-groups") or []:
        if isinstance(group, dict) and DIRECTIVE_KEY in group:
            GroupDirective.model_validate(group[DIRECTIVE_KEY])


def merge_group_members(existing: Any, members: list[str]) -> list:
    """Author-written entries first, then the selected proxies that are not already listed."""
    result = list(existing) if isinstance(existing, list) else []
    seen = {item for item in result if isinstance(item, str)}
    for member in members:
        if member not in seen:
            seen.add(member)
            result.append(member)
    return result
