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
