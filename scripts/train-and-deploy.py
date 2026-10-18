"""Explicit operator command: creates billable Vertex training and serving resources."""
import argparse
from google.cloud import aiplatform

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--project', required=True)
p.add_argument('--region', default='us-central1')
p.add_argument('--image', required=True)
p.add_argument('--bucket', required=True)
p.add_argument('--service-account', required=True)
p.add_argument('--table', required=True)
p.add_argument('--currency', required=True)
p.add_argument('--minimum-auc', type=float, required=True)
args = p.parse_args()
aiplatform.init(project=args.project, location=args.region, staging_bucket=args.bucket)
job = aiplatform.CustomContainerTrainingJob(display_name='truestate-risk-baseline',
    container_uri=args.image, command=['python', '-m', 'model.train'],
    model_serving_container_image_uri=args.image,
    model_serving_container_predict_route='/predict', model_serving_container_health_route='/health',
    model_serving_container_command=['uvicorn', 'model.server:app'],
    model_serving_container_args=['--host', '0.0.0.0', '--port', '8080'],
    model_serving_container_ports=[8080])
model = job.run(args=['--project', args.project, '--table', args.table, '--currency', args.currency,
    '--minimum-auc', str(args.minimum_auc)], replica_count=1, machine_type='n1-standard-4',
    service_account=args.service_account, model_display_name='truestate-risk-' + args.currency)
if model is None:
    raise RuntimeError('Training did not register a model.')
endpoint = model.deploy(machine_type='n1-standard-2', min_replica_count=1,
    max_replica_count=1, service_account=args.service_account)
print('Set VERTEX_PREDICTION_ENDPOINT and redeploy: ' + endpoint.resource_name)
