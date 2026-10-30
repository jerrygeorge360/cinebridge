"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

import {
  PreferenceDraft, registerAttendee, RegistrationDraft, searchTitles, TitleSearchResult, validateRegistrationDraft,
} from "../../event-flow";

const blankPreference = (): PreferenceDraft => ({ titleText: "", enjoyedText: "" });
const initialDraft: RegistrationDraft = { displayName: "", preferences: [blankPreference()] };

type SearchState = {
  results: TitleSearchResult[];
  suggestion: string | null;
  status: "idle" | "loading" | "ready" | "empty" | "error";
  activeIndex: number;
};
const idleSearch = (): SearchState => ({ results: [], suggestion: null, status: "idle", activeIndex: -1 });
const releaseYear = (result: TitleSearchResult) => result.release_year || result.release_date?.slice(0, 4) || "Year unknown";
const mediaLabel = (type: TitleSearchResult["media_type"]) => type === "tv" ? "Series" : "Film";

export default function RegistrationForm({ token }: { token: string }) {
  const [draft, setDraft] = useState<RegistrationDraft>(initialDraft);
  const [searches, setSearches] = useState<Record<number, SearchState>>({});
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const requests = useRef<Record<number, AbortController>>({});

  useEffect(() => () => {
    Object.values(timers.current).forEach(clearTimeout);
    Object.values(requests.current).forEach((request) => request.abort());
  }, []);

  function updateDisplayName(value: string) {
    setDraft((current) => ({ ...current, displayName: value }));
    setError(null);
  }

  function updatePreference(index: number, field: keyof PreferenceDraft, value: string) {
    setDraft((current) => ({ ...current, preferences: current.preferences.map((preference, preferenceIndex) => preferenceIndex === index ? { ...preference, [field]: value } : preference) }));
    setError(null);
  }

  async function fetchTitles(index: number, query: string) {
    const normalized = query.trim();
    if (normalized.length < 2) {
      setSearches((current) => ({ ...current, [index]: idleSearch() }));
      return;
    }
    requests.current[index]?.abort();
    const request = new AbortController();
    requests.current[index] = request;
    setSearches((current) => ({ ...current, [index]: { results: [], suggestion: null, status: "loading", activeIndex: -1 } }));
    try {
      const response = await searchTitles(token, normalized, { signal: request.signal });
      if (requests.current[index] !== request) return;
      setSearches((current) => ({ ...current, [index]: { results: response.results, suggestion: response.suggestion, status: response.results.length ? "ready" : "empty", activeIndex: response.results.length ? 0 : -1 } }));
    } catch (searchError) {
      if (request.signal.aborted || requests.current[index] !== request) return;
      setSearches((current) => ({ ...current, [index]: { results: [], suggestion: null, status: "error", activeIndex: -1 } }));
      setError(searchError instanceof Error ? searchError.message : "Titles are unavailable right now. Try again in a moment.");
    }
  }

  function updateTitle(index: number, value: string) {
    setDraft((current) => ({ ...current, preferences: current.preferences.map((preference, preferenceIndex) => preferenceIndex === index ? { ...preference, titleText: value, tmdbId: undefined, mediaType: undefined, releaseDate: undefined, posterPath: undefined } : preference) }));
    setError(null);
    clearTimeout(timers.current[index]);
    timers.current[index] = setTimeout(() => { void fetchTitles(index, value); }, 260);
  }

  function chooseTitle(index: number, result: TitleSearchResult) {
    clearTimeout(timers.current[index]);
    requests.current[index]?.abort();
    setDraft((current) => ({ ...current, preferences: current.preferences.map((preference, preferenceIndex) => preferenceIndex === index ? { ...preference, titleText: result.title, tmdbId: result.tmdb_id, mediaType: result.media_type, releaseDate: result.release_date, posterPath: result.poster_path || null } : preference) }));
    setSearches((current) => ({ ...current, [index]: idleSearch() }));
    setError(null);
  }

  function clearTitle(index: number) {
    setDraft((current) => ({ ...current, preferences: current.preferences.map((preference, preferenceIndex) => preferenceIndex === index ? blankPreference() : preference) }));
    setSearches((current) => ({ ...current, [index]: idleSearch() }));
  }

  function handleTitleKeyDown(index: number, event: KeyboardEvent<HTMLInputElement>) {
    const search = searches[index];
    if (!search || !search.results.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      setSearches((current) => ({ ...current, [index]: { ...search, activeIndex: (search.activeIndex + direction + search.results.length) % search.results.length } }));
    } else if (event.key === "Enter" && search.activeIndex >= 0) {
      event.preventDefault();
      chooseTitle(index, search.results[search.activeIndex]);
    } else if (event.key === "Escape") {
      setSearches((current) => ({ ...current, [index]: idleSearch() }));
    }
  }

  function addPreference() {
    setDraft((current) => ({ ...current, preferences: [...current.preferences, blankPreference()] }));
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validateRegistrationDraft(draft);
    if (validationError) return setError(validationError);
    setIsSaving(true); setError(null);
    try { await registerAttendee(token, draft); setIsSaved(true); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Your response could not be saved."); }
    finally { setIsSaving(false); }
  }

  if (isSaved) return <div className="registration-card success-card" role="status"><p className="kicker">Response saved</p><h2>Thanks for making room for your taste.</h2><p className="card-copy">Your response is safely with the organizer. You can close this page now.</p><div className="access-note"><span className="note-mark" aria-hidden="true">✦</span><div><strong>Private by design.</strong><br />Your favorites stay in the organizer experience and recommendation process.</div></div></div>;

  return <form className="registration-card" onSubmit={handleSubmit} noValidate>
    <div className="card-heading"><p className="kicker">Attendee registration</p><p className="card-step">02 / 02</p></div>
    <p className="card-intro">A little signal helps the room choose well.</p>
    <label className="field field-wide"><span>Display name</span><input name="displayName" value={draft.displayName} onChange={(event) => updateDisplayName(event.target.value)} placeholder="How should the host recognise you?" maxLength={80} autoComplete="nickname" required /></label>
    <div className="preference-heading"><div><p className="kicker">Favorites · optional · up to three</p><p className="field-help">Search, then choose the exact movie or series. Your note is optional.</p></div><span className="preference-count">{draft.preferences.filter((preference) => preference.titleText.trim()).length} / 3</span></div>
    <div className="preference-list">{draft.preferences.map((preference, index) => {
      const search = searches[index] || idleSearch();
      const selected = Number.isInteger(preference.tmdbId) && preference.mediaType;
      const listboxId = `title-results-${index}`;
      return <div className="preference-row preference-row-search" key={index}>
        <div className="field title-search-field"><span>Favorite {index + 1}</span>
          {selected ? <><div className="selected-title-card">
            {preference.posterPath ? <img src={`https://image.tmdb.org/t/p/w185${preference.posterPath}`} alt="" /> : <span className="selected-title-placeholder" aria-hidden="true">✦</span>}
            <span><strong>{preference.titleText}</strong><small>{preference.mediaType === "tv" ? "Series" : "Film"}{preference.releaseDate ? ` · ${preference.releaseDate.slice(0, 4)}` : ""}</small></span>
            <button type="button" className="change-title" onClick={() => clearTitle(index)} aria-label={`Change ${preference.titleText}`}>Change</button>
          </div>{preference.mediaType === "tv" && <p className="title-resolution-note">Series are saved accurately. This movie-only recommendation engine may not use this pick yet.</p>}</> : <>
            <input name={`favorite-${index + 1}`} value={preference.titleText} onChange={(event) => updateTitle(index, event.target.value)} onKeyDown={(event) => handleTitleKeyDown(index, event)} placeholder={index === 0 ? "Search for a title" : "Add another (optional)"} maxLength={160} autoComplete="off" role="combobox" aria-autocomplete="list" aria-expanded={search.status === "ready"} aria-controls={listboxId} aria-activedescendant={search.activeIndex >= 0 ? `${listboxId}-${search.activeIndex}` : undefined} />
            {search.status === "loading" && <p className="title-search-status" role="status">Searching TMDB…</p>}
            {search.status === "ready" && <div className="title-results" id={listboxId} role="listbox" aria-label={`Title results for favorite ${index + 1}`}>
              {search.suggestion && <button className="title-suggestion" type="button" onClick={() => updateTitle(index, search.suggestion!)}>Looking for <strong>{search.suggestion}</strong>? Search it <span aria-hidden="true">→</span></button>}
              {search.results.map((result, resultIndex) => <button key={`${result.media_type}-${result.tmdb_id}`} id={`${listboxId}-${resultIndex}`} type="button" role="option" aria-selected={search.activeIndex === resultIndex} className={`title-result ${search.activeIndex === resultIndex ? "title-result-active" : ""}`} onMouseEnter={() => setSearches((current) => ({ ...current, [index]: { ...search, activeIndex: resultIndex } }))} onClick={() => chooseTitle(index, result)}>
                {result.poster_url ? <img src={result.poster_url} alt="" /> : <span className="result-poster-placeholder" aria-hidden="true">✦</span>}
                <span><strong>{result.title}</strong><small>{releaseYear(result)} · {mediaLabel(result.media_type)}</small></span><b>Select</b>
              </button>)}
            </div>}
            {search.status === "empty" && <p className="title-search-status">No matching titles. Try the full title or a different spelling.</p>}
            {search.status === "error" && <p className="title-search-status title-search-error">Search is unavailable. You can try again.</p>}
          </>}
        </div>
        <label className="field"><span>What you enjoyed</span><input name={`enjoyed-${index + 1}`} value={preference.enjoyedText} onChange={(event) => updatePreference(index, "enjoyedText", event.target.value)} placeholder={index === 0 ? "e.g. warm ensemble, quiet pacing" : "A short note is enough"} maxLength={500} autoComplete="off" /></label>
      </div>;
    })}</div>
    {draft.preferences.length < 3 && <button className="add-preference" type="button" onClick={addPreference}>+ Add another favorite</button>}
    <div className="access-note"><span className="note-mark" aria-hidden="true">✦</span><div><strong>Your preferences are private.</strong><br />They are used only in the organizer experience and recommendation process.</div></div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <button className="primary-button" type="submit" disabled={isSaving}>{isSaving ? "Saving your response…" : "Save my response"}<span aria-hidden="true">→</span></button>
    <p className="form-footnote">Search results provided by TMDB · no account · no access to anyone else&apos;s response</p>
  </form>;
}
