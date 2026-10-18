"""Release gate executed with the application's IAM service account."""
import json
import os
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from .config import settings
from .gcp import GoogleCloud
from .store import cloud_store
from .migrate import alembic_config
from .seed import verify_dataset, DEFAULT_ROWS


def ready(engine):
    with engine.connect() as connection:
        heads = MigrationContext.configure(connection).get_current_heads()
        expected = ScriptDirectory.from_config(alembic_config()).get_heads()
        if set(heads) != set(expected):
            raise RuntimeError('Database revision differs from this application release.')
        org = os.getenv('SEED_ORGANIZATION_ID')
        if org:
            manifest = connection.execute(text('SELECT status, verified_rows FROM synthetic_loads WHERE org=:org AND dataset_id=:dataset'),
                {'org': org, 'dataset': 'transactions-v1'}).mappings().one_or_none()
            if not manifest or manifest['status'] != 'verified' or manifest['verified_rows'] != DEFAULT_ROWS:
                raise RuntimeError('The required 2,000,000-record load has not passed verification.')
    return {'status': 'ready', 'release': os.getenv('RELEASE_SHA', 'development'), 'schema': list(heads)}


def probe_pdf():
    # A deliberately labelled one-page integration-test document, never business evidence.
    content = b'BT /F1 16 Tf 40 150 Td (TRUESTATE DEPLOYMENT CHECK) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream']
    document = bytearray(b'%PDF-1.4\n'); offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(document)); document += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(document)
    document += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]:
        document += f'{offset:010d} 00000 n \n'.encode()
    document += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return bytes(document)


def main():
    from google.genai import types
    s = settings()
    if s.missing():
        raise RuntimeError('Missing release configuration: ' + ', '.join(s.missing()))
    store = cloud_store(s)
    cloud = GoogleCloud(s)
    try:
        checks = {'database': ready(store.engine)}
        with store.engine.connect() as connection:
            checks['synthetic_data'] = verify_dataset(connection, os.environ['SEED_ORGANIZATION_ID'], DEFAULT_ROWS)
        probes = cloud.verify()
        failed = [name for name, result in probes.items() if result['status'] == 'error']
        if failed:
            raise RuntimeError('Service access check failed: ' + ', '.join(failed))
        checks['resource_access'] = probes
        result = cloud.genai.models.generate_content(model=s.gemini_model,
            contents='For a supplier-payment assessment without invoice evidence, respond only: NEEDS_EVIDENCE.',
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=1024))
        if not result.text:
            raise RuntimeError('Gemini returned no text during the release check.')
        checks['gemini_invocation'] = 'passed'
        extracted = cloud.extract(probe_pdf(), 'application/pdf')
        if 'TRUESTATE' not in extracted.get('text', '').upper():
            raise RuntimeError('Document AI did not extract the integration-test document.')
        checks['document_ai_invocation'] = 'passed'
        cloud.search('TRUESTATE deployment policy retrieval check')
        checks['search_invocation'] = 'passed'
        cloud.analytics()
        checks['bigquery_query'] = 'passed'
        payload = json.dumps({'purpose': 'release integration check', 'release': os.environ['RELEASE_SHA']}).encode()
        obj = cloud.put_object(f'release-checks/{os.environ["RELEASE_SHA"]}.json', payload, 'application/json')
        if cloud.read_object(obj) != payload:
            raise RuntimeError('Private object read/write check failed.')
        checks['storage_roundtrip'] = 'passed'
        permissions = cloud.publisher.test_iam_permissions(request={
            'resource': s.topic, 'permissions': ['pubsub.topics.publish']})
        if 'pubsub.topics.publish' not in permissions.permissions:
            raise RuntimeError('Runtime identity cannot publish workflow events.')
        checks['pubsub_publish_permission'] = 'passed'
        if s.prediction_endpoint:
            prediction = cloud.predict({'amount': 1.0, 'currency': 'USD', 'account_changed': 0,
                                        'document_count': 0, 'content_roots': 0, 'attested_origins': 0})
            if prediction['status'] != 'succeeded':
                raise RuntimeError('Configured prediction endpoint did not succeed.')
            checks['vertex_prediction_invocation'] = 'passed'
        else:
            checks['vertex_prediction_invocation'] = 'not_configured'
        store.put('configuration', 'release_verification', {'release': os.environ['RELEASE_SHA'], 'checks': checks}, actor='release_job')
        print(json.dumps({'status': 'verified', 'checks': checks}), flush=True)
    finally:
        store.engine.dispose()
        store.connector.close()


if __name__ == '__main__':
    main()
