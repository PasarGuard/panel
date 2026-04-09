import io
import zipfile

from app.models.subscription import SubscriptionInboundData

from .base import BaseSubscription


class WireGuardConfiguration(BaseSubscription):
    def __init__(self):
        self.proxy_remarks = []
        self.configs: list[tuple[str, str]] = []

    def _render_config(self, config_dict: dict[str, dict[str, str]]) -> str:
        """Render a structured dictionary to WireGuard .conf format."""
        output = []
        for section, params in config_dict.items():
            output.append(f"[{section}]")
            for key, value in params.items():
                if value is not None:
                    output.append(f"{key} = {value}")
            output.append("")
        return "\n".join(output).strip()

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        components = self._build_wireguard_components(remark, address, inbound, settings)
        if not components:
            return

        payload = components["payload"]

        # Structured configuration data
        config_data = {
            "Interface": {
                "PrivateKey": components["private_key"],
                "Address": ", ".join(components["peer_ips"]),
            },
            "Peer": {
                "PublicKey": payload["publickey"],
                "AllowedIPs": payload["allowedips"].replace(",", ", "),
                "Endpoint": f"{address}:{inbound.port}",
            },
        }

        # Optional Interface settings
        if mtu := payload.get("mtu"):
            config_data["Interface"]["MTU"] = str(mtu)
        if reserved := payload.get("reserved"):
            config_data["Interface"]["Reserved"] = str(reserved)
        if dns_servers := payload.get("dns"):
            config_data["Interface"]["DNS"] = ", ".join(dns_servers)

        # Optional Peer settings
        if preshared_key := payload.get("presharedkey"):
            config_data["Peer"]["PresharedKey"] = preshared_key
        if keepalive := payload.get("keepalive"):
            config_data["Peer"]["PersistentKeepalive"] = str(keepalive)

        config_content = self._render_config(config_data)
        self.configs.append((components["remark"], config_content))

    def render(self) -> bytes:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for remark, config_content in self.configs:
                hostname = remark.replace(" ", "_").replace("/", "_")
                filename = f"{hostname}.conf"
                zip_file.writestr(filename, config_content)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()
