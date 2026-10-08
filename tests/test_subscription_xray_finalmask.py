from copy import deepcopy

import pytest

from app.models.host import FinalMask
from app.subscription.xray import XrayConfiguration


def test_xray_finalmask_serializes_raw_max_split_with_xray_alias():
    stream_settings = XrayConfiguration._stream_setting_config(
        finalmask={
            "tcp": [
                {
                    "type": "fragment",
                    "settings": {
                        "packets": "tlshello",
                        "max_split": "3-6",
                    },
                }
            ]
        }
    )

    settings = stream_settings["finalmask"]["tcp"][0]["settings"]

    assert settings["maxSplit"] == "3-6"
    assert "max_split" not in settings


def test_xray_finalmask_keeps_unrecognized_raw_values_unchanged():
    finalmask = {"tcp": [{"type": "future-type", "settings": {"max_split": "3-6"}}]}

    stream_settings = XrayConfiguration._stream_setting_config(finalmask=finalmask)

    assert stream_settings["finalmask"] == finalmask


@pytest.mark.parametrize("as_model", [False, True])
def test_xray_finalmask_combines_stable_fragment_fields_and_max_split_alias(as_model):
    finalmask = {
        "tcp": [
            {
                "type": "fragment",
                "settings": {
                    "packets": "tlshello",
                    "lengths": ["100-200", "200-300"],
                    "delays": ["10-20", "20-30"],
                    "max_split": "3-6",
                },
            }
        ]
    }
    original = deepcopy(finalmask)
    value = FinalMask.model_validate(finalmask) if as_model else finalmask

    stream_settings = XrayConfiguration._stream_setting_config(finalmask=value)
    settings = stream_settings["finalmask"]["tcp"][0]["settings"]

    assert settings["length"] == "100-200"
    assert settings["delay"] == "10-20"
    assert settings["lengths"] == ["100-200", "200-300"]
    assert settings["delays"] == ["10-20", "20-30"]
    assert settings["maxSplit"] == "3-6"
    assert "max_split" not in settings
    assert finalmask == original
