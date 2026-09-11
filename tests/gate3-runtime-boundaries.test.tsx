// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AppProviders } from "../src/v2/AppProviders";
import RootApp from "../src/v2/RootApp";

const realtimeMocks = vi.hoisted(() => ({ load: vi.fn() }));

vi.mock("../src/v2/realtime/loadRealtime", () => ({
  loadRealtimeAdapter: realtimeMocks.load,
}));

vi.mock("../src/v2/document/DocumentCrop", () => ({
  default: () => <div data-testid="document-crop" />,
}));

vi.mock("../src/v2/document/WorksheetDialog", () => ({
  default: () => <div role="dialog" aria-label="Worksheet" />,
}));

// Match the established route-suite pattern: resolve the production lazy
// boundary before assertions so these tests measure API hydration, not host
// module-import speed.
await import("../src/v2/WorkspaceShell");

const assignment = {
  assignment_id: "asgn_runtime",
  version: 3,
  status: "ready",
  title: "Runtime worksheet",
  source: {
    filename: "runtime.pdf",
    size_bytes: 1024,
    sha256: "b".repeat(64),
    page_count: 1,
  },
  question_count: 1,
  placement_summary: { inline_possible: 0, appendix_only: 1 },
  warnings: [],
  questions: [
    {
      question_id: "q_runtime",
      index: 1,
      prompt: "What is the runtime question?",
      instruction: null,
      page_number: 1,
      placement_capability: "appendix_only",
      candidate: null,
      wording_comparison: null,
      confirmed_answer: null,
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  realtimeMocks.load.mockReset();
});

describe("Gate 3 runtime boundaries", () => {
  it("polls a reload-safe analyzing assignment until it is ready", async () => {
    const analyzing = {
      ...assignment,
      status: "analyzing",
      question_count: 0,
      questions: [],
      source: { ...assignment.source, page_count: null },
    };
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = init?.method === "POST" ? analyzing : assignment;
        return new Response(JSON.stringify(payload), {
          status: init?.method === "POST" ? 201 : 200,
          headers: { "content-type": "application/json" },
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/app?runtime=api"]}>
        <AppProviders>
          <RootApp />
        </AppProviders>
      </MemoryRouter>,
    );

    await user.click(
      await screen.findByRole(
        "button",
        { name: "Try the biology sample" },
        { timeout: 5_000 },
      ),
    );
    expect(
      await screen.findByRole(
        "heading",
        { name: "Your worksheet is ready." },
        { timeout: 3_000 },
      ),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(
      "/api/v2/assignments/asgn_runtime",
    );
  });

  it("fails voice closed without loading the fixture Realtime adapter", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(assignment), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/app/asgn_runtime?runtime=api"]}>
        <AppProviders>
          <RootApp />
        </AppProviders>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", {
        name: "What is the runtime question?",
      }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start answering" }));
    await user.click(screen.getByRole("button", { name: "Start speaking" }));

    expect(
      await screen.findByText("Microphone unavailable"),
    ).toBeInTheDocument();
    expect(realtimeMocks.load).not.toHaveBeenCalled();
  });

  it("reuses a persisted candidate when review retry follows a server failure", async () => {
    let reviewAttempts = 0;
    const candidate = {
      candidate_id: "cand_runtime",
      candidate_version: 1,
      question_id: "q_runtime",
      text: "Exact retry text.",
      origin: "student_verbatim",
      attribution: "Your words",
      created_at: "2026-09-04T12:00:00Z",
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/candidates")) {
        return new Response(JSON.stringify({ version: 4, candidate }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      if (url.endsWith("/review")) {
        reviewAttempts += 1;
        if (reviewAttempts === 1) {
          return new Response(
            JSON.stringify({
              error: {
                code: "review_unavailable",
                message: "Review is temporarily unavailable.",
                recoverable: true,
              },
              version: 4,
            }),
            {
              status: 503,
              headers: { "content-type": "application/json" },
            },
          );
        }
        return new Response(
          JSON.stringify({
            version: 4,
            question_id: "q_runtime",
            candidate,
            attribution: "Your words",
            review_token: "review_runtime",
            expires_at: "2026-09-04T12:10:00Z",
            placement: "appendix",
            preview_context_url:
              "/api/v2/assignments/asgn_runtime/pages/1/context?question_id=q_runtime",
          }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        );
      }
      return new Response(JSON.stringify(assignment), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/app/asgn_runtime?runtime=api"]}>
        <AppProviders>
          <RootApp />
        </AppProviders>
      </MemoryRouter>,
    );

    await screen.findByRole("heading", {
      name: "What is the runtime question?",
    });
    await user.click(screen.getByRole("button", { name: "Type instead" }));
    await user.type(
      screen.getByRole("textbox", { name: "Your words" }),
      candidate.text,
    );
    await user.click(screen.getByRole("button", { name: "Review answer" }));
    expect(
      await screen.findByText("Review is temporarily unavailable."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Review answer" }));
    expect(
      await screen.findByRole("heading", { name: "Review your exact answer" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([input]) =>
          String(input).endsWith("/candidates"),
        ),
      ).toHaveLength(1);
    });
    expect(reviewAttempts).toBe(2);
  });
});
