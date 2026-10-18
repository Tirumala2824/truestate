"""Cookie-owned public sandboxes with durable, cross-instance usage limits."""
import re
import secrets
from contextvars import ContextVar
from hashlib import sha256
from fastapi import HTTPException
from sqlalchemy import select, text
from .domain import utcnow, load_policy
from .store import Store, Record, Job

COOKIE = 'truestate_sandbox'
SANDBOX = re.compile(r'^synthetic-sandbox-[a-f0-9]{64}$')
current_store = ContextVar('sandbox_store', default=None)
LIMITS = {'upload': (20, 100), 'assessment': (10, 100), 'explanation': (20, 200), 'session': (1, 200), 'model_run': (30, 300)}


def organization(token):
    return 'synthetic-sandbox-' + sha256(token.encode()).hexdigest()


def new_token():
    return secrets.token_hex(32)


def valid_token(token):
    return bool(re.fullmatch(r'[a-f0-9]{64}', token or ''))


def reserve(store, action, units=1):
    """Charge visitor and project-wide daily budgets in one locked transaction."""
    if not SANDBOX.fullmatch(store.org):
        return
    personal, shared = LIMITS[action]
    key = utcnow().date().isoformat() + ':' + action
    with store.sessions.begin() as session:
        scopes = sorted([(store.org, personal), ('synthetic-public-budget', shared)])
        if store.engine.dialect.name == 'postgresql':
            for org, _ in scopes:
                session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:org))'), {'org': org})
        rows = []
        for org, limit in scopes:
            row = session.get(Record, (org, 'sandbox_usage', key))
            used = row.data['used'] if row else 0
            if used + units > limit:
                raise HTTPException(429, f'Public sandbox daily {action} limit reached. Try again tomorrow.')
            rows.append((org, row, used))
        for org, row, used in rows:
            if row:
                row.data = {'used': used + units}
            else:
                session.add(Record(org=org, kind='sandbox_usage', id=key, version=1,
                                   data={'used': units}, updated_at=utcnow()))


def initialize(base, org, policy_path):
    scoped = Store(base.engine, org)
    if scoped.get('configuration', 'sandbox'):
        return scoped
    reserve(scoped, 'session')
    # The organization lock also prevents two first requests duplicating the setup.
    with scoped.session() as session:
        marker = scoped._row(session, 'configuration', 'sandbox')
        if marker:
            return scoped
        policy = load_policy(policy_path)
        policy.external_actions = 'disabled'
        policy.auto_clear = False
        scoped._put(session, 'configuration', 'automation_policy', {'policy': policy.model_dump(mode='json')})
        # Copy a small real subset of the seeded demo; never share writable records.
        rows = session.scalars(select(Record).where(Record.org == base.org, Record.kind == 'transaction')
                               .order_by(Record.id.desc()).limit(25)).all()
        for row in rows:
            scoped._put(session, 'transaction', row.id, {**row.data, 'document_ids': [], 'synthetic': True})
        scoped._put(session, 'configuration', 'sandbox', {'created_at': utcnow().isoformat(), 'sample_records': len(rows)})
    return scoped


def worker_organizations(base, limit=201):
    with base.session() as session:
        orgs = session.scalars(select(Job.org).where(Job.status.in_(['queued', 'running']))
                               .distinct().limit(limit)).all()
        indexing = session.scalars(select(Record.org).where(Record.kind == 'knowledge',
            Record.data['indexing']['status'].as_string() == 'submitted').distinct().limit(limit)).all()
    return [org for org in set(orgs + indexing) if org == base.org or SANDBOX.fullmatch(org)]
