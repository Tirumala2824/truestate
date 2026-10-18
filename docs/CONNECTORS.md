# Connect existing source systems

Keep the source connector next to your existing ERP, finance store or security feed. Reuse its supported export/webhook/API capability. TRUESTATE does not require a replacement ERP and cannot infer credentials or capabilities of an unspecified external platform.

Deploy with `SOURCE_CONNECTOR_EMAILS` listing the exact Google service-account identities allowed to submit evidence, attest origins, preflight actions and return receipts. Terraform grants these identities event-topic publishing, action-subscription consuming and worker invocation. Use Workload Identity for a source outside GCP. Do not put a service-account key into the browser.

## Transactions

Publish JSON to the `truestate-events` Pub/Sub topic:

```json
{
  "type": "transaction.ingested",
  "transactions": ["REPLACE_WITH_TRANSACTION_OBJECTS"]
}
```

The string marker above is explanatory, deliberately not a runnable fake transaction. Each object has: `id` (letters/numbers/underscore/hyphen, max 100), `supplier_id`, `supplier_name`, positive two-decimal `amount`, ISO uppercase `currency`, timezone-aware `occurred_at`, optional `reference`, `account_fingerprint`, optional `previous_account_fingerprint`, and `document_ids` (existing IDs; max 30). Unknown properties are rejected. Batch maximum is 1,000 records. Reusing an event ID with different data conflicts. Identical record contents are skipped across distinct events; changes enqueue reassessment.

Pub/Sub authenticates its HTTP push as the dedicated event delivery service account. That delivery identity is not treated as the original data source's attestation.

## Automatic document ingestion

Call `POST WORKER_URL/internal/documents` with a Google-issued OIDC bearer token whose audience is `https://truestate.internal/PROJECT_ID/worker` and whose email is in `SOURCE_CONNECTOR_EMAILS`. Send multipart fields `file`, required `origin_reference`, optional `transaction_id`, and optional `parent_ids` containing a JSON array. PDFs, PNG/JPEG/TIFF images, UTF-8 TXT/CSV and exported EML are supported up to 20 MB, subject to Document AI synchronous page limits.

This stores the private original, records the token's source identity and supplied origin reference, and queues extraction atomically with the document record. Derived sources should name known parents. A human browser upload is never implicitly source-attested. To attest an existing document, call `POST /internal/attest` with its exact `document_id`, `content_sha256`, and `origin_reference`.

## External actions

Enable `external_actions: publish_requests` in the reviewed automation policy. Consume the `truestate-action-requests` subscription. A message includes `request_id`, `transaction_id`, `snapshot_hash`, `decision_version`, `disposition` (`ready` or `hold`), and `expires_at`. Messages may be delivered more than once.

1. Persist/deduplicate `request_id` in your connector.
2. Call `POST /internal/decision-check` with `{"request_id":"THE_RECEIVED_REQUEST_ID"}` using the connector identity. Require `authorized: true` immediately before acting. Validate the returned disposition against the exact operation your integration supports. Never interpret `ready` as an instruction to move money without your organization's configured policy.
3. Execute your real system's supported operation with the same idempotency key. Use conditional writes/authorization in that system if required; preflight and external execution are not a distributed atomic transaction.
4. Call `POST /internal/receipts` with exactly `request_id`, `transaction_id`, `snapshot_hash`, `status` (`executed`, `rejected`, or `failed`) and `external_reference`. Values must be nonempty bounded strings. Identical receipts are idempotent; conflicting receipts are rejected. An unknown or unpublished request cannot receive an execution receipt.
5. Acknowledge the Pub/Sub message only after durably recording the result. Retry transient HTTP failures. Do not blindly retry an external action with a new key.

Automatic expiry and invalidation do not undo an action that already completed. The receipt is an authenticated assertion by the connected system, not cryptographic proof of banking settlement. Human-reviewed decisions and generated assessments are separate from these receipts.
