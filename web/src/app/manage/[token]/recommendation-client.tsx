"use client";

import { useEffect, useState } from "react";

import {
  PrivateEventResponse,
  RecommendationCandidate,
  RecommendationResponse,
  formatCandidateMetadata,
  getAudienceExplanation,
  getCoverageSummary,
  getRecommendationActionLabel,
  getSignalLabel,
  requestRecommendations,
  selectFinalFilm,
} from "../../event-flow";

type RecommendationExperienceProps = {
  token: string;
  event: PrivateEventResponse;
  initialRecommendation: RecommendationResponse | null;
};

function FilmPoster({ candidate, compact = false }: { candidate: RecommendationCandidate; compact?: boolean }) {
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => {
    setImageFailed(false);
  }, [candidate.poster_url]);
  const showImage = Boolean(candidate.poster_url) && !imageFailed;
  const artworkLabel = showImage
    ? `Artwork for ${candidate.title}`
    : `Placeholder artwork for ${candidate.title}`;

  return (
    <div className={`film-poster ${showImage ? "film-poster-has-image" : ""} ${compact ? "film-poster-compact" : ""}`} data-artwork-state={showImage ? "verified" : "placeholder"} aria-label={artworkLabel}>
      {showImage && <img className="film-poster-image" src={candidate.poster_url ?? undefined} alt={`Poster for ${candidate.title}`} onError={() => setImageFailed(true)} />}
      {!showImage && <>
      <div className="poster-sky" />
      <div className="poster-moon" />
      <div className="poster-glow poster-glow-left" />
      <div className="poster-glow poster-glow-right" />
      <div className="poster-figure poster-figure-one" />
      <div className="poster-figure poster-figure-two" />
      <div className="poster-reeds poster-reeds-one" />
      <div className="poster-reeds poster-reeds-two" />
      <div className="poster-placeholder-copy">
        {!compact && <span className="poster-label">Artwork unavailable</span>}
        <strong>{candidate.title}</strong>
        <small>Placeholder for this film</small>
      </div>
      </>}
    </div>
  );
}

function AlternativeCard({
  candidate,
  selected,
  disabled,
  onSelect,
}: {
  candidate: RecommendationCandidate;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`alternative-card ${selected ? "alternative-card-selected" : ""}`}
      type="button"
      onClick={onSelect}
      disabled={disabled}
      aria-pressed={selected}
      aria-label={selected ? `${candidate.title} selected` : `Choose ${candidate.title}`}
    >
      <FilmPoster candidate={candidate} compact />
      <span className="alternative-copy">
        <strong>{candidate.title}</strong>
        <span className="alternative-meta">{formatCandidateMetadata(candidate)}</span>
        <span className="alternative-description">{candidate.fit_explanation}</span>
      </span>
      <span className="alternative-action" aria-hidden="true">{selected ? "Selected" : "Choose"}</span>
    </button>
  );
}

function UnavailableState({
  recommendation,
  isGenerating,
  error,
  onRequest,
}: {
  recommendation: RecommendationResponse | null;
  isGenerating: boolean;
  error: string | null;
  onRequest: () => void;
}) {
  return (
    <section className="recommendation-empty" aria-live="polite">
      <p className="eyebrow">Your recommendation</p>
      <h1>Let’s find the room’s film.</h1>
      <p>{recommendation?.message || "This private recommendation workspace is ready when you are."}</p>
      <div className="unavailable-note">
        <span className="note-mark" aria-hidden="true">●</span>
        <span>{recommendation?.warning || "No candidate films are shown without a complete, provider-backed shortlist."}</span>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary-button recommendation-request" type="button" onClick={onRequest} disabled={isGenerating}>
        {isGenerating ? "Finding a shortlist…" : getRecommendationActionLabel(recommendation)}
        <span aria-hidden="true">→</span>
      </button>
    </section>
  );
}

