import random
from ipaddress import ip_network
from types import SimpleNamespace

import pytest

import app.db.crud.wireguard as wireguard_crud
from app.db.crud.wireguard import (
    _ensure_wireguard_keys,
    _give_back,
    _peer_sort_key,
    _take_offset,
    _usable_capacity,
    match_namespace,
    offset_valid,
    peer_host,
    pick_peer_ip_for_inbound,
    render_peer_ip,
    wg_core_subnets,
    wg_namespaces,
)
from app.models.core import CoreType
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key


def core(interface_name, addresses):
    return SimpleNamespace(type=CoreType.wg, config={"interface_name": interface_name, "address": addresses})


def pool_row(next_offset=1, free_offsets=None):
    return SimpleNamespace(next_offset=next_offset, free_offsets=free_offsets or [])


def test_shared_wireguard_key_is_rotated_only_for_the_reconciled_user():
    private_key, public_key = generate_wireguard_keypair()
    user = SimpleNamespace(
        proxy_settings={"wireguard": {"private_key": private_key, "public_key": public_key}}
    )
    occupied = {public_key}

    assert _ensure_wireguard_keys(user, shared_keys={public_key}, occupied_keys=occupied)
    assert user.proxy_settings["wireguard"]["public_key"] != public_key
    assert (
        get_wireguard_public_key(user.proxy_settings["wireguard"]["private_key"])
        == user.proxy_settings["wireguard"]["public_key"]
    )
    assert len(occupied) == 2


def test_unique_private_key_derives_public_key_without_rotation():
    private_key, public_key = generate_wireguard_keypair()
    user = SimpleNamespace(proxy_settings={"wireguard": {"private_key": private_key}})

    assert _ensure_wireguard_keys(user)
    assert user.proxy_settings["wireguard"]["public_key"] == public_key


def test_wg_core_subnets_v4_and_v6():
    assert wg_core_subnets({"address": ["fd00::1/64", "10.0.0.1/24"]}) == [
        ip_network("fd00::/64"),
        ip_network("10.0.0.0/24"),
    ]
    assert wg_core_subnets({"address": ["10.5.1.7/20"]}) == [ip_network("10.5.0.0/20")]
    assert wg_core_subnets({"address": ["fd00::1/64"]}) == [ip_network("fd00::/64")]
    assert wg_core_subnets({"address": []}) == []
    assert wg_core_subnets({}) == []
    assert wg_core_subnets({"address": ["garbage"]}) == []


def test_render_and_parse_peer_ip():
    v4 = ip_network("10.0.0.0/24")
    assert render_peer_ip(v4, 5) == "10.0.0.5/32"
    assert peer_host("10.0.0.5/32") == (4, int(v4.network_address) + 5)
    assert peer_host("10.0.0.5") == (4, int(v4.network_address) + 5)

    v6 = ip_network("fd00::/64")
    assert render_peer_ip(v6, 5) == "fd00::5/128"
    assert peer_host("fd00::5/128") == (6, int(v6.network_address) + 5)
    assert peer_host("garbage") is None


def test_single_core_namespace_reserves_network_broadcast_and_server():
    namespaces = wg_namespaces([core("WG_1", ["10.0.0.1/24"])])
    assert set(namespaces) == {"10.0.0.0/24"}
    ns = namespaces["10.0.0.0/24"]
    assert ns.subnet == ip_network("10.0.0.0/24")
    assert ns.tags == {"WG_1"}
    assert ns.reserved == {0, 1, 255}
    assert _usable_capacity(ns) == 253


def test_identical_subnet_cores_share_namespace():
    namespaces = wg_namespaces([core("WG_A", ["10.0.0.1/24"]), core("WG_B", ["10.0.0.5/24", "fd00::1/64"])])
    assert set(namespaces) == {"10.0.0.0/24", "fd00::/64"}
    ns = namespaces["10.0.0.0/24"]
    assert ns.tags == {"WG_A", "WG_B"}
    assert {1, 5} <= ns.reserved
    assert namespaces["fd00::/64"].tags == {"WG_B"}


