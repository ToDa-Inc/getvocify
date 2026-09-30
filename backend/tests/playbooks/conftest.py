"""Fixtures for the playbooks tests that need a real PostgreSQL (see pg_support.py for where it comes from)."""

from __future__ import annotations

import pytest

from tests.playbooks import pg_support

NO_PG = "No hay PostgreSQL aislado"


@pytest.fixture(scope="session")
def pg_cluster():
    cluster = pg_support.start_cluster()
    if cluster is None:
        pytest.skip(NO_PG)
    cluster.build_template()
    try:
        yield cluster
    finally:
        cluster.close()


@pytest.fixture
def pg_dsn(pg_cluster):
    """A fresh database with the playbooks schema (040, 055, 066_playbooks_v2)."""
    name = pg_cluster.create_database(template=pg_cluster.template)
    try:
        yield pg_cluster.dsn_for(name)
    finally:
        pg_cluster.drop_database(name)


@pytest.fixture
def pg_empty_dsn(pg_cluster):
    """A fresh, empty database (for tests that apply migrations themselves)."""
    name = pg_cluster.create_database()
    try:
        yield pg_cluster.dsn_for(name)
    finally:
        pg_cluster.drop_database(name)


@pytest.fixture
def pg(pg_dsn):
    return pg_support.PgClient(pg_dsn)
