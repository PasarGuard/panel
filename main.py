import ipaddress
import os
import socket
import ssl

import click
import uvicorn
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from app import create_app  # noqa: F401
from app.nats import require_nats_if_multiworker
from app.utils.logger import LOGGING_CONFIG, get_logger
from config import logging_settings, runtime_settings, server_settings

logger = get_logger("uvicorn-main")

workers = server_settings.workers or 1
if workers < 1:
    logger.warning(f"Invalid UVICORN_WORKERS value '{server_settings.workers}', defaulting to 1.")
    workers = 1
elif workers > 1:
    require_nats_if_multiworker(workers)


def check_and_modify_ip(ip_address: str) -> str:
    """
    Check if an IP address is private. If not, return localhost.

    IPv4 Private range = [
        "192.168.0.0",
        "192.168.255.255",
        "10.0.0.0",
        "10.255.255.255",
        "172.16.0.0",
        "172.31.255.255"
    ]

    Args:
        ip_address (str): IP address to check

    Returns:
        str: Original IP if private, otherwise localhost

    Raises:
        ValueError: If the provided IP address is invalid, return localhost.
    """
    try:
        # Attempt to resolve hostname to IP address
        resolved_ip = socket.gethostbyname(ip_address)

        # Convert string to IP address object
        ip = ipaddress.ip_address(resolved_ip)

        if ip == ipaddress.ip_address("0.0.0.0"):
            return "localhost"
        elif ip.is_private:
            return ip_address
        else:
            return "localhost"

    except ValueError, socket.gaierror:
        return "localhost"


def validate_cert_and_key(cert_file_path, key_file_path, ca_type: str = "public"):
    if not os.path.isfile(cert_file_path):
        raise ValueError(f"SSL certificate file '{cert_file_path}' does not exist.")
    if not os.path.isfile(key_file_path):
        raise ValueError(f"SSL key file '{key_file_path}' does not exist.")

    try:
        context = ssl.create_default_context()
        context.load_cert_chain(certfile=cert_file_path, keyfile=key_file_path)
    except ssl.SSLError as e:
        raise ValueError(f"SSL Error: {e}")

    try:
        with open(cert_file_path, "rb") as cert_file:
            cert_data = cert_file.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

        # Only check for self-signed certificates if ca_type is "public"
        if ca_type == "public" and cert.issuer == cert.subject:
            raise ValueError("The certificate is self-signed and not issued by a trusted CA.")

    except ValueError:
        # Re-raise ValueError exceptions (including our self-signed check)
        raise
    except Exception as e:
        raise ValueError(f"Certificate verification failed: {e}")


if __name__ == "__main__":
    # Validate UVICORN_SSL_CA_TYPE value
    valid_ca_types = ("public", "private")
    ca_type = server_settings.ssl_ca_type
    if ca_type not in valid_ca_types:
        logger.warning(
            f"Invalid UVICORN_SSL_CA_TYPE value '{server_settings.ssl_ca_type}'. "
            f"Expected one of {valid_ca_types}. Defaulting to 'public'."
        )
        ca_type = "public"

    bind_args = {}

    if server_settings.ssl_certfile and server_settings.ssl_keyfile:
        validate_cert_and_key(server_settings.ssl_certfile, server_settings.ssl_keyfile, ca_type=ca_type)

        bind_args["ssl_certfile"] = server_settings.ssl_certfile
        bind_args["ssl_keyfile"] = server_settings.ssl_keyfile

        if server_settings.uds:
            bind_args["uds"] = server_settings.uds
        else:
            bind_args["host"] = server_settings.host
            bind_args["port"] = server_settings.port

    else:
        if server_settings.uds:
            bind_args["uds"] = server_settings.uds
        else:
            ip = check_and_modify_ip(server_settings.host)

            logger.warning(f"""
{click.style("IMPORTANT!", blink=True, bold=True, fg="yellow")}
You're running PasarGuard without specifying {click.style("UVICORN_SSL_CERTFILE", italic=True, fg="magenta")} and {click.style("UVICORN_SSL_KEYFILE", italic=True, fg="magenta")}.
The application will only be accessible through localhost. This means that {click.style("PasarGuard and subscription URLs will not be accessible externally", bold=True)}.

If you need external access, please provide the SSL files to allow the server to bind to 0.0.0.0. Alternatively, you can run the server on localhost or a Unix socket and use a reverse proxy, such as Nginx or Caddy, to handle SSL termination and provide external access.

If you wish to continue without SSL, you can use SSH port forwarding to access the application from your machine. note that in this case, subscription functionality will not work.

Use the following command:

{click.style(f"ssh -L {server_settings.port}:localhost:{server_settings.port} user@server", italic=True, fg="cyan")}

Then, navigate to {click.style(f"http://{ip}:{server_settings.port}", bold=True)} on your computer.
            """)

            bind_args["host"] = ip
            bind_args["port"] = server_settings.port

    if runtime_settings.debug:
        bind_args["uds"] = None
        bind_args["host"] = "0.0.0.0"

    effective_log_level = logging_settings.level
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        LOGGING_CONFIG["loggers"][logger_name]["level"] = effective_log_level

    try:
        uvicorn.run(
            "main:create_app",
            factory=True,
            **bind_args,
            workers=workers,
            reload=runtime_settings.debug,
            log_config=LOGGING_CONFIG,
            log_level=effective_log_level.lower(),
            loop=server_settings.loop,
            proxy_headers=server_settings.proxy_headers,
            forwarded_allow_ips=server_settings.forwarded_allow_ips,
        )
    except FileNotFoundError:  # to prevent error on removing unix sock
        pass
