import ipaddress
import os
import stat
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID

from app.models.certificate import CertificateDetails, CertificateInspectRequest, CertificateInspectResult

MAX_CERTIFICATE_BYTES = 1_048_576
MAX_KEY_BYTES = 65_536


def _read_pem_file(path: str, limit: int) -> bytes:
    # O_NONBLOCK prevents opening a FIFO from tying up a worker. Symlinks are
    # intentionally supported for ACME clients' live/fullchain.pem paths.
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("unsupported_file")
        content = stream.read(limit + 1)
        if len(content) > limit:
            raise ValueError("unsupported_file")
        return content


def _common_name(name: x509.Name) -> str | None:
    attributes = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(attributes[0].value) if attributes else None


def _names(cert: x509.Certificate) -> list[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        return list(
            dict.fromkeys([*san.get_values_for_type(x509.DNSName), *map(str, san.get_values_for_type(x509.IPAddress))])
        )
    except x509.ExtensionNotFound:
        return []


def _matches_name(host: str, cert: x509.Certificate) -> bool:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    # An IP literal must match an IPAddress SAN, never a DNSName containing
    # the same digits. Preserve that distinction when checking the SNI.
    if address is not None:
        return address in san.get_values_for_type(x509.IPAddress)
    names = san.get_values_for_type(x509.DNSName)
    for name in names:
        try:
            expected = name.rstrip(".").encode("idna").decode().lower()
            actual = host.rstrip(".").encode("idna").decode().lower()
        except UnicodeError:
            continue
        if "*" in actual or any(not part or any(char.isspace() for char in part) for part in actual.split(".")):
            return False
        if expected == actual:
            return True
        if expected.startswith("*.") and actual.count(".") == expected.count(".") and actual.endswith(expected[1:]):
            return True
    return False


def _time_status(cert: x509.Certificate, now: datetime) -> str:
    if now < cert.not_valid_before_utc:
        return "not_yet_valid"
    if now >= cert.not_valid_after_utc:
        return "expired"
    if cert.not_valid_after_utc - now <= timedelta(days=30):
        return "expiring"
    return "valid"


def _details(cert: x509.Certificate, now: datetime) -> CertificateDetails:
    try:
        is_ca = cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        is_ca = False
    self_signed = False
    if cert.issuer == cert.subject:
        try:
            cert.verify_directly_issued_by(cert)
            self_signed = True
        except ValueError, TypeError:
            pass
    return CertificateDetails(
        subject=cert.subject.rfc4514_string(),
        issuer=_common_name(cert.issuer) or cert.issuer.rfc4514_string(),
        domains=_names(cert),
        common_name=_common_name(cert.subject),
        not_before=cert.not_valid_before_utc.isoformat(),
        not_after=cert.not_valid_after_utc.isoformat(),
        fingerprint=cert.fingerprint(hashes.SHA256()).hex(":"),
        serial_number=format(cert.serial_number, "x"),
        public_key_algorithm=cert.public_key_algorithm_oid._name or cert.public_key_algorithm_oid.dotted_string,
        is_ca=is_ca,
        self_signed=self_signed,
        status=_time_status(cert, now),
    )


def inspect_certificate(request: CertificateInspectRequest) -> CertificateInspectResult:
    now = datetime.now(UTC)
    result = CertificateInspectResult(status="empty", checked_at=now.isoformat())
    # Content is available to the control plane even when served on a node;
    # node-local paths must never be resolved on the control-plane filesystem.
    if request.serve_on_node and (request.certificate_file or request.key_file):
        result.status = "unavailable"
        result.key_status = "unavailable"
        result.error = "node_local"
        return result
    try:
        pem = (
            _read_pem_file(request.certificate_file, MAX_CERTIFICATE_BYTES)
            if request.certificate_file
            else request.certificate.encode()
        )
    except OSError, ValueError:
        result.status = "unavailable"
        result.key_status = "unavailable"
        result.error = "certificate_file_unreadable"
        return result
    if not pem.strip():
        return result
    try:
        if len(pem) > MAX_CERTIFICATE_BYTES:
            raise ValueError("oversized_certificate")
        chain = x509.load_pem_x509_certificates(pem)
        if len(chain) > 32:
            raise ValueError("oversized_chain")
        result.certificates = [_details(cert, now) for cert in chain]
        result.status = result.certificates[0].status
        if len(chain) > 1:
            try:
                for child, issuer in pairwise(chain):
                    child.verify_directly_issued_by(issuer)
                result.chain_linked = True
            except ValueError, TypeError:
                result.chain_linked = False
        if request.server_name.strip():
            # SANs are authoritative for hostname matching; CN is shown only
            # as a legacy label, never treated as proof of domain coverage.
            result.server_name_matches = _matches_name(request.server_name.strip(), chain[0])
    except Exception:
        result.status = "invalid"
        result.key_status = "unavailable"
        result.error = "invalid_certificate"
        result.certificates = []
        return result
    try:
        key_pem = _read_pem_file(request.key_file, MAX_KEY_BYTES) if request.key_file else request.key.encode()
    except OSError, ValueError:
        result.key_status = "unavailable"
        result.key_error = "key_file_unreadable"
        return result
    if not key_pem.strip():
        return result
    try:
        if len(key_pem) > MAX_KEY_BYTES:
            raise ValueError("oversized_key")
        key = serialization.load_pem_private_key(key_pem, password=None)
        encoding = serialization.Encoding.DER
        public_format = serialization.PublicFormat.SubjectPublicKeyInfo
        result.key_status = (
            "matched"
            if key.public_key().public_bytes(encoding, public_format)
            == chain[0].public_key().public_bytes(encoding, public_format)
            else "mismatch"
        )
    except Exception:
        result.key_status = "invalid"
        result.key_error = "invalid_key"
    return result
