class NodeRevocationError(RuntimeError):
    """A user removal was not acknowledged by every configured runtime node."""

    code = 503
