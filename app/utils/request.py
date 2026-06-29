from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Extract the client's IP address from the request."""
    if request.client:
        return request.client.host
    return "Unknown"
