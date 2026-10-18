# Validation performed in this development environment

Checks performed on the deployment-ready source. [GitHub Actions run 39133915204](https://github.com/Tirumala2824/truestate/actions/runs/39133915204) passed on implementation commit `b90da0cbf4fd6f80975536047246e039c7d9c90a`:

- Redesigned React/TypeScript production build: passed.
- 7 frontend logic tests: passed. Coverage includes quoted/multiline CSV imports, schema/record validation, split UTF-8 streaming frames expired/invalidated decision display and honest unassessed status for synthetic rows. These tests do not establish browser layout or interaction correctness.
- Python module compilation: passed for backend, model and deployment scripts.
- 27 backend tests: passed (21 fast isolated tests plus 6 PostgreSQL integration tests). Coverage includes conservative source deduplication, cycles/missing ancestry, evidence/prediction clearance gates, currency-specific hold limits, atomic ingestion, idempotency conflicts, job leases, policy insert races, snapshot expiry, reviewer compare-and-swap, version-bound requests, immutable receipt semantics, document/outbox rollback, fail-closed API access, scoped input rejection, authenticated extracted-document access with private storage locators omitted, real ADK graph construction and recovery after a report-storage/analytics boundary failure.
- PostgreSQL 16 migration checks: fresh/repeated upgrade, empty downgrade/re-upgrade, ORM metadata comparison, validated legacy adoption, drift rejection and immutable audit triggers passed.
- PostgreSQL bulk-load checks: interrupted-batch recovery, exact-count verification, duplicate-free rerun, concurrent-loader rejection and corrupted-data detection passed. The CI database contained **2,000,000 actual synthetic transaction rows**; the scale test completed in 84.47 seconds, including repeat verification and the indexed workspace query. That duration is specific to the CI runner and does not predict Cloud SQL throughput. No investigation jobs were queued by bulk seeding.
- Application dependency resolution against the pinned requirements: passed; dependencies installed for SDK contract checks.
- Shell deployment syntax: passed.
- Terraform formatting and HCL parsing: passed. Provider installation completed with signed HashiCorp packages. An initial cache checksum mismatch was resolved by reinitialization without disabling checksum verification.

- Full Terraform provider-schema validation: passed for `infra/foundation`, `infra/jobs` and `infra/runtime` in the run linked above. Google provider 7.46.1 is locked in all roots. Local provider execution remains restricted by this environment’s Unix-socket policy; the GitHub runner performed provider validation.

**Not run against GCP:** Terraform plans, Cloud Build/Docker execution, Cloud SQL migration/seeding, IAP login, browser visual checks and live service calls. The PostgreSQL migration/seed checks above ran in CI, not in a user GCP project. The deployment workflow is installed but its automatic run was skipped because automatic deployment was not enabled. Project variables and GCP authorization must be configured through [the GitHub deployment guide](GITHUB_DEPLOYMENT.md). This local environment has no Docker executable. No model was trained, no prediction accuracy was measured, and no external finance-system action was executed. Successful source/provider validation does not establish successful cloud deployment.

ADK 2.12 reports deprecation warnings for ParallelAgent/SequentialAgent; they still instantiate successfully. The test client also reports an upstream httpx deprecation warning. These warnings do not constitute passing live inference tests.

## Required project acceptance run

1. In Cloud Shell, authenticate the deployment principal and run both Terraform `init`/`validate` commands from the README. Review the generated plan, IAM identities, regions and expected billable resources.
2. Run **Actions → Deploy GCP**, or `scripts/deploy.sh` from authenticated Cloud Shell. Require successful Alembic migration, exact 2-million-row Cloud SQL verification and live service checks, then validate IAP login.
3. Submit an organization's actual small document and transaction. Observe Document AI output, Search readiness, genuine Gemini findings, persisted SSE activity, Cloud SQL records, private capsule and BigQuery event.
4. Change the source evidence or policy; verify that the old decision and action preflight become invalid and a new assessment runs. Submit a duplicate event and verify no duplicate job for the same input.
5. Exercise expired decisions, unavailable services, malformed documents, unknown citations and an unrelated prompt embedded in a document. Do not enable automatic clearance until the organization's evaluation passes.
6. Connect a real source/ERP adapter; verify a version-bound request, immediate authorization preflight, downstream idempotency and authenticated execution receipt. A placeholder adapter is not included or represented as execution.
7. Check the live UI on mobile and desktop, keyboard focus, import errors, event reconnection and empty states. Test load, quotas and data-retention requirements before production use.
