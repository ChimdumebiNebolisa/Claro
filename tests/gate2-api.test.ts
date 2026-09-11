import { setupServer } from "msw/node";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { createGate2Handlers } from "../src/mocks/gate2-handlers";
import { fixtureAssignment } from "../src/v2/domain/fixtures";

const server = setupServer(...createGate2Handlers());
const base = `http://claros.test/api/v2/assignments/${fixtureAssignment.id}`;

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => server.resetHandlers(...createGate2Handlers()));
afterAll(() => server.close());

async function body<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

async function createDirectCandidate(text = "Plants need sunlight.") {
  const response = await fetch(`${base}/questions/q_01/candidates`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      assignment_version: 2,
      text,
      origin: "student_verbatim",
      interaction: { kind: "direct_typed" },
    }),
  });
  return {
    response,
    payload: await body<{
      candidate: { id: string; version: number; text: string; origin: string };
      version: number;
    }>(response),
  };
}

async function reviewAndConfirm(candidate: {
  id: string;
  version: number;
  text: string;
}) {
  const reviewResponse = await fetch(`${base}/questions/q_01/review`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      assignment_version: 3,
      candidate_id: candidate.id,
      candidate_version: candidate.version,
    }),
  });
  const review = await body<{
    review_token: string;
    exact_text: string;
    version: number;
  }>(reviewResponse);
  const request = {
    assignment_version: review.version,
    review_token: review.review_token,
    candidate_id: candidate.id,
    candidate_version: candidate.version,
    exact_text: candidate.text,
  };
  const confirmationResponse = await fetch(`${base}/questions/q_01/confirm`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(request),
  });
  return {
    request,
    response: confirmationResponse,
    payload: await body<{ answer: { revision: number }; version: number }>(
      confirmationResponse,
    ),
  };
}

