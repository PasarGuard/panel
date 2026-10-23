from collections.abc import Callable, Iterable
from functools import cached_property

from app.models.subscription import SubscriptionInboundData

DEFAULT_TAG_PREFIX = "out"


def host_tag(tag_prefix: str | None, host_id: int | None) -> str:
    return f"{tag_prefix or DEFAULT_TAG_PREFIX}-{host_id}"


class HostRef:
    """A host as client templates see it, in the `hosts` list.

    The remark and the outbound are built on first access and then kept, so a template that never asks for it costs nothing.
    A host this user may not have (it is restricted to other user statuses, or its inbound or
    protocol is not theirs) has no outbounds and is not `available`: templates that embed outbounds should skip it.
    A disabled host is only `is_disabled`: it is no profile of its own, but templates may still embed it.
    Its tag is `<tag_prefix>-<id>`, so tags are unique and `<tag_prefix>-` selects a group in Xray.
    """

    def __init__(
        self,
        host: SubscriptionInboundData,
        format_remark: Callable[[SubscriptionInboundData], str],
        build_outbounds: Callable[[SubscriptionInboundData, str], list[dict] | None],
        *,
        visible: bool = True,
    ):
        self.id = host.id
        self.tag_prefix = host.tag_prefix or ""
        self.tag = host_tag(host.tag_prefix, host.id)
        self.is_disabled = host.is_disabled
        self.protocol = host.protocol
        self.network = host.network
        self._host = host
        self._visible = visible
        self._format_remark = format_remark
        self._build = build_outbounds

    @cached_property
    def remark(self) -> str:
        return self._format_remark(self._host)

    @cached_property
    def outbounds(self) -> list[dict]:
        """Main outbound first, then the ones it depends on (dialers). Empty if the host cannot be built."""
        return (self._build(self._host, self.tag) or []) if self._visible else []

    @property
    def available(self) -> bool:
        return bool(self.outbounds)

    @property
    def outbound(self) -> dict | None:
        return self.outbounds[0] if self.outbounds else None


def sample_host_refs(tag_prefixes: Iterable[str], count: int = 0) -> list[HostRef]:
    """For validating a template: `count` hosts, at least one untagged and one per tag prefix in use, and a last one
    the user has no access to. The rest repeat the prefixes in turn."""
    prefixes = ["", *dict.fromkeys(tag_prefixes)]
    tagged = [prefixes[index % len(prefixes)] for index in range(max(count - 1, len(prefixes)))]
    no_access_id = len(tagged) + 1

    def build(host: SubscriptionInboundData, tag: str) -> list[dict] | None:
        return None if host.id == no_access_id else [{"tag": tag, "protocol": "freedom", "settings": {}}]

    # Only what HostRef reads is set, so there is nothing to validate; the list can hold thousands
    hosts = [
        SubscriptionInboundData.model_construct(
            id=number, remark=f"Sample {number}", protocol="vless", network="tcp", tag_prefix=prefix or None
        )
        for number, prefix in enumerate([*tagged, prefixes[-1]], 1)
    ]
    return [HostRef(host, lambda host: host.remark, build) for host in hosts]
