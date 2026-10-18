import copy
import uuid
from contextlib import contextmanager
from datetime import timedelta, timezone
from sqlalchemy import (Column, String, Integer, DateTime, JSON, Text, Boolean,
                        UniqueConstraint, create_engine, select, func, text)
from sqlalchemy.orm import declarative_base, sessionmaker
from .domain import utcnow, digest, snapshot, AutomationPolicy, decision_current

Base = declarative_base()


class Record(Base):
    __tablename__ = 'records'
    org = Column(String(100), primary_key=True)
    kind = Column(String(40), primary_key=True)
    id = Column(String(150), primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    data = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class Job(Base):
    __tablename__ = 'jobs'
    id = Column(String(36), primary_key=True)
    org = Column(String(100), nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    target = Column(String(150), nullable=False)
    status = Column(String(30), nullable=False, default='queued', index=True)
    attempts = Column(Integer, nullable=False, default=0)
    lease_until = Column(DateTime(timezone=True))
    dispatched = Column(Boolean, nullable=False, default=False)
    error = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Event(Base):
    __tablename__ = 'events'
    seq = Column(Integer, primary_key=True, autoincrement=True)
    org = Column(String(100), nullable=False, index=True)
    target = Column(String(150), nullable=False, index=True)
    kind = Column(String(60), nullable=False)
    actor = Column(String(250), nullable=False)
    data = Column(JSON, nullable=False)
    previous_hash = Column(String(64), nullable=False)
    hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class Inbox(Base):
    __tablename__ = 'inbox'
    org = Column(String(100), primary_key=True)
    id = Column(String(150), primary_key=True)
    hash = Column(String(64), nullable=False)


class Conflict(Exception):
    pass


class Store:
    def __init__(self, engine, organization):
        self.engine, self.org = engine, organization
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        with self.sessions.begin() as s:
            # Short per-organization transactions serialize mutations and audit sequence.
            # Network/service calls are never made while this lock is held.
            if self.engine.dialect.name == 'postgresql':
                s.execute(text('SELECT pg_advisory_xact_lock(hashtext(:org))'), {'org': self.org})
            yield s

    def _row(self, s, kind, key, lock=False):
        query = select(Record).where(Record.org == self.org, Record.kind == kind, Record.id == key)
        return s.scalar(query.with_for_update() if lock else query)

    def _data(self, row):
        return None if row is None else {**copy.deepcopy(row.data), 'id': row.id,
                                        'version': row.version, 'updated_at': row.updated_at.isoformat()}

    def get(self, kind, key):
        with self.session() as s:
            return self._data(self._row(s, kind, key))

    def list(self, kind, limit=200):
        with self.session() as s:
            rows = s.scalars(select(Record).where(Record.org == self.org, Record.kind == kind)
                             .order_by(Record.updated_at.desc()).limit(limit))
            return [self._data(row) for row in rows]

    def add_document(self, doc_id, data, transaction, actor):
        with self.session() as s:
            self._put(s, 'document', doc_id, data)
            if transaction:
                tx = {**transaction, 'document_ids': list(dict.fromkeys(transaction.get('document_ids', []) + [doc_id]))}
                self._put(s, 'transaction', tx['id'], tx, transaction['version'])
                old = self._row(s, 'decision', tx['id'], True)
                if old:
                    old.data = {**old.data, 'invalidated_at': utcnow().isoformat(), 'invalidated_reason': 'Evidence attached'}
                    old.version += 1
            job_id = self._enqueue(s, 'document', doc_id)
            self._event(s, doc_id, 'document.queued', actor, {'job_id': job_id})
            return job_id

    def _bound_state(self, s, target):
        tx = self._data(self._row(s, 'transaction', target))
        pr = self._data(self._row(s, 'configuration', 'automation_policy'))
        if not tx or not pr:
            raise KeyError('Transaction or automation policy not found')
        todo, seen, docs = list(tx.get('document_ids', [])), set(), []
        while todo:
            key = todo.pop()
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > 100:
                raise Conflict('Evidence lineage exceeds the 100-document analysis limit.')
            doc = self._data(self._row(s, 'document', key))
            if not doc:
                raise Conflict('Referenced evidence is missing.')
            docs.append(doc)
            todo.extend(doc.get('parent_ids', []))
        knowledge = [self._data(r) for r in s.scalars(select(Record).where(Record.org == self.org, Record.kind == 'knowledge'))]
        policy = AutomationPolicy.model_validate(pr['policy'])
        refs = [('transaction', target, tx['version']), ('configuration', 'automation_policy', pr['version'])]
        refs += [('document', d['id'], d['version']) for d in docs]
        refs += [('knowledge', d['id'], d['version']) for d in knowledge]
        return snapshot(tx, docs, policy, knowledge), refs, policy

    def bound_state(self, target):
        with self.session() as s:
            return self._bound_state(s, target)

    def action_check(self, request_id):
        with self.session() as s:
            req = self._data(self._row(s, 'action_request', request_id))
            if not req:
                raise KeyError('Unknown action request')
            current_hash, _, policy = self._bound_state(s, req['transaction_id'])
            decision = self._data(self._row(s, 'decision', req['transaction_id']))
            authorized = bool(decision and policy.external_actions == 'publish_requests' and
                req['status'] in {'queued', 'published'} and decision['version'] == req['decision_version'] and
                decision_current(decision, current_hash) and current_hash == req['snapshot_hash'] and
                decision['disposition'] == req['disposition'] and decision['disposition'] in {'ready', 'hold'})
            return {'authorized': authorized, 'request': req, 'decision': decision, 'checked_at': utcnow().isoformat()}

    def receipt(self, body, caller):
        with self.session() as s:
            req = self._data(self._row(s, 'action_request', body['request_id']))
            if not req or req['status'] != 'published' or any(req[k] != body[k] for k in ('transaction_id', 'snapshot_hash')):
                raise Conflict('Receipt must match an existing published action request.')
            prior = self._data(self._row(s, 'receipt', body['request_id']))
            value = {**body, 'connector': caller}
            if prior:
                if any(prior.get(k) != v for k, v in value.items()):
                    raise Conflict('A different receipt already exists for this request.')
                return prior
            row = self._put(s, 'receipt', body['request_id'], {**value, 'received_at': utcnow().isoformat()})
            self._event(s, body['transaction_id'], 'action.receipt', caller, value)
            return self._data(row)

    def put(self, kind, key, data, expected=None, actor='system'):
        with self.session() as s:
            row = self._put(s, kind, key, data, expected)
            self._event(s, key, kind + '.updated', actor, {'version': row.version})
            return self._data(row)

    def _put(self, s, kind, key, data, expected=None):
        row = self._row(s, kind, key, True)
        if expected is not None and (row is None or row.version != expected):
            raise Conflict('Record changed; refresh before retrying.')
        body = {k: v for k, v in copy.deepcopy(data).items() if k not in {'id', 'version', 'updated_at'}}
        if row:
            row.data, row.version, row.updated_at = body, row.version + 1, utcnow()
        else:
            row = Record(org=self.org, kind=kind, id=key, version=1, data=body, updated_at=utcnow())
            s.add(row)
        s.flush()
        return row

    def _event(self, s, target, kind, actor, data):
        if self.engine.dialect.name == 'postgresql':
            s.execute(text('SELECT pg_advisory_xact_lock(hashtext(:org))'), {'org': self.org})
        previous = s.scalar(select(Event).where(Event.org == self.org).order_by(Event.seq.desc()).limit(1))
        previous_hash = previous.hash if previous else '0' * 64
        at = utcnow()
        value = {'target': target, 'kind': kind, 'actor': actor, 'data': data, 'at': at.isoformat()}
        event = Event(org=self.org, target=target, kind=kind, actor=actor, data=data,
                      previous_hash=previous_hash, hash=digest({'previous': previous_hash, **value}), created_at=at)
        s.add(event)
        s.flush()
        return event.seq

    def event(self, target, kind, data, actor='system'):
        with self.session() as s:
            return self._event(s, target, kind, actor, data)

    def events(self, after=0, target=None, limit=200):
        with self.session() as s:
            q = select(Event).where(Event.org == self.org, Event.seq > after)
            if target:
                q = q.where(Event.target == target)
            return [{'seq': e.seq, 'target': e.target, 'kind': e.kind, 'actor': e.actor,
                     'data': e.data, 'hash': e.hash, 'previous_hash': e.previous_hash,
                     'at': e.created_at.isoformat()} for e in s.scalars(q.order_by(Event.seq).limit(limit))]

    def _enqueue(self, s, kind, target):
        job = Job(id=str(uuid.uuid4()), org=self.org, kind=kind, target=target, status='queued',
                  attempts=0, dispatched=False, created_at=utcnow())
        s.add(job)
        s.flush()
        return job.id

    def enqueue(self, kind, target):
        with self.session() as s:
            return self._enqueue(s, kind, target)

    def ingest(self, transactions, event_id, actor):
        content_hash = digest(transactions)
        with self.session() as s:
            existing = s.get(Inbox, (self.org, event_id))
            if existing:
                if existing.hash != content_hash:
                    raise Conflict('Idempotency key was already used for different input.')
                return {'accepted': 0, 'duplicate': True, 'jobs': []}
            jobs = []
            for tx in transactions:
                for doc_id in tx.get('document_ids', []):
                    if not self._row(s, 'document', doc_id):
                        raise ValueError('Unknown document: ' + doc_id)
                prior = self._row(s, 'transaction', tx['id'])
                if prior and digest(prior.data) == digest({k: v for k, v in tx.items() if k != 'id'}):
                    continue
                self._put(s, 'transaction', tx['id'], tx)
                old = self._row(s, 'decision', tx['id'], True)
                if old:
                    old.data = {**old.data, 'invalidated_at': utcnow().isoformat(), 'invalidated_reason': 'Transaction changed'}
                    old.version += 1
                jobs.append(self._enqueue(s, 'investigate', tx['id']))
                self._event(s, tx['id'], 'transaction.ingested', actor, {'input_hash': digest(tx)})
            s.add(Inbox(org=self.org, id=event_id, hash=content_hash))
            return {'accepted': len(jobs), 'duplicate': False, 'jobs': jobs}

    def affected(self, doc_id=None):
        docs = {d['id']: d for d in self.list('document', None)}
        def includes(keys):
            seen, pending = set(), list(keys)
            while pending:
                key = pending.pop()
                if key == doc_id:
                    return True
                if key not in seen:
                    seen.add(key)
                    pending.extend(docs.get(key, {}).get('parent_ids', []))
            return False
        return [t['id'] for t in self.list('transaction', None)
                if doc_id is None or includes(t.get('document_ids', []))]

    def invalidate(self, target, reason):
        with self.session() as s:
            row = self._row(s, 'decision', target, True)
            if row:
                row.data = {**row.data, 'invalidated_at': utcnow().isoformat(), 'invalidated_reason': reason}
                row.version += 1
            self._event(s, target, 'decision.invalidated', 'system', {'reason': reason})
            return self._enqueue(s, 'investigate', target)

    def claim(self, job_id):
        with self.session() as s:
            job = s.scalar(select(Job).where(Job.org == self.org, Job.id == job_id).with_for_update())
            if not job:
                raise KeyError('Unknown job')
            if job.status in {'completed', 'failed'}:
                return None
            lease = job.lease_until
            if lease and lease.tzinfo is None:
                lease = lease.replace(tzinfo=timezone.utc)
            if job.status == 'running' and lease and lease > utcnow():
                raise Conflict('This job is already running.')
            other = s.scalar(select(Job).where(Job.org == self.org, Job.target == job.target,
                Job.kind == job.kind, Job.id != job.id, Job.status == 'running', Job.lease_until > utcnow()))
            if other:
                raise Conflict('Another job is processing this record.')
            job.status, job.attempts = 'running', job.attempts + 1
            job.lease_until = utcnow() + timedelta(minutes=9)
            return {'id': job.id, 'kind': job.kind, 'target': job.target, 'attempts': job.attempts}

    def finish_job(self, job_id, error=None):
        with self.session() as s:
            job = s.get(Job, job_id)
            if not job or job.org != self.org:
                raise KeyError('Unknown job')
            job.status = ('failed' if job.attempts >= 3 else 'queued') if error else 'completed'
            job.error, job.lease_until = error, None
            if error:
                job.dispatched = False

    def pending(self, limit=50):
        with self.session() as s:
            for job in s.scalars(select(Job).where(Job.org == self.org, Job.status == 'running', Job.lease_until < utcnow())):
                job.status, job.dispatched, job.lease_until = 'queued', False, None
            return [{'id': j.id, 'kind': j.kind, 'target': j.target} for j in
                    s.scalars(select(Job).where(Job.org == self.org, Job.status == 'queued',
                                                Job.dispatched.is_(False)).limit(limit))]

    def dispatched(self, job_id):
        with self.session() as s:
            job = s.get(Job, job_id)
            if job and job.org == self.org:
                job.dispatched = True

    def jobs(self, limit=100):
        with self.session() as s:
            return [{'id': j.id, 'kind': j.kind, 'target': j.target, 'status': j.status,
                     'attempts': j.attempts, 'error': j.error, 'created_at': j.created_at.isoformat()}
                    for j in s.scalars(select(Job).where(Job.org == self.org).order_by(Job.created_at.desc()).limit(limit))]

    def save_decision(self, target, value, input_versions, publish=False, report=None, expected_decision=None):
        with self.session() as s:
            current = {(r.id, r.version) for r in s.scalars(select(Record).where(
                Record.org == self.org, Record.kind == 'knowledge'))}
            expected_corpus = {(key, version) for kind, key, version in input_versions if kind == 'knowledge'}
            if current != expected_corpus:
                raise Conflict('Policy corpus changed during analysis.')
            for kind, key, expected in sorted(input_versions):
                row = self._row(s, kind, key, True)
                if row is None or row.version != expected:
                    raise Conflict('Evidence or policy changed during analysis; re-run required.')
            decision = self._put(s, 'decision', target, value, expected_decision)
            if report:
                self._put(s, 'run', report['run_id'], report)
            if publish and value['disposition'] in {'ready', 'hold'}:
                request_id = str(uuid.uuid4())
                self._put(s, 'action_request', request_id, {'transaction_id': target,
                    'snapshot_hash': value['snapshot_hash'], 'decision_version': decision.version,
                    'disposition': value['disposition'], 'expires_at': value['expires_at'], 'status': 'queued'})
                self._enqueue(s, 'action', request_id)
            self._event(s, target, 'decision.recorded', 'authorization_gateway', value)
            return self._data(decision)


def cloud_store(config):
    if not config.sql_instance or not config.sql_user:
        raise RuntimeError('Cloud SQL configuration is required.')
    from google.cloud.sql.connector import Connector, IPTypes
    connector = Connector(refresh_strategy='LAZY')
    def connect():
        return connector.connect(config.sql_instance, 'pg8000', user=config.sql_user,
                                 db=config.sql_database, enable_iam_auth=True,
                                 ip_type=IPTypes.PRIVATE if config.sql_private_ip else IPTypes.PUBLIC)
    engine = create_engine('postgresql+pg8000://', creator=connect, pool_size=3,
                           max_overflow=2, pool_pre_ping=True, pool_recycle=1800)
    store = Store(engine, config.organization)
    store.connector = connector
    return store
