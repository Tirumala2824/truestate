import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.config import Settings
from backend.main import create_app


def test_public_demo_opens_without_credentials_but_blocks_mutations(store):
    config = Settings(public_demo=True, organization='synthetic-demo')
    client = TestClient(create_app(config, store=store), raise_server_exceptions=False)
    response = client.get('/api/workspace')
    assert response.status_code == 200
    assert response.json()['user'] == {'email': 'Public visitor', 'reviewer': False, 'read_only': True}
    # A caller-supplied IAP header cannot elevate the public visitor.
    assert client.get('/api/workspace', headers={'x-goog-iap-jwt-assertion': 'forged'}).json()['user']['reviewer'] is False
    for path in ['/api/transactions/example/run', '/api/connections/verify']:
        response = client.post(path, headers={'X-Truestate-Client': 'operations'})
        assert response.status_code == 403
        assert 'read-only' in response.json()['detail']
    assert client.post('/internal/dispatch').status_code == 401
    # Anonymous access never reads the shared cross-organization analytics table.
    assert client.get('/api/analytics').json() == {'rows': [], 'source': 'Public synthetic workspace'}


@pytest.mark.parametrize('values', [
    {'organization': 'production'},
    {'organization': 'synthetic-demo', 'mode': 'worker'},
])
def test_public_mode_cannot_open_production_or_worker(values):
    with pytest.raises(ValidationError):
        Settings(public_demo=True, **values)
