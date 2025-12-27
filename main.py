import ipaddress
import os
import socket
import ssl
import threading
from pathlib import Path

import click
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from granian import Granian
from granian.constants import Interfaces, Loops
from granian.log import LogLevels
from granian.server import MPServer

import dashboard  # noqa
from app import app, logger  # noqa
from app.utils.logger import LOGGING_CONFIG
from config import (
    DEBUG,
    LOG_LEVEL,
    UVICORN_HOST,
    UVICORN_LOOP,
    UVICORN_PORT,
    UVICORN_SSL_CA_TYPE,
    UVICORN_SSL_CERTFILE,
    UVICORN_SSL_KEYFILE,
    UVICORN_UDS,
)

shutdown_message_printed = False


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
            return "127.0.0.1"
        elif ip.is_private:
            return resolved_ip
        else:
            return "127.0.0.1"

    except (ValueError, socket.gaierror):
        return "127.0.0.1"


def resolve_bind_address(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        logger.warning(f"Unable to resolve UVICORN_HOST '{host}'. Defaulting to 127.0.0.1.")
        return "127.0.0.1"


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


def resolve_loop(loop_name: str) -> Loops:
    normalized_loop = (loop_name or "").lower()
    try:
        return Loops(normalized_loop)
    except ValueError:
        logger.warning(f"Invalid UVICORN_LOOP value '{loop_name}'. Defaulting to 'auto'.")
        return Loops.auto


def install_interrupt_cleanup(server: MPServer) -> None:
    original_interrupt = server.signal_handler_interrupt
    exit_timer: list[threading.Timer | None] = [None]

    def _interrupt_handler(*args, **kwargs):
        if exit_timer[0] is None:
            global shutdown_message_printed
            if not shutdown_message_printed:
                print("Shutting down PasarGuard...")
                shutdown_message_printed = True
            try:
                dashboard.stop_dashboard_processes()
            except Exception:
                pass
            timer = threading.Timer(5.0, lambda: os._exit(0))
            timer.daemon = True
            timer.start()
            exit_timer[0] = timer
        return original_interrupt(*args, **kwargs)

    server.signal_handler_interrupt = _interrupt_handler


if __name__ == "__main__":
    # Do NOT change workers count for now
    # multi-workers support isn't implemented yet for APScheduler

    # Validate UVICORN_SSL_CA_TYPE value
    valid_ca_types = ("public", "private")
    ca_type = UVICORN_SSL_CA_TYPE
    if ca_type not in valid_ca_types:
        logger.warning(
            f"Invalid UVICORN_SSL_CA_TYPE value '{UVICORN_SSL_CA_TYPE}'. "
            f"Expected one of {valid_ca_types}. Defaulting to 'public'."
        )
        ca_type = "public"

    bind_args = {"address": UVICORN_HOST, "port": UVICORN_PORT}

    if UVICORN_SSL_CERTFILE and UVICORN_SSL_KEYFILE:
        validate_cert_and_key(UVICORN_SSL_CERTFILE, UVICORN_SSL_KEYFILE, ca_type=ca_type)

        bind_args["ssl_cert"] = Path(UVICORN_SSL_CERTFILE)
        bind_args["ssl_key"] = Path(UVICORN_SSL_KEYFILE)
        bind_args["address"] = resolve_bind_address(UVICORN_HOST)

    else:
        if not UVICORN_UDS:
            ip = check_and_modify_ip(UVICORN_HOST)

            logger.warning(f"""
{click.style("IMPORTANT!", blink=True, bold=True, fg="yellow")}
You're running PasarGuard without specifying {click.style("UVICORN_SSL_CERTFILE", italic=True, fg="magenta")} and {click.style("UVICORN_SSL_KEYFILE", italic=True, fg="magenta")}.
The application will only be accessible through localhost. This means that {click.style("PasarGuard and subscription URLs will not be accessible externally", bold=True)}.

If you need external access, please provide the SSL files to allow the server to bind to 0.0.0.0. Alternatively, you can run the server on localhost or a Unix socket and use a reverse proxy, such as Nginx or Caddy, to handle SSL termination and provide external access.

If you wish to continue without SSL, you can use SSH port forwarding to access the application from your machine. note that in this case, subscription functionality will not work. 

Use the following command:

{click.style(f"ssh -L {UVICORN_PORT}:localhost:{UVICORN_PORT} user@server", italic=True, fg="cyan")}

Then, navigate to {click.style(f"http://{ip}:{UVICORN_PORT}", bold=True)} on your computer.
            """)

            bind_args["address"] = ip
            bind_args["port"] = UVICORN_PORT

    if UVICORN_UDS:
        bind_args["uds"] = Path(UVICORN_UDS)
        bind_args.pop("address", None)
        bind_args.pop("port", None)

    if DEBUG:
        bind_args["uds"] = None
        bind_args["address"] = "0.0.0.0"
        bind_args["port"] = UVICORN_PORT

    effective_log_level = LOG_LEVEL
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "_granian", "granian.access"):
        LOGGING_CONFIG["loggers"][logger_name]["level"] = effective_log_level

    try:
        granian_log_level = LogLevels(effective_log_level.lower())
    except ValueError:
        logger.warning(f"Invalid LOG_LEVEL '{effective_log_level}'. Defaulting to 'INFO'.")
        granian_log_level = LogLevels.info

    reload_args = {"reload": DEBUG}
    if DEBUG:
        reload_args["reload_ignore_dirs"] = ("dashboard", "node_modules", ".git", "__pycache__", ".venv")

    dashboard_dev_managed = False
    if DEBUG:
        manage_env = os.getenv("DASHBOARD_DEV_MANAGED", "").lower()
        if manage_env not in {"0", "false", "no"}:
            os.environ["DASHBOARD_DEV_MANAGED"] = "1"
            dashboard_dev_managed = True
            try:
                dashboard.run_dev()
            except Exception as exc:
                logger.warning(f"Failed to start dashboard dev server: {exc}")

    try:
        server = Granian(
            "main:app",
            **bind_args,
            workers=1,
            interface=Interfaces.ASGI,
            log_dictconfig=LOGGING_CONFIG,
            log_level=granian_log_level,
            loop=resolve_loop(UVICORN_LOOP),
            **reload_args,
        )
        install_interrupt_cleanup(server)
        server.serve()
    except FileNotFoundError:  # to prevent error on removing unix sock
        pass
    finally:
        if not shutdown_message_printed:
            print("Shutting down PasarGuard...")
            shutdown_message_printed = True
        if dashboard_dev_managed:
            dashboard.stop_dashboard_processes()
