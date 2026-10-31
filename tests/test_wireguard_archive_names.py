import io
import zipfile

import pytest

from app.subscription.wireguard import WireGuardConfiguration


def _names(*remarks: str) -> list[str]:
    config = WireGuardConfiguration()
    config.configs = [(remark, "[Interface]\n") for remark in remarks]
    with zipfile.ZipFile(io.BytesIO(config.render())) as archive:
        return archive.namelist()


@pytest.mark.parametrize(
    ("remark", "expected"),
    [
        ("Germany 1", "Germany_1.conf"),
        ("../../etc/cron.d/x", "____etc_cron.d_x.conf"),
        ("..\\..\\Windows\\x", "____Windows_x.conf"),
        ("C:\\temp\\x", "C__temp_x.conf"),
        ("bad\x00name\r\n", "bad_name__.conf"),
        ("", "config.conf"),
        ("..", "_.conf"),
        ("  ", "__.conf"),
        ("🇩🇪 Berlin", "🇩🇪_Berlin.conf"),
    ],
)
def test_archive_entry_names_are_flat_file_names(remark, expected):
    assert _names(remark) == [expected]


def test_archive_entry_names_never_leave_the_extraction_folder():
    for name in _names("../a", "/abs", "..\\b", "a/../../c", "x\x00y"):
        assert "/" not in name and "\\" not in name and "\x00" not in name
        assert not name.startswith(".")
        assert ".." not in name


def test_long_remarks_are_truncated():
    (name,) = _names("x" * 200)
    assert name == "x" * 64 + ".conf"


def test_duplicate_names_get_numbered_suffixes():
    assert _names("Node 1", "Node 1", "Node_1", "node 1") == [
        "Node_1.conf",
        "Node_1-2.conf",
        "Node_1-3.conf",
        "node_1-4.conf",
    ]


def test_names_that_collide_after_truncation_get_suffixes():
    assert _names("a" * 64 + "-one", "a" * 64 + "-two") == ["a" * 64 + ".conf", "a" * 64 + "-2.conf"]


def test_suffix_does_not_reuse_an_existing_name():
    assert _names("x-2", "x", "x") == ["x-2.conf", "x.conf", "x-3.conf"]
