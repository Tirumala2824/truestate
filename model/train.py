"""Train on an organization's adjudicated labels; never generate training records."""
import argparse
import io
import json
import os
import re
from datetime import datetime, timezone
import joblib
import numpy as np
from google.cloud import bigquery, storage
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

FEATURES = ['amount', 'account_changed', 'document_count', 'content_roots', 'attested_origins']


def train(rows, currency, minimum_auc):
    if len(rows) < 500:
        raise ValueError('At least 500 real, adjudicated records are required for this baseline.')
    rows = sorted(rows, key=lambda r: r['occurred_at'])
    cut = int(len(rows) * .8)
    cutoff = rows[cut]['occurred_at']
    first, holdout = [r for r in rows if r['occurred_at'] < cutoff], [r for r in rows if r['occurred_at'] >= cutoff]
    # Time-ordered evaluation on suppliers absent from training avoids identity leakage.
    held_suppliers = {r['supplier_id'] for r in holdout}
    first = [r for r in first if r['supplier_id'] not in held_suppliers]
    if len(first) < 300 or len(holdout) < 100:
        raise ValueError('Insufficient disjoint suppliers for the temporal holdout. Collect more labeled data.')
    def arrays(part):
        x = np.asarray([[r[k] for k in FEATURES] for r in part], dtype=float)
        y = np.asarray([r['label'] for r in part], dtype=int)
        if not np.isfinite(x).all() or (x < 0).any() or set(y) != {0, 1} or min(np.bincount(y)) < 20:
            raise ValueError('Each split needs finite nonnegative features and at least 20 examples of each label.')
        return x, y
    x, y = arrays(first)
    hx, hy = arrays(holdout)
    estimator = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
    estimator.fit(x, y)
    probability = estimator.predict_proba(hx)[:, 1]
    metrics = {'roc_auc': float(roc_auc_score(hy, probability)),
        'average_precision': float(average_precision_score(hy, probability)),
        'brier_score': float(brier_score_loss(hy, probability)),
        'train_rows': len(first), 'holdout_rows': len(holdout),
        'holdout_positive_rate': float(hy.mean()), 'currency': currency,
        'cutoff': cutoff.isoformat(), 'evaluated_at': datetime.now(timezone.utc).isoformat(),
        'limitations': 'Baseline probabilities are not guaranteed calibrated. Historical labels can be biased.'}
    if metrics['roc_auc'] < minimum_auc:
        raise ValueError('Measured holdout ROC AUC does not meet the supplied deployment gate: ' + json.dumps(metrics))
    return {'estimator': estimator, 'features': FEATURES, 'currency': currency, 'metrics': metrics}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', required=True)
    p.add_argument('--table', required=True)
    p.add_argument('--currency', required=True)
    p.add_argument('--minimum-auc', type=float, required=True)
    args = p.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]+\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*', args.table):
        raise ValueError('Use a fully qualified BigQuery table name.')
    if not re.fullmatch('[A-Z]{3}', args.currency) or not .5 <= args.minimum_auc <= 1:
        raise ValueError('Supply an ISO currency and a minimum AUC between .5 and 1.')
    client = bigquery.Client(project=args.project)
    query = f"SELECT {','.join(FEATURES)},label,occurred_at,supplier_id FROM `{args.table}` WHERE currency=@currency ORDER BY occurred_at LIMIT 100001"
    rows = [dict(r) for r in client.query(query, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter('currency', 'STRING', args.currency)],
        maximum_bytes_billed=1_000_000_000)).result()]
    if len(rows) > 100000:
        raise ValueError('This baseline is capped at 100,000 records; use a dedicated training pipeline for larger datasets.')
    artifact = train(rows, args.currency, args.minimum_auc)
    uri = os.environ['AIP_MODEL_DIR']
    if not uri.startswith('gs://'):
        raise ValueError('Vertex AI must supply a Cloud Storage artifact directory.')
    bucket, prefix = uri[5:].split('/', 1)
    buffer = io.BytesIO()
    joblib.dump(artifact, buffer)
    cloud = storage.Client(project=args.project).bucket(bucket)
    cloud.blob(prefix.rstrip('/') + '/model.joblib').upload_from_string(buffer.getvalue())
    cloud.blob(prefix.rstrip('/') + '/evaluation.json').upload_from_string(json.dumps(artifact['metrics']), content_type='application/json')
    print(json.dumps(artifact['metrics']))


if __name__ == '__main__':
    main()
