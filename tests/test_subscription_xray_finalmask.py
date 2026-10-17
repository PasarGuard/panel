from copy import deepcopy

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


def test_xray_finalmask_header_custom_items_use_xray_types():
    finalmask = {
        "udp": [
            {
                "type": "header-custom",
                "settings": {
                    "client": [{"type": "array", "rand": "32", "delay": "5-10", "randRange": "32"}],
                    "server": [{"type": "array", "rand": "", "packet": "abc"}],
                },
            }
        ],
        "tcp": [
            {
                "type": "header-custom",
                "settings": {
                    "clients": [[{"type": "array", "rand": "7", "delay": "10", "randRange": "1-9"}]],
                    "servers": [[{"type": "array", "delay": "5-10", "rand_range": "0-255"}]],
                },
            }
        ],
    }

    stream_settings = XrayConfiguration._stream_setting_config(finalmask=finalmask)
    mask = stream_settings["finalmask"]

    assert mask["udp"][0]["settings"] == {
        "client": [{"type": "array", "rand": 32, "randRange": "32"}],
        "server": [{"type": "array", "packet": "abc"}],
    }
    assert mask["tcp"][0]["settings"] == {
        "clients": [[{"type": "array", "rand": 7, "delay": 10, "randRange": "1-9"}]],
        "servers": [[{"type": "array", "delay": "5-10", "randRange": "0-255"}]],
    }


def test_xray_finalmask_noise_keeps_range_strings():
    noise = {"type": "array", "rand": "1-8192", "delay": "5-10", "randRange": "80-120"}
    finalmask = {"udp": [{"type": "noise", "settings": {"noise": [noise]}}]}

    stream_settings = XrayConfiguration._stream_setting_config(finalmask=finalmask)

    assert stream_settings["finalmask"]["udp"][0]["settings"]["noise"] == [noise]


def test_xray_finalmask_legacy_snake_keys_are_emitted_as_xray_keys():
    finalmask = {
        "udp": [
            {
                "type": "noise",
                "settings": {"noise": [{"type": "array", "delay": "5-10", "rand_range": "80-120"}]},
            }
        ]
    }

    stream_settings = XrayConfiguration._stream_setting_config(finalmask=finalmask)

    assert stream_settings["finalmask"]["udp"][0]["settings"]["noise"] == [
        {"type": "array", "delay": "5-10", "randRange": "80-120"}
    ]


@pytest.mark.parametrize("rand", ["abc", "1-8", "3.5", -1])
def test_finalmask_header_custom_rejects_invalid_rand(rand):
    mask = {"udp": [{"type": "header-custom", "settings": {"client": [{"type": "array", "rand": rand}]}}]}

    with pytest.raises(ValidationError):
        FinalMask.model_validate(mask)