def test_overlapping_subnets_keep_largest_and_merge_tags():
    """Smaller overlapping CIDRs are dropped; tags/reserved merge into the largest."""
    namespaces = wg_namespaces([core("WG_A", ["10.0.0.1/20"]), core("WG_B", ["10.0.0.5/24"])])
    assert set(namespaces) == {"10.0.0.0/20"}
    ns = namespaces["10.0.0.0/20"]
    assert ns.tags == {"WG_A", "WG_B"}
    assert {1, 5} <= ns.reserved


def test_disjoint_cores_get_separate_namespaces():
    namespaces = wg_namespaces([core("WG_A", ["10.1.0.1/24"]), core("WG_B", ["10.2.0.1/24"])])
    assert len(namespaces) == 2
    assert match_namespace(namespaces, *peer_host("10.1.0.7")).tags == {"WG_A"}
    assert match_namespace(namespaces, *peer_host("10.2.0.7")).tags == {"WG_B"}
    assert match_namespace(namespaces, *peer_host("10.3.0.7")) is None


def test_ipv6_only_core_gets_namespace():
    namespaces = wg_namespaces([core("WG_V6", ["fd00::1/64"])])
    assert set(namespaces) == {"fd00::/64"}
    ns = namespaces["fd00::/64"]
    assert ns.reserved == {0, 1, ns.subnet.num_addresses - 1}


def test_take_offset_skips_server_and_advances_high_water():
    ns = wg_namespaces([core("WG_1", ["10.0.0.1/24"])])["10.0.0.0/24"]
    row = pool_row()
    assert _take_offset(ns, row) == 2  # .0 network, .1 server -> first user gets .2
    assert _take_offset(ns, row) == 3
    assert row.next_offset == 4


def test_take_offset_prefers_free_list():
    ns = wg_namespaces([core("WG_1", ["10.0.0.1/24"])])["10.0.0.0/24"]
    row = pool_row(next_offset=50, free_offsets=[9, 4, 1])  # 1 is the server: invalid, skipped
    assert _take_offset(ns, row) == 4
    assert row.free_offsets == [9, 1]
    assert row.next_offset == 50


def test_take_offset_exhaustion():
    ns = wg_namespaces([core("WG_T", ["10.9.9.1/30"])])["10.9.9.0/30"]
    row = pool_row()
    assert _take_offset(ns, row) == 2  # .1 server, .2 the only usable host
    with pytest.raises(ValueError):
        _take_offset(ns, row)


def test_take_offset_ipv6():
    ns = wg_namespaces([core("WG_V6", ["fd00::1/64"])])["fd00::/64"]
    row = pool_row()
    assert _take_offset(ns, row) == 2
    assert render_peer_ip(ns.subnet, 2) == "fd00::2/128"


def test_grow_subnet_unblocks_exhausted_pool():
    row = pool_row(next_offset=255)  # /24 fully handed out
    ns24 = wg_namespaces([core("WG_1", ["10.0.0.1/24"])])["10.0.0.0/24"]
    with pytest.raises(ValueError):
        _take_offset(ns24, row)
    ns20 = wg_namespaces([core("WG_1", ["10.0.0.1/20"])])["10.0.0.0/20"]
    assert _take_offset(ns20, row) == 255  # /24's broadcast offset is a normal host in /20


def test_give_back_dedupes_and_bounds():
    row = pool_row(next_offset=10, free_offsets=[3])
    _give_back(row, [3, 4, 0, 42])  # dup, valid, never-valid, beyond high-water
    assert row.free_offsets == [3, 4]


def _take_offset_rescan(ns, row):
    """The allocator before the batch heap: rescans the whole free-list on every take."""
    free = list(row.free_offsets or [])
    valid = [offset for offset in free if offset_valid(ns, offset)]
    if valid:
        offset = min(valid)
        free.remove(offset)
        row.free_offsets = free
        return offset
    offset = row.next_offset
    while offset in ns.reserved:
        offset += 1
    if offset >= ns.subnet.num_addresses - 1:
        raise ValueError(f"WireGuard subnet {ns.subnet} has no free addresses")
    row.next_offset = offset + 1
    return offset


def _replay(namespaces, rows, steps, take):
    results = []
    for step in steps:
        if step[0] == "give":
            _give_back(rows[step[1]], step[2])
            continue
        try:
            results.append(take(namespaces[step[1]], rows[step[1]]))
        except ValueError as exc:
            results.append(str(exc))
    return results, {key: (row.next_offset, row.free_offsets) for key, row in rows.items()}


