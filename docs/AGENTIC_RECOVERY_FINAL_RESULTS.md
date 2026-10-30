# Final agentic-recovery protocol experiment

Status: staging-only. Production recommendation behavior, ranking, eligibility,
UI, release status, and the normal DeepSeek setting remain unchanged.

## Preregistration

One live Code Geass investigation was permitted, with a new DeepSeek aggregate
cap of $0.02 and no retries. The selected item was TMDB `255107` as `tv`,
resolved to Qloo `60FC0842-480F-478E-86D2-B4E3E64B75BF`
(`urn:entity:tv_show`). The initial deterministic movie shortlist was frozen:

1. *Konosuba!: God's Blessing on This Wonderful World! - Legend of Crimson*
2. *Is It Wrong to Try to Pick Up Girls in a Dungeon - Arrow of the Orion*
3. *Demon Slayer: Kimetsu no Yaiba - The Movie: Mugen Train*

The verified selected-entity theme subset was `Political`, `Military strategy`,
`Moral ambiguity`, and `Political intrigue`. Qloo scores and provider ordering
from focused reads were discarded; neither arm could change the initial list.
The machine-readable record is
`docs/AGENTIC_RECOVERY_FINAL_LIVE_LEDGER.json`.

## Earlier rejection classification

| Earlier result | Confirmed classification | Evidence | Conclusion |
| --- | --- | --- | --- |
| First three recovery records without captured provider bodies | Indeterminate beyond local `invalid_final_response` | The old ledger records the validator stop but no raw body. | Do not infer JSON, reasoning, or token failures retrospectively. |
| Captured anime recovery result | Missing evidence IDs | It was syntactically valid JSON but `evidence_refs` was `[]`. | Output-protocol failure. |
| Captured Code Geass recovery result | Missing evidence IDs; unsupported inventory inference | It was syntactically valid JSON but `evidence_refs` was `[]`; it also asserted that no permitted tool could inspect the gap without trying the newly relevant focused-query path. | Protocol failure plus an untested reasoning assertion. |
| Captured weak-coverage recovery result | Invalid evidence-reference format | It called the coverage tool, but returned descriptive strings rather than the required stable `tool:inspect_audience_coverage` ID. | Output-protocol failure; the underlying coverage observation was supported. |
| Later recovery provider attempts | Provider unavailable | No response body or usage was recorded. | Availability failure, not a model-output classification. |
| Earlier DeepSeek value-experiment Code Geass C result | Token truncation and unsupported claim | The response ends mid-JSON exactly at its 250-token output ceiling; it also claimed TV-to-movie cultural affinity was unsupported, although that is the intended Qloo flow. | Both protocol/output-limit and reasoning failures. |

## Protocol change and offline verification

The experiment now asks the provider for `json_schema` structured output with
all five fields required: decision, observation, uncertainty, evidence
references, and stopping reason. Locally, an answer is accepted only when it
uses one or more real, stable references already available in the packet or
tool transcript. It cannot nominate a candidate, add a score, or rerank.

The offline recovery suite passed 13 tests, including schema emission,
reference closure, invalid references, invalid tool arguments, tool limits,
focused-query validation, media-type validation, and shortlist/rank invariance.

## Live comparison

The fixed C0 comparator performed the preregistered theme inspection followed
by one focused Qloo read. The focused read returned all three already-frozen
shortlist titles and no candidate-level rationale, scores, or ranking data.
It therefore produced no new evidence that any particular candidate fits the
organizer's political-strategy/moral-conflict reason.

The DeepSeek arm independently selected the same two permitted reads—first
`inspect_qloo_themes`, then `query_qloo_focused`—without a forced tool choice.
This is genuine model-driven tool selection. Its final answer was structurally
valid under the enforced schema and cited `packet:scenario`,
`tool:inspect_qloo_themes`, and `tool:query_qloo_focused`. It abstained because
the focused read merely repeated the immutable shortlist and did not supply
candidate-level thematic evidence. However, the free-text observation also
called the candidates “fantasy/action anime films”; no permitted evidence
contained candidate genre metadata. The post-run factual audit therefore did
not approve that conclusion as evidence-grounded. No ranking change was
accepted.

| Measure | C0 | DeepSeek recovery agent |
| --- | --- | --- |
| Reads | theme inspection + one focused Qloo read | independently chose the same two reads |
| New candidate-level support | none | none |
| Recommendation/rank changed | no | no |
| Final stance | accepted the existing list under its fixed rule | abstained, but the free-text conclusion was not approved after factual audit |
| Model calls | 0 | 3 |
| DeepSeek tokens / estimated cost | 0 / $0 | 4,760 input + 491 output / $0.0020172 |
| Agent latency | n/a | 10,451 ms |

The total reservation was $0.005040, below the $0.02 cap. Actual estimated
spend was $0.0020172. This is an estimate based on recorded provider usage,
not billing data.

## Decision: NO-GO for submission integration

The structured-output change did fix the demonstrated protocol failures, and
the agent made a conservative, model-driven investigation. But its free-text
output still introduced an unsupported genre assertion, which the factual audit
rejected. The focused Qloo read added no candidate-level evidence, improved no
shortlist, and did not establish recommendation relevance beyond the
deterministic baseline. The only practical difference was that the agent
declined to turn candidate enumeration into support. That is not enough
evidence of product value to justify adding agentic recovery for this
submission.

Stop further agent-development iterations for this submission. Keep DeepSeek
disabled in normal operation and retain deterministic recommendations. A later
experiment would need a provider-supported source of candidate-level evidence
and independent organizer evaluation before a new integration decision.
