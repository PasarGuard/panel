"""Logging of templates and custom variables that failed to render for a subscription.

Rendering falls back (raw text, the default template) so one broken template does not take subscriptions down. That must
not make it invisible, nor flood the log: every failing fetch of every user would write the same line. Each source is
named by a ref (`template:<id>`, `variable:<KEY>`, `variable:<KEY>@admin:<id>`) and logged once per `LOG_WINDOW`, with
the number left out since.

Failures are reported from the render pool's threads, so the state is guarded by a lock.
"""

import threading
import time

from app.utils.logger import get_logger

logger = get_logger("template-failures")

LOG_WINDOW = 60.0
MAX_ERROR_LENGTH = 500
MAX_REFS = 1000

_lock = threading.Lock()
_logged: dict[str, tuple[float, int]] = {}  # ref -> (when it was last logged, how many were left out since)


def template_ref(template_id: int) -> str:
    return f"template:{template_id}"


def variable_ref(key: str, owner: str | None = None) -> str:
    return f"variable:{key}@{owner}" if owner else f"variable:{key}"


def report_failure(ref: str, error: BaseException) -> None:
    text = (str(error) or type(error).__name__)[:MAX_ERROR_LENGTH]
    now = time.monotonic()
    with _lock:
        last_logged, left_out = _logged.get(ref, (None, 0))
        if last_logged is None or now - last_logged >= LOG_WINDOW:
            log = True
            _logged[ref] = (now, 0)
        else:
            log = False
            _logged[ref] = (last_logged, left_out + 1)
        if len(_logged) > MAX_REFS:
            _logged.pop(next(iter(_logged)))
    if log:
        folded = f" ({left_out} more since the last report)" if left_out else ""
        logger.error("%s failed to render%s: %s", ref, folded, text)
