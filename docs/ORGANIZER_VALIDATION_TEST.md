# CineBridge organizer validation test

## Purpose and guardrails

Run this short, moderated staging test with **3–5 real film-club organizers**.
It tests whether they can complete the event-to-recommendation workflow and
whether the deterministic result is relevant, understandable, and trustworthy.
It also compares a deterministic explanation with a DeepSeek explanation using
the same frozen evidence.

This is research, not a production release. Use only fictional attendee names
and the scenarios below. Do not collect personal attendee preferences, store
participants' contact details in this repository, or tell participants that
the model explanation is more accurate. Do not claim this test has occurred
until completed result sheets contain real participant feedback.

The submitted recommendation remains deterministic. The organizer makes the
film choice; do not ask them to rely on an agent or imply that screening rights
or availability were checked.

## Participants and setup

- Recruit 3–5 people who have organized, programmed, or regularly helped
  choose films for a club, screening series, campus society, or similar group.
- Schedule a 30-minute remote or in-person session per person.
- Use a disposable staging database and the running staging site. Confirm that
  the participant sees a public registration URL and a separate private
  management URL.
- Record feedback only in
  `docs/ORGANIZER_VALIDATION_RESULTS.md` using an anonymous ID such as `P01`.
- Explain at the start: “This is an early tool for narrowing a club's options.
  It does not decide the film, guarantee taste, availability, or rights.”

## Four realistic scenarios

Run the first two with every participant. Assign one of the remaining two so
that the group covers all four without making any single session too long.

| ID | Fictional attendee input | What it tests | Safe expected behavior |
| --- | --- | --- | --- |
| S1 — anime motivations | Three attendees select *Death Note* (moral cat-and-mouse), *Attack on Titan* (survival stakes), and *Demon Slayer* (family/catharsis). | Different reasons behind superficially adjacent interests. | One pick, two alternatives, warnings, and no claim that similarity proves enjoyment. |
| S2 — political strategy | One attendee selects TMDB TV title *Code Geass: Rozé of the Recapture* and writes “political strategy and moral conflict.” | Correct TV-to-Qloo mapping and honest explanation limits. | The selection remains TV; no silent movie substitution. The organizer sees a deterministic movie shortlist and any coverage/explainability limit. |
| S3 — split club | 25 attendees prefer quiet character drama; 15 prefer action spectacle. | A real group trade-off. | Surface majority/minority coverage without inventing consensus or silently overriding either group. |
| S4 — thin/ambiguous evidence | One attendee enters historical free text “AOT”; another preference is unresolved; eligible coverage is sparse. | Failure handling and trust. | State limitation, request clarification or present a limited/unavailable result. Do not manufacture confidence. |

Use the frozen equivalents in `api/tests/fixtures/deepseek_value_experiment_v1.json`
for the explanation comparison. For the working workflow, enter only the
fictional inputs above through the interface; do not edit rankings or seed
provider results by hand.

## Session script (25–30 minutes)

1. **Context — 2 minutes.** Ask what kind of club they organize and how they
   currently choose a film. Do not ask for names, email addresses, or real
   attendee preferences.
2. **Create event — 4 minutes.** Ask the participant to create a fictional
   event, name its audience/theme, and identify which link is safe to share
   publicly. Ask: “What do you think each link lets someone do?”
3. **Register attendees — 6 minutes.** Have the facilitator or participant use
   the public link to add the assigned fictional attendees, their selected
   titles, and optional reasons. Observe title selection, mobile/responsive
   clarity if a phone is available, and whether the participant understands
   that a selected title is canonical rather than free text.
4. **Request recommendations — 6 minutes.** Open the private management link,
   review coverage, request the shortlist, and ask the participant to narrate
   what they think the top pick, alternatives, warnings, and “why” information
   mean. Ask them to make a hypothetical final selection, but do not announce
   it.
5. **Blinded explanation comparison — 6 minutes.** Follow the next section.
6. **Wrap-up — 4 minutes.** Ask the questions below, capture their answers,
   and thank them. Do not promise a release date or feature changes.

## Blinded deterministic-versus-DeepSeek comparison

Use only a scenario where both pieces are valid. The available live DeepSeek B
responses for `code-geass-politics-v1` and `weak-coverage-v1` are in
`docs/DEEPSEEK_VALUE_EXPERIMENT_LIVE_RESPONSES.json`; both passed validation.
Do **not** use the rejected Code Geass C output: it was incomplete and made an
unsupported mapping inference.

For each participant:

1. Capture the current deterministic explanation from the scenario's
   organizer result without changing candidate order.
2. Pair it with the corresponding validated live B explanation from the ledger.
   Both must refer to the identical packet and deterministic shortlist.
3. Randomly label the two excerpts `X` and `Y`; alternate their order between
   participants. Keep the mapping in the facilitator's private notes, not in
   the participant-facing sheet.
4. Do not say “AI,” “DeepSeek,” “deterministic,” or which one was shown in the
   application. Ask the participant to rate each excerpt and choose `X`, `Y`,
   “no preference,” or “insufficient information.”
5. Reveal neither label until every session is complete. Aggregate only real
   scores; a tie or preference for fluent prose is not evidence that rankings
   improved.

The existing generic worksheet remains available at
`docs/DEEPSEEK_VALUE_EXPERIMENT_BLIND_REVIEW.md`. This protocol adds the
workflow context and the constraint that invalid model outputs are excluded.

## Questions

Use 1 (strongly disagree) to 5 (strongly agree), followed by “why?”

1. I could tell which link was for attendees and which was for the organizer.
2. The attendee preference entry made it likely that the intended title was
   submitted.
3. The shortlist felt relevant to the stated group preferences.
4. The coverage/warning information made the recommendation's limits clear.
5. The explanation helped me understand the trade-offs without overstating
   certainty.
6. I would trust this result enough to use it as an input to a club discussion.
7. I would be willing to use CineBridge for a real event, subject to checking
   screening rights separately.
8. For anonymous explanation `X` and `Y`: which is more useful for making a
   programming decision, if either? What specific evidence makes it better?
9. What was confusing, missing, or potentially misleading?
10. If the system had limited coverage or an unresolved title, what should it
    do next?

## Success and stop criteria

This is formative research; it has no pre-filled pass score. Record actual
results before making claims. Stop and mark the scenario as a product concern
if a participant cannot distinguish public/private access, interprets an
explanation as rights/availability confirmation, or believes a low-coverage
result is certain. Keep production approval pending regardless of outcome.