def _assert_batch_heap_matches_rescan(namespaces, make_rows, steps):
    valid_heaps = {}
    expected = _replay(namespaces, make_rows(), steps, _take_offset_rescan)
    actual = _replay(namespaces, make_rows(), steps, lambda ns, row: _take_offset(ns, row, valid_heaps))
    assert actual == expected
    return actual


@pytest.mark.parametrize(
    ("next_offset", "free_offsets"),
    [
        (1, []),
        (1, None),
        (40, [9, 4, 1, 4, 0, -3, 255, 300, 9, 2, 4]),  # server, network, broadcast, out of range, duplicates
        (250, [1, 0, 255]),  # only invalid entries: the high-water mark is used and the list stays as it is
        (253, [7, 7, 3]),  # runs out: the free-list, then the last hosts, then exhaustion
    ],
)
def test_take_offset_batch_heap_matches_rescan(next_offset, free_offsets):
    ns = wg_namespaces([core("WG_1", ["10.0.0.1/24"])])["10.0.0.0/24"]
    results, _rows = _assert_batch_heap_matches_rescan(
        {ns.key: ns},
        lambda: {
            ns.key: SimpleNamespace(
                next_offset=next_offset, free_offsets=None if free_offsets is None else list(free_offsets)
            )
        },
        [("take", ns.key)] * 12,
    )
    assert len(results) == 12


def test_take_offset_batch_heap_matches_rescan_with_give_backs_and_trim(monkeypatch):
    monkeypatch.setattr(wireguard_crud, "FREE_OFFSETS_CAP", 12)  # make _trim_free reorder and drop entries
    namespaces = wg_namespaces([core("WG_A", ["10.0.0.1/24"]), core("WG_B", ["10.1.0.1/26"])])
    keys = sorted(namespaces)
    rng = random.Random(1234)
    for _ in range(200):
        free = {key: [rng.randint(-2, 70) for _ in range(rng.randint(0, 15))] for key in keys}
        high = {key: rng.randint(1, 70) for key in keys}
        steps = []
        for _ in range(rng.randint(1, 40)):
            key = rng.choice(keys)
            if rng.random() < 0.3:
                steps.append(("give", key, [rng.randint(-1, 75) for _ in range(rng.randint(1, 3))]))
            else:
                steps.append(("take", key))
        _assert_batch_heap_matches_rescan(
            namespaces,
            lambda free=free, high=high: {
                key: pool_row(next_offset=high[key], free_offsets=list(free[key])) for key in keys
            },
            steps,
        )


def test_pick_peer_ip_for_inbound():
    peer_ips = ["10.1.0.5/32", "10.2.0.9/32", "fd00::5/128"]
    assert pick_peer_ip_for_inbound(["10.1.0.1/24"], peer_ips) == ["10.1.0.5/32"]
    assert pick_peer_ip_for_inbound(["10.2.0.1/24", "fd00::1/64"], peer_ips) == ["10.2.0.9/32", "fd00::5/128"]
    assert pick_peer_ip_for_inbound(["10.3.0.1/24"], peer_ips) == []
    assert pick_peer_ip_for_inbound(["fd00::1/64"], peer_ips) == ["fd00::5/128"]


def test_peer_sort_key_orders_by_host_not_cidr_string():
    """sync/reconcile must compare peer_ips in host order, not lexical CIDR key order."""
    namespaces = wg_namespaces([core("WG_A", ["10.10.0.1/24"]), core("WG_B", ["10.2.0.1/24"])])
    kept = {"10.10.0.0/24": 2, "10.2.0.0/24": 2}
    by_key = [render_peer_ip(namespaces[key].subnet, offset) for key, offset in sorted(kept.items())]
    by_peer = sorted(
        (render_peer_ip(namespaces[key].subnet, offset) for key, offset in kept.items()),
        key=_peer_sort_key,
    )
    assert by_key == ["10.10.0.2/32", "10.2.0.2/32"]
    assert by_peer == ["10.2.0.2/32", "10.10.0.2/32"]
