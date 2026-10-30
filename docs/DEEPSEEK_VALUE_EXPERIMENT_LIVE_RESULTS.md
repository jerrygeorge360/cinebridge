# DeepSeek value experiment — decision report

Executed: 2026-10-27, staging workspace only. Production recommendation
behavior, ranking, UI, and release approval remain unchanged.

## Conditions and evidence

All seven redacted frozen scenarios completed the offline A/B/C0/C harness:
28/28 controls passed. Those B/C0/C outputs were intentionally local fixture
responses, so they verify the evidence boundary but do not establish DeepSeek
quality. The full offline ledger is in
`docs/DEEPSEEK_VALUE_EXPERIMENT_OFFLINE_RESULTS.md`.

The live sample used two of those packets: `code-geass-politics-v1` and
`weak-coverage-v1`. A was the unchanged deterministic result; it made no model
call. B received the same frozen packet without tools. C received the same
packet with the bounded read-only tool schemas. No live Qloo, TMDB, search, or
write tool was called.

| Scenario | A | B | C | Interpretation |
| --- | --- | --- | --- | --- |
| Code Geass political strategy | Unchanged authoritative shortlist | Passed the structural/rank checks; appropriately noted absent per-candidate explanation | Rejected: output reached the 250-token cap before completing JSON; its partial text also treated the valid TV-to-movie pipeline as unsupported | C did not add usable value and exposed a failure mode; no result was accepted into CineBridge. |
| Weak coverage | Unchanged authoritative shortlist and warning | Passed; abstained | Passed; abstained | C matched B's safe behavior but made no tool call or extra evidence-based contribution. |

The Code Geass packet preserves the corrected TMDB `255107` `tv` mapping to a
Qloo `urn:entity:tv_show` signal and a movie-only Insights result. The rejected
C text's contrary inference is therefore unsupported by the frozen evidence.

## Integrity checks

- Offline: candidate order, one-tool maximum, allowlist, safe abstention and
  clarification, mapping invariance, and frozen packet digests passed for all
  seven scenarios.
- Live: all four calls named no candidate, rank, or score; no tool request was
  issued. Three schema-valid responses passed. The incomplete fourth response
  was rejected—not truncated, repaired, or used as a recommendation.
- Remaining limitation: the current validator checks structured references and
  explicit rank fields, but cannot prove semantic citation closure for every
  natural-language assertion. This is why the partial C mapping assertion is
  called out manually rather than silently treated as valid.

## Cost, latency, and tool ledger

The one aggregate cap was **$0.15**. Using the official DeepSeek Flash peak
cache-miss rates checked on 2026-10-27 ($0.30/M input and $1.20/M output), the
runner reserved $0.006000 maximum before calls and recorded an actual
token-based estimate of **$0.0014802**. There were 4 model requests, 0 tool
calls, and no retries. Per-call tokens, estimates, latency, redacted actual
responses, and validation status are in
`docs/DEEPSEEK_VALUE_EXPERIMENT_LIVE_RESPONSES.json`. Costs are estimates; no
provider billing export was available.

The live B calls took 2,547 ms and 2,010 ms; C calls took 2,726 ms and 2,152
ms. C consequently cost more tokens and latency in this sample without a
demonstrated improvement over the same-evidence B control.

## Organizer review and recommendation

The label-free worksheet is prepared in
`docs/DEEPSEEK_VALUE_EXPERIMENT_BLIND_REVIEW.md`. No organizer reviewed it, so
there are no scores, no claimed subjective improvement, and no fabricated
reviewer feedback.

**Recommendation: UNVALIDATED — do not enable DeepSeek in production.** The
experiment validates the offline safeguards, but this small live sample shows
no measurable contribution beyond the deterministic baseline or B, no benefit
from C's tool access, and one rejected C response. A new decision would require
real blinded organizer reviews plus a corrected, separately approved live
protocol; it must not use this result to change ranks or release status.
