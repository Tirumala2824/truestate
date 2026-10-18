# Deploy TRUESTATE from GitHub

The **Deploy GCP** workflow provisions GCP, builds an immutable application image, backs up Cloud SQL, upgrades Alembic, loads and verifies **2,000,000 synthetic transactions**, checks the runtime service identity and GCP APIs, and only then updates the app and worker. The final Cloud Run URL appears in the successful Actions run summary. No ZIP download or local build is required.

Source configuration is complete; a successful source test is not a live deployment. GitHub must first be given access to your billing-enabled GCP project. Variables alone do not establish that authorization.

## 1. Give GitHub access to GCP

Choose one authentication method. Never put credential JSON in a repository variable or commit it to the repository.

**Recommended: Workload Identity Federation.** If you already have a provider and deployment service account, use their values below. Otherwise run this once in Google Cloud Shell as a project administrator:

```bash
git clone https://github.com/Tirumala2824/truestate.git
cd truestate
export PROJECT_ID='YOUR_BILLING_ENABLED_PROJECT'
./scripts/bootstrap-gcp.sh
```

The script creates a deployment service account, assigns the infrastructure-management roles needed by Terraform, and prints the three GitHub variable values. Federation is restricted to this repository's numeric owner/repository IDs, `main`, and `.github/workflows/deploy-gcp.yml`. The deployment account is privileged; the application, event delivery, build and database migration use separate service accounts. Use a dedicated prototype project. A fork must supply its own `GITHUB_REPOSITORY_ID`, `GITHUB_OWNER_ID` and `GITHUB_REPOSITORY_NAME` when bootstrapping.

**Alternative: existing service-account credentials.** Put the complete service-account JSON in the GitHub repository **secret** `GCP_CREDENTIALS_JSON`, leaving the WIF variables empty. The service account needs the deployment permissions listed in `scripts/bootstrap-gcp.sh`. This path does not create missing permissions and cannot bypass a GCP organization policy that disables service-account keys. Prefer federation when available. If both methods are configured, federation is used.

## 2. Set GitHub repository variables

Go to **Settings → Secrets and variables → Actions → Variables**. Use repository variables so automatic deployment can read `DEPLOY_ENABLED` before a job starts. The workflow uses the GitHub environment named `gcp`; any protection rules you configure there still apply.

| Variable | Required? | Value |
|---|---|---|
| `GCP_PROJECT_ID` | Yes | Your billing-enabled project ID, not project number |
| `GEMINI_MODEL` | Yes | A Gemini model ID enabled in your selected Vertex AI region |
| `REVIEWER_EMAILS` | Yes | Comma-separated Google identities allowed to review decisions and policies |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | With federation | Full `projects/.../locations/global/workloadIdentityPools/.../providers/...` name |
| `GCP_SERVICE_ACCOUNT` | With federation | Deployment service-account email |
| `GCP_REGION` | Optional | Default `us-central1` |
| `DEPLOY_ENABLED` | Optional | Set to `true` to deploy future pushes to `main`; manual runs work without it |
| `ORGANIZATION_ID` | Optional | Default `synthetic-demo`, so the seeded records appear in the UI |
| `SEED_ORGANIZATION_ID` | Optional | Default `synthetic-demo`; must start with `synthetic-` |
| `OPERATOR_EMAILS` | Optional | Comma-separated Google identities with operations access |
| `SOURCE_CONNECTOR_EMAILS` | Optional | Comma-separated service-account emails for your source/execution connectors |
| `TF_STATE_BUCKET` | Optional | Default `<project-id>-truestate-tfstate`; must be globally unique |
| `DOCUMENT_AI_LOCATION` | Optional | Default `us` |
| `SEARCH_LOCATION` | Optional | Default `global` |
| `BIGQUERY_LOCATION` | Optional | Default `US` |
| `SQL_TIER` | Optional | Default `db-custom-2-7680` |
| `SQL_DISK_SIZE_GB` | Optional | Default `50`, automatic growth enabled |
| `VERTEX_PREDICTION_ENDPOINT` | Optional | Full resource name of your compatible trained Vertex endpoint |

Cloud SQL passwords are generated in GCP, stored in Secret Manager, and supplied only to the migration and seed jobs. You do not manually copy a database password into GitHub. Terraform state contains sensitive infrastructure values and stays in a private, versioned GCS bucket. Temporary GitHub authentication files are excluded from Git, Docker and Cloud Build uploads.

The supplied Cloud Run IAP setup uses the Google-managed OAuth client. Use identities supported by that configuration, normally identities in your Google Cloud organization. Access for external/personal Google identities needs the corresponding IAP OAuth setup by your Google Cloud administrator; do not disable IAP or expose the application to work around it.

