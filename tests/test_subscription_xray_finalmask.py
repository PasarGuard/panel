import pytest
from pydantic import ValidationError

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


def test_xray_finalmask_keeps_udphop_with_xray_field_names():
    udphop = {
        "type": "udphop",
        "settings": {
            "mode": "intervalRemote",
            "interval": "10-60",
            "remoteIPs": ["203.0.113.0/24"],
            "remotePorts": "20000-20010",
        },
    }
    finalmask = FinalMask.model_validate({"udp": [udphop]}).model_dump(by_alias=True, exclude_none=True, mode="json")

    stream_settings = XrayConfiguration._stream_setting_config(finalmask=finalmask)

    assert stream_settings["finalmask"]["udp"] == [udphop]


def _noise_exp_mask(**item):
    return {"udp": [{"type": "noise", "settings": {"noise": [{"type": "exp", **item}]}}]}


def test_xray_finalmask_keeps_noise_exp_template():
    exp = {"packet": "<b 0d0a0d0a><t><r 24>", "delay": "1-3"}
    finalmask = FinalMask.model_validate(_noise_exp_mask(**exp)).model_dump(
        by_alias=True, exclude_none=True, mode="json"
    )

    stream_settings = XrayConfiguration._stream_setting_config(finalmask=finalmask)

    assert stream_settings["finalmask"]["udp"][0]["settings"]["noise"] == [{"type": "exp", **exp}]


@pytest.mark.parametrize(
    "item",
    [{"packet": [1, 2]}, {"packet": ""}, {"packet": "   "}, {"packet": None}, {}],
    ids=["array", "empty", "blank", "null", "missing"],
)
def test_finalmask_noise_exp_rejects_bad_packet(item):
    with pytest.raises(ValidationError, match="exp noise needs a non-empty packet template string"):
        FinalMask.model_validate(_noise_exp_mask(**item))


@pytest.mark.parametrize(
    ("mask", "match"),
    [
        (
            {"udp": [{"type": "header-custom", "settings": {"client": [{"type": "exp", "packet": "<t>"}]}}]},
            r"client\.0\.type",
        ),
        (
            {"tcp": [{"type": "header-custom", "settings": {"clients": [[{"type": "exp", "packet": "<t>"}]]}}]},
            r"clients\.0\.0\.type",
        ),
    ],
    ids=["udp", "tcp"],
)
def test_finalmask_header_custom_rejects_exp(mask, match):
    with pytest.raises(ValidationError, match=match):
        FinalMask.model_validate(mask)
