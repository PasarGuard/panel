import json

import pytest
from pydantic import ValidationError

from app.core.hosts import _normalize_finalmask_link
from app.models.host import BaseHost, FinalMask


def test_finalmask_link_supports_stable_fragment_fields_without_mutating_input():
    settings = {"tcp": [{"type": "fragment", "settings": {"lengths": ["100-200"], "delays": ["10-20"]}}]}

    result = json.loads(_normalize_finalmask_link(settings))

    assert result["tcp"][0]["settings"] == {
        "lengths": ["100-200"],
        "delays": ["10-20"],
        "length": "100-200",
        "delay": "10-20",
    }
    assert "length" not in settings["tcp"][0]["settings"]


def test_finalmask_link_normalizes_string_payload():
    payload = '{"tcp":[{"type":"fragment","settings":{"lengths":["100-200"],"delays":["10-20"]}}]}'

    result = json.loads(_normalize_finalmask_link(payload))

    assert result["tcp"][0]["settings"]["length"] == "100-200"
    assert result["tcp"][0]["settings"]["delay"] == "10-20"


def test_finalmask_link_emits_camel_case_and_int_header_rand():
    settings = {
        "udp": [
            {
                "type": "header-custom",
                "settings": {"client": [{"type": "array", "packet": [1], "rand": "32", "rand_range": "32"}]},
            }
        ]
    }

    result = json.loads(_normalize_finalmask_link(settings))

    assert result["udp"][0]["settings"]["client"] == [{"type": "array", "packet": [1], "rand": 32, "randRange": "32"}]


def test_host_final_mask_dump_uses_xray_keys():
    host = BaseHost(
        remark="host",
        priority=0,
        final_mask_settings={
            "udp": [{"type": "noise", "settings": {"noise": [{"type": "array", "rand_range": "80-120"}]}}]
        },
    )

    dumped = host.model_dump(exclude={"id", "inbound_tag"})
    noise_item = dumped["final_mask_settings"]["udp"][0]["settings"]["noise"][0]

    assert noise_item["randRange"] == "80-120"
    assert "rand_range" not in noise_item


def _header_custom(kind: str, **item) -> dict:
    layer = {"type": "header-custom", "settings": {"client": [{"type": "array", "packet": [1], **item}]}}
    return {kind: [layer]}


@pytest.mark.parametrize("rand_range", ["256-257", "0-256", "300", "9-1", "a-b", "1-2-3"])
def test_header_custom_rand_range_must_fit_a_byte_range(rand_range: str):
    with pytest.raises(ValidationError):
        FinalMask.model_validate(_header_custom("udp", randRange=rand_range))


@pytest.mark.parametrize("rand_range", ["0-255", "32", "5-10"])
def test_header_custom_rand_range_accepts_byte_ranges(rand_range: str):
    FinalMask.model_validate(_header_custom("udp", randRange=rand_range))


def _tcp_header_custom(**item) -> dict:
    return {"tcp": [{"type": "header-custom", "settings": {"clients": [[{"type": "array", "packet": [1], **item}]]}}]}


@pytest.mark.parametrize("delay", ["abc", "5--10", "10-5", "1-2-3", "5-"])
def test_tcp_header_custom_delay_rejects_invalid_strings(delay: str):
    with pytest.raises(ValidationError):
        FinalMask.model_validate(_tcp_header_custom(delay=delay))


@pytest.mark.parametrize(("delay", "expected"), [("7", 7), (7, 7), ("5-10", "5-10")])
def test_tcp_header_custom_delay_accepts_integer_or_range(delay, expected):
    mask = FinalMask.model_validate(_tcp_header_custom(delay=delay))

    assert mask.tcp[0].settings.clients[0][0].delay == expected
