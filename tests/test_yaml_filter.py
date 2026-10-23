import random
from uuid import UUID

import pytest
import yaml

from app.templates import filters
from app.templates.filters import to_yaml

pytestmark = pytest.mark.skipif(not yaml.__with_libyaml__, reason="libyaml is not available")


def _pure_dump(obj) -> str:
    return yaml.dump(obj, Dumper=yaml.Dumper, allow_unicode=True, indent=2, sort_keys=False)


def _clash_meta_conf() -> dict:
    remarks = [
        "🇩🇪 Germany | user_1 [VLESS - grpc]",
        "🇳🇱 هلند ✅ 10 GB left ⏳ 3 days",
        "🪫 limited 🔌 on hold ⌛️ expired ❌",
        "中文节点 🚀 Fast",
        "plain-ascii-remark",
        "a remark long enough to cross the eighty column width of the emitter " * 2,
        "yes",
        "1.0",
        "#hash: 'quoted' \"double\"",
    ]
    proxies = []
    for index, remark in enumerate(remarks):
        proxies.append(
            {
                "name": remark,
                "type": ("vless", "vmess", "trojan", "ss", "hysteria2")[index % 5],
                "server": f"s{index}.example.com",
                "port": 443,
                "network": "ws",
                "udp": True,
                "uuid": UUID(int=index + 1),
                "tls": True,
                "servername": "cdn.example.com",
                "client-fingerprint": "chrome",
                "alpn": ["h2", "http/1.1"],
                "skip-cert-verify": False,
                "ws-opts": {"path": "/ws?ed=2048", "headers": {"Host": "🌐.example.com"}},
                "reality-opts": {"public-key": "Y0ZJbDZ6S0xxV2pXQ2VtR1hBZm5RZ0pPbmVNbU9uZ0Q", "short-id": ""},
                "smux": {"enabled": False, "padding": None},
            }
        )
    return {"proxies": proxies, "dns": {"enable": True, "nameserver": ["https://1.1.1.1/dns-query#PROXY"]}}


def test_to_yaml_matches_pure_dumper_on_clash_meta_conf(monkeypatch):
    conf = _clash_meta_conf()
    remarks = [proxy["name"] for proxy in conf["proxies"]]
    expected = [_pure_dump(conf), _pure_dump(remarks)]

    # The representative subscription (emoji included) must take the libyaml path, not the fallback
    def no_fallback(*args, **kwargs):
        raise AssertionError("fell back to the pure-Python dumper")

    monkeypatch.setattr(filters.yaml, "dump", no_fallback)
    assert [to_yaml(conf), to_yaml(remarks)] == expected


@pytest.mark.parametrize(
    "doc",
    [
        ["\x85 next line"],
        ["carriage\rreturn"],
        ["🚀\ttab"],
        ["🚀 multi\nline"],
        ["🚀\u2028 line separator"],
        ["lone \ud83d surrogate"],
        ["private \ue000 use"],
        ["\U0010ffff"],
        {"k" * 128: "long key"},
        {"a" * 123: "key of 123 characters"},
        {"a" * 127: "key of 127 characters"},
        {"🇩🇪" * 16: "key of 128 bytes"},
        {"ک" * 63: "key of 126 bytes"},
        {"": "empty key"},
        "top-level 🚀 scalar",
        3,
    ],
)
def test_to_yaml_matches_pure_dumper_on_inputs_libyaml_writes_differently(doc):
    assert to_yaml(doc) == _pure_dump(doc)


_FUZZ_ALPHABET = (
    list("abcXYZ019 -_:#'\"{}[]&*!|>%@`,?=~.\\/")
    + ["\n", "\t", "\r", "\x00", "\x7f", "\x85", "\xa0", "\u2028", "\u2029", "\ufeff", "\ufffe"]
    + list("éüکی中文")
    + ["\ue000", "\uf8ff", "🇩", "🇪", "😀", "🪫", "\U00010000", "\U0010fffe"]
)


def _random_str(rng: random.Random) -> str:
    length = rng.choice([0, 1, 2, 5, 20, 60, 130])
    return "".join(rng.choice(_FUZZ_ALPHABET) for _ in range(length))


def _random_scalar(rng: random.Random):
    return rng.choice([_random_str, _random_str, _random_str, lambda r: r.randint(-5, 5), lambda r: None])(rng)


def _random_doc(rng: random.Random, depth: int = 0):
    if depth > 2 or rng.random() < 0.3:
        return _random_scalar(rng)
    if rng.random() < 0.5:
        return [_random_doc(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {_random_str(rng): _random_doc(rng, depth + 1) for _ in range(rng.randint(0, 4))}


def test_to_yaml_matches_pure_dumper_on_random_documents():
    rng = random.Random(1052)
    for _ in range(3000):
        doc = _random_doc(rng)
        if doc:
            assert to_yaml(doc) == _pure_dump(doc), repr(doc)
