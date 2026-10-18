# TRUESTATE conversation

The interface keeps investigations, explanations, evidence, payments, reports, and evaluations in one chat. The sidebar contains conversation history, not product-section navigation. Source records and tool receipts can be expanded inline.

## Prompt examples

| Goal | Ask |
|---|---|
| Uploaded financial records | Review uploaded documents |
| Compare uploaded account | Compare uploaded documents with this payment |
| Inputs and scope | Show platform scope |
| Overview | Give me a simple overview |
| Investigation | Investigate Aster’s suspicious payment |
| Plain-language finding | Why was it held? |
| Provenance | Show the evidence graph |
| Exact document | Show the signed contract |
| Competing explanations | What are the possible explanations? |
| Next step | What should I do next? |
| Record escalation | Request human verification |
| Report | Give me the audit report |
| Payment filters | Show queued payments above 5 lakh |
| More payments | Show the next 20 payments |
| Case selection | Show TS-1042 |
| Payment selection | Show PAY-02081 |
| Reviewer action | Release this payment |
| Action reason | Reason: Confirmed through our pre-established supplier contact |
| Action confirmation | Confirm release PAY-02081 |
| Cancel action | Cancel this action |
| Scenario selection | Show me the five demo scenarios |
| Legitimate example | Try a legitimate bank change |
| Mismatch example | Run the invoice manipulation scenario |
| Missing sources | Run the insufficient evidence scenario |
| Failure example | Run the failed containment scenario |
| Evaluation | Run the evaluation |
| Evaluation explanation | Explain those results simply |
| Environment | Which integrations are connected? |
| Source download | Download the project |
| Reset | Reset the demo, then Confirm reset when asked |
| Recovery | Recover interrupted investigation (after 65 seconds) |

## Context and persistence

Each conversation retains its selected case/payment, last result topic, payment pagination filters, and any pending confirmation. New conversations start without the previous thread’s focus. A structured copy of each turn is stored in the existing tenant-scoped database aggregate. The browser stores only the selected conversation ID as a display preference. Reset archives working cases while retaining chats and audit history.

Answers and interactive cards use actual records and computed outcomes. Historical text reflects its original turn; case/payment/report cards show their current recorded state. Evidence IDs refer to stored claims. Unknown or out-of-scope requests receive an explicit refusal. The entire request must match a supported financial task; generic questions are not answered, including after a valid financial conversation.

## Demo scope

The chat is a bounded English natural-language command router, not an LLM or a general-purpose ChatGPT integration. It supports the illustrated financial tasks and common wording variations. It extracts labeled supplier/payment fields from supported uploaded financial documents. It does not offer general image interpretation, browse the web, send supplier messages, transfer real funds, or provide unrestricted financial advice. Google ADK/Gemini adapters remain separate, optional advisory integrations and are not connected in the hosted environment.

Automated holds follow the existing independent evidence and policy checks. Manual holds/releases require a reviewer, one active payment, a written reason, and a matching affirmative confirmation. Negated or mismatched confirmations do not execute. Requested human verification records an audit event; it does not send an external message.

## Inputs and scope enforcement

Use **Attach evidence** for PDF, PNG, JPG, WebP, TXT or CSV records. Limits: 3 files per message, 8 MB per file, 10 PDF pages, 18,000 extracted text characters, 30 stored files / 64 MB per workspace. English OCR runs on-device with self-hosted assets. Progress reflects extraction and upload operations. Browser dictation produces editable text; it is never submitted automatically.

Supported field labels include `Supplier:`, `Invoice:`, `Account:` and `Amount:`. The parser is intentionally bounded and does not promise reliable extraction from every layout. Files without recognizable financial fields are rejected. Original bytes are private and tenant-scoped; the server supplies a SHA-256 and checks file signature, size and type. Text files are parsed from original bytes. PDF/OCR text is client-generated and explicitly unverified; it cannot trigger or authorize a payment action. Files referenced by saved conversations are retained with that history.

All messages, voice transcripts and attachment-review prompts pass through the same server scope grammar before routing. A whole request must match. “For my invoice, tell me a joke” is rejected. Roleplay and instruction overrides are not scope exceptions. Context cannot convert a general question into an allowed task. Upload content is data only, with no tool authority; recognized instruction-injection text is rejected. Unknown paraphrases fail closed and show supported financial suggestions.

Reviewer reasons use a bounded vocabulary for financial verification. Example: “Reason: Confirmed the account through our trusted supplier contact.” Scope rejection clears pending confirmations; reviewer identity and current payment state are independently rechecked before any later action.
