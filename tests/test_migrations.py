"""Fast offline/SQLite migration checks; PostgreSQL behavior is tested separately."""
from io import StringIO
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from backend.migrate import alembic_config, upgrade_database
from backend.seed import validate_options


def test_alembic_offline_script_includes_schema_indexes_and_immutable_audit():
    output = StringIO()
    config = alembic_config()
    config.output_buffer = output
    command.upgrade(config, 'head', sql=True)
    script = output.getvalue()
    assert 'CREATE TABLE records' in script
    assert 'CREATE TABLE synthetic_loads' in script
    assert 'CREATE TRIGGER truestate_audit_immutable' in script
    assert 'ix_records_org_kind_updated' in script
    assert '0002_synthetic_load' in script


def test_alembic_upgrades_empty_database_and_repeats_without_schema_changes():
    engine = create_engine('sqlite://')
    assert upgrade_database(engine) == ['0002_synthetic_load']
    assert upgrade_database(engine) == ['0002_synthetic_load']
    assert {'records', 'events', 'jobs', 'inbox', 'synthetic_loads', 'alembic_version'} <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_seed_rejects_real_organization_and_unbounded_batch():
    with pytest.raises(ValueError, match='synthetic-'):
        validate_options('production', 2_000_000, 10000)
    with pytest.raises(ValueError):
        validate_options('synthetic-demo', 2_000_001, 10000)
    with pytest.raises(ValueError):
        validate_options('synthetic-demo', 2_000_000, 20001)
