# REST API

The hosted API requires the Site's authenticated user headers, injected by hosting. Never expose the Worker origin without that boundary. FastAPI requires `Authorization: Bearer <configured token>`, except explicit loopback-only demo setup; OpenAPI is generated at `/docs`.

| Method | Endpoint | Behavior |
|---|---|---|
| GET | /api/state | Personal workspace aggregate, including saved conversations |
| POST | /api/chat | Scope-checked financial turn; contextual response and live investigation SSE |
| POST | /api/uploads | Multipart financial evidence upload and validated extracted fields |
| GET | /api/uploads/{id} | Authenticated original source download |
| DELETE | /api/uploads/{id} | Remove an unreferenced draft upload |
| GET | /api/health | Honest integration configuration state |
| GET | /api/dashboard/overview | Computed queue/case metrics |
| GET | /api/transactions[/{id}] | Tenant-scoped payments |
| GET | /api/investigations[/{id}] | Cases and stored reports |
| GET | /api/investigations/{id}/evidence | Material source claims |
| GET | /api/investigations/{id}/graph | Provenance nodes and edges |
| GET | /api/investigations/{id}/report | JSON report including exact IDs |
| GET | /api/agents/status | Current agent operations |
| GET | /api/agents/runs/{id} | Case execution receipts |
| GET | /api/audit/events | Immutable historical events |
| GET | /api/evaluation/results | Most recent measured run or null |
| POST | /api/simulations/start | Inject event and execute; SSE snapshots |
| POST | /api/events | Event-triggered execution; FastAPI returns final case, Worker streams |
| POST | /api/simulations/reset | Fresh working seed data; archived evidence/audit retained |
| POST | /api/simulations/recover | Escalate an interrupted run after its deadline |
| POST | /api/investigations/{id}/verify | Record human-verification request; no message is sent |
| POST | /api/investigations/{id}/escalate | Record reviewer escalation |
| POST | /api/payments/{id}/request-hold | Explicit reviewer precautionary hold with justification |
| POST | /api/payments/{id}/approve-release | Reviewer-only simulated release with justification |
| POST | /api/evaluation/run | Execute 120 frozen synthetic fixtures |
| POST | /api/pubsub | FastAPI-only authenticated Pub/Sub synthetic event receiver |

Simulation body: `{"scenario":"coordinated","eventId":"unique-event-id"}`. Other scenarios: `legitimate`, `simple`, `insufficient`, `failed`. Reusing an event ID returns its existing case without duplicating the payment action. IDs in the application are UUIDs; external delivery IDs may be arbitrary strings up to 128 characters.

Reviewer action body: `{"reason":"Independently verified supplier authorization through the trusted contact"}`. The server supplies role and identity. No request-body role can grant privileges.

SSE frames use `event: state` and JSON `data`, ending with `event: done`. Errors are explicit. State is committed before being emitted. The demo supports one active investigation per workspace. Concurrent writes return a conflict; callers should refresh before retrying.

Example non-chat trigger in explicit local demo mode:

```bash
curl -X POST http://127.0.0.1:8080/api/events \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"coordinated","eventId":"demo-delivery-001"}'
```

## Frozen synthetic generator

`printf '{"op":"fixtures"}' | node backend/bridge.mjs` returns the 120 deterministic input fixtures. Production financial documents are not accepted by these demo endpoints. The cloud extraction and analytics functions are separate adapters and need an approved ingestion pipeline before they can become authoritative case inputs.

## Conversational endpoint

Send `{"prompt":"Investigate Aster","requestId":"unique-turn-id","conversationId":"existing-id-if-continuing"}` to `/api/chat`. Omit conversationId for a new chat. Preserve requestId on retries, including retries after a lost first response. The server deduplicates accepted turns within the authenticated workspace.

A chat `state` frame contains `{state, conversationId, messageId, runCaseId?}`. `done` contains the response IDs. Investigation frames update actual tool progress and the final assistant summary. Hosted frames are persisted before emission; FastAPI persists every investigation stage and the final conversational summary (intermediate wording is a live projection). Read `/api/state` after reconnecting.

The server resolves contextual case/payment references, supports bounded command patterns, and refuses unknown or cross-tenant conversation IDs. Request bodies cannot grant roles. Reviewer actions collect a reason and await explicit confirmation tied to the exact pending target, expiring after 10 minutes. Action confirmation rechecks role and current payment state. Conversation limits are 100 threads, 200 messages per thread, and 4,000 characters per prompt.

## Multimodal contract

`POST /api/uploads` takes multipart `file` and JSON-text `extraction` fields. Extraction is `{text, method: "text" | "pdf-text" | "ocr", pages, confidence?}`. TXT/CSV content is always re-read from original bytes; PDF/OCR extraction is client-supplied untrusted data. File signature, type, size, document field scope, page count and ownership are checked server-side. Response `{attachment}` contains bounded financial fields, warnings, SHA-256 and an opaque source ID; never an authorization assertion.

Pass up to three owned IDs in `/api/chat` as `attachmentIds`. They are accepted only with a document-review/comparison task. Cross-tenant IDs reject. Original downloads require the same authenticated workspace; no public file URLs are issued. Referenced sources cannot be deleted through the draft-upload endpoint.

Scope refusals are normal streamed assistant results with `scopeRejected: true`, no evidence cards and no domain action. Text matches a full-request financial grammar, not a keyword filter. `status` events describe accepted/rejected scope and actual progress; `response` starts a textual answer; `delta` supplies an answer chunk; `state` supplies persisted state; `done` ends the response. Clients must keep reading through `done` and handle explicit errors/disconnections.
