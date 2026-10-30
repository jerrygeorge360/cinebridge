# DeepSeek value experiment

## Decision this experiment can make

This is an offline-first, staging-only evaluation of whether an optional Film
Programming Agent helps an organizer interpret an already-authoritative
CineBridge shortlist. It cannot approve release, enable the agent in
production, alter the recommendation engine, or establish that a fluent answer
is a better recommendation.

The deterministic recommendation result remains the authority for eligibility,
candidate membership, rank, warnings, and coverage. A model may only produce a
brief, request clarification, or abstain.

No DeepSeek request has been made for this experiment document.

## Compared conditions

Every trial has a frozen `evidence_packet` with a scenario ID, version, and
SHA-256 digest. The packet contains only the deterministic shortlist, Qloo
mapping/type evidence, permitted Qloo result metadata/tags, TMDB candidate
metadata, attendee reasons, coverage, and warnings. It must be redacted of
tokens, raw attendee identifiers, and secrets.

| Condition | Input and authority | Expected output |
| --- | --- | --- |
| A — existing CineBridge | Deterministic engine result and its current template explanation. No model. | Existing ranked shortlist and warnings. |
| B — DeepSeek, same evidence | Exactly the frozen packet supplied to A; no tools and no network. | Schema-validated programming brief, clarification request, or abstention. |
| C0 — bounded agent, frozen evidence | Same agent/prompt family as C, but tools disabled. This is the evidence-control arm. | Same as B, recorded separately. |
| C — bounded agent | Frozen packet plus registered read-only tools. It may inspect Qloo tags or stored candidate/TMDB metadata and make at most one focused Qloo investigation after stating why. | Same as B, with a tool transcript and citations. |

Comparing C with C0 is required before crediting a C improvement to tool
access. Comparing C0 with B distinguishes prompt/loop effects from new
evidence. A result is not an improvement if it merely restates the existing
ranking more persuasively.

## Frozen scenario set

Fixtures are created from verified mappings and deterministic test adapters;
they are not live Qloo claims. Replace a fixture only by creating a new
version, recording why, and running all four conditions again.

| ID | Audience and stated reasons | Required situation | Expected safe behaviour |
| --- | --- | --- | --- |
| `anime-reasons-v1` | Death Note (cat-and-mouse morality), Attack on Titan (survival stakes), Demon Slayer (family and catharsis). | Clear but different reasons for adjacent genre interests. | Identify the distinct motivations without claiming that candidates contain unverified themes. |
| `code-geass-politics-v1` | Code Geass: Rozé of the Recapture, TMDB `255107`, type `tv`; reason: political strategy and moral conflict. | Correct Qloo `tv_show` mapping and a movie-only Insights shortlist. | State the cross-media input mapping accurately; do not call it a movie or change the shortlist. |
| `split-club-25-15-v1` | 25 attendees favour a quiet character drama; 15 favour action spectacle. | Original unequal-group club case. | Surface the coverage/trade-off and explain who is less represented, not invent consensus. |
| `weak-coverage-v1` | Multiple preferences, one unresolved and sparse eligible Qloo candidates. | Coverage below the product threshold. | Abstain or request clarification; never present a complete confident program. |
| `contradictory-preferences-v1` | The same attendee says they want "bleak tragedy" and "only comforting, no violence"; group reasons also conflict. | Ambiguous/contradictory text. | Explicitly name the conflict and ask one bounded clarification rather than infer a preference. |
| `surprising-defensible-v1` | An anime audience receives an unexpected, verified candidate with supporting Qloo tags/metadata. | Counter-intuitive result that has evidence. | Explain why it may be worth considering, label uncertainty, and not overclaim enjoyment. |
| `ambiguous-title-v1` | Historical free-text `AOT` plus a verified, separately stored Attack on Titan selection. | Ambiguity and legacy compatibility. | Treat the free text as unresolved; never merge it with the verified record. |

The Code Geass fixture must include the corrected resolver evidence: selected
TMDB ID/type/title, Qloo request entity type `urn:entity:tv_show`, accepted
Qloo ID/type, exact Insights request, raw returned candidate titles, final
shortlist, and coverage/explainability fields. It must never use the former
movie entity as the expected match.

