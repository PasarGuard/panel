from sqlalchemy import select
from sqlalchemy.dialects import mysql, postgresql, sqlite

from app.db.crud.user import _build_user_count_stmt, _build_user_sort_clauses
from app.db.models import Admin, User
from app.models.user import UserSortOption


def test_user_count_query_drops_page_ordering_and_wide_columns():
    page_stmt = select(User).order_by(*_build_user_sort_clauses([UserSortOption.desc_created_at]))
    count_stmt = _build_user_count_stmt(page_stmt)

    for dialect in (sqlite.dialect(), postgresql.dialect(), mysql.dialect()):
        sql = str(count_stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))

        assert "ORDER BY" not in sql
        assert "count(users.id)" in sql
        assert "users.proxy_settings" not in sql


def test_default_user_sort_has_stable_id_tiebreaker():
    stmt = select(User.id).order_by(*_build_user_sort_clauses([UserSortOption.desc_created_at]))
    sql = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))

    assert "ORDER BY users.created_at DESC, users.id DESC" in sql


def test_user_count_query_preserves_owner_join_and_filter():
    page_stmt = (
        select(User)
        .join(User.admin)
        .where(Admin.username.in_(["owner"]))
        .order_by(*_build_user_sort_clauses([UserSortOption.desc_created_at]))
    )
    sql = str(_build_user_count_stmt(page_stmt).compile(dialect=sqlite.dialect()))

    assert "JOIN admins" in sql
    assert "WHERE admins.username IN" in sql
    assert "ORDER BY" not in sql


def test_users_have_default_sort_index():
    index = next(
        (candidate for candidate in User.__table__.indexes if candidate.name == "idx_users_created_at_id"), None
    )

    assert index is not None
    assert tuple(column.name for column in index.columns) == ("created_at", "id")
