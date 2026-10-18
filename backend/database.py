"""Administrative connections for release jobs, separate from runtime IAM access."""
import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from .config import settings


@contextmanager
def migration_engine():
    direct = os.getenv('MIGRATION_DATABASE_URL')
    connector = None
    if direct:
        if not direct.startswith(('postgresql://', 'postgresql+')):
            raise ValueError('MIGRATION_DATABASE_URL must be a PostgreSQL URL.')
        engine = create_engine(direct, pool_size=1, max_overflow=0, pool_pre_ping=True)
    else:
        from google.cloud.sql.connector import Connector, IPTypes
        s = settings()
        if not s.sql_instance:
            raise RuntimeError('INSTANCE_CONNECTION_NAME is required for Cloud SQL release jobs.')
        connector = Connector(refresh_strategy='LAZY')
        engine = create_engine('postgresql+pg8000://', creator=lambda: connector.connect(
            s.sql_instance, 'pg8000', user=os.environ['MIGRATION_DB_USER'],
            password=os.environ['MIGRATION_DB_PASSWORD'], db=s.sql_database,
            ip_type=IPTypes.PRIVATE if s.sql_private_ip else IPTypes.PUBLIC),
            pool_size=1, max_overflow=0, pool_pre_ping=True, pool_recycle=1800)
    try:
        yield engine
    finally:
        engine.dispose()
        if connector:
            connector.close()
