import asyncio
import os
import ssl
import stat

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from app.models.certificate import CertificateFingerprintRequest

MAX_CERTIFICATE_BYTES = 1048576


class CertificateFingerprintError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _read_certificate_file(file_path: str) -> bytes:
    try:
        # Nonblocking open lets us reject devices and FIFOs without waiting on them.
        fd = os.open(file_path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as certificate_file:
            if not stat.S_ISREG(os.fstat(certificate_file.fileno()).st_mode):
                raise CertificateFingerprintError("Certificate path must be a regular file")
            data = certificate_file.read(MAX_CERTIFICATE_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise CertificateFingerprintError("Cannot read certificate file") from exc
    if len(data) > MAX_CERTIFICATE_BYTES:
        raise CertificateFingerprintError("Certificate file exceeds 1 MiB")
    return data


async def _server_certificate(request: CertificateFingerprintRequest) -> bytes:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # Discovery must also work for self-signed certificates and unknown pins.
    # This retrieves a fingerprint; it does not authenticate the remote server.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.set_alpn_protocols(["h2", "http/1.1"])
    writer = None
    try:
        async with asyncio.timeout(request.timeout):
            _, writer = await asyncio.open_connection(
                request.server,
                request.port,
                ssl=context,
                server_hostname=request.server_name or request.server,
                ssl_handshake_timeout=request.timeout,
            )
            certificate = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
            if not certificate:
                raise CertificateFingerprintError("TLS server did not provide a certificate", 502)
            return certificate
    except TimeoutError as exc:
        raise CertificateFingerprintError("TLS certificate probe timed out", 504) from exc
    except (OSError, ValueError) as exc:
        raise CertificateFingerprintError("Could not retrieve the server TLS certificate", 502) from exc
    finally:
        if writer is not None:
            # Do not wait for an untrusted peer's TLS close-notify response.
            writer.close()


async def get_certificate_fingerprint(request: CertificateFingerprintRequest) -> str:
    if request.server is not None:
        data = await _server_certificate(request)
    elif request.file_path is not None:
        data = await asyncio.to_thread(_read_certificate_file, request.file_path)
    else:
        data = request.pem.encode("utf-8")
    try:
        certificate = (
            x509.load_pem_x509_certificate(data)
            if b"-----BEGIN CERTIFICATE-----" in data
            else x509.load_der_x509_certificate(data)
        )
    except ValueError as exc:
        raise CertificateFingerprintError("Invalid certificate; expected PEM or DER certificate data") from exc
    return certificate.fingerprint(hashes.SHA256()).hex()
