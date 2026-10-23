"""Which core edits nodes can apply to the running Xray without a restart."""

import copy
import json

from app.core.abstract_core import AbstractCore
from app.models.core import CoreType


def node_facing(core: AbstractCore | None) -> dict | None:
    """What nodes receive for a core: its type, config and excluded inbound tags."""
    if core is None:
        return None
    return {
        "type": core.type,
        "config": json.loads(core.to_str()),
        "exclude": sorted(getattr(core, "exclude_inbound_tags", None) or []),
    }


def _without_live_parts(config: dict) -> dict:
    stripped = copy.deepcopy(config)
    stripped.pop("outbounds", None)
    routing = stripped.get("routing")
    if isinstance(routing, dict):
        routing.pop("rules", None)
        routing.pop("balancers", None)
        if not routing:
            del stripped["routing"]
    return stripped


def only_live_parts_changed(before: dict | None, after: dict | None) -> bool:
    """Whether an Xray core edit only touches routing rules, balancers and outbounds.

    Nodes apply such an edit to the running Xray through its API, so the panel can
    send Start without the Stop that forces a restart. A node that cannot apply it
    live still restarts on its own.
    """
    if before is None or after is None:
        return False
    if before["type"] != CoreType.xray or after["type"] != CoreType.xray:
        return False
    if before["exclude"] != after["exclude"]:
        return False
    return _without_live_parts(before["config"]) == _without_live_parts(after["config"])
