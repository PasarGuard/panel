"""widen leftover PostgreSQL INTEGER sequences to BIGINT

Revision ID: 8e2f1a9c4b70
Revises: 7c4bd5128e62
Create Date: 2026-09-08 11:30:00.000000

ALTER COLUMN ... TYPE BIGINT does not change SERIAL/IDENTITY sequence types.
PostgreSQL INSERT ... ON CONFLICT still calls nextval(), so high-churn tables
like node_user_usages exhaust INTEGER sequences at 2147483647.
"""

from alembic import op
import sqlalchemy as sa


revision = "8e2f1a9c4b70"
down_revision = "7c4bd5128e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Idempotent: only sequences still typed as integer are touched.
    # Columns already BIGINT skip the table rewrite; only the sequence type changes.
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                rec RECORD;
            BEGIN
                FOR rec IN
                    SELECT
                        n.nspname AS schema_name,
                        s.relname AS sequence_name,
                        t.relname AS table_name,
                        a.attname AS column_name,
                        format_type(a.atttypid, a.atttypmod) AS column_type
                    FROM pg_class s
                    JOIN pg_namespace n ON n.oid = s.relnamespace
                    JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i')
                    JOIN pg_class t ON t.oid = d.refobjid
                    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
                    JOIN pg_sequence seq ON seq.seqrelid = s.oid
                    WHERE s.relkind = 'S'
                      AND n.nspname = current_schema()
                      AND seq.seqtypid = 'integer'::regtype
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                LOOP
                    IF rec.column_type NOT IN ('bigint', 'int8') THEN
                        EXECUTE format(
                            'ALTER TABLE %I.%I ALTER COLUMN %I TYPE BIGINT',
                            rec.schema_name,
                            rec.table_name,
                            rec.column_name
                        );
                    END IF;

                    EXECUTE format(
                        'ALTER SEQUENCE %I.%I AS bigint',
                        rec.schema_name,
                        rec.sequence_name
                    );
                END LOOP;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    # Values may already exceed INTEGER range; shrinking sequences is unsafe.
    pass
