import pytest

from app.db.models import inbounds_groups_association, users_groups_association


@pytest.mark.parametrize(
    ("table", "index_name", "columns"),
    [
        (
            inbounds_groups_association,
            "ix_inbounds_groups_association_group_id_inbound_id",
            ("group_id", "inbound_id"),
        ),
        (
            users_groups_association,
            "ix_users_groups_association_groups_id_user_id",
            ("groups_id", "user_id"),
        ),
    ],
)
def test_group_associations_have_covering_reverse_indexes(table, index_name, columns):
    index = next((candidate for candidate in table.indexes if candidate.name == index_name), None)

    assert index is not None
    assert tuple(column.name for column in index.columns) == columns
