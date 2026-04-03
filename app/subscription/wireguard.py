from app.models.subscription import SubscriptionInboundData

from .base import BaseSubscription


class WireGuardConfiguration(BaseSubscription):
    def __init__(self):
        self.proxy_remarks = []
        self.configs: list[str] = []

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        components = self._build_wireguard_components(remark, address, inbound, settings)
        if not components:
            return

        payload = components["payload"]
        lines = [
            f"# Name = {components['remark']}",
            "[Interface]",
            f"PrivateKey = {components['private_key']}",
            f"Address = {', '.join(components['peer_ips'])}",
        ]
        if mtu := payload.get("mtu"):
            lines.append(f"MTU = {mtu}")
        if reserved := payload.get("reserved"):
            lines.append(f"Reserved = {reserved}")
        lines.extend(
            [
                "",
                "[Peer]",
                f"PublicKey = {payload['publickey']}",
            ]
        )

        if preshared_key := payload.get("presharedkey"):
            lines.append(f"PresharedKey = {preshared_key}")

        lines.extend(
            [
                f"AllowedIPs = {payload['allowedips'].replace(',', ', ')}",
                f"Endpoint = {address}:{inbound.port}",
            ]
        )

        if keepalive := payload.get("keepalive"):
            lines.append(f"PersistentKeepalive = {keepalive}")

        lines.append("")
        lines.append(f"# URI: {components['uri']}")
        self.configs.append("\n".join(lines))

    def render(self, reverse: bool = False):
        configs = list(self.configs)
        if reverse:
            configs.reverse()
        return "\n\n".join(configs)
