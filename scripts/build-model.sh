#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
model_tag="$(git rev-parse --short=12 HEAD)-$(date -u +%Y%m%d%H%M%S)"
model_image="${REGION}-docker.pkg.dev/${PROJECT_ID}/truestate/risk-model:${model_tag}"
gcloud builds submit . --project "$PROJECT_ID" --region "$REGION" \
  --config model/cloudbuild.yaml --substitutions "_IMAGE=${model_image}" \
  --service-account "projects/${PROJECT_ID}/serviceAccounts/truestate-build@${PROJECT_ID}.iam.gserviceaccount.com" \
  --gcs-source-staging-dir "gs://${PROJECT_ID}-truestate-build/source" \
  --gcs-log-dir "gs://${PROJECT_ID}-truestate-build/logs"
printf 'MODEL_IMAGE=%s\n' "$model_image"
