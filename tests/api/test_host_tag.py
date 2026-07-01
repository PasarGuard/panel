"""API / e2e tests for host tags: CRUD, host assignment, and edge cases.

Runs against the configured test DB (SQLite by default; can target Postgres/MySQL
via TEST_FROM/DATABASE_URL), so it also exercises the migration + M2M cascade.
"""

from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers, create_core, delete_core, get_inbounds, unique_name

UNPROCESSABLE = 422


def _create_tag(token, *, name=None, color="red"):
    resp = client.post(
        "/api/host/tags",
        headers=auth_headers(token),
        json={"name": name or unique_name("tag"), "color": color},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()


def _delete_tag(token, tag_id):
    client.delete(f"/api/host/tags/{tag_id}", headers=auth_headers(token))


def _list_tags(token):
    resp = client.get("/api/host/tags", headers=auth_headers(token))
    assert resp.status_code == status.HTTP_200_OK
    return resp.json()


def _create_host(token, inbound, *, remark=None, tag_ids=None, priority=1):
    payload = {
        "remark": remark or unique_name("host"),
        "address": ["127.0.0.1"],
        "port": 443,
        "inbound_tag": inbound,
        "priority": priority,
    }
    if tag_ids is not None:
        payload["tag_ids"] = tag_ids
    return client.post("/api/host", headers=auth_headers(token), json=payload)


def _get_host(token, host_id):
    return client.get(f"/api/host/{host_id}", headers=auth_headers(token))


def _delete_host(token, host_id):
    client.delete(f"/api/host/{host_id}", headers=auth_headers(token))


def test_host_tag_crud(access_token):
    created = _create_tag(access_token, color="violet")
    tag_id = created["id"]
    try:
        assert isinstance(tag_id, int)
        assert created["color"] == "violet"
        assert any(t["id"] == tag_id for t in _list_tags(access_token))

        resp = client.put(
            f"/api/host/tags/{tag_id}",
            headers=auth_headers(access_token),
            json={"name": created["name"] + "-x", "color": "green"},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["color"] == "green"
        assert resp.json()["name"].endswith("-x")
    finally:
        resp = client.delete(f"/api/host/tags/{tag_id}", headers=auth_headers(access_token))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
    assert not any(t["id"] == tag_id for t in _list_tags(access_token))


def test_host_tag_duplicate_name_conflicts(access_token):
    tag = _create_tag(access_token)
    try:
        resp = client.post(
            "/api/host/tags",
            headers=auth_headers(access_token),
            json={"name": tag["name"], "color": "blue"},
        )
        assert resp.status_code == status.HTTP_409_CONFLICT
    finally:
        _delete_tag(access_token, tag["id"])


def test_host_tag_invalid_color_rejected(access_token):
    resp = client.post(
        "/api/host/tags", headers=auth_headers(access_token), json={"name": unique_name("t"), "color": "neon"}
    )
    assert resp.status_code == UNPROCESSABLE


def test_host_tag_blank_name_rejected(access_token):
    resp = client.post("/api/host/tags", headers=auth_headers(access_token), json={"name": "   ", "color": "red"})
    assert resp.status_code == UNPROCESSABLE


def test_host_tag_modify_missing_is_404(access_token):
    resp = client.put("/api/host/tags/99999999", headers=auth_headers(access_token), json={"color": "sky"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_host_tag_delete_missing_is_404(access_token):
    resp = client.delete("/api/host/tags/99999999", headers=auth_headers(access_token))
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_host_tag_rename_to_existing_conflicts(access_token):
    a = _create_tag(access_token)
    b = _create_tag(access_token)
    try:
        resp = client.put(f"/api/host/tags/{b['id']}", headers=auth_headers(access_token), json={"name": a["name"]})
        assert resp.status_code == status.HTTP_409_CONFLICT
    finally:
        _delete_tag(access_token, a["id"])
        _delete_tag(access_token, b["id"])


def test_host_create_with_tags(access_token):
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    t1 = _create_tag(access_token, color="red")
    t2 = _create_tag(access_token, color="amber")
    host_id = None
    try:
        resp = _create_host(access_token, inbound, tag_ids=[t1["id"], t2["id"]])
        assert resp.status_code == status.HTTP_201_CREATED, resp.text
        body = resp.json()
        host_id = body["id"]
        assert body["tag_ids"] == [t1["id"], t2["id"]]
        assert [t["id"] for t in body["tags"]] == [t1["id"], t2["id"]]
        assert [t["color"] for t in body["tags"]] == ["red", "amber"]

        got = _get_host(access_token, host_id).json()
        assert {t["id"] for t in got["tags"]} == {t1["id"], t2["id"]}
    finally:
        if host_id:
            _delete_host(access_token, host_id)
        _delete_tag(access_token, t1["id"])
        _delete_tag(access_token, t2["id"])
        delete_core(access_token, core["id"])


def test_host_create_with_invalid_tag_id_is_404(access_token):
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    try:
        resp = _create_host(access_token, inbound, tag_ids=[99999999])
        assert resp.status_code == status.HTTP_404_NOT_FOUND
    finally:
        delete_core(access_token, core["id"])


def test_host_create_dedups_repeated_tag_ids(access_token):
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    tag = _create_tag(access_token)
    host_id = None
    try:
        resp = _create_host(access_token, inbound, tag_ids=[tag["id"], tag["id"], tag["id"]])
        assert resp.status_code == status.HTTP_201_CREATED, resp.text
        host_id = resp.json()["id"]
        assert resp.json()["tag_ids"] == [tag["id"]]
        assert len(resp.json()["tags"]) == 1
    finally:
        if host_id:
            _delete_host(access_token, host_id)
        _delete_tag(access_token, tag["id"])
        delete_core(access_token, core["id"])


def test_host_modify_tags(access_token):
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    t1 = _create_tag(access_token)
    t2 = _create_tag(access_token)
    host_id = None
    try:
        host_id = _create_host(access_token, inbound, tag_ids=[t1["id"]]).json()["id"]

        resp = client.put(
            f"/api/host/{host_id}",
            headers=auth_headers(access_token),
            json={
                "remark": unique_name("h"),
                "address": ["127.0.0.1"],
                "port": 443,
                "inbound_tag": inbound,
                "priority": 1,
                "tag_ids": [t2["id"]],
            },
        )
        assert resp.status_code == status.HTTP_200_OK, resp.text
        assert resp.json()["tag_ids"] == [t2["id"]]

        resp = client.put(
            f"/api/host/{host_id}",
            headers=auth_headers(access_token),
            json={
                "remark": unique_name("h"),
                "address": ["127.0.0.1"],
                "port": 443,
                "inbound_tag": inbound,
                "priority": 1,
                "tag_ids": [],
            },
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["tags"] == []
    finally:
        if host_id:
            _delete_host(access_token, host_id)
        _delete_tag(access_token, t1["id"])
        _delete_tag(access_token, t2["id"])
        delete_core(access_token, core["id"])


def test_delete_tag_detaches_from_host(access_token):
    """Deleting a tag must remove it from hosts (M2M cascade), not error or orphan."""
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    tag = _create_tag(access_token)
    host_id = _create_host(access_token, inbound, tag_ids=[tag["id"]]).json()["id"]
    try:
        resp = client.delete(f"/api/host/tags/{tag['id']}", headers=auth_headers(access_token))
        assert resp.status_code == status.HTTP_204_NO_CONTENT

        got = _get_host(access_token, host_id)
        assert got.status_code == status.HTTP_200_OK
        assert got.json()["tags"] == []
        assert got.json()["tag_ids"] == []
    finally:
        _delete_host(access_token, host_id)
        delete_core(access_token, core["id"])


def test_delete_host_keeps_tags(access_token):
    """Deleting a host must not delete the (reusable) tags."""
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    tag = _create_tag(access_token)
    host_id = _create_host(access_token, inbound, tag_ids=[tag["id"]]).json()["id"]
    try:
        _delete_host(access_token, host_id)
        assert any(t["id"] == tag["id"] for t in _list_tags(access_token))
    finally:
        _delete_tag(access_token, tag["id"])
        delete_core(access_token, core["id"])


def test_clone_host_carries_tags(access_token):
    """Mirrors the dashboard 'duplicate host' flow: a new host with the same tag_ids,
    sharing the same (reusable) tag entities."""
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    t1 = _create_tag(access_token)
    t2 = _create_tag(access_token)
    ids = []
    try:
        original = _create_host(access_token, inbound, tag_ids=[t1["id"], t2["id"]]).json()
        ids.append(original["id"])

        clone = _create_host(
            access_token, inbound, remark=original["remark"] + " (copy)", tag_ids=original["tag_ids"]
        ).json()
        ids.append(clone["id"])

        assert {t["id"] for t in clone["tags"]} == {t1["id"], t2["id"]}
        assert {t["id"] for t in original["tags"]} == {t["id"] for t in clone["tags"]}
    finally:
        for host_id in ids:
            _delete_host(access_token, host_id)
        _delete_tag(access_token, t1["id"])
        _delete_tag(access_token, t2["id"])
        delete_core(access_token, core["id"])


def test_bulk_modify_hosts_preserves_tags(access_token):
    """PUT /api/hosts (the drag-reorder path) must keep each host's tags."""
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    tag = _create_tag(access_token)
    host_id = None
    try:
        host = _create_host(access_token, inbound, tag_ids=[tag["id"]]).json()
        host_id = host["id"]

        resp = client.put(
            "/api/hosts",
            headers=auth_headers(access_token),
            json=[
                {
                    "id": host_id,
                    "remark": host["remark"],
                    "address": ["127.0.0.1"],
                    "port": 443,
                    "inbound_tag": inbound,
                    "priority": 7,
                    "tag_ids": host["tag_ids"],
                }
            ],
        )
        assert resp.status_code == status.HTTP_200_OK, resp.text

        updated = _get_host(access_token, host_id).json()
        assert updated["tag_ids"] == [tag["id"]]
    finally:
        if host_id:
            _delete_host(access_token, host_id)
        _delete_tag(access_token, tag["id"])
        delete_core(access_token, core["id"])


def test_bulk_delete_tagged_host_keeps_tag(access_token):
    """Bulk delete (a core DELETE) must remove the host + its tag links but keep the tag."""
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    tag = _create_tag(access_token)
    try:
        host_id = _create_host(access_token, inbound, tag_ids=[tag["id"]]).json()["id"]

        resp = client.post("/api/hosts/bulk/delete", headers=auth_headers(access_token), json={"ids": [host_id]})
        assert resp.status_code == status.HTTP_200_OK, resp.text

        assert _get_host(access_token, host_id).status_code == status.HTTP_404_NOT_FOUND
        assert any(t["id"] == tag["id"] for t in _list_tags(access_token))
    finally:
        _delete_tag(access_token, tag["id"])
        delete_core(access_token, core["id"])


def test_bulk_disable_enable_tagged_host(access_token):
    """Bulk disable/enable serializes each host (refresh + model_validate reads .tags) — must not
    error on a tagged host, and must not drop the tag."""
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    tag = _create_tag(access_token)
    host_id = None
    try:
        host_id = _create_host(access_token, inbound, tag_ids=[tag["id"]]).json()["id"]

        for path in ("/api/hosts/bulk/disable", "/api/hosts/bulk/enable"):
            resp = client.post(path, headers=auth_headers(access_token), json={"ids": [host_id]})
            assert resp.status_code == status.HTTP_200_OK, f"{path}: {resp.text}"

        assert _get_host(access_token, host_id).json()["tag_ids"] == [tag["id"]]
    finally:
        if host_id:
            _delete_host(access_token, host_id)
        _delete_tag(access_token, tag["id"])
        delete_core(access_token, core["id"])
