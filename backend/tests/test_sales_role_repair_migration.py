"""064: every leftover CHECK that references sales_role is dropped before 054's is re-added."""

from pathlib import Path

SQL = (Path(__file__).resolve().parents[1] / "migrations" / "064_sales_role_repair.sql").read_text()


def test_drops_any_check_referencing_sales_role_before_readding():
    assert "pg_constraint" in SQL
    assert "contype = 'c'" in SQL
    assert "ILIKE '%sales_role%'" in SQL
    do_block = SQL.index("DO $$")
    readd = SQL.index("ADD CONSTRAINT company_members_sales_role_check")
    assert SQL.index("DROP CONSTRAINT IF EXISTS company_members_sales_role_check") < do_block < readd


def test_stays_idempotent():
    # The DO block only iterates what exists; the named drop uses IF EXISTS.
    assert "DROP CONSTRAINT IF EXISTS company_members_sales_role_check" in SQL
    assert SQL.count("ADD CONSTRAINT company_members_sales_role_check") == 1
