import pytest
from sqlalchemy import Column, literal_column
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql.mariadb import MariaDBDialect
from sqlalchemy.schema import CreateColumn

from app.db.compiles_types import (
    CaseSensitiveString,
    DateDiff,
    DaysDiff,
    ElapsedSeconds,
    WebAuthnBinary,
    WebAuthnChallenge,
    WebAuthnCredentialId,
)

MYSQL = mysql.dialect()
MARIADB = MariaDBDialect()


def test_a_mariadb_dialect_has_its_own_name():
    assert MARIADB.name == "mariadb"


def test_mariadb_renders_the_same_case_sensitive_column_as_mysql():
    column = Column("name", CaseSensitiveString(256))
    assert "COLLATE utf8mb4_bin" in str(CreateColumn(column).compile(dialect=MARIADB))
    assert str(CreateColumn(column).compile(dialect=MARIADB)) == str(CreateColumn(column).compile(dialect=MYSQL))


@pytest.mark.parametrize(
    "expression",
    [
        DaysDiff(literal_column("a")),
        DateDiff(literal_column("a"), literal_column("b")),
        ElapsedSeconds(literal_column("a"), literal_column("b")),
    ],
    ids=["DaysDiff", "DateDiff", "ElapsedSeconds"],
)
def test_the_date_helpers_compile_on_mariadb_as_they_do_on_mysql(expression):
    assert str(expression.compile(dialect=MARIADB)) == str(expression.compile(dialect=MYSQL))


@pytest.mark.parametrize(
    "column_type",
    [WebAuthnBinary(64), WebAuthnBinary(1024), WebAuthnCredentialId(), WebAuthnChallenge()],
    ids=["binary-small", "binary-large", "credential-id", "challenge"],
)
def test_the_webauthn_columns_use_the_mysql_types_on_mariadb(column_type):
    column = Column("value", column_type)
    assert str(CreateColumn(column).compile(dialect=MARIADB)) == str(CreateColumn(column).compile(dialect=MYSQL))
