import { describe, expect, it } from "vitest";

import {
  registerAttendee,
  RegistrationDraft,
  searchTitles,
  validateRegistrationDraft,
} from "./event-flow";

const draft: RegistrationDraft = {
  displayName: "Maya",
  preferences: [
    { titleText: "Moonlight", enjoyedText: "Quiet, humane pacing", tmdbId: 378064, mediaType: "movie", releaseDate: "2016-10-21", posterPath: "/poster.jpg" },
    { titleText: "Arrival", enjoyedText: "Ideas with emotional weight", tmdbId: 329865, mediaType: "movie", releaseDate: "2016-11-10", posterPath: null },
  ],
};

function response(body: unknown, ok = true, status = ok ? 201 : 422): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("attendee registration flow", () => {
  it("accepts a display name with no preferences", () => {
    expect(
      validateRegistrationDraft({ displayName: "Maya", preferences: [{ titleText: "", enjoyedText: "" }] }),
    ).toBeNull();
  });

  it("explains the three-title limit and incomplete slots", () => {
    expect(
      validateRegistrationDraft({
        displayName: "Maya",
      preferences: [
          { titleText: "One", enjoyedText: "", tmdbId: 1, mediaType: "movie" },
          { titleText: "Two", enjoyedText: "", tmdbId: 2, mediaType: "movie" },
          { titleText: "Three", enjoyedText: "", tmdbId: 3, mediaType: "movie" },
          { titleText: "Four", enjoyedText: "", tmdbId: 4, mediaType: "movie" },
        ],
      }),
    ).toBe("Keep your list to three favorites.");
    expect(
      validateRegistrationDraft({
        displayName: "Maya",
        preferences: [{ titleText: "", enjoyedText: "Strong atmosphere" }],
      }),
    ).toBe("Add a title before describing what you enjoyed.");
  });

  it("requires a TMDB selection instead of accepting an ambiguous typed title", () => {
    expect(validateRegistrationDraft({
      displayName: "Maya", preferences: [{ titleText: "AOT", enjoyedText: "" }],
    })).toContain("Choose each title from the search results");
  });

  it("posts display name and bounded preference input to the public registration path", async () => {
    let request: RequestInfo | URL | undefined;
    let init: RequestInit | undefined;
    const fetcher = async (input: RequestInfo | URL, options?: RequestInit) => {
      request = input;
      init = options;
      return response({ message: "Registration received" });
    };

    const result = await registerAttendee("public/token", draft, {
      baseUrl: "https://api.test",
      fetcher,
    });

    expect(result).toEqual({ message: "Registration received" });
    expect(request).toBe("https://api.test/events/public/public%2Ftoken/registrations");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual({
      display_name: "Maya",
      preferences: [
        { title_text: "Moonlight", enjoyed_text: "Quiet, humane pacing", tmdb_id: 378064, media_type: "movie", release_date: "2016-10-21", poster_path: "/poster.jpg" },
        { title_text: "Arrival", enjoyed_text: "Ideas with emotional weight", tmdb_id: 329865, media_type: "movie", release_date: "2016-11-10", poster_path: null },
      ],
    });
  });

  it("uses the public token for TMDB search and preserves an alias suggestion without selecting it", async () => {
    let request = "";
    const result = await searchTitles("public/token", "AOT", {
      baseUrl: "https://api.test",
      fetcher: async (input) => {
        request = String(input);
        return response({ results: [{ tmdb_id: 1429, media_type: "tv", title: "Attack on Titan", release_date: "2013-04-07", release_year: 2013, poster_url: null }], suggestion: "Attack on Titan" });
      },
    });
    expect(request).toBe("https://api.test/events/public/public%2Ftoken/title-search?q=AOT");
    expect(result.suggestion).toBe("Attack on Titan");
    expect(result.results[0].title).toBe("Attack on Titan");
  });

  it("keeps a TMDB outage actionable instead of treating a typed title as selected", async () => {
    await expect(searchTitles("public-token", "Moonlight", {
      baseUrl: "https://api.test",
      fetcher: async () => response({ detail: "TMDB is temporarily unavailable" }, false, 503),
    })).rejects.toThrow("TMDB is temporarily unavailable");
    expect(validateRegistrationDraft({
      displayName: "Maya", preferences: [{ titleText: "Moonlight", enjoyedText: "" }],
    })).toContain("Choose each title from the search results");
  });

  it("turns registration failures into a safe user-facing error", async () => {
    await expect(
      registerAttendee("public-token", draft, {
        baseUrl: "https://api.test",
        fetcher: async () => response({ detail: "Invalid registration details" }, false),
      }),
    ).rejects.toThrow("Invalid registration details");
  });
});
