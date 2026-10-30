"use client";

import { FormEvent, useMemo, useState } from "react";

import {
  createEvent,
  EventCreationResponse,
  EventDraft,
  getLocalTodayIso,
  validateEventDraft,
} from "./event-flow";

const initialDraft: EventDraft = {
  name: "",
  theme: "",
  screeningDate: "",
  essentialDetails: "",
};

function LinkCard({
  label,
  note,
  url,
  privateLink = false,
}: {
  label: string;
  note: string;
  url: string;
  privateLink?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  async function copyLink() {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className={`link-card${privateLink ? " link-card-private" : ""}`}>
      <div>
        <p className="link-label">{label}</p>
        <p className="link-note">{note}</p>
      </div>
      <div className="link-row">
        <a href={url} className="link-value">
          {url.replace(/^https?:\/\//, "")}
        </a>
        <button className="copy-button" type="button" onClick={copyLink}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

export default function Home() {
  const [draft, setDraft] = useState<EventDraft>(initialDraft);
  const [createdEvent, setCreatedEvent] = useState<EventCreationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const today = useMemo(() => getLocalTodayIso(), []);

  function updateDraft(field: keyof EventDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validateEventDraft(draft, today);
    if (validationError) {
      setError(validationError);
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      setCreatedEvent(await createEvent(draft));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The event could not be created.");
    } finally {
      setIsSaving(false);
    }
  }

  if (createdEvent) {
    return (
      <main className="site-shell">
        <header className="topbar">
          <a className="wordmark" href="/">CineBridge</a>
          <p className="context-tag"><span aria-hidden="true" /> Organizer setup</p>
        </header>
        <section className="handoff-layout" aria-labelledby="handoff-title">
          <div className="handoff-intro">
            <p className="eyebrow">The room is ready</p>
            <h1 id="handoff-title">Two links. Two kinds of access.</h1>
            <p className="lede">
              Share the registration link with guests. Keep the management link somewhere only
              the organizer can reach.
            </p>
            <div className="quiet-note">
              <span aria-hidden="true" />
              No account required. Save both links before you leave this page.
            </div>
          </div>
          <div className="handoff-card">
            <div className="event-summary">
              <p className="kicker">{createdEvent.theme}</p>
              <h2>{createdEvent.name}</h2>
              <p>{createdEvent.screening_date} · {createdEvent.essential_details}</p>
            </div>
            <div className="link-stack">
              <LinkCard
                label="Registration link"
                note="Public · share with attendees"
                url={createdEvent.public_registration_url}
              />
              <LinkCard
                label="Management link"
                note="Private · keep for the organizer"
                url={createdEvent.private_management_url}
                privateLink
              />
            </div>
            <p className="fine-print">CineBridge supports the choice. It does not guarantee enjoyment or verify screening rights.</p>
            <button className="secondary-button" type="button" onClick={() => setCreatedEvent(null)}>
              Create another event
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="site-shell">
      <header className="topbar">
        <a className="wordmark" href="/">CineBridge</a>
        <p className="context-tag"><span aria-hidden="true" /> Organizer setup</p>
      </header>

      <section className="setup-layout" aria-labelledby="setup-title">
        <div className="setup-intro">
          <p className="eyebrow">Before the first frame</p>
          <h1 id="setup-title">Plan a movie night.</h1>
          <p className="lede">
            Set the scene, then give your guests a private place to share what they enjoy
            watching. The final choice stays with you.
          </p>
          <div className="film-frame" aria-hidden="true">
            <div className="film-frame-top"><span /> <span /> <span /></div>
            <div className="frame-copy"><span>CB / 01</span><strong>Make room<br />for every taste.</strong></div>
            <div className="film-frame-bottom"><span /> <span /> <span /></div>
          </div>
        </div>

        <form className="setup-card" onSubmit={handleSubmit} noValidate>
          <div className="card-heading">
            <p className="kicker">Event setup</p>
            <p className="card-step">01 / 02</p>
          </div>
          <p className="card-intro">A few details are all the room needs.</p>

          <div className="field-grid">
            <label className="field field-wide">
              <span>Event name</span>
              <input name="name" value={draft.name} onChange={(event) => updateDraft("name", event.target.value)} placeholder="e.g. Sunday Film Club" maxLength={120} autoComplete="off" required />
            </label>
            <label className="field">
              <span>Theme</span>
              <input name="theme" value={draft.theme} onChange={(event) => updateDraft("theme", event.target.value)} placeholder="e.g. Tender science fiction" maxLength={120} autoComplete="off" required />
            </label>
            <label className="field">
              <span>Screening date</span>
              <input name="screeningDate" type="date" min={today} value={draft.screeningDate} onChange={(event) => updateDraft("screeningDate", event.target.value)} required />
            </label>
            <label className="field field-wide">
              <span>Essential details</span>
              <textarea name="essentialDetails" value={draft.essentialDetails} onChange={(event) => updateDraft("essentialDetails", event.target.value)} placeholder="Venue, timing, accessibility…" maxLength={1000} rows={3} required />
            </label>
          </div>

          <div className="access-note">
            <span className="note-mark" aria-hidden="true">✦</span>
            <div><strong>Two links, two contexts.</strong><br />CineBridge creates a public registration link and a separate private management link.</div>
          </div>

          {error && <p className="form-error" role="alert">{error}</p>}

          <button className="primary-button" type="submit" disabled={isSaving}>
            {isSaving ? "Creating event…" : "Create event"}<span aria-hidden="true">→</span>
          </button>
          <p className="form-footnote">No account required · links are unguessable and stay separate</p>
        </form>
      </section>
    </main>
  );
}
