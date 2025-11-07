import base64
import hashlib
import json
import re
from enum import Enum

from app.templates import render_template
from config import GRPC_USER_AGENT_TEMPLATE, USER_AGENT_TEMPLATE


class BaseSubscription:
    def __init__(self):
        self.proxy_remarks = []
        user_agent_data = json.loads(render_template(USER_AGENT_TEMPLATE))
        if "list" in user_agent_data and isinstance(user_agent_data["list"], list):
            self.user_agent_list = user_agent_data["list"]
        else:
            self.user_agent_list = []

        grpc_user_agent_data = json.loads(render_template(GRPC_USER_AGENT_TEMPLATE))

        if "list" in grpc_user_agent_data and isinstance(grpc_user_agent_data["list"], list):
            self.grpc_user_agent_data = grpc_user_agent_data["list"]
        else:
            self.grpc_user_agent_data = []

        del user_agent_data, grpc_user_agent_data

    def _remark_validation(self, remark):
        if remark not in self.proxy_remarks:
            return remark
        c = 2
        while True:
            new = f"{remark} ({c})"
            if new not in self.proxy_remarks:
                return new
            c += 1

    def _normalize_and_remove_none_values(self, data: dict) -> dict:
        """
        Clean dictionary by removing None, empty strings, and 0 values.
        Converts Enum values and recursively cleans nested dictionaries.

        Args:
            data: Input dictionary to clean

        Returns:
            Cleaned dictionary with empty values removed
        """

        def clean_dict(d: dict) -> dict:
            new_dict = {}
            for k, v in d.items():
                if v not in (None, "", 0):
                    if isinstance(v, dict):
                        if cleaned_dict := clean_dict(v):
                            new_dict[k] = cleaned_dict
                    else:
                        if isinstance(v, Enum):
                            new_dict[k] = v.value
                        else:
                            new_dict[k] = v
            return new_dict

        return clean_dict(data)

    def snake_to_camel(self, snake_str):
        return re.sub(r"_([a-z])", lambda match: match.group(1).upper(), snake_str)

    @staticmethod
    def get_grpc_gun(path: str) -> str:
        """Extract gRPC gun service name from path"""
        if not path.startswith("/"):
            return path

        servicename = path.rsplit("/", 1)[0]
        streamname = path.rsplit("/", 1)[1].split("|")[0]

        if streamname == "Tun":
            return servicename[1:]

        return f"{servicename}/{streamname}"

    @staticmethod
    def get_grpc_multi(path: str) -> str:
        """Extract gRPC multi service name from path"""
        if not path.startswith("/"):
            return path

        servicename = path.rsplit("/", 1)[0]
        streamname = path.rsplit("/", 1)[1].split("|")[1]

        return f"{servicename}/{streamname}"

    @staticmethod
    def ensure_base64_password(password: str, method: str) -> str:
        """
        Ensure password is base64 encoded with correct length for the method:
        - aes-128-gcm: 16 bytes key (22 chars in base64)
        - aes-256-gcm and chacha20-poly1305: 32 bytes key (44 chars in base64)
        """
        try:
            # Check if it's already a valid base64 string
            decoded_bytes = base64.b64decode(password)
            # Check if length is appropriate
            if ("aes-128-gcm" in method and len(decoded_bytes) == 16) or (
                ("aes-256-gcm" in method or "chacha20-poly1305" in method) and len(decoded_bytes) == 32
            ):
                # Already correct length
                return password
        except Exception:
            # Not a valid base64 string
            pass

        # Hash the password to get a consistent byte array
        hash_bytes = hashlib.sha256(password.encode("utf-8")).digest()

        if "aes-128-gcm" in method:
            key_bytes = hash_bytes[:16]  # First 16 bytes for AES-128
        else:
            key_bytes = hash_bytes[:32]  # First 32 bytes for AES-256 or ChaCha20

        return base64.b64encode(key_bytes).decode("ascii")

    @staticmethod
    def password_to_2022(
        inbound_password: str,
        user_password: str,
        method: str,
        relay_passwords: list[str] | None = None,
    ) -> str:
        """
        Convert a password to the format required for 2022-blake3 methods,
        ensuring correct key length.
        """
        base64_string = BaseSubscription.ensure_base64_password(user_password, method)
        parts = []
        if relay_passwords:
            parts.extend(relay_passwords)
        parts.append(inbound_password)
        parts.append(base64_string)
        return ":".join(parts)

    @staticmethod
    def detect_shadowsocks_2022(
        is_2022: bool,
        inbound_method: str,
        user_method: str,
        inbound_password: str,
        user_password: str,
        relay_passwords: list[str] | None = None,
    ) -> tuple[str, str]:
        """Detect and handle Shadowsocks 2022 password format"""
        if is_2022:
            password = BaseSubscription.password_to_2022(
                inbound_password, user_password, inbound_method, relay_passwords
            )
            method = inbound_method
        else:
            password = user_password
            method = user_method
        return method, password
