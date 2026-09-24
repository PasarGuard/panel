"""add wireguard_subnets pool table

Creates the per-subnet WireGuard allocation pool (free-list + high-water offset)
keyed by exact canonical network CIDR (IPv4 and IPv6), and backfills it from WG
core configs and users' existing peer_ips, preserving every IP that fits its
core's subnet. Users whose IPs don't fit get a fresh one.

Revision ID: 3c1a7e5b9d20
Revises: f976bfcf4738
Create Date: 2026-07-19 00:00:00.000000

"""

import json
from ipaddress import ip_interface, ip_network

import sqlalchemy as sa
from alembic import op

from app.db.compiles_types import SqliteCompatibleBigInteger

revision = "3c1a7e5b9d20"
down_revision = "f976bfcf4738"
branch_labels = None
depends_on = None


def _load_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def _core_subnets(config):
    seen = {}
    for cidr in config.get("address") or []:
        try:
            net = ip_interface(str(cidr).strip()).network
        except ValueError:
            continue
        seen.setdefault(str(net), net)
    return list(seen.values())


def _peer_host(entry):
    try:
        net = ip_network(str(entry).strip(), strict=False)
    except ValueError:
        return None
    return net.version, int(net.network_address)


def _build_namespaces(core_rows):
    """canonical network str -> {subnet, reserved offsets, tags}"""
    by_key = {}
    for config in core_rows:
        for subnet in _core_subnets(config):
            by_key.setdefault(str(subnet), []).append(config)

    namespaces = {}
    for key, configs in by_key.items():
        subnet = ip_network(key)
        base = int(subnet.network_address)
        reserved = {0, subnet.num_addresses - 1}
        tags = set()
        for config in configs:
            tag = str(config.get("interface_name") or "").strip()
            if tag:
                tags.add(tag)
            for cidr in config.get("address") or []:
                try:
                    iface = ip_interface(str(cidr).strip())
                except ValueError:
                    continue
                if iface.version == subnet.version and iface.ip in subnet:
                    reserved.add(int(iface.ip) - base)
        namespaces[key] = {"subnet": subnet, "reserved": reserved, "tags": tags}
    return _collapse_overlapping(namespaces)


def _collapse_overlapping(namespaces):
    """Keep the largest subnet when CIDRs overlap; merge tags/reserved from smaller ones into it."""
    if len(namespaces) < 2:
        return namespaces

    ordered = sorted(namespaces.items(), key=lambda item: (item[1]["subnet"].prefixlen, item[0]))
    kept = {}
    for key, ns in ordered:
        keeper_key = None
        for kkey, kns in kept.items():
            if kns["subnet"].version != ns["subnet"].version:
                continue
            if kns["subnet"].overlaps(ns["subnet"]):
                keeper_key = kkey
                break
        if keeper_key is None:
            kept[key] = {
                "subnet": ns["subnet"],
                "reserved": set(ns["reserved"]),
                "tags": set(ns["tags"]),
            }
            continue

        print(
            f"WARNING: WireGuard subnet {key} overlaps {keeper_key}; "
            f"skipping pool row for smaller/overlapping {key}, merging tags into {keeper_key}"
        )
        keeper = kept[keeper_key]
        base = int(keeper["subnet"].network_address)
        for offset in ns["reserved"]:
            host_int = int(ns["subnet"].network_address) + offset
            host = type(keeper["subnet"].network_address)(host_int)
            if host in keeper["subnet"]:
                keeper["reserved"].add(host_int - base)
        keeper["tags"] |= ns["tags"]
    return kept


def _render_peer_ip(subnet, offset):
    host = type(subnet.network_address)(int(subnet.network_address) + offset)
    return f"{host}/{'32' if subnet.version == 4 else '128'}"


