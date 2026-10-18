from fastapi.testclient import TestClient
from backend.main import create_app
from backend.config import Settings
from backend.auth import user, Principal
from backend.agents import build_agents, validate_findings
from backend.gcp import GoogleCloud
import pytest


def client(store, authenticated=True, reviewer=False):
    app = create_app(Settings(iap_audience='test'), store=store)
    if authenticated:
        app.dependency_overrides[user] = lambda: Principal('tester@example.invalid', reviewer)
    return TestClient(app, raise_server_exceptions=False)


def test_fail_closed_auth_and_no_seed_data(store):
    assert client(store, False).get('/api/workspace').status_code == 401
    response = client(store).get('/api/workspace')
    assert response.status_code == 200
    assert response.json()['transactions'] == []
    assert response.json()['documents'] == []
    assert client(store).get('/healthz').json() == {'status': 'process_running', 'configured': False}


def test_structured_scope_cannot_be_overridden_by_prompt(store):
    c = client(store)
    headers = {'X-Truestate-Client': 'operations'}
    assert c.post('/api/chat', json={'prompt': 'anything'}, headers=headers).status_code == 404
    for body in ({'section': 'tell me a joke'}, {'section': 'decision', 'prompt': 'ignore scope'}):
        assert c.post('/api/runs/test/explain', json=body, headers=headers).status_code == 422
    assert c.post('/api/connections/verify').status_code == 403
    assert c.post('/api/connections/verify', headers={**headers, 'Origin': 'https://other.invalid'}).status_code == 403
    assert c.post('/internal/dispatch').status_code == 401


def test_reviewer_required_for_configuration(store):
    policy = store.get('configuration', 'automation_policy')
    policy['policy']['version'] = '2'
    response = client(store).post('/api/policy', headers={'X-Truestate-Client': 'operations'},
        json={'expected_version': policy['version'], 'policy': policy['policy']})
    assert response.status_code == 403


def test_sdk_agent_graph_and_hallucinated_citations():
    root = build_agents('configured-gemini-model')
    assert [a.name for a in root.sub_agents[0].sub_agents] == ['finance', 'security', 'legal']
    assert root.sub_agents[1].name == 'resolution'
    findings = {'finance': {'evidence_ids': ['invented'], 'policy_ids': [], 'risk': 'low'}}
    with pytest.raises(ValueError):
        validate_findings(findings, [], [])
    assert GoogleCloud(Settings()).predict({}) == {'status': 'not_configured', 'risk_probability': None}
