import io
import re
import unicodedata
import zipfile

from app.models.subscription import SubscriptionInboundData

from .base import BaseSubscription

# Windows device names, reserved with any extension ("NUL.conf", "con.x.conf").
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)
# The WireGuard Android app rejects tunnel names longer than 15 characters.
_ANDROID_NAME_LIMIT = 15
_NAME_LIMIT = 64


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
            if isinstance(dns_servers, str):
                config_data["Interface"]["DNS"] = dns_servers.replace(",", ", ")
            else:
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
        used_names: set[str] = set()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for remark, config_content in self.configs:
                zip_file.writestr(self._archive_name(remark, used_names), config_content)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    @staticmethod
    def _archive_name(remark: str, used_names: set[str]) -> str:
        """Turn a host remark into a unique, flat ``.conf`` file name for the archive.

        Clients take the tunnel name from the file name, so spaces become ``_`` as before. Path
        separators, ``..`` and characters invalid in file names are replaced so every entry stays a
        plain file in the extraction folder, Windows device names get a ``_`` prefix, and names that
        collide get ``-2``, ``-3`` suffixes within the length limit.
        """
        name = unicodedata.normalize("NFC", remark or "")
        name = re.sub(r'[\\/:*?"<>| \x00-\x1f\x7f]', "_", name)
        name = name.replace("..", "_").strip(".")[:_NAME_LIMIT] or "config"
        if name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            name = f"_{name}"[:_NAME_LIMIT]
        # A suffix must not push a name that fits Android's limit past it, or any name past ours.
        limit = _ANDROID_NAME_LIMIT if len(name) <= _ANDROID_NAME_LIMIT else _NAME_LIMIT
        candidate, suffix = name, 1
        # Windows and macOS extract "A.conf" and "a.conf" (and NFC/NFD forms of one name) to one file.
        while (key := unicodedata.normalize("NFC", candidate.casefold())) in used_names:
            suffix += 1
            tail = f"-{suffix}"
            candidate = f"{name[: limit - len(tail)]}{tail}"
        used_names.add(key)
        return f"{candidate}.conf"
