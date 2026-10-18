"""Indexed workspace access, append-only audit protection and resumable seed state."""
from alembic import op, context
import sqlalchemy as sa

revision = '0002_synthetic_load'
down_revision = '0001_baseline'
branch_labels = depends_on = None


def upgrade():
    op.create_index('ix_records_org_kind_updated', 'records',
                    ['org', 'kind', sa.text('updated_at DESC'), sa.text('id DESC')])
    op.create_index('ix_events_org_seq', 'events', ['org', 'seq'])
    op.create_index('ix_jobs_org_status_dispatched', 'jobs', ['org', 'status', 'dispatched'])
    op.create_table('synthetic_loads',
        sa.Column('org', sa.String(100), primary_key=True),
        sa.Column('dataset_id', sa.String(40), primary_key=True),
        sa.Column('expected_rows', sa.Integer, nullable=False),
        sa.Column('completed_rows', sa.Integer, nullable=False),
        sa.Column('verified_rows', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True)))
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""CREATE OR REPLACE FUNCTION truestate_preserve_audit()
          RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Audit events are append-only'; END; $$""")
        op.execute('DROP TRIGGER IF EXISTS truestate_audit_immutable ON events')
        op.execute('''CREATE TRIGGER truestate_audit_immutable BEFORE UPDATE OR DELETE ON events
          FOR EACH ROW EXECUTE FUNCTION truestate_preserve_audit()''')


def downgrade():
    if not context.is_offline_mode() and op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM synthetic_loads LIMIT 1)')):
        raise RuntimeError('Refusing to remove populated synthetic-load history.')
    op.drop_table('synthetic_loads')
    op.drop_index('ix_jobs_org_status_dispatched', table_name='jobs')
    op.drop_index('ix_events_org_seq', table_name='events')
    op.drop_index('ix_records_org_kind_updated', table_name='records')
    # Preserve the audit trigger even when rolling back this index/manifest revision.
