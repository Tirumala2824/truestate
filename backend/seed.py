"""Deterministic PostgreSQL bulk loader. No model calls, tasks, or invented findings.

Each batch and its checkpoint commit together. Interrupted runs resume; existing
records are never overwritten. The release requires exactly 2,000,000 verified
transaction rows in a reserved synthetic organization, plus small control records.
"""
import argparse
import json
import os
import re
from sqlalchemy import text
from .database import migration_engine
from .migrate import initialize_policy

DATASET = 'transactions-v1'
DEFAULT_ROWS = 2_000_000

INSERT_BATCH = text('''
INSERT INTO records (org, kind, id, version, data, updated_at)
SELECT :org, 'transaction', 'syn-v1-' || lpad(n::text, 10, '0'), 1,
 json_build_object(
   'supplier_id', 'synthetic-supplier-' || lpad((n % 20000)::text, 5, '0'),
   'supplier_name', 'Synthetic Supplier ' || lpad((n % 20000)::text, 5, '0'),
   'amount', ((100 + (n * 7919) % 4999900) / 100.0)::numeric(12,2)::text,
   'currency', (ARRAY['USD','INR','EUR','GBP'])[(n % 4 + 1)::int],
   'occurred_at', to_char(TIMESTAMPTZ '2025-01-01 00:00:00+00' + (n % 31536000) * INTERVAL '1 second',
                           'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
   'reference', 'SYNTHETIC / TEST ONLY / ' || n::text,
   'account_fingerprint', 'synthetic-' || md5('account-' || (n % 20000)::text),
   'previous_account_fingerprint', CASE WHEN n % 5 = 0 THEN 'synthetic-' || md5('old-account-' || (n % 20000)::text) ELSE NULL END,
   'document_ids', '[]'::json,
   'synthetic', true, 'dataset_id', CAST(:dataset AS text), 'seed_index', n),
 TIMESTAMPTZ '2025-01-01 00:00:00+00' + n * INTERVAL '1 second'
FROM generate_series(CAST(:start AS bigint), CAST(:end AS bigint)) AS n
ON CONFLICT (org, kind, id) DO NOTHING
''')


def validate_options(organization, rows, batch_size):
    if not re.fullmatch(r'synthetic-[a-z0-9][a-z0-9-]{0,88}', organization):
        raise ValueError('Seeding is restricted to a synthetic-* organization.')
    if not 1 <= rows <= DEFAULT_ROWS or not 1 <= batch_size <= 20000:
        raise ValueError('Use 1–2,000,000 rows and batches of 1–20,000.')


def verify_dataset(connection, organization, rows):
    manifest = connection.execute(text('SELECT * FROM synthetic_loads WHERE org=:org AND dataset_id=:dataset'),
        {'org': organization, 'dataset': DATASET}).mappings().one_or_none()
    if not manifest or manifest['expected_rows'] != rows or manifest['completed_rows'] != rows:
        raise RuntimeError('The synthetic-load checkpoint is incomplete or mismatched.')
    result = connection.execute(text('''
        SELECT count(*) AS total, count(*) FILTER (WHERE
          data->>'dataset_id' = :dataset AND data->>'synthetic' = 'true'
          AND json_typeof(data->'synthetic') = 'boolean'
          AND id = 'syn-v1-' || lpad(data->>'seed_index', 10, '0')
          AND id >= 'syn-v1-0000000000' AND id <= :last_id
          AND id ~ '^syn-v1-[0-9]{10}$'
          AND data->>'supplier_name' LIKE 'Synthetic Supplier %'
          AND data->>'reference' LIKE 'SYNTHETIC / TEST ONLY / %'
        ) AS valid
        FROM records WHERE org=:org AND kind='transaction' AND id LIKE 'syn-v1-%'
    '''), {'org': organization, 'dataset': DATASET, 'last_id': f'syn-v1-{rows-1:010d}'}).mappings().one()
    if result['total'] != rows or result['valid'] != rows:
        raise RuntimeError(f'Seed verification failed: expected {rows}; total={result["total"]}, valid={result["valid"]}.')
    return {'organization': organization, 'dataset_id': DATASET, 'expected_rows': rows,
            'verified_rows': result['valid'], 'synthetic': True}


