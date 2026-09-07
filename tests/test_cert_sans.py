import datetime
import json
from ipaddress import ip_address

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.utils.crypto import get_cert_SANs


def _pem_cert_with_dns_and_ip_sans() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.com")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("example.com"),
                    x509.DNSName("www.example.com"),
                    x509.IPAddress(ip_address("1.2.3.4")),
                    x509.IPAddress(ip_address("2001:db8::1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def test_get_cert_sans_returns_json_serializable_strings() -> None:
    sans = get_cert_SANs(_pem_cert_with_dns_and_ip_sans())
    assert all(isinstance(item, str) for item in sans)
    assert "example.com" in sans
    assert "www.example.com" in sans
    assert "1.2.3.4" in sans
    assert "2001:db8::1" in sans
    json.dumps({"sni": sans})
