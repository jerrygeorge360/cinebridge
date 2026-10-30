# Recommendation quality audit — 2026-10-26

## Scope and method

This audit examined the reported one-attendee case with the submitted titles
`Death Note`, `AOT`, and `Demon Slayer`. It traced the current adapter and
ranking code, inspected the persisted run's aggregate data, and made a single
redacted live Qloo trace. The trace retained only submitted and returned film
titles, provider identifiers, and safe metadata; it did not retain raw provider
payloads, scores, credentials, or attendee text.

No DeepSeek request was made for this audit. The controlled comparison is
fixture-first, so no conclusion depends on fluent model wording.

## Why *A Dream of Kings* was returned

The original run had one registered, usable, and represented attendee. Its
three submitted interests were assigned equal one-third weight. At that time,
the Qloo search response for `AOT` was accepted as **Behold a Pale Horse**
because the adapter took the first syntactically valid movie result without
checking its title against the submitted text. The first result for that wrong
interest was *A Dream of Kings*.

The two other inputs resolved plausibly: *Death Note* produced *Flatliners* as
its first candidate, and `Demon Slayer` resolved to *Mugen Train* and produced
the *Tsuzumi Mansion Arc* as its first candidate. After eligibility filtering,
each first-place candidate had the same normalized score (`1.0 / 3`). The
engine's documented deterministic tie-breaker then sorted by title, producing:

1. *A Dream of Kings*
2. *Demon Slayer: Kimetsu no Yaiba — Tsuzumi Mansion Arc*
3. *Flatliners*

The order was therefore valid under the algorithm that was running, but it was
not a defensible interpretation of `AOT`.

## Evidence and deterministic correction

The audit's redacted live trace confirmed the defect: an `AOT` search can lead
with an unrelated movie. A full `Attack on Titan` query resolves to the intended
title. Current Qloo candidate order can change over time and is not evidence
about the historical run; raw Qloo responses are intentionally not persisted.

The adapter now accepts a title only when the provider title is an exact
normalized match, or the submitted title is an unambiguous base title followed
by a subtitle delimiter. `Demon Slayer` can therefore resolve to its qualified
movie title, while `AOT` is treated as unresolved rather than silently mapped
to another film. This is an entity-resolution correction, not an anime rule,
year penalty, semantic rejection rule, or scoring change.

The deterministic engine still:

- filters to validated eligible films;
- ignores provider raw scores;
- normalizes positions inside each Qloo query only;
- divides each represented attendee's weight equally over their resolved
  interests; and
- returns a limited or unavailable result where its existing coverage rules
  require it.

An unresolved abbreviation should be re-entered as its full movie title before
an organizer relies on it as evidence.

## Controlled comparison

| Check | A — deterministic engine | B — current DeepSeek-assisted path |
| --- | --- | --- |
| Eligibility and numerical rank | Deterministic and testable | Must be identical; agent has no authority to alter it |
| Death Note / AOT / Demon Slayer case | Exposes the former resolution defect; corrected by the acceptance gate | Receives no extra verified evidence in the current implementation |
| Normal, ambiguous, contradictory, insufficient cases | Covered by deterministic fixtures and failure/coverage tests | No agent-specific fixtures yet for evidence interpretation, clarification, or abstention |
| Explanation | Generic but traceable to rank/coverage rules | Currently the same deterministic fallback |
| Unsupported claims | Avoided by fixed templates and warnings | Avoided only because model prose is ignored |
| Latency/tokens/cost | No DeepSeek cost | One planning call can occur, but no tool result is returned for a second turn |

The existing Film Programming Agent makes one Responses API call, collects any
function-call outputs, and does not send those outputs back in a second turn.
It also ignores model prose. It therefore does not inspect the shortlist,
interpret an anomaly, request clarification, abstain, or improve a user-visible
recommendation. The current verdict is **no demonstrated quality value beyond
the deterministic Qloo engine**.

The agent remains disabled by default while this verdict holds. Re-enabling it
requires fixture coverage for a complete two-turn tool transcript, malformed
arguments, provider failure, clarification/abstention, exact rank invariance,
and zero unsupported factual claims. A future live evaluation must use the same
frozen evidence for A and B, a blind rubric, and a hard cap of 10 calls or
$0.05, whichever happens first.

## Cost record

The redacted Qloo trace made no DeepSeek request. DeepSeek expenditure for this
audit is **$0.00**. The local persisted recommendation-run ledger currently
records 585 input tokens, 44 output tokens, and 228 micro-USD (**$0.000228**)
across five earlier runs. That ledger is a peak, cache-miss model estimate and
does not include standalone Search billing; it must not be treated as an
account-billing statement.

