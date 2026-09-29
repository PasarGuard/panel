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