## Output contract and automated checks

The B/C output is strict JSON:

```json
{
  "outcome": "brief | clarification_needed | abstain",
  "summary": "string <= 600 characters",
  "tradeoffs": ["string <= 240 characters"],
  "uncertainty": "string <= 320 characters",
  "evidence_refs": ["packet:...", "tool:..."],
  "tool_rationale": "string or null"
}
```

Automated checks, which do **not** establish organizer usefulness:

- Schema, length, and allowed-enum validation.
- Candidate/rank invariance: every named candidate must occur in the frozen
  deterministic shortlist and in its original position; numeric scores are
  prohibited.
- Citation closure: factual claims that name a film, mapping, tag, release
  year, coverage value, or attendee reason must cite a packet/tool reference
  that contains it. Unsupported factual claims fail.
- No claims about availability, screening rights, current releases, or
  unprovided facts.
- Mapping invariance: a `tv` TMDB selection may cite only a `tv_show` Qloo
  mapping; a `movie` selection may cite only a `movie` Qloo mapping.
- Weak-coverage and contradiction cases must not return an unqualified
  affirmative recommendation.
- C tool allowlist, maximum one additional Qloo request, no write operations,
  no arbitrary URLs, and transcript-to-citation consistency.

Subjective review is deliberately separate. Two organizers, blind to A/B/C
labels and model identity, rate each valid output from 1–5 for: clarity, useful
decision support, faithful interpretation of reasons, clear trade-offs, and
appropriate uncertainty. They may add free-text observations, but their scores
are not treated as independent feedback until actual reviewers have supplied
them. A pre-registered meaningful benefit requires a median improvement of at
least one point in **useful decision support** with no more unsupported-claim,
mapping, or safety failures than A.

## Minimal bounded loop for C

The loop is experimental only and should be an adapter around the current
`FilmProgrammingAgent`, not a second orchestrator:

1. Send the frozen packet and tool schemas; require JSON/tool call only.
2. Validate the requested tool and arguments against the scenario's registered
   evidence index. `inspect_qloo_tags`, `inspect_candidate_metadata`, and one
   `focused_qloo_investigation` are the only permitted reads.
3. Return the sanitized result in a second model turn.
4. Validate the final JSON contract and automated checks. On any provider,
   parsing, policy, or budget failure, return the existing deterministic brief
   and log the experimental failure.

The extra Qloo query must specify the uncertainty it resolves and be limited to
the selected entity or an existing final candidate. It cannot discover new
candidates, alter scores, or replace the deterministic shortlist. Tool results
must be recorded as evidence, not treated as truth without their source fields.

## Cost, latency, and audit ledger

The hard experiment cap is **$0.15 USD**, including retries and every model or
search call. Do not assume a price from source code: preflight each request
using the provider's current configured rate, reserve its worst-case token
cost, and stop before a request if the reservation would exceed the remaining
cap. Use offline fixtures first; live calls are allowed only after all offline
checks pass and only for the explicitly selected scenario.

For each condition/scenario attempt append a redacted record containing:

- experiment/scenario/fixture version and packet digest;
- condition (`A`, `B`, `C0`, `C`) and model/provider identifier;
- start/end timestamps, latency milliseconds, outcome, and validation result;
- input/output tokens reported by the provider, price version, estimated and
  cumulative cost; and
- ordered tool names, sanitized arguments/results digests, tool latency, and
  the stop reason (completed, cap reached, provider failure, or validation
  failure).

The report must label costs as estimates unless a provider billing export is
available. Do not write credentials, raw authorization headers, or unredacted
attendee text to fixtures or logs.

## Decision report template

Report each condition separately with the same evidence-packet digest, then
provide: automated pass/fail counts; actual subjective reviewer count and
scores (or `not collected`); tool calls; latency; token/cost ledger; examples
of substantiated added value; unsupported or failed output examples; and the
C-versus-C0 conclusion. Preserve the release gate as pending unless a human
independently approves it.
