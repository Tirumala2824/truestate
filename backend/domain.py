"""Evidence-version binding and deterministic authorization, outside the LLM."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
import yaml
from pydantic import Field, field_validator
from .schemas import StrictModel


def utcnow():
    return datetime.now(timezone.utc)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


class AutomationPolicy(StrictModel):
    version: str = Field(min_length=1, max_length=100)
    auto_hold: bool = True
    auto_clear: bool = False
    max_auto_hold_amount: dict[str, Decimal] = Field(default_factory=dict)
    minimum_attested_origins: int = Field(default=2, ge=1)
    minimum_confidence: float = Field(default=0.9, ge=0, le=1)
    decision_ttl_minutes: int = Field(default=30, ge=1, le=1440)
    prediction_required_for_clear: bool = True
    prediction_high_risk_threshold: float = Field(default=0.8, ge=0, le=1)
    external_actions: Literal['disabled', 'publish_requests'] = 'disabled'

    @field_validator('max_auto_hold_amount')
    @classmethod
    def money_limits(cls, value):
        import re
        if any(not re.fullmatch('[A-Z]{3}', k) or not v.is_finite() or v <= 0 for k, v in value.items()):
            raise ValueError('Hold limits need three-letter uppercase currencies and positive finite amounts.')
        return value


def load_policy(path: str) -> AutomationPolicy:
    return AutomationPolicy.model_validate(yaml.safe_load(Path(path).read_text()))


def provenance(documents: list[dict]) -> dict:
    """Repeated content and declared ancestry never count as independent sources."""
    by_id = {d['id']: d for d in documents}
    unresolved, cycles = set(), set()

    def roots(doc_id, trail):
        if doc_id in trail:
            cycles.add(doc_id)
            return set()
        doc = by_id.get(doc_id)
        if not doc:
            unresolved.add(doc_id)
            return set()
        parents = doc.get('parent_ids', [])
        if parents:
            result = set()
            for parent in parents:
                result |= roots(parent, trail | {doc_id})
            return result
        return {doc.get('content_sha256', doc_id)}

    groups = {d['id']: sorted(roots(d['id'], set())) for d in documents}
    root_hashes = {r for group in groups.values() for r in group}
    # A trusted connector attests an origin; an upload is never promoted to trusted.
    # Maximum bipartite matching: one identity and one content root per vote.
    # Neither duplicate bytes signed by different connectors nor one connector
    # uploading different bytes can manufacture multiple independent origins.
    candidates = {}
    for d in documents:
        if d.get('source_attested') and not d.get('parent_ids') and d.get('source_identity'):
            candidates.setdefault(d['source_identity'], set()).add(d['content_sha256'])
    matched = {}
    def match(identity, visited):
        for root in sorted(candidates[identity]):
            if root in visited:
                continue
            visited.add(root)
            if root not in matched or match(matched[root], visited):
                matched[root] = identity
                return True
        return False
    for identity in sorted(candidates):
        match(identity, set())
    return {'document_count': len(documents), 'distinct_content_roots': len(root_hashes),
            'attested_origins': len(matched), 'groups': groups,
            'incomplete_documents': [d['id'] for d in documents if d.get('status') != 'processed' or d.get('truncated')],
            'unresolved_parents': sorted(unresolved), 'cycles': sorted(cycles),
            'independence_limit': 'Lineage and identity assertions do not prove document authenticity.'}


def snapshot(transaction: dict, documents: list[dict], policy: AutomationPolicy, knowledge: list[dict]):
    return digest({'transaction': transaction,
                   'documents': sorted([{'id': d['id'], 'version': d['version'],
                     'sha256': d['content_sha256'], 'parents': d.get('parent_ids', []),
                     'source': d.get('source_identity'), 'attested': d.get('source_attested', False)}
                     for d in documents], key=lambda d: d['id']),
                   'automation_policy': policy.model_dump(mode='json'),
                   'knowledge': sorted([{'id': p['id'], 'version': p['version']} for p in knowledge], key=lambda p: p['id'])})


def authorize(transaction, evidence, findings, resolution, prediction, policy: AutomationPolicy):
    reasons = []
    risk = [f['risk'] for f in findings.values()]
    incomplete = not findings or any(f['gaps'] or f['risk'] == 'unknown' for f in findings.values())
    conflicts = bool(resolution.get('disagreements')) or any(f['contradictions'] for f in findings.values())
    bank_change = bool(transaction.get('previous_account_fingerprint') and
                       transaction['account_fingerprint'] != transaction['previous_account_fingerprint'])
    limit = policy.max_auto_hold_amount.get(transaction['currency'])
    high = 'high' in risk or (prediction.get('status') == 'succeeded' and
                             prediction['risk_probability'] >= policy.prediction_high_risk_threshold)
    if high and policy.auto_hold and limit is not None and Decimal(str(transaction['amount'])) <= limit:
        disposition = 'hold'
        reasons.append('Risk findings meet the configured precautionary hold policy.')
    elif incomplete or evidence.get('incomplete_documents') or evidence['unresolved_parents'] or evidence['cycles'] or not evidence['document_count']:
        disposition = 'needs_evidence'
        reasons.append('Required evidence is missing, unresolved, or inconclusive.')
    elif conflicts:
        disposition = 'review'
        reasons.append('Contradictions or specialist disagreements need resolution.')
    elif (policy.auto_clear and not high and resolution['disposition'] == 'ready' and not bank_change and
          all(f['risk'] == 'low' and f['confidence'] >= policy.minimum_confidence for f in findings.values()) and
          evidence['attested_origins'] >= policy.minimum_attested_origins and
          (not policy.prediction_required_for_clear or prediction.get('status') == 'succeeded')):
        disposition = 'ready'
        reasons.append('All configured automatic-clearance conditions passed.')
    else:
        disposition = 'review'
        reasons.append('The current policy does not authorize automatic clearance for this evidence.')
    return {'disposition': disposition, 'reasons': reasons,
            'policy_version': policy.version,
            'expires_at': (utcnow() + timedelta(minutes=policy.decision_ttl_minutes)).isoformat(),
            'external_execution': 'not_executed'}


def decision_current(decision, current_hash):
    return (decision.get('snapshot_hash') == current_hash and
            datetime.fromisoformat(decision['expires_at']) > utcnow() and
            not decision.get('invalidated_at'))
