import { describe, expect, it } from "vitest";

import {
  createEvent,
  EventDraft,
  readPrivateEvent,
  readPublicEvent,
  validateEventDraft,
} from "./event-flow";

const draft: EventDraft = {
  name: "Sunday Film Club",
  theme: "Tender science fiction",
  screeningDate: "2099-01-12",
  essentialDetails: "Doors at 18:30 · step-free venue",
};

function response(body: unknown, ok = true, status = ok ? 200 : 422): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("event setup flow", () => {
  it("requires a future date and the four event details", () => {
    expect(validateEventDraft({ ...draft, name: "" }, "2099-01-01")).toBe("Give the event a name.");
    expect(validateEventDraft({ ...draft, screeningDate: "2099-01-01" }, "2099-01-01")).toBe(
      "Choose a future screening date.",
    );
    expect(validateEventDraft(draft, "2099-01-01")).toBeNull();
  });

  it("posts only the approved event fields and returns the two handoff links", async () => {
    let request: RequestInfo | URL | undefined;
    let init: RequestInit | undefined;
    const fetcher = async (input: RequestInfo | URL, options?: RequestInit) => {
      request = input;
      init = options;
      return response({
        ...draft,
        screening_date: draft.screeningDate,
        essential_details: draft.essentialDetails,
        public_registration_url: "https://cinebridge.test/join/public-token",
        private_management_url: "https://cinebridge.test/manage/private-token",
      }, true, 201);
    };

    const result = await createEvent(draft, { baseUrl: "https://api.test", fetcher });
    expect(request).toBe("https://api.test/events");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual({
      name: draft.name,
      theme: draft.theme,
      screening_date: draft.screeningDate,
      essential_details: draft.essentialDetails,
    });
    expect(result.public_registration_url).toContain("/join/");
    expect(result.private_management_url).toContain("/manage/");
  });

  it("keeps public and private reads on separate API paths", async () => {
    const paths: string[] = [];
    const fetcher = async (input: RequestInfo | URL) => {
      paths.push(String(input));
      return response({
        name: draft.name,
        theme: draft.theme,
        screening_date: draft.screeningDate,
        essential_details: draft.essentialDetails,
        registered_count: 0,
        usable_preference_count: 0,
        represented_attendee_count: 0,
      });
    };

    await readPublicEvent("public-token", { baseUrl: "https://api.test", fetcher });
    await readPrivateEvent("private-token", { baseUrl: "https://api.test", fetcher });
    expect(paths).toEqual([
      "https://api.test/events/public/public-token",
      "https://api.test/events/private/private-token",
    ]);
  });

  it("turns a non-success API response into a safe user-facing error", async () => {
    await expect(
      createEvent(draft, {
        baseUrl: "https://api.test",
        fetcher: async () => response({ detail: "Invalid event details" }, false),
      }),
    ).rejects.toThrow("Invalid event details");
  });
});
