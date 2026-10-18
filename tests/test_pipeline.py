import asyncio
import json
from types import SimpleNamespace
import pytest
from backend.pipeline import Pipeline
from backend.domain import digest


class TestCloud:
    """Test-only boundary double. It never appears in application startup."""
    __test__ = False
    def __init__(self):
        self.objects, self.analytics, self.messages = {}, {}, []
        self.fail_analytics = True
    def search(self, query):
        return [{'id': 'policy'}]
    def predict(self, features):
        assert features['currency'] == 'USD'
        return {'status': 'not_configured', 'risk_probability': None}
    def put_object(self, key, data, mime):
        assert key not in self.objects or self.objects[key] == data
        self.objects[key] = data
        return {'object': key, 'generation': '1', 'content_sha256': digest(data.hex())}
    def write_analytics(self, tx, key, decision, prediction):
        if self.fail_analytics:
            self.fail_analytics = False
            raise TimeoutError('Test-only simulated boundary failure')
        self.analytics[key] = decision
    def publish(self, payload, action=False):
        self.messages.append((payload, action))
        return str(len(self.messages))


class TestTeam:
    __test__ = False
    s = SimpleNamespace(gemini_model='test-only-model')
    calls = 0
    async def run(self, run_id, context, emit):
        self.calls += 1
        await emit('agent.completed', {'agent': 'test-only-double'})
        finding = {'risk': 'low', 'confidence': .95, 'gaps': [], 'contradictions': [],
            'evidence_ids': ['evidence'], 'policy_ids': ['policy'], 'summary': 'Test fixture', 'obligations': []}
        return {k: finding for k in ('finance', 'security', 'legal')}, {
            'disposition': 'ready', 'disagreements': [], 'summary': 'Test fixture', 'evidence_ids': ['evidence'], 'next_steps': []}


@pytest.mark.parametrize('truncated_policy', [False, True])
def test_pipeline_resumes_committed_report_after_service_failure(store, transaction, truncated_policy):
    for key, purpose in [('evidence', 'evidence'), ('policy', 'policy')]:
        store.put('document', key, {'content_sha256': digest(key), 'status': 'processed',
            'purpose': purpose, 'filename': key + '.txt', 'text': ('x' * 25000 if truncated_policy and purpose == 'policy' else 'Test-only evidence'), 'parent_ids': []})
    store.put('knowledge', 'policy', {'active': True})
    job_id = store.ingest([{**transaction, 'document_ids': ['evidence']}], 'fixture-event', 'test')['jobs'][0]
    cloud, team = TestCloud(), TestTeam()
    pipeline = Pipeline(store, cloud, team)
    with pytest.raises(TimeoutError):
        asyncio.run(pipeline.execute(job_id))
    assert store.get('run', job_id)
    assert store.get('decision', transaction['id'])['disposition'] == ('needs_evidence' if truncated_policy else 'review')
    result = asyncio.run(pipeline.execute(job_id))
    assert result['status'] == 'completed' and team.calls == 1
    assert len(cloud.objects) == 1 and len(cloud.analytics) == 1
    assert asyncio.run(pipeline.execute(job_id))['status'] == 'already_finished'
    assert not store.list('action_request')
