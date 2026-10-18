# Evaluation contract

The v1 frozen dataset contains 120 synthetic cases: 24 each for legitimate changes, invoice mismatches, coordinated-source manipulation, missing independent evidence, and failed containment. Account identifiers and amounts vary deterministically. They are not independent samples from real fraud incidents.

`node scripts/evaluate.mjs` verifies the generator against the frozen JSON, runs the same tool engine used by the product, and writes a timestamped result with dataset SHA-256. The initial product dashboard contains no measured benchmark scores. A user-triggered API run persists a new result.

## Baselines

1. **Record matching:** flags a case when invoice, ERP, and approval account strings disagree.
2. **Supplier-change rules:** flags a changed account when the independent authorized account/contact does not confirm it.
3. **Provenance only:** flags records that share an origin, without independent verification.
4. **Full workflow:** executes tools, independently verifies, applies policy, attempts a simulated hold, reads state back, and escalates failures.

Baseline flags are treated as proposed holds to count unnecessary holds in legitimate fixtures. They do not actually execute payment actions, so their operational verification/timing metrics are shown as not evaluated.

## Denominators

- Coordinated-risk recall: flagged coordinated fixtures / 24. It is a risk-detection label, not a finding of criminal intent.
- False-positive rate: flagged legitimate-change fixtures / 24.
- Root attribution accuracy: correct shared/non-shared origin determination / 120.
- Retrieval correctness: independent retrieved account values match the fixture's available independent sources / 120.
- Verified outcomes: expected payment state AND unchanged unrelated payments / 120. A legitimate queued payment counts; a failed hold does not.
- Escalation: missing-evidence or failed-containment cases / 120.
- Policy violations: held payments without an authorized policy decision.
- Mean investigation: engine elapsed time measured with a monotonic clock; no UI pacing, network, or paid model calls.
- Mean authorized containment: elapsed milliseconds through the successful action, on successful holds only. The millisecond clock can quantize these very small local operations.

The committed `evaluation-latest.json` is an executed local run. The expected structural result is that simple change-verification rules and the full workflow both detect all coordinated fixtures, while provenance alone also flags legitimate shared-source updates. Full workflow outcome verification is 80% because the failed-containment cohort intentionally remains queued. This dataset does not establish superiority over commercial fraud systems, real-world recall, or calibrated confidence.
