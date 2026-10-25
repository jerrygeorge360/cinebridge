# Product requirements

## Purpose

CineBridge helps independent film clubs and themed-screening organizers select a film for a registered audience with different interests. It recommends one film and two alternatives, explains the choices, and leaves the decision with the organizer. It never promises that an attendee will enjoy a film.

## MVP users and flows

### 1. Organizer creates an event

The organizer enters an event name, theme, date, and essential details. CineBridge creates an unguessable public registration link and a separate unguessable private management link. No organizer account is required.

### 2. Attendee registers

An attendee opens the public link, enters a display name, and may optionally provide up to three favorite movies or shows plus what they enjoyed about them. Registration requires no account. Preferences are private to the organizer experience and recommendation process.

### 3. Organizer chooses a film

The organizer opens the private management link, reviews registration count and usable preference coverage, and requests recommendations. CineBridge returns one top pick and two alternatives. “Why this movie?” gives a plain-language explanation and relevant warnings. The organizer selects the final film. Automatic announcement is not required.

## Recommendation policy

Future implementation will:

1. Resolve supported interest titles with Qloo.
2. Apply event and film eligibility constraints before ranking.
3. Request rankings for represented interests or audience groups.
4. Normalize positions within each Qloo ranking query.
5. Combine normalized ranks using the number of attendees represented.
6. Consider qualities attendees explicitly say they enjoyed.
7. Return one film and two alternatives with understandable explanations and warnings.

The system must not combine incomparable raw affinity scores across queries, claim cultural similarity proves enjoyment, automatically override the majority to favor a minority, or fabricate results when Qloo has insufficient coverage or fails.

## MVP boundaries

Included: event creation, separate public/private links, attendee registration, preference coverage, three recommendation candidates, explanations, warnings, and organizer film selection.

Excluded: payments, ticketing integrations, organizer accounts, analytics dashboards, custom ML, automatic announcements, screening-rights verification, and unrelated discovery features. Organizers remain responsible for screening rights.

## Acceptance criteria

- Public and private event access use distinct, securely random tokens.
- A public visitor cannot access management data or attendee preferences.
- Attendee favorites and explanations are optional and limited as defined above.
- Qloo credentials never reach the browser or repository.
- Failed or low-coverage Qloo requests produce an honest unavailable/limited result, not invented films.
- Every successful recommendation contains exactly one top pick and two alternatives, an explanation path, and relevant warnings.
- The organizer alone chooses the final film; no automatic announcement occurs.
- Inputs are validated, sensitive values are not logged, and request limits protect public endpoints.
- The application can run as one Docker-compatible instance with persistent SQLite storage.
- Responsive customer-facing screens use natural language and one dominant action per screen.

