# TRUESTATE — Autonomous Financial Truth & Risk

**When every financial record agrees, but the truth is wrong.**

A runnable hackathon platform for Meridian Finance Operations. It investigates synthetic supplier-account changes, reconstructs evidence provenance, retrieves independent records, applies a policy-authorized hold to a simulated payment, verifies the result, and preserves an audit report.

## What works

- One ChatGPT-style conversation: describe a task, get results inline, and ask contextual follow-up questions without navigating separate product pages.
- Searchable conversation history, contextual next steps, plain-language explanations, inline payment tables and evidence cards.
- Responsive workspace with light/dark themes, live queue counts, a compact composer, keyboard quick actions (Ctrl/Cmd + K), and per-conversation drafts retained in this browser tab.
- Tablet drawer navigation, phone payment/evaluation cards, 44 px touch controls, safe-area spacing, keyboard-aware viewport height, scrollable dialogs, and an opt-in touch graph with a readable source list.
- Drag-and-drop files, one-click sample invoice preparation, reusable saved evidence, extraction progress and cancellation.
- Inline reviewer reason entry, exact-action confirmation, expiry feedback, and a four-stage investigation progress view.
- A fail-closed financial command grammar checked on the server. Unrelated, mixed, disguised, and unsupported requests receive an explicit scope rejection.
- Multimodal evidence: PDF, PNG/JPG/WebP images with English OCR, and TXT/CSV records. Optional browser voice dictation passes through the same scope gate.
- Real SSE status, response chunks, and investigation events; local extraction and upload progress. Private source-file storage in R2 (hosted) or a configurable filesystem volume (portable).
- A real event-driven, 13-step investigation with six specialist roles. DEMO MODE runs actual deterministic tool functions, not prerecorded messages or invented Gemini outputs.
- Five scenarios, 120 seeded payments, and a frozen 120-case evaluation dataset.
- Clickable React Flow graph, exact evidence IDs, competing hypotheses, explicit uncertainty, live SSE tool receipts, and bounded retries.
- D1 persistence on the private hosted Site. A portable FastAPI backend uses SQLite or PostgreSQL with a normalized domain projection.
- Reviewer-authorized simulated holds and releases; idempotent agent actions; unrelated-payment checks; immutable audit triggers; tenant scoping.
- PDF and JSON investigation exports, including tool receipts and evidence references.
- Optional real Google ADK/Gemini advisory reasoning and clean Google Cloud adapters. **These integrations are not configured or live-tested in the hosted demo.**

## Runtime choices

| Runtime | Frontend | Backend | Persistence | Status |
|---|---|---|---|---|
| Hosted Site | React / TypeScript / Next-compatible Vinext / Tailwind / React Flow / Recharts | TypeScript Worker REST + SSE | Cloudflare D1 | Working demo |
| Portable local | Standard Next.js, same React UI | Python FastAPI + shared Node tool engine | SQLite; PostgreSQL optional | API integration-tested |
| Google Cloud | Deploy Next.js separately | FastAPI / Google ADK advisory reasoning | PostgreSQL required | Adapter code + setup; unconfigured |

Cloudflare Workers cannot run the Python/Google SDK backend. The hosted application therefore uses the same deterministic TypeScript engine directly. The portable FastAPI transport invokes that engine over a JSON subprocess bridge, keeping permission and scenario behavior in one implementation. Node 24 is required alongside Python for this transport.

## Quick start: local frontend and FastAPI

Prerequisites: Node 24, Python 3.12+, pnpm (or the equivalent package installer).

```bash
pnpm install --frozen-lockfile
pnpm prepare:multimodal
python -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

Terminal 1 — explicit synthetic local reviewer identity:

```bash
TRUESTATE_MODE=demo TRUESTATE_LOCAL_DEMO_AUTH=1 python -m uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

Terminal 2 — standard Next.js frontend:

```bash
TRUESTATE_FASTAPI_URL=http://127.0.0.1:8080 pnpm exec next dev frontend --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. FastAPI's interactive API documentation is at `http://127.0.0.1:8080/docs`. No paid services or credentials are required for demo mode. The `.env.example` documents configuration; the server reads environment variables, so load them explicitly with your process manager. Windows users can set the same variables in PowerShell before running these commands.

For the Python API in Docker:

```bash
docker compose up --build
```

This exposes only `127.0.0.1:8080`, persists SQLite in a Docker volume, and explicitly enables local synthetic identity. Run the frontend separately.

## Run the demonstration

1. Ask **Investigate Aster’s suspicious payment**. Watch the real tool activity unfold inside the answer.
2. Ask **Why was it held?** for a plain-language explanation.
3. Ask **Show the evidence graph**, then **Show the signed contract**. Sources remain inside this conversation.
4. Ask **What are the possible explanations?** to inspect competing hypotheses and uncertainty.
5. Ask **Give me the audit report**. Download PDF or JSON from the inline report card.
6. Ask **Try a legitimate bank change**, **Run the failed containment scenario**, or **Run the evaluation**.

To review a payment action, ask “Release this payment.” Enter the financial grounds in the inline review form (or reply “Reason: …”), then confirm the exact payment using the result card or conversation. Cancelling, asking why, or switching to an analyst identity never authorizes a release. Agent holds still use the existing deterministic policy.

Conversations and evidence are stored in your authenticated workspace. If a stream is interrupted, refresh saved state. Ask “Recover interrupted investigation” after 65 seconds to mark an unfinished run for human review. “Reset the demo” asks for confirmation and retains prior conversations, archived cases, and audit history.

