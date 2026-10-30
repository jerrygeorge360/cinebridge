# Agentic recovery experiment — live attempt ledger

Executed on 2026-10-27, staging-only. The aggregate reservation ceiling was
**$0.10**. Across all attempts, the runner reserved **$0.016800** and received
usage from seven successful DeepSeek responses for an estimated **$0.003272**.
There were ten HTTP attempts in total; three later attempts failed before a
provider response was available. Costs are estimates, not a billing export.

The three frozen live scenarios were a normal anime-reasons case, Code Geass
with weak candidate explanation evidence, and low coverage. The agent made one
actual backend evidence call:

| Scenario | Tool execution | Agent result | Validation |
| --- | --- | --- | --- |
| Anime reasons | No lookup: no resolvable registered evidence gap | Final response supplied no valid reference ID | Rejected |
| Code Geass | No lookup: the model recognized that interest tags would not establish candidate fit | Final response supplied no valid reference ID | Rejected |
| Low coverage | `inspect_audience_coverage` returned the below-threshold coverage and unresolved preference evidence | The final answer used descriptive citations rather than allowed `tool:inspect_audience_coverage` | Rejected |

No live focused Qloo Insights query was selected. Consequently no additional
candidate evidence changed a deterministic shortlist, and no DeepSeek recovery
answer was accepted. The redacted raw provider records, typed tool argument and
result, model usage, latency, and stop reasons are in
`docs/AGENTIC_RECOVERY_LIVE_LEDGER.json`.

This is useful negative evidence: the previous zero-tool result was partly a
test-design limitation, because the revised model did choose and execute the
coverage inspection when it could resolve a specific uncertainty. But the
strict evidence-reference contract prevented that response from becoming a
valid result, and the agent did not demonstrate a recommendation improvement.
Production behavior remains unchanged.
