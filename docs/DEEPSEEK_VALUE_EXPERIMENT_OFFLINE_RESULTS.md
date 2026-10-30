# DeepSeek value experiment — offline run record

Run date: 2026-10-27 (staging workspace only)
Experiment: `cinebridge-deepseek-value-v1`
Frozen-packet set: `api/tests/fixtures/deepseek_value_experiment_v1.json`
Set SHA-256: `01e2c67791f2b09e7198dac61687265df0edf58b6dc5deb1bfc2aca8692bd8ec`

## Scope and result

All seven synthetic, redacted frozen packets completed the **offline harness**
for A, B, C0, and C (28 condition/scenario records). No DeepSeek, Qloo, TMDB,
or other network provider was contacted. The B, C0, and C messages are local
fixture responses used to test the contract and tool boundary; they are not
DeepSeek responses and cannot demonstrate model value.

Consequently the decision after this run is **UNVALIDATED**. It is not a GO,
PIVOT, or NO-GO result: no actual model comparison or organizer review exists.
Production remains pending and unchanged.

## Packet ledger

| Scenario | SHA-256 | A | B / C0 offline control | C offline control | Expected safe outcome |
| --- | --- | --- | --- | --- | --- |
| `anime-reasons-v1` | `3a1323640f50688f69b0067cc7bfaf1127dbb47507c2885b5dabc644d7d1a65c` | passed | passed; no tools | passed; no tools | brief |
| `code-geass-politics-v1` | `3d034a983dd0137aa3f2532e37d5a9f63916094efdcdf841263acc332e249042` | passed | passed; no tools | passed; no tools | brief |
| `split-club-25-15-v1` | `3b9eca3b830e208c792c27a2d4f5c5ae48fd04ddc0f64e5417906a4d1859cfc5` | passed | passed; no tools | passed; no tools | brief |
| `weak-coverage-v1` | `9d70e454ebfc8b9a3cfa032881fbfedb0f1339fef4c7f1440797837e6ba38831` | passed | passed; no tools | passed; no tools | abstain |
| `contradictory-preferences-v1` | `1b803f77879c2e824188558b02e99a31d175e7e04a24391f93c6bfd0abb118fa` | passed | passed; no tools | passed; no tools | clarification needed |
| `surprising-defensible-v1` | `c096cf8ac3443c0abe565ce61277e69cb4fd29ae352e836adff4789fb4a8de2d` | passed | passed; no tools | passed; one `inspect_movie_metadata` fixture lookup | brief |
| `ambiguous-title-v1` | `e578dc42c93a11d3e3a918f967eebe0a73678ec9de03dc7a68b917183b9ac748` | passed | passed; no tools | passed; no tools | clarification needed |

The Code Geass packet asserts TMDB `255107` as `tv`, Qloo lookup and accepted
entity type `urn:entity:tv_show`, and an Insights request from that TV entity
to a movie-only result set. The former movie substitution is not present.

## Automated checks and cost ledger

- A preserved every deterministic shortlist and original candidate order.
- B and C0 used the exact frozen packet, made no lookup, and emitted only
  schema-valid local fixture output.
- C made zero or one allow-listed read; the only tool transcript was the
  synthetic `inspect_movie_metadata` lookup in `surprising-defensible-v1`.
- Weak coverage produced `abstain`. Contradictory and ambiguous cases produced
  `clarification_needed`.
- Fixture prose deliberately names no candidate, rank, or score, so it cannot
  nominate or reorder a candidate.
- Code Geass mapping and ambiguous historical `AOT` separation were asserted
  independently.
- Actual provider calls: 0. Actual provider tokens: 0. Actual spend: **$0.00**.
- The fixture harness reported 82 input and 16 output *simulated* tokens for C
  controls only; at the code's test pricing this is $0.0000438 simulated cost.
  It is neither billed nor counted against the $0.15 aggregate live cap.
- Actual latency: not applicable (local in-process stubs). Tool latency: not
  applicable. Stop reason: offline harness completed.

## Important validation boundary

This run verifies the known schema, allow-list, one-tool bound, mapping fixture,
safe abstention/clarification responses, and frozen-order path. It does **not**
prove that arbitrary natural-language model prose has semantic citation closure:
the current JSON validator checks evidence-reference identifiers and prohibited
JSON fields, but does not parse every factual assertion inside prose. Likewise,
it rejects structured `rank`/`score` fields but does not semantically detect a
rank claim hidden in arbitrary prose. No unsupported claim was present in the
controlled fixture responses, so none was accepted during this run.

This is a validation gap to record before live spend; it is not evidence that
DeepSeek provides value. The bounded loop also requires an aggregate budget
ledger around multiple live calls: its current `max_cost_usd` applies to an
individual run.

## Blinded organizer materials

The reviewer worksheet is in
[`DEEPSEEK_VALUE_EXPERIMENT_BLIND_REVIEW.md`](DEEPSEEK_VALUE_EXPERIMENT_BLIND_REVIEW.md).
It contains no labels that identify A, B, C0, or C and no pre-filled scores.
No organizer reviewer has been recruited or scored this experiment.
