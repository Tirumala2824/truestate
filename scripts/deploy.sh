#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PROJECT_ID:?Set PROJECT_ID to your billing-enabled GCP project}"
: "${GEMINI_MODEL:?Set GEMINI_MODEL to an enabled model in your project}"
: "${REOPERATOR_EMAILS:?Set REOPERATOR_EMAILS to a comma-separated list of Google identities}"
REGION="${REGION:-us-central1}"
TF_STATE_BUCKET="${TF_STATE_BUCKET:-${PROJECT_ID}-truestate-tfstate}"
export PROJECT_ID GEMINI_MODEL REOPERATOR_EMAILS REGION
command -v gcloud >/dev/null
command -v terraform >/dev/null
command -v python3 >/dev/null
gcloud auth print-access-token >/dev/null
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com storage.googleapis.com iam.googleapis.com --project "$PROJECT_ID"
if ! gcloud storage buckets describe "gs://${TF_STATE_BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${TF_STATE_BUCKET}" --project "$PROJECT_ID" --location "$REGION" --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://${TF_STATE_BUCKET}" --versioning
terraform -chdir=infra/foundation init -backend-config="bucket=${TF_STATE_BUCKET}" -backend-config="prefix=foundation"
terraform -chdir=infra/foundation validate
terraform -chdir=infra/foundation apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}"
deploy_tmp="$(mktemp -d)"
trap 'rm -rf "$deploy_tmp"' EXIT
terraform -chdir=infra/foundation output -json configuration > "$deploy_tmp/foundation.json"
export TRUESTATE_DEPLOY_TMP="$deploy_tmp"
build_identity="$(python3 -c 'import json,os; print(json.load(open(os.environ["TRUESTATE_DEPLOY_TMP"]+"/foundation.json"))["build_email"])')"
build_bucket="$(python3 -c 'import json,os; print(json.load(open(os.environ["TRUESTATE_DEPLOY_TMP"]+"/foundation.json"))["build_bucket"])')"
image_tag="$(git rev-parse --short=12 HEAD)-$(date -u +%Y%m%d%H%M%S)"
export TRUESTATE_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/truestate/application:${image_tag}"
gcloud builds submit . --project "$PROJECT_ID" --region "$REGION" --tag "$TRUESTATE_IMAGE" \
  --service-account "projects/${PROJECT_ID}/serviceAccounts/${build_identity}" \
  --gcs-source-staging-dir "gs://${build_bucket}/source" --gcs-log-dir "gs://${build_bucket}/logs"
gcloud beta services identity create --service=iap.googleapis.com --project "$PROJECT_ID"
gcloud beta services identity create --service=pubsub.googleapis.com --project "$PROJECT_ID"
python3 - <<'PY'
import json,os
from pathlib import Path
p=Path(os.environ['TRUESTATE_DEPLOY_TMP'])
split=lambda k:[v.strip() for v in os.getenv(k,'').split(',') if v.strip()]
config={'foundation':json.loads((p/'foundation.json').read_text()),'image':os.environ['TRUESTATE_IMAGE'],
 'gemini_model':os.environ['GEMINI_MODEL'],'reoperator_emails':split('REOPERATOR_EMAILS'),
 'operator_emails':split('OPERATOR_EMAILS'),'source_connector_emails':split('SOURCE_CONNECTOR_EMAILS'),
 'prediction_endpoint':os.getenv('VERTEX_PREDICTION_ENDPOINT',''),
 'organization_id':os.getenv('ORGANIZATION_ID','default')}
(p/'runtime.tfvars.json').write_text(json.dumps(config))
PY
terraform -chdir=infra/runtime init -backend-config="bucket=${TF_STATE_BUCKET}" -backend-config="prefix=runtime"
terraform -chdir=infra/runtime validate
terraform -chdir=infra/runtime apply -var-file="$deploy_tmp/runtime.tfvars.json"
gcloud run jobs execute truestate-migrate --project "$PROJECT_ID" --region "$REGION" --wait
terraform -chdir=infra/runtime output app_url
printf '%s\n' 'Cloud Run deployment and schema migration completed. Open the URL and run connection verification.'
