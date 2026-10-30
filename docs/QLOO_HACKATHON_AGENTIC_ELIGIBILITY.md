# Qloo Agentic Hackathon — eligibility assessment

Assessed: 2026-10-27. This is an engineering assessment, not a guarantee of
eligibility; Qloo and Devpost make the final determination.

## Current result: not ready to claim agentic eligibility

CineBridge already makes real backend Qloo calls for title/entity resolution
and deterministic Insights-based shortlists. That is a meaningful Qloo
integration, but the current organizer workflow is not a working agentic tool:

- `api/app/recommendations.py` deterministically resolves entities, filters,
  and ranks candidates. It does not choose tools or pursue a goal iteratively.
- `api/app/programming.py` contains an optional `FilmProgrammingAgent`, but it
  is disabled by default and its experimental bounded loop is not wired into
  the organizer flow.
- The completed DeepSeek experiment found no validated user value from that
  loop and specifically recommends against enabling it in production.

Therefore CineBridge should **not** describe the present build as satisfying
the “agentic” route solely because it uses Qloo or contains experimental agent
code.

The official rules require a working app integrating Qloo that either functions
as an agentic tool, is built with an agent framework, or integrates Qloo into
an existing agent. They also require a functional demo, public source
repository with a visible open-source license, and a deployed externally
accessible demo. See the [official rules](https://qloo.devpost.com/rules) and
[submission page](https://qloo.devpost.com/). The current workspace has a
Docker/localhost workflow, and no `LICENSE*` file was found; external hosting,
public-repository status, and the required visible license are consequently
**unverified or unmet** here.

## Smallest genuinely useful future agent workflow

Do not implement this until the organizer test results justify it.

**Evidence-gap investigator:** after CineBridge's unchanged deterministic
shortlist is generated, an organizer may ask “what evidence supports this
shortlist?” The agent receives only the existing ranked candidates, coverage
state, warnings, resolved Qloo entity types, and approved attendee-reason
summary. It chooses one of three bounded actions:

1. answer from the existing evidence;
2. make **one** read-only Qloo lookup for tags/metadata of an already-resolved
   entity or existing candidate, then return a cited explanation; or
3. abstain and ask one precise clarification when coverage or mapping evidence
   is insufficient.

It can never search for a new candidate, alter eligibility, change a score or
rank, submit a selection, claim rights/availability, or receive raw attendee
identity data. The deterministic resolver remains authoritative.

This is small but useful: it helps an organizer distinguish “we have evidence
for this fit” from “we need another preference,” while demonstrating an actual
goal → tool-choice → tool-result → bounded-answer loop using Qloo. It is more
credible than attaching a decorative chat box or calling Qloo through a model
without a user-facing decision.

## Evidence required before claiming eligibility

- A visible organizer control and a working end-to-end demo of the bounded
  agent workflow.
- Tool transcript showing the agent's reason, one permitted Qloo read, returned
  evidence, and a safe final answer or abstention.
- Tests for no rank changes, unpermitted tool requests, provider failure,
  unresolved mappings, low coverage, and no credentials in the browser/logs.
- Real organizer validation showing whether the clarification/explanation is
  useful; the current experiment is explicitly UNVALIDATED.
- External hosted demo, public repository, and a visible open-source license
  before submission; confirm all requirements against the official rules near
  submission because they may change.

## Recommendation

Run the 3–5 organizer sessions first. If organizers identify a concrete need
for evidence clarification and the results show it improves decision support,
seek approval for the bounded Evidence-gap investigator as a separate,
reviewed change. Otherwise submit CineBridge only after confirming another
valid agentic route; do not force an LLM into the product merely for
eligibility. Production approval remains pending.
