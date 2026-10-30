export type EventDraft = {
  name: string;
  theme: string;
  screeningDate: string;
  essentialDetails: string;
};

export type EventCreationResponse = {
  name: string;
  theme: string;
  screening_date: string;
  essential_details: string;
  public_registration_url: string;
  private_management_url: string;
};

export type PublicEventResponse = Omit<
  EventCreationResponse,
  "public_registration_url" | "private_management_url"
>;

export type PrivateEventResponse = PublicEventResponse & {
  registered_count: number;
  usable_preference_count: number;
  represented_attendee_count: number;
  selection: SelectionSummary | null;
};

export type RecommendationCandidate = {
  rank: 1 | 2 | 3;
  title: string;
  release_year: number | null;
  runtime_minutes: number | null;
  content_rating: string | null;
  languages: string[];
  fit_explanation: string;
  warning_text: string;
  poster_url?: string | null;
};

export type SelectionSummary = {
  rank: 1 | 2 | 3;
  title: string;
};

export type RecommendationResponse = {
  status: "succeeded" | "limited" | "unavailable";
  registered_count: number;
  usable_preference_count: number;
  represented_attendee_count: number;
  warning_code: string | null;
  warning: string;
  message: string;
  top_pick: RecommendationCandidate | null;
  alternatives: RecommendationCandidate[];
  selection: SelectionSummary | null;
  programming_brief?: ProgrammingBrief | null;
};

export type ProgrammingSource = { title: string; url: string; date: string | null };
export type ProgrammingToolObservation = {
  name: string;
  arguments: Record<string, unknown>;
  observation: Record<string, unknown> | null;
  status: "executed" | "rejected";
};
export type ProgrammingBrief = {
  status: "ready" | "clarification_needed" | "unavailable";
  summary: string;
  tradeoffs: string[];
  uncertainty: string;
  sources: ProgrammingSource[];
  tools_used: string[];
  evidence_refs: string[];
  tool_observations: ProgrammingToolObservation[];
  model_turns: number;
  agent_activity: "deterministic_only" | "agent_requested_shortlist" | "agent_checked_shortlist" | "agent_no_action" | "agent_tool_loop" | "agent_provider_unavailable" | "agent_rejected_output" | "agent_limits_exceeded";
};

export type SelectionResponse = {
  message: string;
  selection: SelectionSummary;
};

export type PreferenceDraft = {
  titleText: string;
  enjoyedText: string;
  tmdbId?: number;
  mediaType?: "movie" | "tv";
  releaseDate?: string | null;
  posterPath?: string | null;
};

export type RegistrationDraft = {
  displayName: string;
  preferences: PreferenceDraft[];
};

export type RegistrationResponse = {
  message: string;
};

export type TitleSearchResult = {
  tmdb_id: number;
  media_type: "movie" | "tv";
  title: string;
  release_date: string | null;
  release_year: number | null;
  poster_url: string | null;
  poster_path?: string | null;
};

export type TitleSearchResponse = {
  results: TitleSearchResult[];
  suggestion: string | null;
};

export type EventApiFetcher = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export function getLocalTodayIso(): string {
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${today.getFullYear()}-${month}-${day}`;
}

export function validateEventDraft(draft: EventDraft, today = getLocalTodayIso()): string | null {
  if (!draft.name.trim()) return "Give the event a name.";
  if (!draft.theme.trim()) return "Add a theme so the night has a point of view.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.screeningDate) || draft.screeningDate <= today) {
    return "Choose a future screening date.";
  }
  if (!draft.essentialDetails.trim()) return "Add the practical details guests need.";
  return null;
}

export function validateRegistrationDraft(draft: RegistrationDraft): string | null {
  if (!draft.displayName.trim()) return "Tell the host how to recognise you.";
  if (draft.displayName.trim().length > 80) return "Keep your display name under 80 characters.";

  const filledPreferences = draft.preferences.filter(
    (preference) => preference.titleText.trim() || preference.enjoyedText.trim(),
  );
  if (filledPreferences.length > 3) return "Keep your list to three favorites.";
  if (filledPreferences.some((preference) => !preference.titleText.trim())) {
    return "Add a title before describing what you enjoyed.";
  }
  if (filledPreferences.some((preference) => !Number.isInteger(preference.tmdbId) || !preference.mediaType)) {
    return "Choose each title from the search results so CineBridge can identify it correctly.";
  }
  if (filledPreferences.some((preference) => preference.titleText.trim().length > 160)) {
    return "Keep each title under 160 characters.";
  }
  if (filledPreferences.some((preference) => preference.enjoyedText.trim().length > 500)) {
    return "Keep each note under 500 characters.";
  }
  return null;
}

export function getBrowserApiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
}

export function getServerApiBaseUrl(): string {
  return (process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(
    /\/$/,
    "",
  );
}

export async function searchTitles(
  token: string,
  query: string,
  options: { baseUrl?: string; fetcher?: EventApiFetcher; signal?: AbortSignal } = {},
): Promise<TitleSearchResponse> {
  const normalized = query.trim();
  if (normalized.length < 2) return { results: [], suggestion: null };
  const fetcher = options.fetcher || fetch;
  const response = await fetcher(
    `${options.baseUrl || getBrowserApiBaseUrl()}/events/public/${encodeURIComponent(token)}/title-search?q=${encodeURIComponent(normalized)}`,
    { signal: options.signal },
  );
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : "Titles are unavailable right now. Try again in a moment.";
    throw new Error(detail);
  }
  return payload as TitleSearchResponse;
}

export async function createEvent(
  draft: EventDraft,
  options: { baseUrl?: string; fetcher?: EventApiFetcher } = {},
): Promise<EventCreationResponse> {
  const fetcher = options.fetcher || fetch;
  const response = await fetcher(`${options.baseUrl || getBrowserApiBaseUrl()}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: draft.name,
      theme: draft.theme,
      screening_date: draft.screeningDate,
      essential_details: draft.essentialDetails,
    }),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : "The event could not be created.";
    throw new Error(detail);
  }
  return payload as EventCreationResponse;
}

