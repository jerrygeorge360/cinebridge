# Agentic recommendation-recovery experiment

## Scope

This is a staging-only evaluation of whether an evidence-gathering agent can
make a more useful recovery decision than fixed rules when a deterministic
CineBridge shortlist is weakly explained, surprising, or incomplete. It is not
a production feature. The normal recommendation endpoint, ranking algorithm,
candidate universe, organizer selection flow, UI, and release gate are
unchanged. `FILM_AGENT_ENABLED` remains disabled for normal use.

The factory's current `film-programming-change-review` stage is already gated
for human approval. This experiment is recorded separately and does not amend
or approve that stage.

## Why the previous experiment made no tool calls

The previous live C sample used Code Geass and low-coverage packets that did
not expose incremental tag/candidate evidence. Its tool executor returned only
the already supplied packet and deliberately made no Qloo query. The prompt
also did not require the model to identify a resolvable uncertainty. Low
coverage correctly abstained. Therefore zero calls measured the constrained
test design, not DeepSeek's inability to choose a tool.

## Experimental workflow

1. The existing deterministic Qloo engine produces its usual immutable
   shortlist.
2. The recovery agent receives a bounded organizer objective, attendee reasons,
   coverage/mapping evidence, and that shortlist.
3. It either finishes, asks for clarification/abstains, or selects one typed,
   read-only evidence action.
4. The backend validates arguments, executes the action, records its result,
   and supplies it to a subsequent model turn.
5. The agent may take at most two lookups across at most three model turns,
   then returns `accept_existing_shortlist`, `clarification_needed`, or
   `abstain` with evidence references and a stopping reason.

The agent cannot create, rank, select, remove, or reorder candidates. A
focused Qloo query is restricted to verified entity IDs and verified theme tags
and may only return evidence about existing shortlist members. Provider scores
are never accepted or compared across Qloo queries.

## Typed tool registry

| Tool | Validated inputs | Evidence returned | Hard limit |
| --- | --- | --- | --- |
| `inspect_qloo_themes` | Existing Qloo entity ID and its matching `movie`/`tv` media type | Registered verified Qloo tags | Read-only |
| `inspect_movie_evidence` | Existing deterministic candidate title | Registered candidate metadata/evidence | Read-only |
| `query_qloo_focused` | Existing verified entity, matching media type, subset of registered tags, bounded question | Registered focused-Qloo evidence for existing candidates only | One query; no ranking/score/new candidate |
| `inspect_audience_coverage` | No arguments | Existing coverage and unresolved-preference evidence | Read-only |

## Conditions and success criteria

- **A:** existing deterministic result.
- **C0:** the same registry, using transparent fixed triggers.
- **C:** DeepSeek dynamically chooses the permitted lookup or stops.

All conditions preserve the exact deterministic candidate snapshot. Automated
checks cover tool allowlists, argument validation, entity media type, verified
tags, lookup/turn/query caps, transcript integrity, no raw-score use,
clarification/abstention, and immutable candidates/ranks. Human relevance is
only assessed through the existing blinded organizer materials after real
participants take part.

## Cost and release controls

Offline fixtures and mocked responses run first. Any live DeepSeek run uses a
single external aggregate ledger capped at **$0.10**, including every retry.
It records model, turns, calls, redacted arguments/results, usage, latency, and
estimated cost. No provider credentials or raw attendee identifiers enter the
fixture, transcript, or report.

No outcome from this experiment enables production behavior. Production
approval remains pending.
