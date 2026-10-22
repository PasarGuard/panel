#!/usr/bin/env python3
"""Generate opt-in, panel-managed VLESS/VMess/Trojan inbounds; no shared credentials."""

import argparse
import ipaddress
import json
from pathlib import PurePosixPath

PROTOCOLS = ("vless", "vmess", "trojan")


def build_config(
    *, protocols=PROTOCOLS, base_port=10001, listen="127.0.0.1", behind_tls_proxy=False, cert=None, key=None
):
    protocols = tuple(protocols)
    if not protocols or len(set(protocols)) != len(protocols) or any(p not in PROTOCOLS for p in protocols):
        raise ValueError("Select distinct protocols from vless, vmess, trojan")
    if not 1 <= base_port <= 65535 - len(protocols) + 1:
        raise ValueError("The complete inbound port range must be within 1..65535")
    address = ipaddress.ip_address(listen)
    if behind_tls_proxy:
        if not address.is_loopback:
            raise ValueError("TLS-proxy mode requires a loopback listener; do not expose plaintext credentials")
        if cert or key:
            raise ValueError("Choose TLS-proxy mode OR certificate/key, not both")
    elif not cert or not key:
        raise ValueError("Provide both certificate/key or explicitly select --behind-tls-proxy")
    elif not all(PurePosixPath(p).is_absolute() for p in (cert, key)):
        raise ValueError("Certificate/key paths must be absolute paths on the panel/core host")

    inbounds = []
    for index, protocol in enumerate(protocols):
        stream = {
            "network": "ws",
            "security": "none" if behind_tls_proxy else "tls",
            "wsSettings": {"path": f"/pasarguard/{protocol}"},
        }
        if not behind_tls_proxy:
            stream["tlsSettings"] = {"minVersion": "1.2", "certificates": [{"certificateFile": cert, "keyFile": key}]}
        settings = {"clients": []}
        if protocol == "vless":
            settings["decryption"] = "none"
        inbounds.append(
            {
                "tag": f"{protocol.upper()} WS",
                "listen": str(address),
                "port": base_port + index,
                "protocol": protocol,
                "settings": settings,
                "streamSettings": stream,
            }
        )
    return {
        "log": {"loglevel": "warning"},
        "policy": {"levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True, "statsUserOnline": True}}},
        "inbounds": inbounds,
        "outbounds": [{"tag": "DIRECT", "protocol": "freedom"}, {"tag": "BLOCK", "protocol": "blackhole"}],
        # Literal ranges avoid an undeclared dependency on a geoip.dat asset.
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "outboundTag": "BLOCK",
                    "ip": [
                        "0.0.0.0/8",
                        "10.0.0.0/8",
                        "100.64.0.0/10",
                        "127.0.0.0/8",
                        "169.254.0.0/16",
                        "172.16.0.0/12",
                        "192.168.0.0/16",
                        "224.0.0.0/4",
                        "240.0.0.0/4",
                        "::/128",
                        "::1/128",
                        "fc00::/7",
                        "fe80::/10",
                        "ff00::/8",
                    ],
                }
            ]
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", choices=PROTOCOLS, action="append", dest="protocols")
    parser.add_argument("--base-port", type=int, default=10001)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--behind-tls-proxy", action="store_true")
    parser.add_argument("--cert")
    parser.add_argument("--key")
    args = vars(parser.parse_args())
    if args["protocols"] is None:
        args["protocols"] = PROTOCOLS
    try:
        config = build_config(**args)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
