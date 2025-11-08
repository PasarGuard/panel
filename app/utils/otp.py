"""Utility helpers for handling admin OTP (2FA) secrets and codes."""

from __future__ import annotations

import pyotp
import qrcode

DEFAULT_ISSUER = "PasarGuard"


def generate_otp_secret() -> str:
    """Return a new random base32 secret for TOTP."""
    return pyotp.random_base32()


def get_provisioning_uri(username: str, secret: str, issuer: str = DEFAULT_ISSUER) -> str:
    """Build an otpauth URI that authenticator apps can use."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def verify_otp(secret: str | None, code: str | None, valid_window: int = 1) -> bool:
    """Validate an OTP code against the stored secret."""
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=valid_window)


def build_qr_ascii(data: str) -> str:
    """Generate a simple ASCII QR code representation for terminal/TUI usage."""
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)
    lines: list[str] = []
    for row in qr.get_matrix():
        # Double-width blocks keep QR square looking in monospace fonts.
        lines.append("".join("██" if cell else "  " for cell in row))
    return "\n".join(lines)