## Release conclusion

Production release remains pending. Before approval, the application still
needs a human review of the corrected ambiguous-title behavior and, if an LLM
agent is reconsidered, evidence that it improves the pre-defined objective
rubric rather than merely producing more persuasive prose.

## Addendum — Lupin/Home Alone multi-attendee run (2026-10-30)

### Evidence boundary

The persisted run artifact available for this audit is run
`cd99632d-8ff4-45fe-8fbe-05e8f9f267fb`, dated 2026-10-27. It records two
registered attendees, two attendees with non-blank usable input, and two
represented attendees. The retained artifact identifies the preference rows,
but not attendee display names or attendee IDs; the safe labels below are the
selected preference titles, not claims about the attendees' names.

| Stored preference row | Selected TMDB record | Persisted Qloo resolution |
| --- | --- | --- |
| Lupin | `96677` (`tv`) | `07BA6A65-209C-4941-AC0A-B6549410A2F8` (`urn:entity:tv_show`) |
| Home Alone | `65282` (`tv`) | unresolved |

The persisted shortlist was:

| Rank | Candidate | Stored support language |
| ---: | --- | --- |
| 1 | *Home Alone 2: Lost in New York* | support from 1 represented attendee |
| 2 | *The Stronghold* | support from 1 represented attendee |
| 3 | *How the Grinch Stole Christmas* | support from 1 represented attendee |

This is candidate-level support, not audience-level coverage. The run-level
`represented_attendee_count = 2` means both registered rows had at least one
title that entered the resolved-interest set. It does not mean every
candidate was returned for, or supported by, both attendees. The stored
candidate rows do not retain the contributor IDs or the interest query that
produced each candidate, so the artifact cannot identify which attendee
supported each one. The candidate explanations are the only persisted
candidate-by-candidate coverage evidence.

### Controlled read-only diagnostics

No production request, live Qloo request, DeepSeek request, ranking change, or
UI change was made for this addendum. The code-path check used the persisted
fields and deterministic adapter tests only. The current deterministic path:

1. uses a persisted Qloo entity ID when one exists;
2. otherwise calls `resolve_title(title_text)` from the free-text preference;
3. gives each represented attendee one unit of weight, divided equally among
   that attendee's unique resolved interests;
4. normalizes positions within each interest query and ignores provider raw
   scores; and
5. records candidate support as the set of represented attendee IDs whose
   query returned that candidate.

The persisted selected-TMDB metadata is used during the initial resolution in
`api/app/main.py`, but `_audience_for_event` passes only title text, enjoyed
text, and Qloo ID into the engine. If the Home Alone row is unresolved, the
engine therefore falls back to a bare free-text resolution in
`api/app/recommendations.py`. The adapter's default for a missing media type
is a movie entity. This is a confirmed canonical-resolution defect. It is a
plausible explanation for a Home Alone movie candidate in the stored
shortlist, but historical causation cannot be proven because raw Qloo
responses and per-interest query provenance were not persisted.

Attendee reasons are persisted and loaded, but `enjoyed_text` is not read by
the ranking or explanation logic. That is a confirmed implementation gap
against the PRD requirement to consider qualities attendees explicitly say
they enjoyed; this audit does not invent a weighting rule for those reasons.
Also, `usable_preference_count` is named as a preference count but currently
counts attendees with at least one non-blank title. This is an observability
and terminology defect, not evidence of a ranking error.

### Regression coverage added

`api/tests/test_recommendations.py` now covers dissimilar groups, similar
groups, candidates supported by only one attendee, missing plus unresolved
preferences, and unequal interest counts. It also contains an explicit
expected-failure regression for the unresolved selected-title re-resolution
defect. Existing tests continue to cover per-query position normalization,
eligibility filtering, provider failure, and low-coverage shortlist behavior.

### Findings and approval-gated follow-up

- Confirmed defect: an unresolved selected canonical title can be re-resolved
  from bare text and lose its TMDB media context during aggregation.
- Confirmed gap: stated attendee reasons do not affect ranking or explanations.
- Limitation: candidate explanations expose support counts but the stored run
  cannot prove per-candidate contributor identity or source query.
- Limitation: the historical run cannot be independently replayed from this
  repository because its raw Qloo payloads and full attendee identifiers are
  not retained.

Separate approval-gated repair task: preserve selected title media/date
metadata and resolution status through the engine boundary, refuse fallback
re-resolution of an explicitly unresolved canonical selection, and persist
candidate contributor/query provenance. A separate product decision is needed
before defining how stated reasons should influence ranking. No repair was
implemented in this audit.
