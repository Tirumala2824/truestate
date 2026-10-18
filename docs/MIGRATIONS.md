# Alembic migrations and database release jobs

`alembic.ini`, `migrations/env.py`, the revision template and versioned scripts are included in the same immutable image as the application. Application startup never calls `Base.metadata.create_all()` or runs schema migrations. `python -m backend.migrate` is the supported release entry point.

## Revision history

| Revision | Change |
|---|---|
| `0001_baseline` | Original records, jobs, events and inbox tables, primary keys and indexes |
| `0002_synthetic_load` | Workspace/event/job indexes, append-only audit trigger, resumable synthetic-load manifest |

An empty database is upgraded from base to head. A database produced by the older `create_all()` migration is adopted only if all four legacy tables, column types/nullability, primary keys and original indexes match. The migration stamps only `0001_baseline`, then executes every later revision. Partial or incompatible legacy schemas fail without a blind `stamp head`. Existing records are preserved.

Migrations run within a PostgreSQL transaction and acquire a database-wide advisory lock. Schema-lock waiting is bounded to 60 seconds; individual migration statements are bounded to 15 minutes. A second release cannot interleave schema changes. The migration job verifies the final Alembic head before granting runtime permissions and initializing absent policies. It never resets an existing policy or inserts business transactions.

## Connections and privileges

On GCP, the job connects using the Cloud SQL connector with the dedicated SQL migration user and a Secret Manager password. Runtime services use Cloud SQL IAM database authentication. Runtime grants allow record/job/inbox operations and audit insertion; audit updates/deletes are not granted, and the append-only database trigger adds enforcement. Runtime can read migration and synthetic-load metadata but cannot write it.

`MIGRATION_DATABASE_URL` is an explicit administrative PostgreSQL connection for CI or a locally managed PostgreSQL instance. It is not an application fallback; the runtime still requires Cloud SQL. Never store a real URL/password in source or shell history. The CI test service uses disposable credentials and an isolated schema per test.

## Commands

Run these from the repository after installing `requirements.txt`:

```bash
# No database access required: review the SQL generated for an empty PostgreSQL database.
alembic upgrade head --sql > /tmp/truestate-migration.sql
alembic history
alembic heads

# With administrative GCP configuration or MIGRATION_DATABASE_URL:
alembic current
alembic check

# Production entry point: also validates legacy adoption, grants IAM runtime
# access and initializes absent policies. Requires DB_IAM_USER.
python -m backend.migrate

# Generate a future revision against the configured administrative database.
alembic revision --autogenerate -m 'describe the schema change'
```

Review generated revisions; autogeneration does not infer data migrations, application compatibility or every trigger change. Revision files must contain stable schema operations instead of importing live model definitions. Update runtime grants for new application tables as needed. Test upgrades from both empty and preceding schemas before deployment.

## Synthetic loader

```bash
# Same commands used by the GCP release jobs; PostgreSQL required.
python -m backend.seed --organization synthetic-demo
python -m backend.seed --organization synthetic-demo --verify-only
```

The default and required release size is 2,000,000 transactions. `--rows` supports smaller isolated test populations; the production release checker still requires 2,000,000. Batches default to 10,000 and never exceed 20,000. PostgreSQL generates each batch server-side, so the process does not accumulate millions of Python objects or upload a giant CSV. No Faker package, browser fixture or fake cloud adapter is used.

The `synthetic_loads` row records expected, committed and verified counts and timestamps. Verification checks the complete reserved ID population, unique primary-key bounds, dataset markers and synthetic names/references. `ANALYZE records` refreshes query planning statistics. The composite `(org, kind, updated_at DESC, id DESC)` index supports the workspace's limited recent-record query.

## Rollback

The deployment never executes an automatic downgrade. PostgreSQL DDL failures roll back in their transaction; use the pre-release backup/PITR or a reviewed forward migration for later data problems. Downgrade code exists for empty integration-test databases, but refuses to drop populated original tables or remove populated seed history. Do not run `stamp head` to skip a failed revision. Do not delete the `alembic_version` or `synthetic_loads` tables to retry a deployment.

The old `truestate-migrate` job, if present in the runtime Terraform state, is removed during the final runtime apply. Its replacement, `truestate-release-migrate`, is owned by the separate jobs root and has already completed before that change. Existing foundation/runtime state prefixes remain unchanged; the jobs root uses the new `jobs` prefix.

## Validation

GitHub Actions starts PostgreSQL 16 and tests empty upgrade/repeat/downgrade, metadata agreement, legacy adoption, drift rejection, append-only audit enforcement, interrupted-batch resume, duplicate prevention, concurrent-loader refusal and corrupted-data rejection. It also loads and verifies the full 2,000,000-row population, reruns without duplication and checks that the workspace query uses its index. This database is disposable CI infrastructure; it does not substitute for the separate required load in your GCP database.