## 3. Run the deployment

Open **Actions → Deploy GCP → Run workflow**, selecting `main`. Updating variables does not itself trigger a GitHub Actions run. After initial setup, `DEPLOY_ENABLED=true` also enables deployment on pushes to `main`.

The workflow runs these gates in order:

1. Validate the three Terraform roots, frontend build, application tests, PostgreSQL migrations, and a real 2-million-row load in the isolated CI database.
2. Authenticate to your GCP project and provision foundational services, identities and private Terraform state.
3. Build the exact checked-out source with Cloud Build. Use its immutable image digest for every job and service in the release.
4. Create/update the release jobs, then take a managed Cloud SQL backup.
5. Execute `truestate-release-migrate`: schema validation/adoption, `alembic upgrade head`, runtime grants and policy initialization.
6. Execute `truestate-seed`: bounded PostgreSQL batches, persisted checkpoints, full row verification, table statistics refresh.
7. Execute `truestate-release-verify` as the **runtime** service account: current Alembic head, exact dataset count, actual Gemini response, Document AI extraction, Search request, BigQuery query, private object roundtrip and Pub/Sub publish permission. If a Vertex prediction endpoint is supplied, invoke it as well.
8. Apply the application and worker configuration. `/readyz` rejects incompatible schemas or an unverified seed manifest, so an unready new revision does not pass startup.
9. Print the Cloud Run URL in the Actions summary.

The pipeline stops on a failed gate. Every saved Terraform plan is inspected before apply; automatic deployment rejects all resource deletions and replacements. Such changes need an explicit infrastructure migration. The Search data store also has `prevent_destroy` protection and explicitly declares Google's default digital parser to avoid replacement caused by refreshed API defaults. The current store ID is `truestate-policies-v2`; the original empty store ID entered Google's asynchronous deletion process during the initial deployment retry.

The pipeline does not apply application changes when migration, loading or pre-release checks fail. Infrastructure provisioned earlier in a failed run remains for diagnosis and retry; it is not automatically destroyed. Previously deployed services remain on their earlier release until the service-apply stage. Application and worker updates within that stage are not an atomic cross-service rollout; future migrations must remain compatible with the preceding release.

## Synthetic data behavior

The loader creates **2,000,000 transaction records**, plus a small policy/load-metadata footprint. Every generated transaction has a stable `syn-v1-...` ID, a synthetic marker, a fixed dataset/version identifier, fabricated supplier names, deterministic amounts/currencies/dates and synthetic account fingerprints. It contains no actual personal or financial data. Documents, approvals, model conclusions, execution receipts and savings are not fabricated.

The UI labels the workspace as synthetic and shows unassessed rows as **Not assessed**. The UI's latest-200-record limit still applies; the database contains the full population. An operator can run real assessments on selected records. The seed job does not queue 2 million model calls or publish 2 million transaction events. Untouched seed rows are excluded from bulk policy-change reassessment. External action publication and authorization are blocked server-side for synthetic workspaces even if their policy is changed.

Each batch's rows and checkpoint commit in the same database transaction. A session advisory lock prevents concurrent loaders for the same dataset. A retry resumes from the last committed batch. A completed rerun validates the population again and does not duplicate or overwrite it. Invalid markers, missing rows or a mismatched row count fail verification. Use a different `synthetic-*` organization for an independent dataset. Reserve the `syn-v1-` ID prefix for generated records.

For a workspace containing actual records, use a different `ORGANIZATION_ID`; the required synthetic dataset remains separate under `SEED_ORGANIZATION_ID`. No synthetic dataset is used as training labels. A prediction endpoint is not invented or automatically trained from fabricated outcomes.

## Retry, rollback and acceptance

Rerun a failed deployment after fixing its reported cause. Cloud Run job retries and the seed checkpoint preserve committed progress. A timed-out GitHub job may leave a Cloud Run execution running; inspect that execution before starting another release. Check Cloud Logging for job failures; do not reset or truncate data to retry.

The release creates a managed backup and Cloud SQL PITR is enabled. A failed migration transaction rolls back. A successful migration is not automatically downgraded when a later stage fails. Use a forward migration for populated databases. See [Alembic operations](MIGRATIONS.md) for schema inspection, offline SQL and rollback rules.

The service checks establish actual API invocation, not model quality or full business acceptance. Sign in through IAP, import a small organization-owned transaction/document, inspect streaming/citations and perform the connector receipt flow before calling the system production-ready. Pub/Sub permission verification does not simulate downstream ERP execution. Provisioned services, storage, backups and model/document API calls incur GCP charges.
