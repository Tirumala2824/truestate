import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.store import Base, Store
from backend.domain import AutomationPolicy


@pytest.fixture
def store():
    # SQLite exists only in the isolated test harness, never as an application fallback.
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    result = Store(engine, 'test-org')
    result.put('configuration', 'automation_policy', {'policy': AutomationPolicy(version='test').model_dump(mode='json')})
    yield result
    engine.dispose()


@pytest.fixture
def transaction():
    return {'id': 'test-tx', 'supplier_id': 'test-supplier', 'supplier_name': 'Test fixture only',
            'amount': '100.00', 'currency': 'USD', 'occurred_at': '2026-01-01T00:00:00+00:00',
            'reference': '', 'account_fingerprint': 'test-hash', 'document_ids': []}
