# A concrete differentiated workflow, not a uniqueness claim

The candidate differentiator is the combination of three observable behaviors in one vendor-change workflow:

1. **Evidence independence accounting.** A scanned invoice, an exported email quoting it, and a derivative document are not automatically treated as three independent sources. Declared ancestry, content hashes, and authenticated connector identities determine conservative independent-origin counts.
2. **Evidence-bound decision leases.** Decisions expire and bind the exact inputs. A policy insertion or source attestation change can invalidate an earlier decision even if the transaction amount is unchanged. A reviewer changing the disposition invalidates older action requests on the same evidence.
3. **Automatic reassessment with execution receipts.** Updates enqueue reassessment through a durable SQL outbox. Report storage or BigQuery failures resume the committed assessment instead of silently substituting data. Connected-system receipts distinguish requested, failed, rejected and executed actions.

These are implemented behaviors and covered by repository tests. They are not a verified claim that no existing platform offers similar capabilities. Existing products already automate investigations and legal workflows, including [Trustmi](https://www.trustmi.ai/resource/fraud-investigation-automation) and [Ironclad](https://ironcladapp.com/news/press-releases/ironclad-launches-new-ai-agents-grounded-in-commercial-context/). A patent, novelty, or exhaustive market claim would require separate research.

The current scope is deliberately concrete: supplier-payment evidence and policy checks. It does not eliminate every task performed by financial, security, or legal departments. It automates ingestion, extraction, retrieval, specialist assessment, decision gating, reassessment, analytics, report assembly and event dispatch; missing evidence, conflicts and organization-specific external actions still require a configured policy or integration.

The REA skill was inspected. Its instructions exclude ordinary source repository analysis, so this work used normal source, SDK and repository tools. It did not pretend to reverse-engineer a binary or extract a proprietary platform. Existing Google open-source orchestration and managed services are reused instead of rebuilt.
