# Multi-attendee recommendation audit

## Stored evidence

The 2026-10-27 run `cd99632d-8ff4-45fe-8fbe-05e8f9f267fb` recorded two registered, usable, and represented attendees. Lupin was TMDB `96677` (`tv`) and resolved to Qloo `07BA6A65-209C-4941-AC0A-B6549410A2F8` (`urn:entity:tv_show`). The selected Home Alone record was TMDB `65282` (`tv`) and remained unresolved.

The shortlist was Home Alone 2: Lost in New York, The Stronghold, and How the Grinch Stole Christmas. Each stored explanation says support from one represented attendee. This is candidate coverage, not total run coverage: `represented_attendee_count` for the run is two.

## Pipeline finding

The recommendation service constructs its own title-key resolution map from attendee title text, then aggregates one normalized Qloo position list per resolved entity. A member has total weight 1.0, divided equally across unique resolved interests. Candidate points are the sum of normalized positions; missing candidates do not receive zeroes. Ties are contributor count, title, then entity ID. Provider affinity scores are discarded.

This permits an unresolved selected canonical preference to be re-resolved from free text during aggregation. That is a confirmed canonical-resolution defect. Raw Qloo result payloads and per-candidate query provenance were not stored, so the precise source of Home Alone 2 cannot be proven retrospectively.

Attendee reasons are persisted but do not enter the deterministic ranking service.

## Conclusion

The interface wording is technically correct but can be misread: it reports candidate support rather than overall audience representation. No ranking formula defect was established. The separately registered canonical-preference aggregation repair must preserve the formula while using persisted canonical Qloo resolution and storing contributor provenance.