See `docs/CONVERSATION.md` for the supported prompt patterns and honest demo limits.

## Tests and evaluation

```bash
node --test tests/engine.test.mjs tests/conversation.test.mjs tests/scope-multimodal.test.mjs
node tests/extraction-smoke.mjs
python -m pytest tests/test_api.py -q
pnpm exec tsc --noEmit
node scripts/evaluate.mjs
```

The evaluation script checks the frozen fixture generator against `datasets/synthetic-v1.json`, records its SHA-256, runs the tools, and writes `docs/evaluation-latest.json`. The UI starts without benchmark results; **Run evaluation** executes a new measurement in your workspace.

Hosted build and Worker integration check (Miniflare, no browser required):

```bash
pnpm run build
node tests/worker-smoke.mjs
```

The tiny synthetic set is a functional check, not evidence of production fraud detection accuracy. Supplier-change rules perform as well as the full workflow on its positive/negative labels. The demo's additional contribution is explicit provenance, explainable source selection, controlled execution, failure handling, and auditability. See `docs/EVALUATION.md`.

## Repository map

```text
app/                    Hosted React interface and Worker API routes
components/conversation/ Inline chat cards and interactive provenance graph
lib/truestate/conversation.ts Natural-language routing, context, confirmation
lib/truestate/scope.ts   Whole-request financial allowlist and rejection policy
lib/truestate/evidence-input.ts Untrusted document validation and field extraction
lib/truestate/multimodal-client.ts On-device PDF extraction and image OCR
app/api/uploads/         Authenticated source upload/download (R2)
scripts/prepare-multimodal.mjs Self-hosted OCR and PDF asset preparation
lib/truestate/engine.ts  Fixtures, event sentinel, tools, policy, holds, evaluation
lib/truestate/store.ts   D1 compare-and-swap persistence and audit writes
db/ + drizzle/          Hosted schema and immutable audit migration
frontend/               Standard Next.js shell for the FastAPI transport
backend/main.py         FastAPI REST, SSE, Pub/Sub receiver, authorization
backend/bridge.mjs      JSON bridge into the shared deterministic engine
backend/models.py       Normalized SQLAlchemy domain schema and projection
backend/repository.py   SQLite/PostgreSQL persistence and optimistic concurrency
backend/adk_agents.py   Six optional real ADK agents; advisory, no action authority
backend/cloud.py        Google Cloud SDK adapters, explicit health states
backend/migrations/     Initial SQLite/PostgreSQL schema snapshots
datasets/               Frozen 120-case synthetic evaluation set
tests/                  Core, API/security, and built Worker integration tests
docs/                   Architecture, cloud setup, API, limitations, demo script
Dockerfile* + compose   Portable demo and optional Cloud Run container recipes
.env.example            Configuration names, no credentials
```

## Security boundary and limits

Demo queue accounts and funds are fictional. Uploaded source files are user-supplied, explicitly unverified, and cannot authorize payment actions. No connector can transfer funds or modify a real bank account. The hosted Site gives each authenticated visitor a separate synthetic workspace with a demo-reviewer role; it is not an enterprise role-management implementation. FastAPI roles are configured server-side by bearer-token mapping. Never expose local demo authentication on a public host.

Risk reasoning and action authority are separate. The demo policy permits agent holds only on a case's own queued payment, with evidence and an eligible assessment, up to ₹10,00,000. Releases require reviewer identity, a written justification, and explicit conversational confirmation. Historical signatures are synthetic assertions. The app does not perform real cryptographic signature, account ownership, or supplier telephone verification.

See `docs/SECURITY.md` and `docs/GOOGLE_CLOUD.md` before adapting this prototype to real data. This is an audit-support tool, not a legal compliance certification or a universal fraud solution.

## Multimodal scope and streaming

Attach up to three financial records per message (8 MB each, 10 PDF pages, 18,000 extracted characters). Ask **Review uploaded documents**. Review the extracted Supplier, Invoice, Account and Amount fields and download the original source from the same card. Select a case/payment and ask **Compare uploaded documents with this payment** for a read-only comparison. Use **Use sample invoice** on the welcome screen to prepare a fictional PDF for review. You can also drag files into the composer or use Attach. The folder button opens saved evidence for reuse. Removing a file from a draft does not delete its stored original.

Image analysis is English OCR of financial documents, not general image understanding. PDFs with text use PDF.js; scanned pages use OCR. Extraction runs on the device and its result is explicitly unverified on the server. No extracted document instruction enters the command router. Unknown or unrelated files are rejected when no supported financial fields can be extracted. Unsupported text is rejected rather than sent to a general model. Voice dictation is available only in browsers with a speech-recognition API, may use that browser’s speech service, and requires reviewing/sending the transcript.

The whole text request must match the server's bounded financial grammar. Finite patterns intentionally reject unsupported paraphrases and mixed requests; adding financial keywords does not authorize generic chat. No safety mechanism claims to infer arbitrary image semantics or prove that a supplied document is authentic. Payment authorization remains a separate deterministic gate.

The SSE stream emits `status`, `response`, `delta`, `state`, `done`, and `error` events. These are deterministic application replies and real workflow progress, not invented LLM tokens. Hosted investigation steps are committed before state emission. The UI shows extraction, upload, and workflow progress and retains explicit failure/retry handling.

Validation covers image OCR, PDF extraction, malformed/injected/unrelated uploads, cross-tenant access, adversarial text requests, and initial SSE delivery before investigation completion. Browser/device visual, touch, virtual-keyboard, keyboard-interaction, and microphone QA were unavailable in the build environment; voice support and permission handling must be checked on the target browser.
