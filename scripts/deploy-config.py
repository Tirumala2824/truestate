"""Validate GitHub/Cloud Shell inputs and write Terraform JSON without shell interpolation."""
import json
import os
import re
import sys
from pathlib import Path


def inputs():
    env = os.environ
    required = ['PROJECT_ID', 'GEMINI_MODEL', 'REVIEWER_EMAILS']
    missing = [key for key in required if not env.get(key, '').strip()]
    if missing:
        raise ValueError('Set these GitHub repository variables: ' + ', '.join('GCP_PROJECT_ID' if k == 'PROJECT_ID' else k for k in missing))
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]', env['PROJECT_ID']):
        raise ValueError('GCP_PROJECT_ID must be a valid Google Cloud project ID, not the project number.')
    split = lambda key: [v.strip().lower() for v in env.get(key, '').split(',') if v.strip()]
    reviewers, operators, connectors = split('REVIEWER_EMAILS'), split('OPERATOR_EMAILS'), split('SOURCE_CONNECTOR_EMAILS')
    if not reviewers or any(not re.fullmatch(r'[^\s@,]+@[^\s@,]+\.[^\s@,]+', value) for value in reviewers + operators + connectors):
        raise ValueError('Supply comma-separated Google identity email addresses.')
    seed_org = env.get('SEED_ORGANIZATION_ID') or 'synthetic-demo'
    if not re.fullmatch(r'synthetic-[a-z0-9][a-z0-9-]{0,88}', seed_org):
        raise ValueError('SEED_ORGANIZATION_ID must use the reserved synthetic-* namespace.')
    org = env.get('ORGANIZATION_ID') or seed_org
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', org):
        raise ValueError('ORGANIZATION_ID must contain 1–100 letters, digits, underscores or hyphens.')
    return {'gemini_model': env['GEMINI_MODEL'], 'reviewer_emails': reviewers,
            'operator_emails': operators, 'source_connector_emails': connectors,
            'prediction_endpoint': env.get('VERTEX_PREDICTION_ENDPOINT', ''),
            'organization_id': org, 'seed_organization_id': seed_org}


def main():
    config = inputs()
    if len(sys.argv) == 1:
        print('Deployment inputs validated. Required seed count: 2,000,000.')
        return
    directory = Path(sys.argv[1])
    foundation = {'project_id': os.environ['PROJECT_ID'], 'region': os.getenv('REGION') or 'us-central1',
                  'document_location': os.getenv('DOCUMENT_AI_LOCATION') or 'us',
                  'search_location': os.getenv('SEARCH_LOCATION') or 'global',
                  'bigquery_location': os.getenv('BIGQUERY_LOCATION') or 'US',
                  'sql_tier': os.getenv('SQL_TIER') or 'db-custom-2-7680',
                  'sql_disk_size': int(os.getenv('SQL_DISK_SIZE_GB') or '50')}
    (directory / 'foundation.tfvars.json').write_text(json.dumps(foundation))
    if (directory / 'foundation.json').exists():
        config.update({'foundation': json.loads((directory / 'foundation.json').read_text()),
                       'image': os.environ['TRUESTATE_IMAGE'], 'release_sha': os.environ['RELEASE_SHA']})
        (directory / 'runtime.tfvars.json').write_text(json.dumps(config))
        jobs = {key: value for key, value in config.items() if key != 'operator_emails'}
        (directory / 'jobs.tfvars.json').write_text(json.dumps(jobs))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc))
