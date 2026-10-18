"""Alembic owns schema changes. Credentials are supplied only at execution time."""
from logging.config import fileConfig
from alembic import context
from sqlalchemy import text
from backend.database import migration_engine
from backend.store import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata,
                      compare_type=True, compare_server_default=True)
    with context.begin_transaction():
        if connection.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(734830194)'))
        context.run_migrations()


if context.is_offline_mode():
    context.configure(dialect_name='postgresql', target_metadata=Base.metadata,
                      literal_binds=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()
else:
    connection = config.attributes.get('connection')
    if connection is not None:
        migrate(connection)
    else:
        with migration_engine() as engine, engine.begin() as connection:
            migrate(connection)
