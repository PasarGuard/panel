from random import randint
from uuid import uuid4

from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers, create_user, delete_user


def _digits_id() -> str:
    # Telegram-like numeric username, unique per test run
    return str(randint(1_000_000_000, 8_999_999_999))


def _search(access_token: str, search: str, **params) -> dict:
    response = client.get(
        "/api/users",
        headers=auth_headers(access_token),
        params={"search": search, "sort": "-created_at", **params},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()


def test_exact_username_comes_first_even_when_other_notes_mention_it(access_token):
    tg_id = _digits_id()
    created = [create_user(access_token, username=tg_id)["username"]]
    try:
        # Newer users whose notes mention the id (orders paid by this Telegram user) used to push it to the last page
        for _ in range(3):
            created.append(
                create_user(
                    access_token,
                    username=f"u_{uuid4().hex[:8]}",
                    payload={"note": f"order: robokassa_123, payer: telegram_{tg_id}"},
                )["username"]
            )

        data = _search(access_token, tg_id, limit=2)
        assert data["total"] == 4
        assert data["users"][0]["username"] == tg_id
    finally:
        for username in created:
            delete_user(access_token, username)


def test_search_pins_exact_and_keeps_chosen_sort_for_the_rest(access_token):
    base = uuid4().hex[:8]
    # The exact match is the oldest, so -created_at alone would put it last
    exact = create_user(access_token, username=base)["username"]
    prefix = create_user(access_token, username=f"{base}x")["username"]
    contains = create_user(access_token, username=f"x{base}")["username"]
    note_only = create_user(access_token, username=f"n{uuid4().hex[:8]}", payload={"note": f"see {base}"})["username"]
    try:
        data = _search(access_token, base)
        assert [user["username"] for user in data["users"]] == [exact, note_only, contains, prefix]
    finally:
        for username in (exact, note_only, contains, prefix):
            delete_user(access_token, username)


def test_underscore_and_percent_are_literal(access_token):
    base = uuid4().hex[:8]
    wanted = create_user(access_token, username=f"u_{base}")["username"]
    # "_" used to be a LIKE wildcard, so u_<id> also matched ua<id>
    lookalike = create_user(access_token, username=f"ua{base}")["username"]
    try:
        data = _search(access_token, wanted)
        assert [user["username"] for user in data["users"]] == [wanted]

        assert _search(access_token, f"%{base}")["total"] == 0
    finally:
        delete_user(access_token, wanted)
        delete_user(access_token, lookalike)


def test_search_ignores_surrounding_spaces(access_token):
    tg_id = _digits_id()
    create_user(access_token, username=tg_id)
    try:
        data = _search(access_token, f"  {tg_id} ")
        assert [user["username"] for user in data["users"]] == [tg_id]
    finally:
        delete_user(access_token, tg_id)


def test_simple_list_puts_exact_username_first(access_token):
    tg_id = _digits_id()
    created = [create_user(access_token, username=tg_id)["username"]]
    try:
        created.append(create_user(access_token, username=f"{tg_id}0")["username"])
        created.append(create_user(access_token, username=f"9{tg_id}")["username"])

        response = client.get(
            "/api/users/simple",
            headers=auth_headers(access_token),
            params={"search": tg_id, "sort": "-username"},
        )
        assert response.status_code == status.HTTP_200_OK
        usernames = [user["username"] for user in response.json()["users"]]
        # Only the exact username is pinned, the rest follow -username
        assert usernames == [tg_id, f"9{tg_id}", f"{tg_id}0"]
    finally:
        for username in created:
            delete_user(access_token, username)


def test_exact_username_ignores_case_and_same_case_wins(access_token):
    base = uuid4().hex[:8]
    # Older first, so -created_at alone would put the other-case username ahead
    upper = create_user(access_token, username=f"ABC{base}")["username"]
    lower = create_user(access_token, username=f"abc{base}")["username"]
    longer = create_user(access_token, username=f"abc{base}0")["username"]
    try:
        # A newer prefix match must not beat the exact username typed in another case
        assert _search(access_token, f"aBc{base}")["users"][0]["username"] in (lower, upper)
        assert [user["username"] for user in _search(access_token, upper)["users"]] == [upper, lower, longer]
    finally:
        for username in (lower, upper, longer):
            delete_user(access_token, username)


def test_underscore_in_note_is_literal(access_token):
    base = uuid4().hex[:8]
    noted = create_user(access_token, username=f"n{base}", payload={"note": f"payer xa{base}"})["username"]
    try:
        assert _search(access_token, f"x_{base}")["total"] == 0
    finally:
        delete_user(access_token, noted)


def test_relevance_sort_ranks_exact_then_prefix_then_contains_then_note(access_token):
    base = uuid4().hex[:8]
    # Created in reverse rank order, so newest-first alone would give the opposite of the expected order
    prefix = create_user(access_token, username=f"{base}x")["username"]
    contains = create_user(access_token, username=f"x{base}")["username"]
    note_only = create_user(access_token, username=f"n{uuid4().hex[:8]}", payload={"note": f"see {base}"})["username"]
    exact = create_user(access_token, username=base)["username"]
    try:
        data = _search(access_token, base, sort="relevance")
        assert [user["username"] for user in data["users"]] == [exact, prefix, contains, note_only]
        assert data["total"] == 4
    finally:
        for username in (exact, note_only, contains, prefix):
            delete_user(access_token, username)


def test_relevance_sort_is_newest_first_inside_a_group(access_token):
    base = uuid4().hex[:8]
    older = create_user(access_token, username=f"{base}a")["username"]
    newer = create_user(access_token, username=f"{base}b")["username"]
    try:
        data = _search(access_token, base, sort="relevance")
        assert [user["username"] for user in data["users"]] == [newer, older]
    finally:
        delete_user(access_token, older)
        delete_user(access_token, newer)


def test_relevance_sort_without_search_is_newest_first(access_token):
    first = create_user(access_token, username=f"r{uuid4().hex[:8]}")["username"]
    second = create_user(access_token, username=f"r{uuid4().hex[:8]}")["username"]
    try:
        response = client.get(
            "/api/users", headers=auth_headers(access_token), params={"sort": "relevance", "limit": 2}
        )
        assert response.status_code == status.HTTP_200_OK
        assert [user["username"] for user in response.json()["users"]] == [second, first]
    finally:
        delete_user(access_token, first)
        delete_user(access_token, second)


def test_relevance_with_another_sort_orders_inside_each_group(access_token):
    base = uuid4().hex[:8]
    # The newer prefix match sorts lower by -username, so newest-first inside the group would fail
    prefix_b = create_user(access_token, username=f"{base}b")["username"]
    prefix_a = create_user(access_token, username=f"{base}a")["username"]
    contains = create_user(access_token, username=f"x{base}")["username"]
    try:
        data = _search(access_token, base, sort="relevance,-username")
        assert [user["username"] for user in data["users"]] == [prefix_b, prefix_a, contains]
    finally:
        for username in (prefix_b, prefix_a, contains):
            delete_user(access_token, username)
