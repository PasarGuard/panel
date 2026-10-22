"""Deleted group/template ids are stripped from role allowlists under a row lock."""

import pytest

from app.db.crud import admin_role


class _CapturingSession:
    def __init__(self):
        self.statements = []

    async def flush(self):
        pass

    async def execute(self, statement):
        self.statements.append(statement)
        return self

    def scalars(self):
        return []


@pytest.mark.asyncio
async def test_allowlist_strip_locks_and_reloads_role_rows():
    # Two concurrent deletes must not both read the same allowlist: the later write would restore the id the
    # earlier one removed. The roles are read with FOR UPDATE and reloaded, so the second delete waits and sees
    # the first one's result.
    db = _CapturingSession()

    await admin_role.remove_ids_from_role_access(db, "allowed_group_ids", [7])

    (statement,) = db.statements
    assert statement._for_update_arg is not None
    assert statement.get_execution_options().get("populate_existing") is True


@pytest.mark.asyncio
async def test_allowlist_strip_without_ids_runs_no_query():
    db = _CapturingSession()

    await admin_role.remove_ids_from_role_access(db, "allowed_group_ids", [])

    assert db.statements == []
