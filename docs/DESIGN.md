# Design direction and Penpot handoff

## Approval state

The dark, warm, independent-cinema direction is approved. The organizer movie recommendation screen is the first reference screen. Its high-fidelity design does not exist yet and therefore is not approved.

Penpot is the source of truth. No direct Penpot automation or local integration was available during repository setup, so this document is a manual handoff and does not claim that a Penpot file was created.

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
6. Share the Penpot link and exports for human review. Only explicit human approval can complete this stage.

