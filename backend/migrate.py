"""Run once as the dedicated Cloud Run migration job; never at application startup."""
import os
from sqlalchemy import create_engine, text
from google.cloud.sql.connector import Connector
from .config import settings
from .store import Base, Store
from .domain import load_policy


def main():
    s = settings()
    with Connector(refresh_strategy='LAZY') as connector:
        engine = create_engine('postgresql+pg8000://', creator=lambda: connector.connect(
            s.sql_instance, 'pg8000', user=os.environ['MIGRATION_DB_USER'],
            password=os.environ['MIGRATION_DB_PASSWORD'], db=s.sql_database))
        Base.metadata.create_all(engine)
        # Quote the IAM login as an SQL identifier; it is never a raw SQL fragment.
        role = engine.dialect.identifier_preparer.quote(s.sql_user)
        with engine.begin() as connection:
            connection.execute(text(f'GRANT USAGE ON SCHEMA public TO {role}'))
            connection.execute(text(f'GRANT SELECT, INSERT, UPDATE ON records, jobs, inbox TO {role}'))
            connection.execute(text(f'GRANT SELECT, INSERT ON events TO {role}'))
            connection.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}'))
            connection.execute(text('''CREATE OR REPLACE FUNCTION truestate_preserve_audit()
              RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              RAISE EXCEPTION 'Audit events are append-only'; END; $$'''))
            connection.execute(text('DROP TRIGGER IF EXISTS truestate_audit_immutable ON events'))
            connection.execute(text('''CREATE TRIGGER truestate_audit_immutable BEFORE UPDATE OR DELETE ON events
              FOR EACH ROW EXECUTE FUNCTION truestate_preserve_audit()'''))
        store = Store(engine, s.organization)
        if not store.get('configuration', 'automation_policy'):
            policy = load_policy(s.policy_path)
            store.put('configuration', 'automation_policy', {'policy': policy.model_dump(mode='json')}, actor='migration')
        engine.dispose()
    print('Database schema and application grants are ready. No business data was inserted.')


if __name__ == '__main__':
    main()
