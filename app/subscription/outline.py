import json
from .funcs import detect_shadowsocks_2022


class OutlineConfiguration:
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

    def make_outbound(self, remark: str, address: str, port: int, password: str, method: str):
        config = {
            "method": method,
            "password": password,
            "server": address,
            "server_port": port,
            "tag": remark,
        }
        return config

    def add(self, remark: str, address: str, inbound: dict, settings: dict):
        if inbound["protocol"] != "shadowsocks":
            return

        method, password = detect_shadowsocks_2022(
            inbound.get("is_2022", False),
            inbound.get("method", ""),
            settings["method"],
            inbound.get("password"),
            settings["password"],
        )

        outbound = self.make_outbound(
            remark=remark,
            address=address,
            port=inbound["port"],
            password=password,
            method=method,
        )
        self.add_directly(outbound)
