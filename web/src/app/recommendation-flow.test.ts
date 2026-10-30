import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  RecommendationResponse,
  formatCandidateMetadata,
  getAudienceExplanation,
  getCoverageSummary,
  getRecommendationActionLabel,
  getSignalLabel,
  selectFinalFilm,
} from "./event-flow";

const candidate = {
  rank: 1 as const,
  title: "Past Lives",
  release_year: 2023,
  runtime_minutes: 106,
  content_rating: "PG-13",
  languages: ["English", "Korean"],
  fit_explanation: "The strongest combined fit across the represented audience.",
  warning_text: "Cultural similarity is a signal, not a guarantee.",
};

function recommendation(overrides: Partial<RecommendationResponse> = {}): RecommendationResponse {
  return {
    status: "succeeded",
    registered_count: 24,
    usable_preference_count: 18,
    represented_attendee_count: 18,
    warning_code: null,
    warning: "Cultural similarity is a signal, not a guarantee.",
    message: "These films are a starting point for the organizer's decision.",
    top_pick: candidate,
    alternatives: [],
    selection: null,
    ...overrides,
  };
}

describe("organizer recommendation presentation states", () => {
  it("keeps the successful state readable and gives it one primary signal", () => {
    expect(getCoverageSummary(recommendation())).toEqual({
      summary: "18 of 24 attendees shared usable preferences",
      warning: null,
    });
    expect(formatCandidateMetadata(candidate)).toBe("2023 · PG-13 · 1h 46m · English / Korean");
    expect(getSignalLabel("succeeded")).toBe("Good signal, not a guarantee");
  });

  it("surfaces low coverage without hiding that the shortlist is complete", () => {
    const limited = recommendation({
      status: "limited",
      warning_code: "limited_coverage",
      represented_attendee_count: 12,
    });
    expect(getCoverageSummary(limited).warning).toBe("Limited coverage · 12 attendees are not represented");
    expect(getSignalLabel("limited")).toBe("Limited signal");
    expect(limited.top_pick).not.toBeNull();
  });

  it("maps unavailable and not-requested states to an honest recovery action", () => {
    expect(getRecommendationActionLabel(null)).toBe("Get recommendations");
    expect(getRecommendationActionLabel(recommendation({
      status: "unavailable",
      warning_code: "provider_unavailable",
      top_pick: null,
      alternatives: [],
    }))).toBe("Try again");
    expect(getRecommendationActionLabel(recommendation({
      status: "unavailable",
      warning_code: "not_requested",
      top_pick: null,
      alternatives: [],
    }))).toBe("Get recommendations");
  });

  it("keeps the explanation path explicit and does not promise enjoyment", () => {
    expect(getAudienceExplanation(candidate)).toContain("not a promise of enjoyment");
    expect(candidate.fit_explanation).toContain("strongest combined fit");
  });

  it("posts only the private rank when the organizer selects a film", async () => {
    let request: RequestInfo | URL | undefined;
    let init: RequestInit | undefined;
    const fetcher = async (input: RequestInfo | URL, options?: RequestInit) => {
      request = input;
      init = options;
      return new Response(JSON.stringify({
        message: "Final film selected for this private workspace. No announcement was sent.",
        selection: { rank: 2, title: "The Farewell" },
      }), { status: 200, headers: { "content-type": "application/json" } });
    };

    const result = await selectFinalFilm("private/token", 2, { baseUrl: "https://api.test", fetcher });
    expect(request).toBe("https://api.test/events/private/private%2Ftoken/selection");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual({ rank: 2 });
    expect(result.selection).toEqual({ rank: 2, title: "The Farewell" });
    expect(result.message).toContain("No announcement was sent");
  });

  it("keeps the top pick before alternatives on the responsive layout", () => {
    const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
    expect(styles).toContain(".recommendation-grid { display: grid;");
    expect(styles).toContain(".heading-mobile { display: none; }");
    expect(styles).toContain("@media (max-width: 40rem)");
    expect(styles).toContain(".heading-desktop { display: none; }");
    expect(styles).toContain(".alternatives-panel { border: 0; background: transparent;");
    expect(styles).toContain(".explanation-block { margin-top: 1rem; padding-top: 0.8rem; }");
    expect(styles).not.toContain(".explanation-block { display: none; }");
  });
});
