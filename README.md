# TRUESTATE · Evidence-bound operations

A GCP-backed operations console for supplier-payment and vendor-change reviews across finance, security, and legal teams. Four Google ADK agents process the work automatically; people work from a queue of evidence gaps and exceptions. There is no general chat interface.

**Deployment status:** the GitHub deployment pipeline and Alembic/seed configuration are implemented. The GCP deployment job has not run in this development session; GitHub project variables and cloud authorization must be configured first. This version has not yet been end-to-end verified against live GCP services. Real model responses, OCR, search indexing, Cloud SQL IAM, IAP and external execution still need a project acceptance run. The old hosted demo is not this implementation.

## What works in the implementation

- Actual transaction import through CSV or authenticated Pub/Sub events, with idempotency and a durable SQL outbox.
- PDF, image, text, CSV and exported email ingestion; Document AI OCR for scans; private original-file storage. Connectors can submit documents automatically.
- Approved company policy indexing and retrieval through Vertex AI Search, including delayed-index readiness handling.
- Finance, security and legal Gemini specialists, followed by a resolution agent. Versioned repository skills supply their instructions.
- Deterministic policy authorization, source ancestry/content deduplication, connector attestations, expiring decisions and automatic invalidation/reassessment.
- Real Vertex prediction endpoint integration; optional baseline training on your adjudicated BigQuery data. No endpoint means no invented prediction.
- Real BigQuery assessment analytics, persisted server-sent events, streamed bounded explanations, JSON evidence reports and an audit ledger.
- Version-bound action requests and authenticated receipts for your ERP/payment connector. An application decision alone never claims a payment was held or released.
- Responsive operations, evidence, policy, analytics, connection and audit screens; keyboard dialogs and empty/error states.

Synthetic cloud responses, local database fallbacks, the old chat UI and Cloudflare deployment components remain removed. An explicitly requested PostgreSQL seed job now creates 2,000,000 clearly labelled transactions in a reserved synthetic workspace. It does not fabricate documents, model findings, receipts or real business outcomes. Small test fixtures remain under `tests/`.

## Google Cloud services

| Service | Responsibility |
|---|---|
| Gemini on Vertex AI + Google ADK | Bounded specialist assessments, resolution and streaming explanations |
| Vertex prediction | Organization-trained risk classification |
| Document AI | Pretrained OCR for financial and non-traditional documents |
| Vertex AI Search | Organization policy retrieval |
| Cloud Run | IAP-protected console/API, private worker, migration job |
| Cloud SQL PostgreSQL | Authoritative records, decisions, versions, durable jobs and audit events |
| BigQuery | Transaction/risk analytics and adjudicated training labels |
| Pub/Sub + Cloud Scheduler | Event processing, durable dispatch recovery and action requests |
| Cloud Storage | Private original evidence, report capsules and model artifacts |
| IAP, IAM, Secret Manager, Cloud Build, Artifact Registry | Identity, least-privilege runtime access and deployment |

No non-GCP hosted runtime service is required. Google open-source libraries, React, FastAPI, SQLAlchemy and scikit-learn are reused. See [reuse and licenses](docs/OPEN_SOURCE.md).

## Deploy from GitHub (recommended)

Follow [GitHub deployment setup](docs/GITHUB_DEPLOYMENT.md) for the exact variables and authentication settings. Run **Actions → Deploy GCP** after configuring them. The pipeline provisions GCP, backs up Cloud SQL, runs Alembic migrations, seeds and verifies 2,000,000 transactions, checks live services and only then deploys the app/worker. See [Alembic migration operations](docs/MIGRATIONS.md).

## Deploy from Google Cloud Shell

Use a dedicated billing-enabled GCP project with an organization-managed Google identity. Native Cloud Run IAP uses a Google-managed OAuth client; if external Google identities must access it, configure the appropriate custom OAuth client/IAP settings before granting access. The supplied script targets organization-managed access; do not disable IAP to work around identity configuration.

Install Terraform 1.9 or later and Git. The deployment principal needs permission to enable services, manage the listed resources/IAM grants, run Cloud Build, impersonate deployment service accounts and execute the migration job. In a dedicated prototype project, a project administrator can perform this bootstrap; the runtime uses separate restricted service identities.

```bash
git clone https://github.com/Tirumala2824/truestate.git
cd truestate
gcloud auth login
gcloud auth application-default login
export PROJECT_ID='YOUR_BILLING_ENABLED_PROJECT'
export REGION='us-central1'
export GEMINI_MODEL='YOUR_ENABLED_VERTEX_GEMINI_MODEL_ID'
export REVIEWER_EMAILS='YOUR_ORGANIZATION_GOOGLE_EMAIL'
export ORGANIZATION_ID='synthetic-demo'
export SEED_ORGANIZATION_ID='synthetic-demo'
# Optional comma-separated Google identities and allowed service accounts:
export OPERATOR_EMAILS=''
export SOURCE_CONNECTOR_EMAILS=''
./scripts/deploy.sh
```

