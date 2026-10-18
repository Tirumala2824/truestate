#!/usr/bin/env bash
# Each release gate must succeed before the application/worker Terraform apply.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/deploy-config.py
REGION="${REGION:-us-central1}"
TF_STATE_BUCKET="${TF_STATE_BUCKET:-${PROJECT_ID}-truestate-tfstate}"
RELEASE_SHA="$(git rev-parse HEAD)"
export PROJECT_ID REGION RELEASE_SHA
command -v gcloud >/dev/null
command -v terraform >/dev/null
gcloud auth print-access-token >/dev/null
describe_build() {
  gcloud builds describe "$1" --project "$PROJECT_ID" --region "$REGION" \
    --format='json(id,status,statusDetail,failureInfo,warnings,timing,createTime,startTime,finishTime,serviceAccount,logsBucket,options.logging,options.pool)'
}
if [[ -n "${DIAGNOSTIC_BUILD_ID:-}" ]]; then
  if [[ ! "$DIAGNOSTIC_BUILD_ID" =~ ^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$ ]]; then
    printf '%s\n' 'Diagnostic build ID must be a Cloud Build UUID.' >&2
    exit 1
  fi
  describe_build "$DIAGNOSTIC_BUILD_ID"
  gcloud builds log "$DIAGNOSTIC_BUILD_ID" --project "$PROJECT_ID" --region "$REGION" || true
  project_number="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  printf '%s\n' 'Cloud Build service-agent project roles:'
  gcloud projects get-iam-policy "$PROJECT_ID" --flatten='bindings[].members' \
    --filter="bindings.members=serviceAccount:service-${project_number}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
    --format='table(bindings.role)'
  printf '%s\n' 'Dedicated build account project roles:'
  gcloud projects get-iam-policy "$PROJECT_ID" --flatten='bindings[].members' \
    --filter="bindings.members=serviceAccount:truestate-build@${PROJECT_ID}.iam.gserviceaccount.com" \
    --format='table(bindings.role)'
  printf '%s\n' 'Logs for the selected build:'
  gcloud logging read "resource.type=\"build\" AND resource.labels.build_id=\"${DIAGNOSTIC_BUILD_ID}\"" \
    --project "$PROJECT_ID" --freshness=24h --limit=30 --order=asc \
    --format='json(timestamp,severity,textPayload,jsonPayload.message,protoPayload.status)' || true
  for job_name in truestate-release-migrate truestate-seed truestate-release-verify; do
    printf 'Release job: %s\n' "$job_name"
    gcloud run jobs executions list --job "$job_name" --project "$PROJECT_ID" --region "$REGION" \
      --limit=1 --format='json(metadata.name,status.conditions,status.succeededCount,status.failedCount,status.runningCount,status.startTime,status.completionTime)' || true
    gcloud logging read "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${job_name}\" AND resource.labels.location=\"${REGION}\"" \
      --project "$PROJECT_ID" --freshness=1h --limit=12 --order=desc \
      --format='json(timestamp,severity,textPayload,jsonPayload.message)' || true
  done
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf '## Diagnostic check completed\n\n**This run did not deploy an application.**\n\nInspected Cloud Build `%s`. See the job logs for its status and diagnostics.\n' \
      "$DIAGNOSTIC_BUILD_ID" >> "$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi
release_tmp="$(mktemp -d)"
trap 'rm -rf "$release_tmp"' EXIT
export TRUESTATE_DEPLOY_TMP="$release_tmp"

apply_root() {
  local root="$1" vars="$2" prefix="$3"
  terraform -chdir="$root" init -input=false -backend-config="bucket=${TF_STATE_BUCKET}" -backend-config="prefix=${prefix}"
  terraform -chdir="$root" validate -no-color
  terraform -chdir="$root" plan -input=false -lock-timeout=300s -var-file="$vars" -out="$release_tmp/${prefix}.tfplan"
  terraform -chdir="$root" show -json "$release_tmp/${prefix}.tfplan" > "$release_tmp/${prefix}.plan.json"
  python3 scripts/check_terraform_plan.py "$release_tmp/${prefix}.plan.json"
  terraform -chdir="$root" apply -input=false -auto-approve "$release_tmp/${prefix}.tfplan"
}

gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com storage.googleapis.com iam.googleapis.com --project "$PROJECT_ID"
if ! gcloud storage buckets describe "gs://${TF_STATE_BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${TF_STATE_BUCKET}" --project "$PROJECT_ID" --location "$REGION" --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://${TF_STATE_BUCKET}" --versioning
python3 scripts/deploy-config.py "$release_tmp"
apply_root infra/foundation "$release_tmp/foundation.tfvars.json" foundation
terraform -chdir=infra/foundation output -json configuration > "$release_tmp/foundation.json"
build_identity="$(python3 -c 'import json,os; print(json.load(open(os.environ["TRUESTATE_DEPLOY_TMP"]+"/foundation.json"))["build_email"])')"
build_bucket="$(python3 -c 'import json,os; print(json.load(open(os.environ["TRUESTATE_DEPLOY_TMP"]+"/foundation.json"))["build_bucket"])')"
image_repository="${REGION}-docker.pkg.dev/${PROJECT_ID}/truestate/application"
build_id="$(gcloud builds submit . --project "$PROJECT_ID" --region "$REGION" --async --format='value(id)' \
  --timeout=1800s --tag "${image_repository}:${RELEASE_SHA}" \
  --service-account "projects/${PROJECT_ID}/serviceAccounts/${build_identity}" \
  --gcs-source-staging-dir "gs://${build_bucket}/source" --gcs-log-dir "gs://${build_bucket}/logs")"
gcloud builds log "$build_id" --project "$PROJECT_ID" --region "$REGION" --stream || true
build_status="$(gcloud builds describe "$build_id" --project "$PROJECT_ID" --region "$REGION" --format='value(status)')"
if [[ "$build_status" != SUCCESS ]]; then
  describe_build "$build_id"
  printf '%s\n' "Cloud Build did not succeed: ${build_status}" >&2
  exit 1
fi
image_digest="$(gcloud builds describe "$build_id" --project "$PROJECT_ID" --region "$REGION" --format='value(results.images[0].digest)')"
if [[ ! "$image_digest" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  printf '%s\n' 'Cloud Build returned no immutable image digest.' >&2
  exit 1
fi
export TRUESTATE_IMAGE="${image_repository}@${image_digest}"
gcloud beta services identity create --service=iap.googleapis.com --project "$PROJECT_ID"
gcloud beta services identity create --service=pubsub.googleapis.com --project "$PROJECT_ID"
python3 scripts/deploy-config.py "$release_tmp"
apply_root infra/jobs "$release_tmp/jobs.tfvars.json" jobs
# Managed backup and PITR are both available before the first migration runs.
gcloud sql backups create --instance truestate-postgres --project "$PROJECT_ID" --description "Before release ${RELEASE_SHA}" --quiet
# --wait propagates a failed job execution. Never deploy services after a failed gate.
gcloud run jobs execute truestate-release-migrate --project "$PROJECT_ID" --region "$REGION" --wait
gcloud run jobs execute truestate-seed --project "$PROJECT_ID" --region "$REGION" --wait
gcloud run jobs execute truestate-release-verify --project "$PROJECT_ID" --region "$REGION" --wait
apply_root infra/runtime "$release_tmp/runtime.tfvars.json" runtime
app_url="$(terraform -chdir=infra/runtime output -raw app_url)"
printf '%s\n' "Release ${RELEASE_SHA} deployed: ${app_url}"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    printf '## GCP deployment completed\n\n'
    printf -- '- Release: `%s`\n' "$RELEASE_SHA"
    printf -- '- Application: [%s](%s)\n' "$app_url" "$app_url"
    printf -- '- Alembic migration: passed\n- Synthetic transactions: **2,000,000 verified**\n'
    printf -- '- Runtime IAM, Gemini, Document AI, Search, BigQuery, private storage and Pub/Sub permission checks: passed\n'
    printf -- '- App and worker startup readiness: passed\n'
    printf '\nSign in with a configured Google identity. Human IAP login, connector execution and model quality still require acceptance testing.\n'
  } >> "$GITHUB_STEP_SUMMARY"
fi
