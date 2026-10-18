import asyncio
import json
from uuid import uuid4
from .domain import AutomationPolicy, authorize, snapshot, provenance, utcnow, decision_current
from .store import Conflict


class Pipeline:
    def __init__(self, store, cloud, team):
        self.store, self.cloud, self.team = store, cloud, team

    async def dispatch(self):
        count = 0
        for job in await asyncio.to_thread(self.store.pending):
            await asyncio.to_thread(self.cloud.publish, {'job_id': job['id']})
            await asyncio.to_thread(self.store.dispatched, job['id'])
            count += 1
        return count

    async def check_indexing(self):
        # Search indexing is asynchronous. Reassess automatically when a submitted
        # policy first becomes retrievable; creation alone never means searchable.
        records = await asyncio.to_thread(self.store.list, 'knowledge', None)
        for record in [r for r in records if r.get('active') and r.get('indexing', {}).get('status') == 'submitted'][:20]:
            matches = await asyncio.to_thread(self.cloud.search, record['filename'])
            if not any(m['id'] == record['id'] for m in matches):
                continue
            await asyncio.to_thread(self.store.put, 'knowledge', record['id'],
                {**record, 'indexing': {**record['indexing'], 'status': 'searchable'}}, record['version'])
            for target in await asyncio.to_thread(self.store.affected):
                await asyncio.to_thread(self.store.invalidate, target, 'Policy became searchable')

    async def execute(self, job_id):
        job = await asyncio.to_thread(self.store.claim, job_id)
        if job is None:
            return {'status': 'already_finished'}
        try:
            async with asyncio.timeout(480):
                if job['kind'] == 'document':
                    await self.process_document(job)
                elif job['kind'] == 'investigate':
                    await self.investigate(job)
                elif job['kind'] == 'action':
                    await self.publish_action(job)
                else:
                    raise ValueError('Unsupported job kind')
            await asyncio.to_thread(self.store.finish_job, job_id)
            return {'status': 'completed'}
        except Exception as exc:
            # Store an error classification; never put raw SDK messages or secrets into the UI.
            error = type(exc).__name__ + ': service operation did not complete; check Cloud Logging.'
            await asyncio.to_thread(self.store.event, job['target'], 'job.failed', {'job_id': job_id, 'error': error})
            await asyncio.to_thread(self.store.finish_job, job_id, error)
            raise

    async def publish_action(self, job):
        check = await asyncio.to_thread(self.store.action_check, job['target'])
        req = check['request']
        if not check['authorized']:
            await asyncio.to_thread(self.store.event, req['transaction_id'], 'action.skipped', {'request_id': req['id'], 'reason': 'Decision no longer authorizes this request'})
            return
        message_id = await asyncio.to_thread(self.cloud.publish, {'type': 'decision.requested',
            'request_id': req['id'], 'transaction_id': req['transaction_id'],
            'snapshot_hash': req['snapshot_hash'], 'disposition': req['disposition'],
            'decision_version': req['decision_version'], 'expires_at': req['expires_at']}, True)
        await asyncio.to_thread(self.store.put, 'action_request', req['id'], {**req, 'status': 'published', 'message_id': message_id})
        await asyncio.to_thread(self.store.event, req['transaction_id'], 'action.requested', {'message_id': message_id, 'request_id': req['id']})

    async def process_document(self, job):
        doc = await asyncio.to_thread(self.store.get, 'document', job['target'])
        if not doc:
            raise KeyError('Document does not exist')
        if doc['status'] != 'processed':
            data = await asyncio.to_thread(self.cloud.read_object, doc)
            result = await asyncio.to_thread(self.cloud.extract, data, doc['mime_type'])
            doc = await asyncio.to_thread(self.store.put, 'document', doc['id'],
                                         {**doc, **result, 'status': 'processed'}, doc['version'])
        if doc['purpose'] == 'policy' and not await asyncio.to_thread(self.store.get, 'knowledge', doc['id']):
            indexed = await asyncio.to_thread(self.cloud.index_policy, doc)
            await asyncio.to_thread(self.store.put, 'knowledge', doc['id'],
                {'document_id': doc['id'], 'active': True, 'indexing': indexed, 'filename': doc['filename']})
        targets = await asyncio.to_thread(self.store.affected, None if doc['purpose'] == 'policy' else doc['id'])
        for target in targets:
            await asyncio.to_thread(self.store.invalidate, target, 'Evidence or policy corpus changed')
        await asyncio.to_thread(self.store.event, doc['id'], 'document.processed', {'purpose': doc['purpose']})
        await self.dispatch()

    async def investigate(self, job):
        store, target, run_id = self.store, job['target'], job['id']
        saved = await asyncio.to_thread(store.get, 'run', run_id)
        if saved:
            await self.finalize(saved)
            return
        async def emit(kind, data):
            await asyncio.to_thread(store.event, target, kind, {'run_id': run_id, **data})
        await emit('investigation.started', {})
        tx = await asyncio.to_thread(store.get, 'transaction', target)
        if not tx:
            raise KeyError('Transaction does not exist')
        policy_record = await asyncio.to_thread(store.get, 'configuration', 'automation_policy')
        if not policy_record:
            raise RuntimeError('Automation policy has not been installed by the migration job.')
        policy = AutomationPolicy.model_validate(policy_record['policy'])
        documents = []
        pending = list(tx.get('document_ids', []))
        seen = set()
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > 100:
                raise Conflict('Evidence lineage exceeds the 100-document analysis limit.')
            doc = await asyncio.to_thread(store.get, 'document', key)
            if not doc:
                raise Conflict('Referenced evidence is missing.')
            documents.append(doc)
            pending += doc.get('parent_ids', [])
        lineage = provenance(documents)
        lineage['incomplete_documents'] = sorted(set(lineage['incomplete_documents']) | {d['id'] for d in documents if len(d.get('text', '')) > 24000})
        knowledge_records = await asyncio.to_thread(store.list, 'knowledge', None)
        active = {p['id']: p for p in knowledge_records if p.get('active')}
        await emit('retrieval.started', {'service': 'Vertex AI Search'})
        matches = await asyncio.to_thread(self.cloud.search,
            f"Supplier payment bank account change approval evidence {tx['supplier_name']} {tx['reference']}")
        policies = []
        for match in matches:
            if match['id'] in active:
                doc = await asyncio.to_thread(store.get, 'document', match['id'])
                if doc and doc['status'] == 'processed':
                    if doc.get('truncated') or len(doc['text']) > 24000:
                        lineage['incomplete_documents'].append(doc['id'])
                    policies.append({'id': doc['id'], 'title': doc['filename'], 'text': doc['text'][:24000]})
        # All active corpus versions are bound, including policies not retrieved for this query.
        versions = [('transaction', tx['id'], tx['version']),
                    ('configuration', 'automation_policy', policy_record['version'])]
        versions += [('document', d['id'], d['version']) for d in documents]
        versions += [('knowledge', p['id'], p['version']) for p in knowledge_records]
        bound_hash = snapshot(tx, documents, policy, knowledge_records)
        await emit('retrieval.completed', {'policies': len(policies), 'independent_content_roots': lineage['distinct_content_roots']})
        features = {'amount': float(tx['amount']), 'currency': tx['currency'],
                    'account_changed': int(bool(tx.get('previous_account_fingerprint') and
                        tx['account_fingerprint'] != tx['previous_account_fingerprint'])),
                    'document_count': len(documents), 'content_roots': lineage['distinct_content_roots'],
                    'attested_origins': lineage['attested_origins']}
        prediction = await asyncio.to_thread(self.cloud.predict, features)
        await emit('prediction.completed', prediction)
        evidence = [{'id': d['id'], 'title': d['filename'], 'status': d['status'],
                     'text': d.get('text', '')[:24000], 'source_attested': d.get('source_attested', False)}
                    for d in documents]
        context = {'transaction': tx, 'evidence': evidence, 'policies': policies,
                   'provenance': lineage, 'prediction': prediction}
        findings, resolution = await self.team.run(run_id, context, emit)
        decision = {**authorize(tx, lineage, findings, resolution, prediction, policy),
                    'snapshot_hash': bound_hash, 'transaction_version': tx['version'], 'run_id': run_id}
        # A new policy insert has no old row to lock, so compare the corpus again as well.
        current_knowledge = await asyncio.to_thread(store.list, 'knowledge', None)
        if [(k['id'], k['version']) for k in current_knowledge] != [(k['id'], k['version']) for k in knowledge_records]:
            raise Conflict('The policy corpus changed during analysis.')
        report = {'run_id': run_id, 'transaction_id': target, 'transaction': tx, 'snapshot_hash': bound_hash,
                  'decision': decision, 'findings': findings, 'resolution': resolution,
                  'provenance': lineage, 'prediction': prediction, 'evidence': evidence,
                  'policies': policies, 'created_at': utcnow().isoformat(),
                  'model': self.team.s.gemini_model}
        await asyncio.to_thread(store.save_decision, target, decision, versions,
                                policy.external_actions == 'publish_requests', report)
        report = await asyncio.to_thread(store.get, 'run', run_id)
        await self.finalize(report)

    async def finalize(self, report):
        store, run_id = self.store, report['run_id']
        target, bound_hash, decision = report['transaction_id'], report['snapshot_hash'], report['decision']
        tx = await asyncio.to_thread(store.get, 'transaction', target)
        policy_record = await asyncio.to_thread(store.get, 'configuration', 'automation_policy')
        policy = AutomationPolicy.model_validate(policy_record['policy'])
        capsule = await asyncio.to_thread(self.cloud.put_object,
            f'{store.org}/capsules/{run_id}/{bound_hash}.json', json.dumps(report, default=str).encode(), 'application/json')
        if not await asyncio.to_thread(store.get, 'capsule', run_id):
            await asyncio.to_thread(store.put, 'capsule', run_id, capsule)
        await asyncio.to_thread(self.cloud.write_analytics, report['transaction'],
                                run_id, decision, report['prediction'])
        await self.dispatch()
        await asyncio.to_thread(store.event, target, 'investigation.completed', {'run_id': run_id, 'decision': decision})
