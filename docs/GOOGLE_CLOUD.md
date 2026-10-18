# Google Cloud setup — optional, not connected in the hosted demo

The delivered Site runs deterministic local adapters. This guide configures the separately deployable FastAPI service and optional live ADK advisory reasoning. No project, credentials, paid API calls, or real financial systems were provisioned during the build.

## Prerequisites

- A billing-enabled project with organization permission to enable APIs and create service accounts.
- A selected Gemini model actually enabled in that project and region; set `GEMINI_MODEL` explicitly.
- Cloud SQL PostgreSQL for durable cloud-mode state. Local SQLite is intentionally rejected in cloud mode.
- A reviewed synthetic-only dataset, a Document AI processor if extraction is needed, and an Agent Search engine if retrieval is needed.

Official references checked for this implementation:

- [Google ADK model configuration](https://adk.dev/agents/models/google-gemini/)
- [ADK function tools](https://adk.dev/tools-custom/function-tools/)
- [ADK Python dependencies](https://github.com/google/adk-python/blob/main/pyproject.toml)
- [Google Gen AI Python SDK](https://github.com/googleapis/python-genai)
- [Application Default Credentials](https://docs.cloud.google.com/docs/authentication/provide-credentials-adc)
- [Document AI client processing](https://docs.cloud.google.com/document-ai/docs/process-documents-client-libraries)
- [BigQuery named query parameters](https://docs.cloud.google.com/bigquery/docs/samples/bigquery-query-params-named)
- [Agent Search client example](https://docs.cloud.google.com/generative-ai-app-builder/docs/samples/genappbuilder-search)
- [Pub/Sub and Cloud Run](https://docs.cloud.google.com/run/docs/tutorials/pubsub)
- [Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract)

`requirements-cloud.txt` pins ADK 2.12.0 and google-genai 2.31.0 from the current official releases. These optional dependencies were not installed/live-tested in this session. Current Google documentation uses `enterprise=True` / `GOOGLE_GENAI_USE_ENTERPRISE=true`; the legacy `vertexai=True` spelling remains an SDK alias. Do not select a model based on a hard-coded example name.

## Local credentials and dependencies

```bash
python -m pip install -r backend/requirements-cloud.txt
gcloud auth application-default login
```

Use ADC only on an appropriate development machine. On Cloud Run, attach a dedicated service account; do not copy service-account JSON keys into the image.

Set the following environment variables through your process manager or an ignored local file:

```dotenv
TRUESTATE_MODE=cloud
TRUESTATE_LOCAL_DEMO_AUTH=0
GOOGLE_GENAI_USE_ENTERPRISE=true
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_CLOUD_LOCATION=your-enabled-model-region
GEMINI_MODEL=your-enabled-model-id
DATABASE_URL=postgresql+psycopg://configured-via-secret-manager
DOCUMENT_AI_LOCATION=us
DOCUMENT_AI_PROCESSOR_ID=your-existing-processor
AGENT_SEARCH_LOCATION=global
AGENT_SEARCH_ENGINE_ID=your-tenant-isolated-engine
BIGQUERY_TABLE=your_project.your_dataset.transactions
PUBSUB_TOPIC=truestate-synthetic-events
GCS_BUCKET=your-private-report-bucket
```

`TRUESTATE_API_TOKENS` is a JSON mapping from strong bearer tokens to `{user_id, role}`. Store it in Secret Manager, not a checked-in env file. It is a prototype service-auth mechanism; replace it with your organization's verified identity and reviewer authorization for real use. The supplied Next.js proxy supports local demo mode, not a complete cloud SSO integration.

## Least-privilege services

Enable only services you use:

```bash
gcloud services enable aiplatform.googleapis.com run.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com \
  sqladmin.googleapis.com secretmanager.googleapis.com \
  bigquery.googleapis.com documentai.googleapis.com \
  discoveryengine.googleapis.com pubsub.googleapis.com storage.googleapis.com
```

Grant narrowly scoped permissions to the runtime service account: model invocation, BigQuery job creation plus read on the designated dataset, processor access on the designated Document AI processor, retrieval on the designated search engine, Pub/Sub publisher on the one topic, and object create/read on the reports bucket. Grant Secret Manager accessor only to the specific runtime secrets. Use a separate migration database role for DDL and restrict the runtime SQL role to application tables. Cloud SQL connectivity requires its connection permission and a reviewed network/connector configuration.

The BigQuery adapter uses fixed SQL and a parameterized tenant predicate; the configured table must contain `tenant_id`, `created_at`, and `amount`. Agent Search requires a tenant-isolated engine or correctly enforced retrieval ACLs; the adapter alone is not a multitenant authorization layer. No adapter takes an arbitrary destination URL from a document.

## Deploy the API

Create your Cloud SQL instance/database, private report bucket, secrets, Artifact Registry repository, and service accounts according to your organization's policy. `Dockerfile.cloud` contains Python and Node, because the FastAPI transport uses the shared TypeScript engine.

```bash
gcloud builds submit --config deploy/cloudbuild.yaml \
  --substitutions=_IMAGE=REGION-docker.pkg.dev/PROJECT/REPOSITORY/truestate-api:VERSION

gcloud run deploy truestate-api \
  --image REGION-docker.pkg.dev/PROJECT/REPOSITORY/truestate-api:VERSION \
  --region YOUR_REGION \
  --service-account YOUR_RUNTIME_SERVICE_ACCOUNT \
  --no-allow-unauthenticated \
  --port 8080 \
  --set-env-vars TRUESTATE_MODE=cloud,TRUESTATE_LOCAL_DEMO_AUTH=0,GOOGLE_GENAI_USE_ENTERPRISE=true,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT,GOOGLE_CLOUD_LOCATION=YOUR_REGION,GEMINI_MODEL=YOUR_MODEL \
  --set-secrets DATABASE_URL=truestate-database-url:latest,TRUESTATE_API_TOKENS=truestate-api-token-map:latest
```

Configure the Cloud SQL network/socket connection and database URL to match your chosen deployment; this template does not automatically create that infrastructure. Startup can initialize the prototype schema. For a production migration workflow, run `python -m backend.repository` with a migration identity before deployment and set `TRUESTATE_MIGRATE_ON_START=0` for the restricted runtime identity. Review the generated schema snapshots under `backend/migrations/` before execution.

The service remains private. Configure approved invocation and identity rather than making it public to bypass an authentication problem. A separate frontend deployment and end-user SSO proxy are required to expose the Cloud Run API through an enterprise web UI.

## Authenticated synthetic event ingestion

The Pub/Sub subscriber endpoint is `/api/pubsub`. Set:

- `PUBSUB_AUDIENCE` to the exact configured OIDC audience.
- `PUBSUB_SERVICE_ACCOUNT` to the permitted push identity email.
- `PUBSUB_TENANT_ID` to the tenant that this subscription is allowed to affect.

Grant that push service account `roles/run.invoker` on the service, then configure an authenticated push subscription:

```bash
gcloud pubsub subscriptions create truestate-synthetic-push \
  --topic truestate-synthetic-events \
  --push-endpoint https://YOUR_CLOUD_RUN_ORIGIN/api/pubsub \
  --push-auth-service-account YOUR_PUSH_SERVICE_ACCOUNT \
  --push-auth-token-audience YOUR_CONFIGURED_AUDIENCE \
  --ack-deadline 120
```

Cloud Run checks invocation permission. The handler also validates the OIDC audience and expected verified email and binds that service identity to one configured tenant. It uses the Pub/Sub message ID for deduplication. Confirm the delivered Authorization header behavior in your actual Cloud Run configuration before declaring the push path live. Do not treat configured status as successful delivery.

Payloads are synthetic scenario events, e.g. `{"scenario":"coordinated"}`. The receiver acknowledges only after its bounded execution has been persisted. This is sufficient for the demo but is not a durable high-throughput orchestration system; for production, enqueue a persisted job and use leased workers plus independent reconciliation.

## Verify services explicitly

The health endpoint reports **Not configured** or **Configured; not live-verified**. It never reports a successful connection from the presence of environment variables alone. A completed ADK run has structured live receipts and usage counts on the case; it still uses synthetic evidence unless a reviewed ingestion system is added.

Exercise each configured adapter against synthetic records, verify permissions and tenant isolation, inspect logs without confidential payloads, and test actual failure/retry behavior. Cloud mode stops and escalates if ADK reasoning fails. It does not report a mock result as a live Gemini answer.
