# Agentic recommendation-recovery experiment — decision report

## Result: PIVOT — do not integrate into CineBridge yet

The experiment built a genuinely bounded investigation loop, but it has not
shown that DeepSeek improves an organizer's recommendation decision beyond
deterministic recovery. The production endpoint, ranking formula, UI, and
release gate remain unchanged; `FILM_AGENT_ENABLED` remains disabled.

## What changed in the experiment

`api/app/recovery_experiment.py` is an experimental-only module with no API
route. It receives an immutable deterministic shortlist and runs at most three
model turns, two read-only lookups, and one focused Qloo Insights query. Its
typed registry validates entity IDs, TMDB media types, candidate membership,
and verified tags. It records tool transcript, observation, decision, usage,
latency, and stopping reason. Invalid requests, new candidates, provider ranks,
and raw scores are rejected.

`query_qloo_focused` now has a backend-only Qloo adapter path. It uses a
verified selected entity as the Insights signal, filters returned evidence to
the already deterministic shortlist, and strips scores/positions. It is not
called by the production endpoint and was not selected in the live sample.

## Why the former experiment had zero tools

The former C sample offered no incremental candidate/tag evidence in the two
live packets, made its tools return only packet content, did not identify a
resolvable uncertainty in the prompt, and correctly let weak coverage abstain.
Zero calls therefore reflected the protocol, not proof that DeepSeek cannot
choose a tool.

## Offline A / C0 / C evidence

The seven frozen scenarios are covered by the existing baseline fixtures and
the new recovery fixture. A remains the immutable deterministic shortlist.
C0 uses transparent fixed rules: it accepts normal evidence, inspects coverage
and abstains for weak coverage, and asks clarification for conflict/ambiguous
cases. The mocked C loop proves valid two-lookup transcripts, typed media/tag
validation, maximum-three-turn/two-lookup/one-focused-query limits, rejection
of invented entities/candidates/scores/ranks, and safe abstention.

The offline controls establish mechanics, not DeepSeek usefulness or real Qloo
quality. They do not change a candidate, rank, score, or eligibility decision.

## Live evidence

The staging live attempt is recorded in
`docs/AGENTIC_RECOVERY_LIVE_RESULTS.md` and the full redacted ledger.

- DeepSeek made one meaningful tool choice: in the low-coverage scenario it
  called `inspect_audience_coverage`. The backend returned the actual frozen
  evidence: below-threshold sparse coverage and an unresolved preference.
- It made no tool call for normal anime reasons, which is appropriate when
  there is no registered resolvable gap.
- For Code Geass it declined a tag lookup because interest tags cannot prove
  thematic fit for the existing movie candidates. That is a defensible
  limitation, but it did not retrieve new evidence.
- All final live outputs were rejected. The first two omitted required stable
  evidence-reference IDs; the coverage result used narrative citations instead
  of `tool:inspect_audience_coverage`. Three subsequent provider attempts
  failed before a response. No response influenced CineBridge.
- No focused Qloo Insights query ran live, so no real Qloo recovery evidence
  was collected. No recommendation was improved or changed.

## Cost and latency

The aggregate ceiling was $0.10. The runner reserved $0.016800 maximum across
ten HTTP attempts. Seven responses reported token usage totaling an estimated
**$0.003272**. Individual response latency and token totals are recorded in the
ledger. This excludes any billing-export confirmation and did not make a Qloo
focused-query call.

## Comparison and recommendation

| Condition | Outcome |
| --- | --- |
| A — deterministic CineBridge | Continues to provide the authoritative candidate universe, eligibility, coverage, and rank. |
| C0 — deterministic recovery | Handles the frozen coverage/conflict/ambiguity cases predictably with the same read-only evidence boundary. |
| C — DeepSeek recovery | Demonstrated one appropriate coverage lookup, but no accepted final decision, focused Qloo investigation, or improvement over C0. |

There are no independent organizer scores; none are invented. The result is a
**PIVOT**, not a GO: retain the experimental module and improve the *protocol*
before spending more credits—use structured JSON-schema enforcement for exact
evidence IDs, record provider failures separately from calls, and run one
pre-registered live Code Geass focused-query case only after confirming the
backend Qloo response shape. Then repeat the blinded organizer comparison.

Do **not** integrate or enable the agent in production based on this evidence.
Production approval is pending.
