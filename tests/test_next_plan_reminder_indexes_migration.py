"""MySQL/MariaDB commit every DDL statement on its own, so the downgrade has to finish from any step it stopped at."""

import importlib.util
from pathlib import Path

import pytest


def _load_migration_module():
    path = Path("app/db/migrations/versions/e4b8a1c6d2f7_index_next_plans_and_reminders.py")
    spec = importlib.util.spec_from_file_location("next_plan_reminder_indexes_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Table:
    """One table as the downgrade sees it: is our index there, and under which name is the user_id FK."""

    def __init__(self, index: bool, fk: str | None):
        self.index = index
        self.fk = fk
        self.calls: list[str] = []


class _Op:
    def __init__(self, tables: dict[str, _Table], fail_at: str | None = None):
        self.tables = tables
        self.fail_at = fail_at

    def _step(self, table_name: str, call: str) -> _Table:
        if call == self.fail_at:
            raise RuntimeError("connection lost")
        table = self.tables[table_name]
        table.calls.append(call)
        return table

    def drop_constraint(self, name, table_name, type_):
        table = self._step(table_name, "drop_fk")
        assert table.fk == name and type_ == "foreignkey"
        table.fk = None

    def drop_index(self, name, table_name):
        table = self._step(table_name, "drop_index")
        assert table.index
        # MySQL refuses to drop the last index a foreign key needs
        assert table.fk is None
        table.index = False

    def create_foreign_key(self, name, table_name, referent, local_cols, remote_cols, ondelete):
        table = self._step(table_name, "create_fk")
        assert table.fk is None
        assert (referent, local_cols, remote_cols, ondelete) == ("users", ["user_id"], ["id"], "CASCADE")
        table.fk = name


def _patch(monkeypatch, module, op: _Op, mysql: bool = True):
    monkeypatch.setattr(module, "op", op)
    monkeypatch.setattr(module, "_is_mysql", lambda: mysql)
    monkeypatch.setattr(module, "_index_exists", lambda table_name, name, default=False: op.tables[table_name].index)
    monkeypatch.setattr(module, "_fk_name", lambda table_name, default: op.tables[table_name].fk)


def _tables(index: bool, fk: str | None) -> dict[str, _Table]:
    return {"next_plans": _Table(index, fk), "notification_reminders": _Table(index, fk)}


@pytest.mark.parametrize(
    ("index", "fk", "calls"),
    [
        pytest.param(True, "custom_fk", ["drop_fk", "drop_index", "create_fk"], id="not-started"),
        pytest.param(True, None, ["drop_index", "create_fk"], id="stopped-after-the-fk-was-dropped"),
        pytest.param(False, None, ["create_fk"], id="stopped-after-the-index-was-dropped"),
        pytest.param(False, "custom_fk", [], id="already-downgraded"),
    ],
)
def test_mysql_downgrade_finishes_from_any_step(monkeypatch, index, fk, calls):
    module = _load_migration_module()
    op = _Op(_tables(index, fk))
    _patch(monkeypatch, module, op)

    module.downgrade()

    expected_names = {table_name: fk_name for _, table_name, _, fk_name in module._INDEXES}
    for table_name, table in op.tables.items():
        assert table.calls == calls
        assert not table.index
        # The existing name is kept; a foreign key that was lost gets the expected one
        assert table.fk == (fk or expected_names[table_name])


@pytest.mark.parametrize("fail_at", ["drop_index", "create_fk"])
def test_mysql_downgrade_run_again_after_a_failure_restores_the_foreign_key(monkeypatch, fail_at):
    module = _load_migration_module()
    tables = _tables(True, "custom_fk")
    _patch(monkeypatch, module, _Op(tables, fail_at=fail_at))
    with pytest.raises(RuntimeError):
        module.downgrade()

    _patch(monkeypatch, module, _Op(tables))
    module.downgrade()

    for table in tables.values():
        assert not table.index
        assert table.fk is not None


def test_other_databases_only_drop_the_index(monkeypatch):
    module = _load_migration_module()
    op = _Op(_tables(True, None))
    _patch(monkeypatch, module, op, mysql=False)

    module.downgrade()
    module.downgrade()

    assert [table.calls for table in op.tables.values()] == [["drop_index"], ["drop_index"]]
