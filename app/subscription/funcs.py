import base64
import hashlib


def get_grpc_gun(path: str) -> str:
    if not path.startswith("/"):
        return path

    servicename = path.rsplit("/", 1)[0]
    streamname = path.rsplit("/", 1)[1].split("|")[0]

    if streamname == "Tun":
        return servicename[1:]

    return "%s%s%s" % (servicename, "/", streamname)


def get_grpc_multi(path: str) -> str:
    if not path.startswith("/"):
        return path

    servicename = path.rsplit("/", 1)[0]
    streamname = path.rsplit("/", 1)[1].split("|")[1]

    return "%s%s%s" % (servicename, "/", streamname)


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


def password_to_2022(inbound_password: str, user_password: str, method: str) -> str:
    """
    Convert a password to the format required for 2022-blake3 methods,
    ensuring correct key length.
    """
    base64_string = ensure_base64_password(user_password, method)
    return f"{inbound_password}:{base64_string}"


def detect_shadowsocks_2022(
    is_2022: bool, inbound_method: str, user_method: str, inbound_password: str, user_password: str
) -> tuple[str, str]:
    if is_2022:
        password = password_to_2022(inbound_password, user_password, inbound_method)
        method = inbound_method
    else:
        password = user_password
        method = user_method
    return method, password
