import copy
import json
from types import SimpleNamespace

from app.core.live_update import node_facing, only_live_parts_changed
from app.models.core import CoreType

BASE = {
    "log": {"loglevel": "warning"},
    "inbounds": [{"tag": "in", "port": 443, "protocol": "vless", "settings": {"clients": [], "decryption": "none"}}],
    "outbounds": [{"tag": "DIRECT", "protocol": "freedom"}, {"tag": "BLOCK", "protocol": "blackhole"}],
    "routing": {
        "domainStrategy": "AsIs",
        "rules": [{"type": "field", "ip": ["geoip:private"], "outboundTag": "BLOCK"}],
    },
}


def view(config: dict, *, core_type=CoreType.xray, exclude=()) -> dict:
    core = SimpleNamespace(type=core_type, to_str=lambda: json.dumps(config), exclude_inbound_tags=set(exclude))
    return node_facing(core)


def edited(change) -> dict:
    config = copy.deepcopy(BASE)
    change(config)
    return config


def test_unchanged_config_is_live():
    assert only_live_parts_changed(view(BASE), view(copy.deepcopy(BASE)))


def test_rule_change_is_live():
    after = edited(
        lambda c: c["routing"]["rules"].append({"type": "field", "domain": ["x.com"], "outboundTag": "BLOCK"})
    )
    assert only_live_parts_changed(view(BASE), view(after))


def test_balancer_change_is_live():
    after = edited(lambda c: c["routing"].update(balancers=[{"tag": "b", "selector": ["DIRECT"]}]))
    assert only_live_parts_changed(view(BASE), view(after))


def test_outbound_changes_are_live():
    added = edited(lambda c: c["outbounds"].append({"tag": "WARP", "protocol": "wireguard"}))
    changed = edited(lambda c: c["outbounds"][1].update(settings={"response": {"type": "http"}}))
    removed = edited(lambda c: c["outbounds"].pop())
    for after in (added, changed, removed):
        assert only_live_parts_changed(view(BASE), view(after))


def test_first_routing_rules_are_live():
    before = edited(lambda c: c.pop("routing"))
    after = edited(lambda c: c["routing"].pop("domainStrategy"))
    assert only_live_parts_changed(view(before), view(after))


def test_other_changes_need_a_restart():
    changes = [
        lambda c: c["routing"].update(domainStrategy="IPIfNonMatch"),
        lambda c: c["inbounds"][0].update(port=8443),
        lambda c: c.update(dns={"servers": ["1.1.1.1"]}),
        lambda c: c["log"].update(loglevel="debug"),
    ]
    for change in changes:
        assert not only_live_parts_changed(view(BASE), view(edited(change)))


def test_exclude_change_needs_a_restart():
    assert not only_live_parts_changed(view(BASE, exclude={"in"}), view(BASE))


def test_exclude_order_does_not_matter():
    assert only_live_parts_changed(view(BASE, exclude=["a", "b"]), view(BASE, exclude=["b", "a"]))


def test_non_xray_core_is_never_live():
    assert not only_live_parts_changed(view(BASE, core_type=CoreType.wg), view(BASE, core_type=CoreType.wg))


def test_missing_core_is_never_live():
    assert node_facing(None) is None
    assert not only_live_parts_changed(None, view(BASE))
