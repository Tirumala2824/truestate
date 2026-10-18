"""Exercise the deployed anonymous upload -> Pub/Sub -> Gemini -> report path."""
import http.cookiejar
import json
import sys
import time
import uuid
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError


def client():
    return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(opener, base, path, data=None, content_type=None, headers=None):
    headers = {'X-Truestate-Client': 'operations', 'Origin': base, **(headers or {})}
    if content_type:
        headers['Content-Type'] = content_type
    with opener.open(Request(base + path, data=data, headers=headers), timeout=90) as response:
        return json.load(response)


def multipart(fields, filename, mime, content):
    boundary = 'truestate-' + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + content + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts), 'multipart/form-data; boundary=' + boundary


def wait_for(check, label, seconds=600):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        result = check()
        if result:
            print(label + ': passed', flush=True)
            return result
        time.sleep(10)
    raise RuntimeError(label + ': timed out; inspect Cloud Run worker logs.')


def main():
    base = sys.argv[1].rstrip('/')
    first, other = client(), client()
    workspace = request(first, base, '/api/workspace')
    assert workspace['sandbox']['enabled'] and not workspace['user']['read_only']
    request(other, base, '/api/workspace')
    # Hand-built labelled PDF makes the test use actual Document AI OCR.
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.probe_document import probe_pdf
    body, mime = multipart({'purpose': 'evidence'}, 'synthetic-release-check.pdf', 'application/pdf', probe_pdf())
    uploaded = request(first, base, '/api/documents', body, mime)
    document_id = uploaded['id']
    def document_ready():
        doc = request(first, base, '/api/documents/' + document_id)
        jobs = request(first, base, '/api/workspace')['jobs']
        if any(job['target'] == document_id and job['status'] == 'failed' for job in jobs):
            raise RuntimeError('Document processing job failed; inspect Cloud Run worker logs.')
        return doc if doc.get('status') == 'processed' else None
    doc = wait_for(document_ready, 'Anonymous PDF upload and Document AI extraction')
    assert 'TRUESTATE' in doc['text'].upper()
    try:
        request(other, base, '/api/documents/' + document_id)
        raise AssertionError('A different visitor could read the uploaded document.')
    except HTTPError as error:
        assert error.code == 404
    target = 'sandbox-check-' + uuid.uuid4().hex[:12]
    csv = ('id,supplier_id,supplier_name,amount,currency,occurred_at,reference,account_fingerprint,document_ids\n'
           f'{target},release-check,SYNTHETIC RELEASE CHECK,100.00,USD,2026-01-01T00:00:00Z,TEST ONLY,test-account-0001,{document_id}\n').encode()
    body, mime = multipart({}, 'synthetic-check.csv', 'text/csv', csv)
    imported = request(first, base, '/api/transactions/import', body, mime, {'Idempotency-Key': target})
    assert imported['accepted'] == 1
    def completed_report():
        state = request(first, base, '/api/workspace')
        if any(job['target'] == target and job['status'] == 'failed' for job in state['jobs']):
            raise RuntimeError('Assessment job failed; inspect Cloud Run worker logs.')
        runs = [run for run in state['runs'] if run.get('transaction_id') == target]
        return request(first, base, '/api/runs/' + runs[0]['id']) if runs else None
    report = wait_for(completed_report, 'Anonymous transaction assessment with real Gemini agents')
    assert set(report['findings']) == {'finance', 'security', 'legal'}
    assert report['decision']['disposition'] in {'ready', 'hold', 'needs_evidence', 'review'}
    # Wait for finalization too: a saved report alone does not prove BigQuery publication.
    def finalized():
        state = request(first, base, '/api/workspace')
        return any(job['target'] == target and job['status'] == 'completed' for job in state['jobs'])
    wait_for(finalized, 'Worker completion and BigQuery analytics write')
    analytics = request(first, base, '/api/analytics')
    assert any(row['currency'] == 'USD' and int(row['transactions']) >= 1 for row in analytics['rows'])
    isolated = request(other, base, '/api/workspace')
    assert not any(tx['id'] == target for tx in isolated['transactions'])
    assert isolated['policy']['policy']['external_actions'] == 'disabled'
    print('Public sandbox release verified: upload, OCR, queue, agents, analytics and visitor isolation.', flush=True)


if __name__ == '__main__':
    main()