The script provisions a private Terraform state bucket, managed services and identities; builds an immutable image with Cloud Build; deploys the release jobs; backs up Cloud SQL; executes Alembic, bulk seeding and service verification; and finally deploys the console and worker. It prints the actual Cloud Run URL after completion. Terraform prints and automatically applies saved plans as part of this authorized release pipeline. Resources incur GCP charges; the script does not invent a price estimate or silently destroy resources. SQL and BigQuery deletion protection are enabled. Rerun with the same project/state bucket for updates.

Cloud SQL and application defaults use the selected region. Document AI defaults to `us`, Search to `global`, and BigQuery to `US`; change the foundation variables before initial provisioning if your residency requirements differ. Model availability and quota must be verified for your selected region/model. Cloud SQL public-IP connectivity uses the authenticated Cloud SQL connector, encrypted transport and no authorized IP networks.

## First real workflow

1. Open the deployed URL, sign in through IAP, and select **Connections → Verify service access**. Metadata reachability is shown separately from an actual model invocation.
2. Register your approved company policies in **Evidence** with purpose **Approved company policy**. Search registration is asynchronous; the scheduler checks retrieval readiness.
3. Use **Import transactions → Get template** to get an empty schema. Populate it with your actual records; no sample monetary records are bundled. Account fingerprints should be irreversible identifiers produced by your source system, not raw bank details.
4. Attach relevant invoices, contracts, approvals and source messages. Alternatively, connect an existing source system using [the authenticated connector contract](docs/CONNECTORS.md).
5. Imported/changed data automatically enters the worker pipeline. Review current findings, citations, source relationships, prediction availability, decision expiry and receipts in the full-page case workspace.
6. A reviewer can change the automation policy, with a new version. Defaults do not automatically clear transactions and do not publish external action requests. Set actual currency limits and evidence requirements before enabling the corresponding actions.

The default policy has **no invented monetary thresholds**. `auto_hold` requires an explicitly configured `max_auto_hold_amount` for the transaction's currency. `auto_clear` is false. Enabling `external_actions: publish_requests` still requires your connector to validate and execute each request; it does not connect an unspecified bank or ERP on its own.

## Predictive model

Use your existing compatible Vertex endpoint by setting `VERTEX_PREDICTION_ENDPOINT` to its full resource name and rerunning deployment. Its contract is documented in [MODEL.md](docs/MODEL.md). The included baseline training pipeline requires real labels, independent temporal evaluation, an operator-supplied quality gate and a single training currency. It cannot train from an empty dataset or synthetic examples.

## Explore the redesigned frontend locally

The interface uses a light operations workspace, a dark navigation rail, a visual agent workflow, list/board work queues, full-page cases, searchable evidence, guided imports, readable policy controls and responsive layouts. There is no general chat screen.

With Node 22.13 or later, open the repository and run:

```bash
npm ci
npm run dev
```

Open the local URL printed by Vite. You can explore navigation, agent responsibilities, help, workspace search and CSV preparation without a backend. The interface explicitly shows **Setup needed**; business metrics remain unavailable, submissions stay disabled, and no sample records are generated. Viewing real cases, policies and documents requires the deployed, authenticated API.

The development server proxies `/api` to `http://127.0.0.1:8080`. A backend there still requires the documented GCP configuration and authenticated access; frontend inspection does not bypass it. For the live system, use the Cloud Run deployment instructions above.

## Development and checks

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest
python -m pytest -q tests
npm ci
npm run test:frontend
npm run build
terraform -chdir=infra/foundation init -backend=false
terraform -chdir=infra/foundation validate
terraform -chdir=infra/jobs init -backend=false
terraform -chdir=infra/jobs validate
terraform -chdir=infra/runtime init -backend=false
terraform -chdir=infra/runtime validate
```

The application uses ADC and configured GCP resources even during development. There is no auth bypass or fake-service mode. The dedicated seed job inserts labelled synthetic transactions into PostgreSQL; it is separate from application startup and never supplies fabricated cloud responses. Tests explicitly inject isolated adapters and a test-only SQLite store; they do not establish live cloud connectivity. See [validation evidence and remaining gates](docs/VALIDATION.md), [architecture](docs/ARCHITECTURE.md), [security boundaries](docs/SECURITY.md), and [differentiation](docs/DIFFERENTIATION.md).

## Scope and limits

The initial workflow covers supplier payments and account-change evidence; it does not automate every financial, legal or security task. It does not execute money movement, make binding legal determinations, or replace an external system's conditional transaction controls. There is no claim of industry-first novelty. Multimodal input here means documents/images plus structured transactions; live microphone/video sessions are not implemented.

The prototype displays the latest 200 transactions/documents and 100 assessments; lineage processing is limited to 100 documents and 24,000 extracted characters per document in model context. Truncated or incomplete evidence blocks automatic clearance. OCR uses Document AI synchronous processing and its processor-specific page limits; split oversized documents or extend to the batch API. The SQL implementation favors correctness with short per-organization locks over high-volume throughput. Add pagination, load testing, observability alerts, data-retention controls and organization-specific evaluation before production rollout.
