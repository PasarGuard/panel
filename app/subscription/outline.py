import json
from app.models.subscription import SubscriptionInboundData
from .base import BaseSubscription


class OutlineConfiguration(BaseSubscription):
    def __init__(self):
        self.config = {}

    def add_directly(self, data: dict):
        self.config.update(data)

    def render(self, reverse=False):
        if reverse:
            items = list(self.config.items())
            items.reverse()
            self.config = dict(items)
        return json.dumps(self.config, indent=0)

    def _build_shadowsocks(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build Shadowsocks outbound with 2022 support"""
        method, password = self.detect_shadowsocks_2022(
            inbound.is_2022,
            inbound.method,
            settings["method"],
            inbound.password,
            settings["password"],
        )

        return {
            "method": method,
            "password": password,
            "server": address,
            "server_port": inbound.port,
            "tag": remark,
        }

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        """Add outbound - Outline only supports Shadowsocks"""
        if inbound.protocol != "shadowsocks":
            return

        outbound = self._build_shadowsocks(remark, address, inbound, settings)
        self.add_directly(outbound)
