from app.models.host import FinalMask, dump_final_mask_for_xray
from app.subscription.xray import XrayConfiguration


def test_finalmask_fragment_emits_stable_and_new_schema_fields():
    finalmask = FinalMask.model_validate(
        {
            "tcp": [
                {
                    "type": "fragment",
                    "settings": {
                        "packets": "tlshello",
                        "lengths": ["3-5", "6-8"],
                        "delays": [0, "10-20"],
                    },
                }
            ]
        }
    )

    dumped = dump_final_mask_for_xray(finalmask)
    settings = dumped["tcp"][0]["settings"]

    assert settings["lengths"] == ["3-5", "6-8"]
    assert settings["delays"] == [0, "10-20"]
    assert settings["length"] == "3-5"
    assert settings["delay"] == 0


def test_finalmask_fragment_preserves_explicit_singular_fallbacks():
    dumped = dump_final_mask_for_xray(
        {
            "tcp": [
                {
                    "type": "fragment",
                    "settings": {
                        "lengths": ["3-5", "6-8"],
                        "delays": ["10-20"],
                        "length": "20-30",
                        "delay": "30-40",
                    },
                }
            ]
        }
    )

    settings = dumped["tcp"][0]["settings"]
    assert settings["length"] == "20-30"
    assert settings["delay"] == "30-40"


def test_finalmask_fragment_replaces_empty_singular_fallbacks():
    dumped = dump_final_mask_for_xray(
        {
            "tcp": [
                {
                    "type": "fragment",
                    "settings": {
                        "lengths": ["3-5"],
                        "delays": ["10-20"],
                        "length": None,
                        "delay": "",
                    },
                }
            ]
        }
    )

    settings = dumped["tcp"][0]["settings"]
    assert settings["length"] == "3-5"
    assert settings["delay"] == "10-20"


def test_xray_stream_settings_use_compatible_finalmask_dump():
    finalmask = FinalMask.model_validate(
        {
            "tcp": [
                {
                    "type": "fragment",
                    "settings": {"length": "10-20", "delay": "5-10"},
                }
            ]
        }
    )

    stream_settings = XrayConfiguration._stream_setting_config(finalmask=finalmask)
    settings = stream_settings["finalmask"]["tcp"][0]["settings"]

    assert settings == {
        "lengths": ["10-20"],
        "delays": ["5-10"],
        "length": "10-20",
        "delay": "5-10",
    }