async function readEvent<T>(
  path: string,
  options: { baseUrl?: string; fetcher?: EventApiFetcher } = {},
): Promise<T | null> {
  const fetcher = options.fetcher || fetch;
  const response = await fetcher(`${options.baseUrl || getServerApiBaseUrl()}${path}`, {
    cache: "no-store",
  });
  if (!response.ok) return null;
  return (await response.json()) as T;
}

export function readPublicEvent(
  token: string,
  options: { baseUrl?: string; fetcher?: EventApiFetcher } = {},
): Promise<PublicEventResponse | null> {
  return readEvent<PublicEventResponse>(`/events/public/${encodeURIComponent(token)}`, options);
}

export function readPrivateEvent(
  token: string,
  options: { baseUrl?: string; fetcher?: EventApiFetcher } = {},
): Promise<PrivateEventResponse | null> {
  return readEvent<PrivateEventResponse>(`/events/private/${encodeURIComponent(token)}`, options);
}

export function readRecommendations(
  token: string,
  options: { baseUrl?: string; fetcher?: EventApiFetcher } = {},
): Promise<RecommendationResponse | null> {
  return readEvent<RecommendationResponse>(
    `/events/private/${encodeURIComponent(token)}/recommendations`,
    options,
  );
}

export async function requestRecommendations(
  token: string,
  options: { baseUrl?: string; fetcher?: EventApiFetcher } = {},
): Promise<RecommendationResponse> {
  const fetcher = options.fetcher || fetch;
  const response = await fetcher(
    `${options.baseUrl || getBrowserApiBaseUrl()}/events/private/${encodeURIComponent(token)}/recommendations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  );
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : "Recommendations could not be generated.";
    throw new Error(detail);
  }
  return payload as RecommendationResponse;
}

export async function selectFinalFilm(
  token: string,
  rank: 1 | 2 | 3,
  options: { baseUrl?: string; fetcher?: EventApiFetcher } = {},
): Promise<SelectionResponse> {
  const fetcher = options.fetcher || fetch;
  const response = await fetcher(
    `${options.baseUrl || getBrowserApiBaseUrl()}/events/private/${encodeURIComponent(token)}/selection`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rank }),
    },
  );
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : "The final film could not be selected.";
    throw new Error(detail);
  }
  return payload as SelectionResponse;
}

export function formatRuntime(runtimeMinutes: number | null): string | null {
  if (runtimeMinutes === null) return null;
  const hours = Math.floor(runtimeMinutes / 60);
  const minutes = runtimeMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function formatCandidateMetadata(candidate: RecommendationCandidate): string {
  return [
    candidate.release_year ? String(candidate.release_year) : null,
    candidate.content_rating,
    formatRuntime(candidate.runtime_minutes),
    candidate.languages.length ? candidate.languages.join(" / ") : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function getCoverageSummary(recommendation: RecommendationResponse): {
  summary: string;
  warning: string | null;
} {
  const registered = recommendation.registered_count;
  const usable = recommendation.usable_preference_count;
  const represented = recommendation.represented_attendee_count;
  const summary = registered
    ? `${usable} of ${registered} ${registered === 1 ? "attendee shared" : "attendees shared"} usable preferences`
    : "No attendees have shared usable preferences yet";
  if (recommendation.status !== "limited") return { summary, warning: null };
  const missing = Math.max(registered - represented, 0);
  return {
    summary,
    warning: `Limited coverage · ${missing} ${missing === 1 ? "attendee is" : "attendees are"} not represented`,
  };
}

export function getRecommendationActionLabel(recommendation: RecommendationResponse | null): string {
  if (!recommendation || recommendation.warning_code === "not_requested") return "Get recommendations";
  return recommendation.status === "unavailable" ? "Try again" : "Refresh recommendations";
}

export function getSignalLabel(status: RecommendationResponse["status"]): string {
  return status === "limited" ? "Limited signal" : "Good signal, not a guarantee";
}

export function getAudienceExplanation(candidate: RecommendationCandidate): string {
  return `${candidate.fit_explanation} Eligibility was applied before audience fit; this is a useful signal for the organizer, not a promise of enjoyment.`;
}

export async function registerAttendee(
  token: string,
  draft: RegistrationDraft,
  options: { baseUrl?: string; fetcher?: EventApiFetcher } = {},
): Promise<RegistrationResponse> {
  const fetcher = options.fetcher || fetch;
  const response = await fetcher(
    `${options.baseUrl || getBrowserApiBaseUrl()}/events/public/${encodeURIComponent(token)}/registrations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: draft.displayName,
        preferences: draft.preferences.map((preference) => ({
          title_text: preference.titleText,
          enjoyed_text: preference.enjoyedText,
          ...(Number.isInteger(preference.tmdbId) && preference.mediaType
            ? {
                tmdb_id: preference.tmdbId,
                media_type: preference.mediaType,
                release_date: preference.releaseDate || null,
                poster_path: preference.posterPath || null,
              }
            : {}),
        })),
      }),
    },
  );
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : "Your response could not be saved.";
    throw new Error(detail);
  }
  return payload as RegistrationResponse;
}
