# Security boundaries and known gaps

## Enforced in this prototype

- Synthetic-only accounts, organizations, documents and payment queue; no transfer or bank-modification API exists.
- Hosted private access, authenticated per-user data, server-derived roles, and tenant-scoped case lookup.
- API request bodies cannot choose a reviewer role. FastAPI's typed mutation schema rejects unexpected fields.
- Risk assessment does not confer execution authority. The deterministic gateway rechecks target payment, queued state, evidence presence, assessment, amount ceiling and agent role.
- An agent cannot release a disputed payment. Human reviewer identity and a minimum-length written justification are required.
- Hold actions use a per-case idempotency key; duplicate events reuse the case; retries read actual simulator state and stop after two attempts.
- Outcome verification compares every unrelated payment against its pre-action state.
- Optimistic revisions and atomic audit writes protect against concurrent mutation loss. SQL triggers reject audit update/delete operations.
- Reset archives evidence and cases and retains audit; it is not an audit erasure operation.
- Retrieved document text is inert data. No evaluation or permission parser interprets instructions embedded in a document. Optional ADK tools bind case identity and expose no payment execution/release operation. Final model citations must be a subset of known evidence IDs.
- Secrets are environment configuration, not source. Google APIs use ADC/service accounts. Document AI uploads are restricted by MIME and size. BigQuery uses fixed SQL and parameterized tenant IDs.

## Deliberate limits

This is a demonstrable prototype, not a production financial control system. The hosted six roles are deterministic logic, not six live LLM agents. Cloud ADK reasoning is optional and advisory; its service integration has not been tested against a real project here. Native integration into real ERP, account verification, supplier communication, and signed-document systems is not implemented.

Source integrity labels in demo data are synthetic assertions. PDF exports are unsigned. Audit triggers protect ordinary application writes, not a database administrator; use independent immutable storage and signed receipts for stronger tamper evidence. The normalized SQL read model is generated from snapshots; it does not yet contain a complete procurement ingestion pipeline.

The hosted Site gives a signed-in user reviewer rights over that user's own fake funds. It does not implement enterprise reviewer onboarding, dual approval, or separation between multiple employees within a shared tenant. FastAPI role mapping is static server configuration. A production identity provider and reviewer authorization lifecycle are required for real organizations. Do not enable TRUESTATE_LOCAL_DEMO_AUTH on a public host; the supplied container binds localhost in compose and disables this path on Cloud Run.

The cloud document-search adapter must be configured with a tenant-isolated search engine or enforced retrieval ACLs. It is not exposed directly to an arbitrary browser query and does not itself establish multitenant document authorization. BigQuery table configuration must point only to reviewed data. Do not pass production financial information into the synthetic fixture APIs.

Request-scoped runs have a 60-second bound, but they are not a durable distributed job queue. A disconnected/terminated host can leave a case unfinished until explicit recovery. Before continuous unattended operation, add persistent job leasing, retries across deployments, independent reconciliation, recovery scheduling, quotas and load testing. Cloud mode fails closed if reasoning is unavailable; no model result silently becomes a mock result.

The functional dataset contains only five scenario families. The reported 100% values are expected properties of narrow fixtures, not measured generalization to real fraud. The product never presents LLM confidence as a calibrated probability. No claim of automatic legal or regulatory compliance is made.

## Verification limits for this build

Core engine tests, FastAPI integration/security tests, TypeScript checks, and a built-Worker/D1/SSE test are included. Google Cloud services were not provisioned or live-tested. No browser-control tool was available in the build session, so interactive visual QA was not performed. Both the hosted Vinext build and the standard Next.js production build passed. Docker recipes were supplied; image builds require a Docker-capable host.
