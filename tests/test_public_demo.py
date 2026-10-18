import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from pydantic import ValidationError
from backend.config import Settings
from backend.main import create_app
from backend.sandbox import initialize, organization, reserve


def visitor(app):
    return TestClient(app, base_url='https://testserver', raise_server_exceptions=False)


def test_public_sandbox_isolates_visitors_and_allows_assessments(store, transaction):
    store.put('transaction', transaction['id'], transaction)
    app = create_app(Settings(public_demo=True, organization='synthetic-demo'), store=store)
    first, second = visitor(app), visitor(app)
    response = first.get('/api/workspace')
    assert response.status_code == 200
    assert response.json()['user'] == {'email': 'Sandbox visitor', 'reviewer': False, 'read_only': False}
    assert response.json()['sandbox']['enabled']
    assert 'Secure' in response.headers['set-cookie'] and 'HttpOnly' in response.headers['set-cookie']
    assert first.get('/api/workspace').json()['transactions'][0]['id'] == transaction['id']
    second.get('/api/workspace')
    headers = {'X-Truestate-Client': 'operations'}
    # Publication can be unavailable in this test; the durable outbox still accepts work.
    response = first.post('/api/transactions/test-tx/run', headers=headers)
    assert response.status_code == 200
    assert len(first.get('/api/workspace').json()['jobs']) == 1
    assert second.get('/api/workspace').json()['jobs'] == []
    assert store.jobs() == []  # shared seed organization is never changed
    assert first.post('/internal/dispatch').status_code == 401
    assert first.post('/api/transactions/test-tx/run', headers={**headers, 'Origin': 'https://other.invalid'}).status_code == 403
    report_id = response.json()['job_id']
    assert second.get('/api/runs/' + report_id).status_code == 404


def test_public_sandbox_accepts_uploads_without_leaking_documents(store):
    class Cloud:
        def put_object(self, key, content, mime):
            return {'object': key, 'generation': '1', 'content_sha256': 'test-hash'}
        def publish(self, *args):
            return 'test-message'
    app = create_app(Settings(public_demo=True, organization='synthetic-demo'), store=store, cloud=Cloud())
    first, second = visitor(app), visitor(app)
    first.get('/api/workspace'); second.get('/api/workspace')
    result = first.post('/api/documents', headers={'X-Truestate-Client': 'operations'},
        files={'file': ('test.txt', b'Synthetic invoice USD 100', 'text/plain')}, data={'purpose': 'evidence'})
    assert result.status_code == 200
    doc_id = result.json()['id']
    assert first.get('/api/documents/' + doc_id).status_code == 200
    assert second.get('/api/documents/' + doc_id).status_code == 404
    assert store.list('document') == []


def test_sandbox_budgets_are_durable_and_synthetic_actions_stay_disabled(store):
    scoped = initialize(store, organization('a' * 64), 'automation-policy.yaml')
    policy = scoped.get('configuration', 'automation_policy')['policy']
    assert policy['external_actions'] == 'disabled' and not policy['auto_clear']
    for _ in range(10):
        reserve(scoped, 'assessment')
    with pytest.raises(HTTPException) as error:
        reserve(scoped, 'assessment')
    assert error.value.status_code == 429
    # Recreating the Store cannot reset the daily count.
    recreated = initialize(store, scoped.org, 'automation-policy.yaml')
    with pytest.raises(HTTPException):
        reserve(recreated, 'assessment')


@pytest.mark.parametrize('values', [{'organization': 'production'}, {'organization': 'synthetic-demo', 'mode': 'worker'}])
def test_public_mode_cannot_open_production_or_worker(values):
    with pytest.raises(ValidationError):
        Settings(public_demo=True, **values)


def test_sandbox_policy_cannot_enable_real_actions(store):
    c = visitor(create_app(Settings(public_demo=True, organization='synthetic-demo'), store=store))
    data = c.get('/api/workspace').json()
    policy = data['policy']['policy']
    policy.update({'version': 'sandbox-test-2', 'external_actions': 'publish_requests'})
    result = c.post('/api/policy', headers={'X-Truestate-Client': 'operations'},
        json={'expected_version': data['policy']['version'], 'policy': policy})
    assert result.status_code == 403
    assert c.get('/api/workspace').json()['policy']['policy']['external_actions'] == 'disabled'


def test_worker_routes_sandbox_job_by_pubsub_organization(store, transaction, monkeypatch):
    import base64
    import json
    from backend import main
    from backend.sandbox import worker_organizations
    from backend.pipeline import Pipeline
    scoped = initialize(store, organization('b' * 64), 'automation-policy.yaml')
    scoped.put('transaction', transaction['id'], transaction)
    job_id = scoped.enqueue('investigate', transaction['id'])
    assert scoped.org in worker_organizations(store)
    seen = []
    async def execute(self, received):
        seen.append((self.store.org, self.cloud.s.organization, self.team.s.organization, received))
        return {'status': 'completed'}
    monkeypatch.setattr(main, 'service', lambda request, connectors=False: 'authorized-worker')
    monkeypatch.setattr(Pipeline, 'execute', execute)
    c = visitor(create_app(Settings(mode='worker', organization='synthetic-demo'), store=store))
    message = {'message': {'data': base64.b64encode(json.dumps({'job_id': job_id}).encode()).decode(),
                           'attributes': {'organization': scoped.org}}}
    assert c.post('/internal/pubsub', json=message).status_code == 200
    assert seen == [(scoped.org, scoped.org, scoped.org, job_id)]
    message['message']['attributes']['organization'] = 'production'
    assert c.post('/internal/pubsub', json=message).status_code == 400
