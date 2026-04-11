"""split singbox templates into legacy and new formats

Revision ID: b5b1c2d3e4f7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-11 21:30:00.000000

"""

import json

from alembic import op
import sqlalchemy as sa


revision = "b5b1c2d3e4f7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


DEFAULT_SINGBOX_LEGACY_SUBSCRIPTION_TEMPLATE = """{
  "log": {
    "level": "warn",
    "timestamp": false
  },
  "dns": {
    "servers": [
      {
        "tag": "dns-remote",
        "address": "1.1.1.2",
        "detour": "proxy"
      },
      {
        "tag": "dns-local",
        "address": "local",
        "detour": "direct"
      }
    ],
    "rules": [
      {
        "outbound": "any",
        "server": "dns-local"
      }
    ],
    "final": "dns-remote"
  },
  "inbounds": [
    {
      "type": "tun",
      "tag": "tun-in",
      "interface_name": "sing-tun",
      "address": [
        "172.19.0.1/30",
        "fdfe:dcba:9876::1/126"
      ],
      "auto_route": true,
      "route_exclude_address": [
        "192.168.0.0/16",
        "10.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "fe80::/10",
        "fc00::/7"
      ]
    }
  ],
  "outbounds": [
    {
      "type": "selector",
      "tag": "proxy",
      "outbounds": null,
      "interrupt_exist_connections": true
    },
    {
      "type": "urltest",
      "tag": "Best Latency",
      "outbounds": null
    },
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "route": {
    "rules": [
      {
        "inbound": "tun-in",
        "action": "sniff"
      },
      {
        "protocol": "dns",
        "action": "hijack-dns"
      }
    ],
    "final": "proxy",
    "auto_detect_interface": true,
    "override_android_vpn": true
  },
  "experimental": {
    "cache_file": {
      "enabled": true,
      "store_rdrc": true
    }
  }
}"""


DEFAULT_SINGBOX_SUBSCRIPTION_TEMPLATE = """{
  "log": {
    "level": "warn",
    "timestamp": false
  },
  "dns": {
    "servers": [
      {
        "type": "udp",
        "tag": "dns-remote",
        "server": "1.1.1.2",
        "detour": "proxy"
      },
      {
        "type": "local",
        "tag": "dns-local"
      }
    ],
    "final": "dns-remote"
  },
  "inbounds": [
    {
      "type": "tun",
      "tag": "tun-in",
      "interface_name": "sing-tun",
      "address": [
        "172.19.0.1/30",
        "fdfe:dcba:9876::1/126"
      ],
      "auto_route": true,
      "route_exclude_address": [
        "192.168.0.0/16",
        "10.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "fe80::/10",
        "fc00::/7"
      ]
    }
  ],
  "outbounds": [
    {
      "type": "selector",
      "tag": "proxy",
      "outbounds": null,
      "interrupt_exist_connections": true
    },
    {
      "type": "urltest",
      "tag": "Best Latency",
      "outbounds": null
    },
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "route": {
    "rules": [
      {
        "inbound": "tun-in",
        "action": "sniff"
      },
      {
        "protocol": "dns",
        "action": "hijack-dns"
      }
    ],
    "final": "proxy",
    "auto_detect_interface": true,
    "override_android_vpn": true,
    "default_domain_resolver": "dns-local"
  },
  "experimental": {
    "cache_file": {
      "enabled": true,
      "store_rdrc": true
    }
  }
}"""


