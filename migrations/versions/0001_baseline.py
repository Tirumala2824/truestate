"""Version the original application schema without depending on live ORM models."""
from alembic import op, context
import sqlalchemy as sa

revision = '0001_baseline'
down_revision = None
branch_labels = depends_on = None


def upgrade():
    op.create_table('records',
        sa.Column('org', sa.String(100), primary_key=True),
        sa.Column('kind', sa.String(40), primary_key=True),
        sa.Column('id', sa.String(150), primary_key=True),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('data', sa.JSON, nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org', sa.String(100), nullable=False),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('target', sa.String(150), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('attempts', sa.Integer, nullable=False),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('dispatched', sa.Boolean, nullable=False),
        sa.Column('error', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_jobs_org', 'jobs', ['org'])
    op.create_index('ix_jobs_status', 'jobs', ['status'])
    op.create_table('events',
        sa.Column('seq', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('org', sa.String(100), nullable=False),
        sa.Column('target', sa.String(150), nullable=False),
        sa.Column('kind', sa.String(60), nullable=False),
        sa.Column('actor', sa.String(250), nullable=False),
        sa.Column('data', sa.JSON, nullable=False),
        sa.Column('previous_hash', sa.String(64), nullable=False),
        sa.Column('hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_events_org', 'events', ['org'])
    op.create_index('ix_events_target', 'events', ['target'])
    op.create_table('inbox',
        sa.Column('org', sa.String(100), primary_key=True),
        sa.Column('id', sa.String(150), primary_key=True),
        sa.Column('hash', sa.String(64), nullable=False))


def downgrade():
    if not context.is_offline_mode():
        for table in ('records', 'jobs', 'events', 'inbox'):
            if op.get_bind().scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table} LIMIT 1)')):
                raise RuntimeError('Refusing to drop a populated schema. Restore or migrate data explicitly.')
    for table in ('inbox', 'events', 'jobs', 'records'):
        op.drop_table(table)
