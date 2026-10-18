from datetime import timedelta
import pytest
from backend.domain import provenance, authorize, AutomationPolicy, decision_current, utcnow
from backend.store import Conflict


def document(key, content, identity=None, parents=None):
    return {'id': key, 'content_sha256': content, 'source_attested': bool(identity),
        'source_identity': identity, 'parent_ids': parents or [], 'status': 'processed'}


def test_duplicate_content_and_identity_cannot_multiply_votes():
    docs = [document('a', 'same', 'one'), document('b', 'same', 'two'),
            document('c', 'different', 'one'), document('d', 'derived', 'three', ['a'])]
    result = provenance(docs)
    assert result['attested_origins'] == 2
    assert result['distinct_content_roots'] == 2
    assert result['groups']['d'] == ['same']
    assert provenance(docs[:2])['attested_origins'] == 1
    assert provenance([docs[0], docs[2]])['attested_origins'] == 1


def test_cycles_and_missing_parents_are_explicit():
    result = provenance([document('a', 'a', parents=['b']), document('b', 'b', parents=['a', 'missing'])])
    assert result['cycles'] and result['unresolved_parents'] == ['missing']
    assert result['distinct_content_roots'] == 0


def good_findings():
    return {k: {'risk': 'low', 'gaps': [], 'contradictions': [], 'confidence': .98} for k in ('finance', 'security', 'legal')}


def test_clearance_requires_complete_independent_evidence_and_prediction(transaction):
    policy = AutomationPolicy(version='1', auto_clear=True)
    evidence = provenance([document('a', 'a', 'one'), document('b', 'b', 'two')])
    resolution = {'disposition': 'ready', 'disagreements': []}
    def decide(prediction, ev=evidence, tx=transaction):
        return authorize(tx, ev, good_findings(), resolution, prediction, policy)['disposition']
    assert decide({'status': 'not_configured'}) == 'review'
    assert decide({'status': 'succeeded', 'risk_probability': .02}) == 'ready'
    assert decide({'status': 'succeeded', 'risk_probability': .99}) == 'review'
    assert decide({'status': 'succeeded', 'risk_probability': .02}, {**evidence, 'incomplete_documents': ['a']}) == 'needs_evidence'
    assert decide({'status': 'succeeded', 'risk_probability': .02}, tx={**transaction, 'previous_account_fingerprint': 'different'}) == 'review'


def test_precautionary_hold_needs_currency_limit(transaction):
    findings = good_findings(); findings['security']['risk'] = 'high'
    args = (transaction, provenance([]), findings, {'disposition': 'hold'}, {'status': 'not_configured'})
    assert authorize(*args, AutomationPolicy(version='1'))['disposition'] == 'needs_evidence'
    assert authorize(*args, AutomationPolicy(version='1', max_auto_hold_amount={'USD': '200'}))['disposition'] == 'hold'


def test_ingestion_is_atomic_and_idempotent(store, transaction):
    first = store.ingest([transaction], 'event-1', 'test')
    assert first['accepted'] == 1
    assert store.ingest([transaction], 'event-1', 'test')['duplicate']
    with pytest.raises(Conflict):
        store.ingest([{**transaction, 'amount': '120'}], 'event-1', 'test')
    with pytest.raises(ValueError):
        store.ingest([{**transaction, 'id': 'bad', 'document_ids': ['absent']}], 'event-2', 'test')
    assert store.get('transaction', 'bad') is None
    assert len(store.jobs()) == 1
    job = store.claim(first['jobs'][0])
    with pytest.raises(Conflict):
        store.claim(job['id'])
    store.finish_job(job['id'])
    assert store.claim(job['id']) is None


def setup_decision(store, transaction, publish=False):
    policy = store.get('configuration', 'automation_policy')
    if publish:
        policy['policy']['external_actions'] = 'publish_requests'
        store.put('configuration', policy['id'], policy, policy['version'])
    store.ingest([transaction], 'initial', 'test')
    state, refs, _ = store.bound_state(transaction['id'])
    decision = {'snapshot_hash': state, 'disposition': 'hold', 'expires_at': (utcnow()+timedelta(minutes=20)).isoformat()}
    result = store.save_decision(transaction['id'], decision, refs, publish=publish)
    return state, refs, result


def test_snapshot_cas_detects_new_policy_and_changed_evidence(store, transaction):
    state, refs, decision = setup_decision(store, transaction)
    store.put('knowledge', 'new-policy', {'active': True})
    with pytest.raises(Conflict):
        store.save_decision(transaction['id'], decision, refs)
    new_state, _, _ = store.bound_state(transaction['id'])
    assert new_state != state and not decision_current(decision, new_state)


def test_action_is_bound_to_decision_version_and_receipt(store, transaction):
    state, refs, prior = setup_decision(store, transaction, publish=True)
    request = store.list('action_request')[0]
    assert store.action_check(request['id'])['authorized']
    body = {'request_id': request['id'], 'transaction_id': transaction['id'], 'snapshot_hash': state,
            'status': 'executed', 'external_reference': 'test-external-ref'}
    with pytest.raises(Conflict):
        store.receipt(body, 'connector')
    store.put('action_request', request['id'], {**request, 'status': 'published'})
    receipt = store.receipt(body, 'connector')
    assert store.receipt(body, 'connector')['version'] == receipt['version']
    with pytest.raises(Conflict):
        store.receipt({**body, 'status': 'failed'}, 'connector')
    store.save_decision(transaction['id'], {**prior, 'disposition': 'ready'}, refs, expected_decision=prior['version'])
    assert not store.action_check(request['id'])['authorized']
    with pytest.raises(Conflict):
        store.save_decision(transaction['id'], prior, refs, expected_decision=prior['version'])


def test_expiry_and_ancestor_changes(store, transaction):
    root = document('root', 'root-content', 'connector')
    child = document('child', 'child-content', parents=['root'])
    store.put('document', 'root', root); store.put('document', 'child', child)
    state, refs, decision = setup_decision(store, {**transaction, 'document_ids': ['child']})
    assert store.affected('root') == [transaction['id']]
    store.put('document', 'root', {**root, 'source_identity': 'changed'})
    current, _, _ = store.bound_state(transaction['id'])
    assert not decision_current(decision, current)
    assert not decision_current({**decision, 'expires_at': (utcnow()-timedelta(seconds=1)).isoformat()}, state)
    events = store.events()
    assert events[0]['previous_hash'] == '0' * 64
    assert all(b['previous_hash'] == a['hash'] for a, b in zip(events, events[1:]))


def test_document_and_outbox_rollback_together(store, transaction):
    store.ingest([transaction], 'first', 'test')
    stale = store.get('transaction', transaction['id'])
    store.put('transaction', transaction['id'], {**stale, 'reference': 'changed'})
    with pytest.raises(Conflict):
        store.add_document('new-doc', document('new-doc', 'new'), stale, 'test')
    assert store.get('document', 'new-doc') is None
    assert not any(j['kind'] == 'document' for j in store.jobs())
