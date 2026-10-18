# Validation performed in this development environment

Checks performed on the v2 source:

- React/TypeScript production build: passed.
- Python module compilation: passed for backend, model and deployment scripts.
- 14 isolated tests: passed. Coverage includes conservative source deduplication, cycles/missing ancestry, evidence/prediction clearance gates, currency-specific hold limits, atomic ingestion, idempotency conflicts, job leases, policy insert races, snapshot expiry, reviewer compare-and-swap, version-bound requests, immutable receipt semantics, document/outbox rollback, fail-closed API access, scoped input rejection, real ADK graph construction and recovery after a report-storage/analytics boundary failure.
- Application dependency resolution against the pinned requirements: passed; dependencies installed for SDK contract checks.
- Shell deployment syntax: passed.
- Terraform formatting and HCL parsing: passed. Provider installation completed with signed HashiCorp packages. An initial cache checksum mismatch was resolved by reinitialization without disabling checksum verification.

**Not passed or not run:** full Terraform provider-schema validation could not run because this environment rejects the providers' local Unix sockets (`socket: operation not permitted`). `terraform validate` must therefore be run in Cloud Shell before apply. This limitation is not represented as a successful infrastructure validation. A credential-free GitHub Actions workflow is included to run that provider validation on repository pushes; a configured workflow is not a claimed passing run. Terraform plans, Cloud Build/Docker execution, database migration, IAP login, browser visual checks and live service calls were not run: no GCP project/ADC identity was available, and this environment has no Docker executable. No model was trained, no prediction accuracy was measured, and no external finance-system action was executed.

ADK 2.12 reports deprecation warnings for ParallelAgent/SequentialAgent; they still instantiate successfully. The test client also reports an upstream httpx deprecation warning. These warnings do not constitute passing live inference tests.

## Required project acceptance run

1. In Cloud Shell, authenticate the deployment principal and run both Terraform `init`/`validate` commands from the README. Review the generated plan, IAM identities, regions and expected billable resources.
2. Build and deploy with `scripts/deploy.sh`. Require successful schema migration, IAP login and connection verification.
3. Submit an organization's actual small document and transaction. Observe Document AI output, Search readiness, genuine Gemini findings, persisted SSE activity, Cloud SQL records, private capsule and BigQuery event.
4. Change the source evidence or policy; verify that the old decision and action preflight become invalid and a new assessment runs. Submit a duplicate event and verify no duplicate job for the same input.
5. Exercise expired decisions, unavailable services, malformed documents, unknown citations and an unrelated prompt embedded in a document. Do not enable automatic clearance until the organization's evaluation passes.
6. Connect a real source/ERP adapter; verify a version-bound request, immediate authorization preflight, downstream idempotency and authenticated execution receipt. A placeholder adapter is not included or represented as execution.
7. Check the live UI on mobile and desktop, keyboard focus, import errors, event reconnection and empty states. Test load, quotas and data-retention requirements before production use.