export default function RecommendationExperience({
  token,
  event,
  initialRecommendation,
}: RecommendationExperienceProps) {
  const [recommendation, setRecommendation] = useState(initialRecommendation);
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectingRank, setSelectingRank] = useState<1 | 2 | 3 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const runRequest = async () => {
    setError(null);
    setIsGenerating(true);
    try {
      setRecommendation(await requestRecommendations(token));
      setWhyOpen(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Recommendations could not be generated.");
    } finally {
      setIsGenerating(false);
    }
  };

  const chooseFilm = async (rank: 1 | 2 | 3) => {
    if (!recommendation || recommendation.selection) return;
    setError(null);
    setSelectingRank(rank);
    try {
      const result = await selectFinalFilm(token, rank);
      setRecommendation({ ...recommendation, selection: result.selection });
    } catch (selectionError) {
      setError(selectionError instanceof Error ? selectionError.message : "The final film could not be selected.");
    } finally {
      setSelectingRank(null);
    }
  };

  if (!recommendation || !recommendation.top_pick || recommendation.status === "unavailable") {
    return (
      <main className="recommendation-shell">
        <header className="topbar recommendation-topbar">
          <a className="wordmark" href="/">CineBridge</a>
          <div className="event-context"><span>{event.name}</span><span className="event-context-divider">/</span><span>{event.theme}</span></div>
          <p className="context-tag"><span aria-hidden="true" /> Organizer view · Private</p>
        </header>
        <UnavailableState recommendation={recommendation} isGenerating={isGenerating} error={error} onRequest={runRequest} />
        <RecommendationFooter />
      </main>
    );
  }

  const coverage = getCoverageSummary(recommendation);
  const topPick = recommendation.top_pick;
  const allCandidates = [topPick, ...recommendation.alternatives];
  const selectedRank = recommendation.selection?.rank ?? null;
  const selectedTitle = recommendation.selection?.title;

  return (
    <main className="recommendation-shell">
      <header className="topbar recommendation-topbar">
        <a className="wordmark" href="/">CineBridge</a>
        <div className="event-context"><span>{event.name}</span><span className="event-context-divider">/</span><span>{event.theme}</span></div>
        <p className="context-tag"><span aria-hidden="true" /> Organizer view · Private</p>
      </header>

      <section className="coverage-bar" aria-label="Audience preference coverage">
        <span className="coverage-signal" aria-hidden="true" />
        <strong>{coverage.summary}</strong>
        {coverage.warning && <span className="coverage-warning">{coverage.warning}</span>}
      </section>

      {isGenerating && <p className="analysis-progress" role="status">Checking audience coverage, cultural affinity, and evidence…</p>}

      <section className="recommendation-heading" aria-labelledby="recommendation-title">
        <p className="eyebrow">Your recommendation</p>
        <h1 id="recommendation-title">
          <span className="heading-desktop">A roomful of tastes. One thoughtful choice.</span>
          <span className="heading-mobile">Here’s our top pick</span>
        </h1>
      </section>

      {selectedTitle && (
        <div className="selection-banner" role="status">
          <span className="selection-check" aria-hidden="true">✓</span>
          <span><strong>{selectedTitle}</strong> is the final film for this private workspace. No announcement was sent.</span>
        </div>
      )}

      <section className="recommendation-grid" aria-label="Film recommendations">
        <article className="top-pick-card">
          <div className="top-pick-poster">
            <FilmPoster candidate={topPick} />
          </div>
          <div className="top-pick-details">
            <p className="kicker">Here’s our top pick</p>
            <h2>{topPick.title}</h2>
            <p className="film-meta">{formatCandidateMetadata(topPick)}</p>
            <p className="film-summary">{topPick.fit_explanation}</p>
            <div className="explanation-block">
              <p className="explanation-label">Why it fits this audience</p>
              {whyOpen && <p className="explanation-detail">{getAudienceExplanation(topPick)}</p>}
            </div>
            <div className={`signal-note ${recommendation.status === "limited" ? "signal-note-limited" : ""}`}>
              <span className="signal-note-dot" aria-hidden="true" />
              <div><strong>{getSignalLabel(recommendation.status)}</strong><span>{topPick.warning_text}</span></div>
            </div>
            {recommendation.programming_brief && (
              <section className="programming-brief" aria-label="Film Programming Brief">
                <p className="explanation-label">Film Programming Brief</p>
                <p className={`agent-status agent-status-${recommendation.programming_brief.agent_activity}`}>
                  {recommendation.programming_brief.agent_activity === "agent_tool_loop"
                    ? `DeepSeek inspected verified evidence in ${recommendation.programming_brief.model_turns} turns; the deterministic ranking remains unchanged`
                    : recommendation.programming_brief.agent_activity === "agent_provider_unavailable"
                      ? "DeepSeek was unavailable; the deterministic briefing was retained"
                      : recommendation.programming_brief.agent_activity === "agent_limits_exceeded"
                        ? "DeepSeek reached its staging budget; the deterministic briefing was retained"
                        : recommendation.programming_brief.agent_activity === "agent_rejected_output"
                          ? "DeepSeek output was rejected; the deterministic briefing was retained"
                          : recommendation.programming_brief.agent_activity === "agent_requested_shortlist"
                    ? "DeepSeek requested the shortlist; the deterministic ranking remains unchanged"
                    : recommendation.programming_brief.agent_activity === "agent_checked_shortlist"
                      ? "Historical brief: DeepSeek requested the shortlist; the deterministic ranking remains unchanged"
                    : recommendation.programming_brief.agent_activity === "agent_no_action"
                      ? "DeepSeek responded without requesting more evidence"
                      : "Deterministic Qloo result — no DeepSeek call used"}
                </p>
                <p>{recommendation.programming_brief.summary}</p>
                <button className="explanation-toggle" type="button" onClick={() => setEvidenceOpen((open) => !open)} aria-expanded={evidenceOpen}>Evidence & sources <span aria-hidden="true">→</span></button>
                {evidenceOpen && <div className="evidence-details"><p>Qloo-backed shortlist: {recommendation.programming_brief.tools_used.includes("inspect_shortlist") ? "requested by DeepSeek; deterministic ranking retained" : "deterministic ranking retained"}.</p><ul>{recommendation.programming_brief.tradeoffs.map((tradeoff) => <li key={tradeoff}>{tradeoff}</li>)}</ul><p className="brief-uncertainty">{recommendation.programming_brief.uncertainty}</p>{recommendation.programming_brief.sources.map((source) => <p key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>{source.date ? ` · ${source.date}` : ""}</p>)}</div>}
              </section>
            )}
            {error && <p className="form-error" role="alert">{error}</p>}
            <button
              className="primary-button choose-button"
              type="button"
              onClick={() => chooseFilm(1)}
              disabled={Boolean(recommendation.selection) || selectingRank !== null}
            >
              {selectedRank === 1 ? "Selected as final film" : selectingRank === 1 ? "Selecting…" : "Choose this movie"}
              <span aria-hidden="true">→</span>
            </button>
            <button className="explanation-toggle" type="button" onClick={() => setWhyOpen((open) => !open)} aria-expanded={whyOpen}>
              Why this movie? <span aria-hidden="true">→</span>
            </button>
          </div>
        </article>

        <aside className="alternatives-panel" aria-labelledby="alternatives-title">
          <p className="kicker">Also worth your room</p>
          <h2 id="alternatives-title">Two nearby choices</h2>
          <p className="alternatives-intro">Strong fits with a different emotional temperature.</p>
          <div className="alternative-list">
            {allCandidates.slice(1).map((candidate) => (
              <AlternativeCard
                key={candidate.rank}
                candidate={candidate}
                selected={selectedRank === candidate.rank}
                disabled={Boolean(recommendation.selection) || selectingRank !== null}
                onSelect={() => chooseFilm(candidate.rank)}
              />
            ))}
          </div>
          <div className="shortlist-note">
            <p className="explanation-label">About this shortlist</p>
            <p>Eligibility was applied before audience fit. CineBridge supports your decision — you still make the call.</p>
          </div>
        </aside>
      </section>

      <RecommendationFooter />
    </main>
  );
}

function RecommendationFooter() {
  return (
    <footer className="recommendation-footer">
      <span>CineBridge supports the choice. It does not guarantee enjoyment or verify screening rights.</span>
      <span>Private organizer workspace · No attendee preferences are shown</span>
      <span>This product uses the TMDB API but is not endorsed or certified by TMDB.</span>
    </footer>
  );
}