def load_dataset(engine, organization='synthetic-demo', rows=DEFAULT_ROWS, batch_size=10000,
                 progress=None):
    validate_options(organization, rows, batch_size)
    if engine.dialect.name != 'postgresql':
        raise ValueError('The bulk loader requires PostgreSQL, matching Cloud SQL.')
    initialize_policy(engine, organization)
    with engine.connect() as connection:
        # A session lock spans batch commits; a second loader fails instead of racing.
        lock_key = f'truestate.seed:{organization}:{DATASET}'
        locked = connection.scalar(text('SELECT pg_try_advisory_lock(hashtextextended(:key, 0))'), {'key': lock_key})
        connection.commit()
        if not locked:
            raise RuntimeError('Another synthetic load is already running for this organization.')
        try:
            with connection.begin():
                connection.execute(text("SET TIME ZONE 'UTC'"))
                manifest = connection.execute(text('SELECT * FROM synthetic_loads WHERE org=:org AND dataset_id=:dataset'),
                    {'org': organization, 'dataset': DATASET}).mappings().one_or_none()
                if manifest is None:
                    if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM records WHERE org=:org AND kind='transaction')"), {'org': organization}):
                        raise RuntimeError('Refusing to seed an existing untracked transaction population.')
                    connection.execute(text('''INSERT INTO synthetic_loads
                        (org,dataset_id,expected_rows,completed_rows,verified_rows,status,started_at)
                        VALUES (:org,:dataset,:rows,0,0,'loading',CURRENT_TIMESTAMP)'''),
                        {'org': organization, 'dataset': DATASET, 'rows': rows})
                    completed = 0
                else:
                    if manifest['expected_rows'] != rows:
                        raise RuntimeError('This dataset was created with a different row count; use a different synthetic organization.')
                    completed = manifest['completed_rows']
            while completed < rows:
                end = min(completed + batch_size, rows)
                with connection.begin():
                    connection.execute(text("SET LOCAL statement_timeout = '5min'"))
                    connection.execute(INSERT_BATCH, {'org': organization, 'dataset': DATASET,
                                                     'start': completed, 'end': end - 1})
                    connection.execute(text('''UPDATE synthetic_loads SET completed_rows=:completed,
                        status='loading', verified_rows=0, verified_at=NULL
                        WHERE org=:org AND dataset_id=:dataset'''),
                        {'completed': end, 'org': organization, 'dataset': DATASET})
                completed = end
                if progress:
                    progress({'completed_rows': completed, 'expected_rows': rows})
            with connection.begin():
                connection.execute(text("UPDATE synthetic_loads SET status='verifying', verified_rows=0, verified_at=NULL WHERE org=:org AND dataset_id=:dataset"), {'org': organization, 'dataset': DATASET})
            with connection.begin():
                result = verify_dataset(connection, organization, rows)
                connection.execute(text('''UPDATE synthetic_loads SET status='verified',
                    verified_rows=:rows, verified_at=CURRENT_TIMESTAMP WHERE org=:org AND dataset_id=:dataset'''),
                    {'org': organization, 'dataset': DATASET, 'rows': rows})
            connection.execute(text('ANALYZE records'))
            connection.commit()
            return result
        finally:
            connection.rollback()
            connection.execute(text('SELECT pg_advisory_unlock(hashtextextended(:key, 0))'), {'key': lock_key})
            connection.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--organization', default=os.getenv('SEED_ORGANIZATION_ID', 'synthetic-demo'))
    parser.add_argument('--rows', type=int, default=DEFAULT_ROWS)
    parser.add_argument('--batch-size', type=int, default=int(os.getenv('SEED_BATCH_SIZE', '10000')))
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    validate_options(args.organization, args.rows, args.batch_size)
    with migration_engine() as engine:
        if args.verify_only:
            with engine.connect() as connection:
                result = verify_dataset(connection, args.organization, args.rows)
        else:
            result = load_dataset(engine, args.organization, args.rows, args.batch_size,
                                  lambda event: print(json.dumps(event), flush=True))
    print(json.dumps({'status': 'verified', **result}), flush=True)


if __name__ == '__main__':
    main()