def upgrade() -> None:
    op.create_table(
        "wireguard_subnets",
        sa.Column("id", SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.Column("network", sa.String(length=64), nullable=False),
        sa.Column("next_offset", SqliteCompatibleBigInteger(), nullable=False, server_default="1"),
        sa.Column("free_offsets", sa.JSON(none_as_null=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wireguard_subnets")),
        sa.UniqueConstraint("network", name=op.f("uq_wireguard_subnets_network")),
    )

    bind = op.get_bind()

    core_configs = sa.table(
        "core_configs", sa.column("id", sa.Integer), sa.column("type", sa.String), sa.column("config", sa.JSON)
    )
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("proxy_settings", sa.JSON))
    users_groups = sa.table(
        "users_groups_association", sa.column("user_id", sa.Integer), sa.column("groups_id", sa.Integer)
    )
    groups = sa.table("groups", sa.column("id", sa.Integer), sa.column("is_disabled", sa.Boolean))
    inbounds_groups = sa.table(
        "inbounds_groups_association", sa.column("inbound_id", sa.Integer), sa.column("group_id", sa.Integer)
    )
    inbounds = sa.table("inbounds", sa.column("id", sa.Integer), sa.column("tag", sa.String))
    pool = sa.table(
        "wireguard_subnets",
        sa.column("network", sa.String),
        sa.column("next_offset", sa.BigInteger),
        sa.column("free_offsets", sa.JSON),
    )

    core_rows = [
        _load_json(config)
        for (config,) in bind.execute(
            sa.select(core_configs.c.config).where(sa.cast(core_configs.c.type, sa.String) == "wg")
        ).fetchall()
    ]
    namespaces = _build_namespaces(core_rows)
    if not namespaces:
        return

    # user_id -> accessible inbound tags (through enabled groups)
    tag_rows = bind.execute(
        sa.select(users_groups.c.user_id, inbounds.c.tag)
        .select_from(
            users_groups.join(
                groups, sa.and_(groups.c.id == users_groups.c.groups_id, groups.c.is_disabled.is_(False))
            )
            .join(inbounds_groups, inbounds_groups.c.group_id == groups.c.id)
            .join(inbounds, inbounds.c.id == inbounds_groups.c.inbound_id)
        )
    ).fetchall()
    tags_by_user = {}
    for user_id, tag in tag_rows:
        tags_by_user.setdefault(user_id, set()).add(tag)

    def match_namespace(version, host_int):
        for key, ns in namespaces.items():
            subnet = ns["subnet"]
            if subnet.version != version:
                continue
            if int(subnet.network_address) <= host_int <= int(subnet.broadcast_address):
                return key
        return None

    used = {key: set() for key in namespaces}
    updates = []
    user_rows = bind.execute(sa.select(users.c.id, users.c.proxy_settings)).fetchall()
    parsed_users = []
    for user_id, proxy_settings in user_rows:
        proxy_settings = _load_json(proxy_settings)
        old_ips = list((proxy_settings.get("wireguard") or {}).get("peer_ips") or [])
        tags = tags_by_user.get(user_id, set())
        targets = {key for key, ns in namespaces.items() if ns["tags"] & tags}
        kept = {}
        for entry in old_ips:
            host = _peer_host(entry)
            key = match_namespace(*host) if host is not None else None
            if key is None:
                continue
            ns = namespaces[key]
            offset = host[1] - int(ns["subnet"].network_address)
            if (
                key in targets
                and key not in kept
                and 0 < offset < ns["subnet"].num_addresses - 1
                and offset not in ns["reserved"]
                and offset not in used[key]
            ):
                kept[key] = offset
                used[key].add(offset)
        parsed_users.append((user_id, proxy_settings, old_ips, targets, kept))

    # in-memory allocation for eligible users missing an IP (scan order = user id order)
    cursors = {key: 1 for key in namespaces}
    for user_id, proxy_settings, old_ips, targets, kept in parsed_users:
        for key in sorted(targets - set(kept)):
            ns = namespaces[key]
            cursor = cursors[key]
            while cursor in ns["reserved"] or cursor in used[key]:
                cursor += 1
            cursors[key] = cursor + 1
            if cursor >= ns["subnet"].num_addresses - 1:
                continue  # subnet exhausted; user is left without an IP for it
            used[key].add(cursor)
            kept[key] = cursor

        new_ips = [_render_peer_ip(namespaces[key]["subnet"], offset) for key, offset in sorted(kept.items())]
        if new_ips != old_ips:
            wg = dict(proxy_settings.get("wireguard") or {})
            wg["peer_ips"] = new_ips
            proxy_settings = dict(proxy_settings)
            proxy_settings["wireguard"] = wg
            updates.append({"_id": user_id, "proxy_settings": proxy_settings})

    if updates:
        bind.execute(users.update().where(users.c.id == sa.bindparam("_id")), updates)

    pool_rows = []
    for key, ns in namespaces.items():
        offsets = used[key]
        next_offset = max(offsets) + 1 if offsets else 1
        free = [
            offset
            for offset in range(1, next_offset)
            if offset not in offsets and offset not in ns["reserved"] and offset < ns["subnet"].num_addresses - 1
        ]
        pool_rows.append({"network": key, "next_offset": next_offset, "free_offsets": free})
    bind.execute(pool.insert(), pool_rows)


def downgrade() -> None:
    # peer_ips live in users.proxy_settings either way; only the pool state is dropped
    op.drop_table("wireguard_subnets")
