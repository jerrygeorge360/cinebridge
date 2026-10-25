# Design direction and Penpot handoff

## Approval state

The dark, warm, independent-cinema direction is approved. The organizer movie recommendation screen is the first reference screen. Its high-fidelity design does not exist yet and therefore is not approved.

Penpot is the source of truth. The external AI Factory now uses the globally configured Penpot Cloud MCP provider to create, inspect, and repair editable boards. This document does not claim that a board exists until its checkpoint metadata records the real board IDs and credential-free share URL.

## Direction

- Mostly dark, cinematic, warm, simple, thoughtful, and visually distinctive.
- Strong film imagery and editorial typography with restrained wine-red and warm accents.
- High contrast, clear hierarchy, minimal cognitive load, and one main action per screen.
- Responsive layouts that preserve the film image, recommendation hierarchy, and action clarity.
- Natural language: “Plan a movie night,” “What do you enjoy watching?”, “Here’s our top pick,” “Why this movie?”, and “Choose this movie.”

An earlier unapproved Figma draft received two positive reviews and one criticism that it felt too muted for a film product. Treat that as feedback: use stronger imagery, contrast, and a few expressive editorial moments without adding clutter.

## Visual anti-goals

Avoid generic AI-SaaS styling, glowing gradients, needless glass effects, card grids, heavy shadows, decorative noise, technical customer language, overloaded movie grids, complicated dashboards, and competing primary actions.

## First reference screen: organizer recommendation

Create desktop and mobile frames in Penpot (starting frames: 1440 × 1024 and 390 × 844).

The screen should contain:

1. A quiet top bar with CineBridge, event context, and private-management context without exposing the token.
2. A compact audience-coverage line that says how many attendees supplied usable preferences and surfaces low-coverage warnings.
3. A dominant top-pick composition with one strong film image, title, essential eligibility details, a short audience-fit explanation, and a restrained confidence/coverage warning where needed.
4. One primary action, “Choose this movie,” and one subordinate explanation action, “Why this movie?”.
5. Two clearly secondary alternatives shown without turning the page into a movie grid.
6. A plain reminder that CineBridge supports the choice; it does not guarantee enjoyment or verify screening rights.

On mobile, keep the top pick and main action above the alternatives. Preserve readable image cropping, avoid sticky elements that obscure content, and use full-width actions where appropriate.

## Starting design language

Use these as working Penpot tokens, not as a newly approved color system:

- Canvas: near-black brown `#120F10`.
- Raised surface: warm charcoal `#1D191A`.
- Primary text: warm ivory `#F4EBDD`.
- Secondary text: muted sand `#B9AA98` with accessible contrast.
- Wine accent: `#8A3046`, reserved for selection and the main action.
- Warm highlight: `#D7A96B`, used sparingly for metadata or focus.
- Display typography: expressive, film-poster-adjacent serif; body and controls: highly legible sans serif. Use locally available or properly licensed fonts.
- Corners and shadows: restrained; imagery, type scale, spacing, and contrast should carry the design.

## Penpot workflow and approval gate

1. Create a CineBridge design file and a page named `Reference — Organizer recommendation`.
2. Define color, typography, spacing, and radius tokens before composing the frames.
3. Build reusable top-pick, alternative, warning, and action components.
4. Test long titles, missing imagery, low preference coverage, and Qloo-unavailable states.
5. Review desktop and mobile frames against the PRD and anti-goals.
6. Export and validate evidence, then present the Penpot link and exports for human review. Only explicit human approval can complete this stage.

## Review evidence contract

The factory validates real review evidence; it does not treat prose or an agent claim as a design artifact. The persisted internal sequence is create, review, repair when defects are open, export/validate, and human approval. Creation requires `provider`, a credential-free `penpot_url`, `desktop_board_id`, `mobile_board_id`, stable export paths, and `workflow_status: created`; PNG files are deliberately not required yet. Review records `review.defects`, repair closes open defects, and final evidence uses `workflow_status: ready_for_human_review`.

For the first gate, the exact exports are `docs/design/organizer-recommendation-desktop.png` and `docs/design/organizer-recommendation-mobile.png`. Penpot Cloud MCP can render shapes for review, but its remote export tool does not provide a reliable repository file-save path. If automation cannot save authentic PNGs, the factory stops after the export attempt and requests only those two manual exports before revalidation. It never fabricates files or weakens the validator.

The later core-flow gate uses `docs/design/core-responsive-flows.json`, `docs/design/core-responsive-flows-desktop.png`, and `docs/design/core-responsive-flows-mobile.png` with the same phased contract. Ready-for-review markers never mean approved; approval remains an explicit factory gate.
