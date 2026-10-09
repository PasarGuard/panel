import base64
import binascii
import ipaddress
from datetime import UTC, datetime

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

WARP_API = "https://api.cloudflareclient.com/v0a4005/reg"
WARP_TIMEOUT = 20


class WarpRegistrationError(ValueError):
    pass


def _key(value: str) -> str:
    try:
        if len(base64.b64decode(value, validate=True)) == 32:
            return value
    except ValueError, TypeError, binascii.Error:
        pass
    raise WarpRegistrationError("Cloudflare returned an invalid WireGuard key. Try again.")


def warp_settings(response: dict, private_key: str) -> dict:
    """Keep only tunnel credentials, never the registration token or account payload."""
    try:
        config = response["config"]
        addresses = config["interface"]["addresses"]
        address = [
            f"{ipaddress.IPv4Address(addresses['v4'])}/32",
            f"{ipaddress.IPv6Address(addresses['v6'])}/128",
        ]
        reserved = list(base64.b64decode(config["client_id"], validate=True))
        if len(reserved) != 3:
            raise ValueError
        peer = config["peers"][0]
        public_key = _key(peer["public_key"])
        endpoint = peer["endpoint"]["host"]
        if not isinstance(endpoint, str) or not endpoint or len(endpoint) > 256:
            raise ValueError
        host, port = endpoint.rsplit(":", 1)
        if not host or not 1 <= int(port) <= 65535 or any(c.isspace() for c in host):
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error) as exc:
        raise WarpRegistrationError("Cloudflare returned incomplete WARP settings. Try again.") from exc
    return {
        "secretKey": _key(private_key),
        "address": address,
        "reserved": reserved,
        "peers": [{"publicKey": public_key, "endpoint": endpoint, "allowedIPs": ["0.0.0.0/0", "::/0"]}],
        "mtu": 1420,
        "noKernelTun": True,
        # Older Xray versions use these fields; unknown JSON fields are ignored by Xray.
        "kernelMode": False,
        "domainStrategy": "ForceIPv4",
    }


async def register_warp() -> dict:
    private = X25519PrivateKey.generate()
    private_key = base64.b64encode(private.private_bytes_raw()).decode()
    public_key = base64.b64encode(
        private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    payload = {
        "key": public_key,
        "tos": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "type": "PC",
        "model": "PasarGuard",
    }
    try:
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=WARP_TIMEOUT)) as session,
            session.post(
                WARP_API,
                json=payload,
                headers={"CF-Client-Version": "a-6.30-3596"},
                allow_redirects=False,
            ) as response,
        ):
            if response.status == 429:
                raise WarpRegistrationError("Cloudflare temporarily limited WARP registrations. Try again later.")
            if not 200 <= response.status < 300:
                raise WarpRegistrationError(f"Cloudflare rejected WARP registration (HTTP {response.status}).")
            # Do not log or return this response: it contains account credentials.
            data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise WarpRegistrationError("Cannot reach Cloudflare WARP. Check connectivity and try again.") from exc
    except (ValueError, TypeError) as exc:
        if isinstance(exc, WarpRegistrationError):
            raise
        raise WarpRegistrationError("Cloudflare returned an invalid WARP response. Try again.") from exc
    return warp_settings(data, private_key)
