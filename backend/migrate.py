"""Upgrade to Alembic head, verify it, grant runtime access and initialize policy."""
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from .config import settings
from .database import migration_engine
from .store import Base, Store
from .domain import load_policy

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '0001_baseline'
BASE_TABLES = {'records', 'jobs', 'events', 'inbox'}


def alembic_config(connection=None):
    config = Config(str(ROOT / 'alembic.ini'))
    if connection is not None:
        config.attributes['connection'] = connection
    return config


def validate_legacy_schema(connection):
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if not BASE_TABLES <= tables:
        raise RuntimeError('Partial legacy schema: refusing to stamp it as migrated.')
    for name in BASE_TABLES:
        expected = Base.metadata.tables[name]
        actual = {c['name']: c for c in inspector.get_columns(name)}
        if set(actual) != set(expected.columns.keys()):
            raise RuntimeError(f'Legacy schema columns differ: {name}')
        for column in expected.columns:
            found = actual[column.name]
            if (str(found['type'].compile(dialect=connection.dialect)) !=
                    str(column.type.compile(dialect=connection.dialect)) or
                    found['nullable'] != column.nullable):
                raise RuntimeError(f'Legacy column definition differs: {name}.{column.name}')
        if inspector.get_pk_constraint(name)['constrained_columns'] != [c.name for c in expected.primary_key]:
            raise RuntimeError(f'Legacy primary key differs: {name}')
        for index_name, columns in {
            'jobs': {'ix_jobs_org': ['org'], 'ix_jobs_status': ['status']},
            'events': {'ix_events_org': ['org'], 'ix_events_target': ['target']},
        }.get(name, {}).items():
            if not any(i['name'] == index_name and i['column_names'] == columns for i in inspector.get_indexes(name)):
                raise RuntimeError(f'Legacy index missing or changed: {index_name}')


def upgrade_database(engine):
    with engine.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '60s'"))
            connection.execute(text("SET LOCAL statement_timeout = '15min'"))
            connection.execute(text('SELECT pg_advisory_xact_lock(734830194)'))
        config = alembic_config(connection)
        tables = set(inspect(connection).get_table_names())
        if 'alembic_version' not in tables and BASE_TABLES & tables:
            validate_legacy_schema(connection)
            command.stamp(config, BASELINE)
        command.upgrade(config, 'head')
        current = MigrationContext.configure(connection).get_current_heads()
        if set(current) != set(ScriptDirectory.from_config(config).get_heads()):
            raise RuntimeError('Database did not reach the packaged Alembic head.')
        return list(current)


def grant_runtime(engine, sql_user):
    if not sql_user:
        raise RuntimeError('DB_IAM_USER is required before granting runtime access.')
    role = engine.dialect.identifier_preparer.quote(sql_user)
    with engine.begin() as connection:
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO {role}'))
        connection.execute(text(f'GRANT SELECT, INSERT, UPDATE ON records, jobs, inbox TO {role}'))
        connection.execute(text(f'GRANT SELECT, INSERT ON events TO {role}'))
        connection.execute(text(f'GRANT SELECT ON synthetic_loads, alembic_version TO {role}'))
        connection.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}'))


def initialize_policy(engine, organization):
    store = Store(engine, organization)
    if not store.get('configuration', 'automation_policy'):
        policy = load_policy(settings().policy_path)
        if organization.startswith('synthetic-'):
            policy.external_actions = 'disabled'
            policy.auto_clear = False
        store.put('configuration', 'automation_policy', {'policy': policy.model_dump(mode='json')}, actor='migration')


def main():
    s = settings()
    with migration_engine() as engine:
        revisions = upgrade_database(engine)
        grant_runtime(engine, s.sql_user)
        for org in {s.organization, os.getenv('SEED_ORGANIZATION_ID', 'synthetic-demo')}:
            initialize_policy(engine, org)
    print(f'Alembic upgrade verified: {revisions}. Runtime grants and policies are ready.')


if __name__ == '__main__':
    main()
