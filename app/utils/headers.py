"""Checks for response headers built from settings or plugin output."""

import re

HTTP_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def check_response_header(header_name: str, header_value: str) -> None:
    """Raise ``ValueError`` if the pair cannot be sent as an HTTP response header."""
    if not header_name or header_name != header_name.strip():
        raise ValueError("Invalid response header name: empty or whitespace wrapped")
    if not HTTP_HEADER_NAME_PATTERN.fullmatch(header_name):
        raise ValueError(f'Invalid response header name "{header_name}"')

    if "\r" in header_value or "\n" in header_value or "\x00" in header_value:
        raise ValueError(f'Invalid response header "{header_name}": value contains forbidden control characters')

    try:
        header_name.encode("latin-1")
        header_value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ValueError(f'Invalid response header "{header_name}": value contains non latin-1 characters') from exc
