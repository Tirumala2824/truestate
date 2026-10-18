"""CI exercises the exact PostgreSQL path; it never substitutes SQLite for bulk load."""
import json
import os
import time
import uuid
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.exc import DBAPIError
from backend.migrate import alembic_config, upgrade_database, grant_runtime
from backend.seed import load_dataset, verify_dataset, DEFAULT_ROWS, DATASET
from backend.release_check import ready
from backend.store import Base, Store

pytestmark = pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Requires isolated PostgreSQL service; enabled in GitHub Actions')


@pytest.fixture
def pg():
    url = os.environ['TEST_DATABASE_URL']
    admin = create_engine(url)
    schema = 'test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, pool_size=3, max_overflow=0)

    @event.listens_for(engine, 'connect')
    def set_schema(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        dbapi_connection.commit()
        cursor.close()
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_upgrade_repeat_downgrade_and_metadata(pg):
    upgrade_database(pg)
    upgrade_database(pg)
    with pg.begin() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        command.downgrade(alembic_config(connection), 'base')
    assert set(inspect(pg).get_table_names()) == {'alembic_version'}
    upgrade_database(pg)
    store = Store(pg, 'test-org')
    store.put('configuration', 'test', {'test': True})
    for statement in ('UPDATE events SET actor=\'changed\'', 'DELETE FROM events'):
        with pytest.raises(DBAPIError, match='append-only'):
            with pg.begin() as connection:
                connection.execute(text(statement))


def test_legacy_create_all_schema_is_checked_before_adoption(pg):
    # Reconstruct the previous deployment schema, without stamping a newer revision.
    with pg.begin() as connection:
        command.upgrade(alembic_config(connection), '0001_baseline')
        connection.execute(text('DROP TABLE alembic_version'))
    store = Store(pg, 'test-org')
    store.put('transaction', 'preserved', {'amount': '7.00'})
    upgrade_database(pg)
    assert store.get('transaction', 'preserved')['amount'] == '7.00'


def test_schema_drift_is_not_silently_stamped(pg):
    with pg.begin() as connection:
        command.upgrade(alembic_config(connection), '0001_baseline')
        connection.execute(text('DROP TABLE alembic_version'))
        connection.execute(text('ALTER TABLE records ALTER COLUMN version DROP NOT NULL'))
    with pytest.raises(RuntimeError, match='definition differs'):
        upgrade_database(pg)
    assert 'alembic_version' not in inspect(pg).get_table_names()


def test_seed_commits_checkpoint_then_resumes_and_refuses_corruption(pg, monkeypatch):
    upgrade_database(pg)
    org = 'synthetic-resume'
    def interrupt(progress):
        if progress['completed_rows'] == 31:
            raise RuntimeError('Injected interruption after a committed batch')
    with pytest.raises(RuntimeError, match='Injected interruption'):
        load_dataset(pg, org, rows=123, batch_size=31, progress=interrupt)
    with pg.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM records WHERE kind='transaction'")) == 31
        assert connection.scalar(text('SELECT completed_rows FROM synthetic_loads')) == 31
    assert load_dataset(pg, org, rows=123, batch_size=31)['verified_rows'] == 123
    assert load_dataset(pg, org, rows=123, batch_size=31)['verified_rows'] == 123
    with pytest.raises(RuntimeError, match='different row count'):
        load_dataset(pg, org, rows=124)
    with pg.begin() as connection:
        assert connection.scalar(text('SELECT count(*) FROM jobs')) == 0
        connection.execute(text("UPDATE records SET data=json_build_object('synthetic', false) WHERE kind='transaction' AND id='syn-v1-0000000001'"))
    with pytest.raises(RuntimeError, match='Seed verification failed'):
        with pg.connect() as connection:
            verify_dataset(connection, org, 123)
    monkeypatch.setenv('SEED_ORGANIZATION_ID', org)
    with pytest.raises(RuntimeError, match='2,000,000-record'):
        ready(pg)


def test_second_loader_cannot_race_the_checkpoint(pg):
    upgrade_database(pg)
    org = 'synthetic-lock'
    with pg.connect() as connection:
        connection.execute(text('SELECT pg_advisory_lock(hashtextextended(:key, 0))'),
                           {'key': f'truestate.seed:{org}:{DATASET}'})
        connection.commit()
        try:
            with pytest.raises(RuntimeError, match='already running'):
                load_dataset(pg, org, rows=5)
        finally:
            connection.execute(text('SELECT pg_advisory_unlock_all()'))
            connection.commit()


@pytest.mark.skipif(os.getenv('RUN_SCALE_TEST') != '1', reason='Explicit 2-million-row CI scale gate')
def test_two_million_actual_postgres_rows_and_indexed_workspace(pg, monkeypatch):
    upgrade_database(pg)
    org = 'synthetic-scale'
    started = time.monotonic()
    result = load_dataset(pg, org)
    assert result['verified_rows'] == DEFAULT_ROWS
    # A repeated release verifies the dataset without duplicating it.
    assert load_dataset(pg, org)['verified_rows'] == DEFAULT_ROWS
    store = Store(pg, org)
    assert len(store.list('transaction')) == 200
    assert store.affected() == []  # a policy change must not queue 2 million untouched rows
    with pg.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM jobs')) == 0
        plan = connection.scalar(text("EXPLAIN (FORMAT JSON) SELECT * FROM records WHERE org=:org AND kind='transaction' ORDER BY updated_at DESC, id DESC LIMIT 200"), {'org': org})
        assert 'ix_records_org_kind_updated' in json.dumps(plan)
    monkeypatch.setenv('SEED_ORGANIZATION_ID', org)
    assert ready(pg)['status'] == 'ready'
    print(json.dumps({'scale_test': 'passed', 'verified_transactions': DEFAULT_ROWS,
                      'elapsed_seconds': round(time.monotonic() - started, 2)}))
