import pytest
from pydantic import ValidationError

from app.models.node import NodeCoreUpdate


@pytest.mark.parametrize(
    ("given", "sent"),
    [
        ("latest", "latest"),
        ("v25.8.31", "v25.8.31"),
        ("25.8.31", "v25.8.31"),
    ],
)
def test_core_version_is_sent_in_node_serviced_format(given, sent):
    # node-serviced and pg-node look versions up by release tag, which always starts with "v".
    assert NodeCoreUpdate(core_version=given).model_dump(mode="json") == {"core_version": sent}


def test_core_version_defaults_to_latest():
    assert NodeCoreUpdate().core_version == "latest"


@pytest.mark.parametrize("given", ["", "v25.8", "newest", "25.8.31-beta"])
def test_core_version_rejects_unknown_formats(given):
    with pytest.raises(ValidationError):
        NodeCoreUpdate(core_version=given)
