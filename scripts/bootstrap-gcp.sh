#!/usr/bin/env bash
# One-time project-admin setup when using keyless GitHub authentication.
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID to your billing-enabled Google Cloud project}"
GITHUB_REPOSITORY_ID="${GITHUB_REPOSITORY_ID:-1424271600}"
GITHUB_OWNER_ID="${GITHUB_OWNER_ID:-93667512}"
GITHUB_REPOSITORY_NAME="${GITHUB_REPOSITORY_NAME:-Tirumala2824/truestate}"
DEPLOYER_EMAIL="truestate-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com serviceusage.googleapis.com --project "$PROJECT_ID"
if ! gcloud iam service-accounts describe "$DEPLOYER_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create truestate-deployer --display-name 'TRUESTATE GitHub infrastructure deployer' --project "$PROJECT_ID"
fi
roles=(roles/serviceusage.serviceUsageAdmin roles/resourcemanager.projectIamAdmin roles/iam.serviceAccountAdmin
  roles/iam.serviceAccountUser roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.admin
  roles/cloudsql.admin roles/storage.admin roles/secretmanager.admin roles/bigquery.admin roles/pubsub.admin
  roles/documentai.admin roles/discoveryengine.admin roles/cloudscheduler.admin roles/iap.admin roles/logging.viewer)
for role in "${roles[@]}"; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${DEPLOYER_EMAIL}" --role "$role" --condition=None --quiet >/dev/null
done
if ! gcloud iam workload-identity-pools describe truestate-github --location global --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create truestate-github --location global --project "$PROJECT_ID" --display-name 'TRUESTATE GitHub releases'
fi
provider_args=(--project "$PROJECT_ID" --location global --workload-identity-pool truestate-github
  --issuer-uri 'https://token.actions.githubusercontent.com'
  --attribute-mapping 'google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id'
  --attribute-condition "assertion.repository_id == '${GITHUB_REPOSITORY_ID}' && assertion.repository_owner_id == '${GITHUB_OWNER_ID}' && assertion.ref == 'refs/heads/main' && assertion.workflow_ref == '${GITHUB_REPOSITORY_NAME}/.github/workflows/deploy-gcp.yml@refs/heads/main'")
if gcloud iam workload-identity-pools providers describe github --project "$PROJECT_ID" --location global --workload-identity-pool truestate-github >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers update-oidc github "${provider_args[@]}"
else
  gcloud iam workload-identity-pools providers create-oidc github "${provider_args[@]}"
fi
project_number="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_EMAIL" --project "$PROJECT_ID" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${project_number}/locations/global/workloadIdentityPools/truestate-github/attribute.repository_id/${GITHUB_REPOSITORY_ID}" --quiet >/dev/null
printf 'GitHub variable GCP_PROJECT_ID=%s\n' "$PROJECT_ID"
printf 'GitHub variable GCP_SERVICE_ACCOUNT=%s\n' "$DEPLOYER_EMAIL"
printf 'GitHub variable GCP_WORKLOAD_IDENTITY_PROVIDER=projects/%s/locations/global/workloadIdentityPools/truestate-github/providers/github\n' "$project_number"