describe("Gate 2 deterministic API fixtures", () => {
  it("derives candidate provenance and preserves state after a stale mutation", async () => {
    const forged = await fetch(`${base}/questions/q_01/candidates`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        assignment_version: 2,
        text: "A forged suggestion",
        origin: "claros_rephrase",
        interaction: { kind: "direct_typed" },
      }),
    });
    expect(forged.status).toBe(422);
    expect(await body(forged)).toMatchObject({
      error: { code: "invalid_candidate_origin", recoverable: true },
      version: 2,
    });

    const created = await createDirectCandidate("  Café’s CO₂ answer.  ");
    expect(created.response.ok).toBe(true);
    expect(created.payload).toMatchObject({
      candidate: {
        text: "  Café’s CO₂ answer.  ",
        origin: "student_verbatim",
      },
      version: 3,
    });
    expect(created.response.headers.get("etag")).toBe('"assignment-version-3"');

    const stale = await fetch(`${base}/questions/q_01/candidates`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        assignment_version: 2,
        text: "This must not overwrite the current candidate.",
        origin: "student_verbatim",
        interaction: { kind: "direct_typed" },
      }),
    });
    expect(stale.status).toBe(409);
    expect(await body(stale)).toMatchObject({
      error: { code: "assignment_version_conflict" },
      version: 3,
    });
  });

  it("keeps both rephrasing choices unselected until a validated choice", async () => {
    const { payload: created } = await createDirectCandidate();
    const rephraseResponse = await fetch(`${base}/questions/q_01/rephrase`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ assignment_version: created.version }),
    });
    const comparison = await body<{
      rephrase_id: string;
      original: { text: string };
      suggestion: { id: string; text: string };
      selected: null;
      version: number;
    }>(rephraseResponse);
    expect(comparison.selected).toBeNull();
    expect(comparison.original.text).toBe(created.candidate.text);
    expect(comparison.suggestion.text).not.toBe(comparison.original.text);

    const selectedResponse = await fetch(`${base}/questions/q_01/candidates`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        assignment_version: comparison.version,
        text: comparison.suggestion.text,
        origin: "claros_rephrase",
        interaction: {
          kind: "selected_rephrase",
          rephrase_id: comparison.rephrase_id,
          suggestion_candidate_id: comparison.suggestion.id,
        },
      }),
    });
    expect(selectedResponse.ok).toBe(true);
    expect(await body(selectedResponse)).toMatchObject({
      attribution: "Suggested wording",
      version: 5,
    });
  });

  it("confirms once and returns the original result for an exact replay", async () => {
    const { payload: created } = await createDirectCandidate();
    const confirmed = await reviewAndConfirm(created.candidate);
    expect(confirmed.response.ok).toBe(true);
    expect(confirmed.payload).toMatchObject({
      answer: { revision: 1 },
      version: 4,
    });

    const replayResponse = await fetch(`${base}/questions/q_01/confirm`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(confirmed.request),
    });
    expect(replayResponse.ok).toBe(true);
    expect(await body(replayResponse)).toEqual(confirmed.payload);

    const assignmentResponse = await fetch(base);
    const assignment = await body<{
      version: number;
      confirmed_answers: Array<{ revision: number }>;
    }>(assignmentResponse);
    expect(assignment.version).toBe(4);
    expect(assignment.confirmed_answers).toHaveLength(1);
    expect(assignment.confirmed_answers[0].revision).toBe(1);
  });

  it("rejects an expired review token without changing the assignment", async () => {
    server.use(...createGate2Handlers({ reviewTtlMs: -1 }));
    const { payload: created } = await createDirectCandidate();
    const confirmation = await reviewAndConfirm(created.candidate);

    expect(confirmation.response.status).toBe(409);
    expect(confirmation.payload).toMatchObject({
      error: { code: "stale_review" },
      version: 3,
    });
    const assignment = await body<{ confirmed_answers: unknown[] }>(
      await fetch(base),
    );
    expect(assignment.confirmed_answers).toEqual([]);
  });

  it("does not replay a review token against another question", async () => {
    const { payload: created } = await createDirectCandidate();
    const reviewResponse = await fetch(`${base}/questions/q_01/review`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        assignment_version: 3,
        candidate_id: created.candidate.id,
        candidate_version: created.candidate.version,
      }),
    });
    const review = await body<{ review_token: string; version: number }>(
      reviewResponse,
    );
    const crossQuestion = await fetch(`${base}/questions/q_02/confirm`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        assignment_version: review.version,
        review_token: review.review_token,
        candidate_id: created.candidate.id,
        candidate_version: created.candidate.version,
        exact_text: created.candidate.text,
      }),
    });

    expect(crossQuestion.status).toBe(409);
    expect(await body(crossQuestion)).toMatchObject({
      error: { code: "stale_review" },
      version: 3,
    });
  });

  it("allows idempotent partial export only after one answer is confirmed", async () => {
    const noAnswer = await fetch(`${base}/exports`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ assignment_version: 2 }),
    });
    expect(noAnswer.status).toBe(409);
    expect(await body(noAnswer)).toMatchObject({
      error: { code: "no_confirmed_answers" },
    });

    const { payload: created } = await createDirectCandidate();
    const confirmed = await reviewAndConfirm(created.candidate);
    const exportRequest = () =>
      fetch(`${base}/exports`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ assignment_version: confirmed.payload.version }),
      });
    const first = await body<{
      export_id: string;
      confirmed_answers: unknown[];
      version: number;
    }>(await exportRequest());
    const replay = await body<{ export_id: string }>(await exportRequest());
    expect(first.confirmed_answers).toHaveLength(1);
    expect(replay.export_id).toBe(first.export_id);
    expect(first.version).toBe(4);
  });

  it("keeps the confirmed revision exportable when revision begins", async () => {
    const { payload: created } = await createDirectCandidate();
    const confirmed = await reviewAndConfirm(created.candidate);
    const revisionResponse = await fetch(`${base}/questions/q_01/answer`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ assignment_version: confirmed.payload.version }),
    });
    expect(revisionResponse.ok).toBe(true);
    expect(await body(revisionResponse)).toMatchObject({
      candidate: { origin: "student_edited" },
      retained_answer: { revision: 1, exact_text: created.candidate.text },
      version: 5,
    });
  });

  it("routes downloads to the checked-in PDF fixture", async () => {
    const response = await fetch(`${base}/exports/export_fixture_01/download`, {
      redirect: "manual",
    });

    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(
      "http://claros.test/api/v2/fixtures/biology/export",
    );
  });
});
