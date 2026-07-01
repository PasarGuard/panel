"""Unit tests for host-tag Pydantic schemas (no DB required)."""

import pytest
from pydantic import ValidationError

from app.models.host import BaseHost, HostTag, HostTagColor, HostTagCreate, HostTagModify


def test_host_tag_color_enum_values():
    assert HostTagColor("red") is HostTagColor.red
    assert {c.value for c in HostTagColor} == {
        "slate",
        "red",
        "orange",
        "amber",
        "green",
        "teal",
        "sky",
        "blue",
        "violet",
        "pink",
    }


def test_host_tag_color_rejects_unknown():
    with pytest.raises(ValueError):
        HostTagColor("neon")


def test_host_tag_create_strips_name():
    tag = HostTagCreate(name="  Germany  ", color="red")
    assert tag.name == "Germany"
    assert tag.color is HostTagColor.red


def test_host_tag_create_rejects_blank_name():
    with pytest.raises(ValidationError):
        HostTagCreate(name="   ", color="red")


def test_host_tag_create_rejects_empty_name():
    with pytest.raises(ValidationError):
        HostTagCreate(name="", color="red")


def test_host_tag_create_rejects_too_long_name():
    with pytest.raises(ValidationError):
        HostTagCreate(name="x" * 65, color="red")


def test_host_tag_create_rejects_bad_color():
    with pytest.raises(ValidationError):
        HostTagCreate(name="ok", color="rainbow")


def test_host_tag_modify_all_optional():
    empty = HostTagModify()
    assert empty.name is None and empty.color is None

    color_only = HostTagModify(color="blue")
    assert color_only.name is None
    assert color_only.color is HostTagColor.blue


def test_host_tag_modify_strips_name():
    modified = HostTagModify(name="  Prod ")
    assert modified.name == "Prod"


def test_host_tag_modify_rejects_blank_name():
    with pytest.raises(ValidationError):
        HostTagModify(name="   ")


def test_base_host_carries_tags_and_tag_ids():
    host = BaseHost(
        remark="h1",
        priority=0,
        tags=[HostTag(id=1, name="Germany", color="red"), HostTag(id=2, name="Premium", color="amber")],
        tag_ids=[1, 2],
    )
    assert [t.name for t in host.tags] == ["Germany", "Premium"]
    assert host.tag_ids == [1, 2]


def test_base_host_defaults_tags_empty():
    host = BaseHost(remark="h1", priority=0)
    assert host.tags == []
    assert host.tag_ids == []


def test_base_host_reads_tags_from_orm_like_object():
    """from_attributes should pull tags + the tag_ids property off an ORM-like object."""

    class FakeTag:
        def __init__(self, id, name, color):
            self.id, self.name, self.color = id, name, color

    class FakeHost:
        remark = "orm-host"
        priority = 3
        tags = [FakeTag(1, "Germany", "red")]

        @property
        def tag_ids(self):
            return [t.id for t in self.tags]

    host = BaseHost.model_validate(FakeHost())
    assert host.tags[0].color is HostTagColor.red
    assert host.tag_ids == [1]
