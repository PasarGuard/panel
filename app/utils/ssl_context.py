import ssl

import certifi


def create_outbound_ssl_context() -> ssl.SSLContext:
    """Build a native client context with both system and Mozilla CA roots."""
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context