def _parse_json(value):
    if not value:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _migrate_settings_subscription_targets(connection, to_legacy: bool) -> None:
    settings_table = sa.table(
        "settings",
        sa.column("id", sa.Integer),
        sa.column("subscription", sa.JSON),
    )

    settings_rows = connection.execute(sa.select(settings_table.c.id, settings_table.c.subscription)).fetchall()
    updates = []

    for settings_id, subscription_json in settings_rows:
        subscription = _parse_json(subscription_json)
        if not isinstance(subscription, dict):
            continue

        changed = False

        rules = subscription.get("rules")
        if isinstance(rules, list):
            updated_rules = []
            for rule in rules:
                if not isinstance(rule, dict):
                    updated_rules.append(rule)
                    continue

                updated_rule = dict(rule)
                if to_legacy and updated_rule.get("target") == "sing_box":
                    updated_rule["target"] = "sing_box_legacy"
                    changed = True
                elif not to_legacy and updated_rule.get("target") == "sing_box_legacy":
                    updated_rule["target"] = "sing_box"
                    changed = True
                updated_rules.append(updated_rule)

            if changed:
                subscription["rules"] = updated_rules

        manual_sub_request = subscription.get("manual_sub_request")
        if isinstance(manual_sub_request, dict):
            updated_manual_sub_request = dict(manual_sub_request)
            if to_legacy:
                legacy_enabled = updated_manual_sub_request.get("sing_box", True)
                if updated_manual_sub_request.get("sing_box_legacy") != legacy_enabled:
                    changed = True
                updated_manual_sub_request["sing_box_legacy"] = updated_manual_sub_request.get(
                    "sing_box_legacy", legacy_enabled
                )
            else:
                legacy_enabled = updated_manual_sub_request.get(
                    "sing_box_legacy", updated_manual_sub_request.get("sing_box", True)
                )
                if updated_manual_sub_request.get("sing_box") != legacy_enabled:
                    changed = True
                updated_manual_sub_request["sing_box"] = legacy_enabled
                if "sing_box_legacy" in updated_manual_sub_request:
                    updated_manual_sub_request.pop("sing_box_legacy")
                    changed = True

            subscription["manual_sub_request"] = updated_manual_sub_request

        if changed:
            updates.append({"_id": settings_id, "subscription": json.dumps(subscription, ensure_ascii=False)})

    if updates:
        connection.execute(
            settings_table.update().where(settings_table.c.id == sa.bindparam("_id")),
            updates,
        )


def upgrade() -> None:
    connection = op.get_bind()
    client_templates_table = sa.table(
        "client_templates",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("template_type", sa.String),
        sa.column("content", sa.Text),
        sa.column("is_default", sa.Boolean),
        sa.column("is_system", sa.Boolean),
    )

    legacy_template_content = DEFAULT_SINGBOX_LEGACY_SUBSCRIPTION_TEMPLATE
    new_template_content = DEFAULT_SINGBOX_SUBSCRIPTION_TEMPLATE

    connection.execute(
        client_templates_table.update()
        .where(client_templates_table.c.template_type == "singbox_subscription")
        .values(template_type="singbox_legacy_subscription")
    )

    existing_legacy_template = connection.execute(
        sa.select(sa.func.count())
        .select_from(client_templates_table)
        .where(client_templates_table.c.template_type == "singbox_legacy_subscription")
    ).scalar()
    if not existing_legacy_template:
        connection.execute(
            client_templates_table.insert().values(
                name="Default Singbox Legacy Subscription",
                template_type="singbox_legacy_subscription",
                content=legacy_template_content,
                is_default=True,
                is_system=True,
            )
        )

    existing_new_template = connection.execute(
        sa.select(sa.func.count())
        .select_from(client_templates_table)
        .where(client_templates_table.c.template_type == "singbox_subscription")
    ).scalar()

    if not existing_new_template:
        connection.execute(
            client_templates_table.insert().values(
                name="Default Singbox Subscription",
                template_type="singbox_subscription",
                content=new_template_content,
                is_default=True,
                is_system=True,
            )
        )

    _migrate_settings_subscription_targets(connection, to_legacy=True)


def downgrade() -> None:
    connection = op.get_bind()
    client_templates_table = sa.table(
        "client_templates",
        sa.column("id", sa.Integer),
        sa.column("template_type", sa.String),
    )

    connection.execute(
        client_templates_table.delete().where(client_templates_table.c.template_type == "singbox_subscription")
    )
    connection.execute(
        client_templates_table.update()
        .where(client_templates_table.c.template_type == "singbox_legacy_subscription")
        .values(template_type="singbox_subscription")
    )

    _migrate_settings_subscription_targets(connection, to_legacy=False)
