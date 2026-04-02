from urllib.parse import quote

from app.models.subscription import SubscriptionInboundData

from .base import BaseSubscription


class WireGuardConfiguration(BaseSubscription):
    def __init__(self):
        self.configs: list[str] = []

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        peer_ips = settings.get("peer_ips", [])
        private_key = settings.get("private_key", "")
        if not private_key or not peer_ips:
            return

        lines = [
            f"# {remark}",
            "[Interface]",
            f"PrivateKey = {private_key}",
            f"Address = {', '.join(peer_ips)}",
            "",
            "[Peer]",
            f"PublicKey = {inbound.wireguard_public_key}",
        ]

        if inbound.wireguard_pre_shared_key:
            lines.append(f"PresharedKey = {inbound.wireguard_pre_shared_key}")

        lines.extend(
            [
                f"AllowedIPs = {', '.join(inbound.wireguard_allowed_ips or ['0.0.0.0/0', '::/0'])}",
                f"Endpoint = {address}:{inbound.port}",
            ]
        )

        if inbound.wireguard_keepalive:
            lines.append(f"PersistentKeepalive = {inbound.wireguard_keepalive}")

        lines.append("")
        lines.append(f"# URI: wireguard://{quote(private_key, safe='')}@{address}:{inbound.port}")
        self.configs.append("\n".join(lines))

    def render(self, reverse: bool = False):
        configs = list(self.configs)
        if reverse:
            configs.reverse()
        return "\n\n".join(configs)
