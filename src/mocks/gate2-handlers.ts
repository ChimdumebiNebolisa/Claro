import { http, HttpResponse, type HttpHandler } from "msw";
import {
  attributionForOrigin,
  type CandidateOrigin,
} from "@/v2/domain/contracts";
import {
  candidateFor,
  directSuggestionText,
  fixtureAssignment,
  fixtureExportResult,
} from "@/v2/domain/fixtures";

export type CandidateInteraction =
  | { kind: "direct_typed" }
  | {
      kind: "direct_voice";
      source_turn_ids: string[];
      normalization: "none" | "speech_cleanup";
    }
  | {
      kind: "guided_final";
      source_turn_ids: string[];
      input: "typed" | "voice";
    }
  | {
      kind: "student_edit";
      prior_candidate_id: string;
      prior_candidate_version: number;
    }
  | {
      kind: "selected_rephrase";
      rephrase_id: string;
      suggestion_candidate_id: string;
    };

type CandidateRequest = {
  assignment_version: number;
  text: string;
  origin: CandidateOrigin;
  interaction: CandidateInteraction;
};

type VersionedRequest = { assignment_version: number };

type ConfirmRequest = VersionedRequest & {
  review_token: string;
  candidate_id: string;
  candidate_version: number;
  exact_text: string;
};

type FixtureCandidate = ReturnType<typeof candidateFor>;

type FixtureApiState = {
  version: number;
  candidate: FixtureCandidate | null;
  originalCandidate: FixtureCandidate | null;
  suggestion: FixtureCandidate | null;
  reviewToken: string | null;
  reviewExpiresAt: string | null;
  confirmed: Record<
    string,
    {
      question_id: string;
      revision: number;
      exact_text: string;
      origin: CandidateOrigin;
      placement: "inline" | "appendix";
    }
  >;
  confirmationReplays: Map<string, unknown>;
  exportsByVersion: Map<number, typeof fixtureExportResult>;
};

export type Gate2FixtureOptions = {
  now?: string;
  assignmentVersion?: number;
  reviewTtlMs?: number;
};

const jsonHeaders = (version: number) => ({
  ETag: `"assignment-version-${version}"`,
  "Cache-Control": "no-store",
});

const errorResponse = (
  status: number,
  code: string,
  message: string,
  recoverable: boolean,
  version: number,
) =>
  HttpResponse.json(
    { error: { code, message, recoverable }, version },
    { status, headers: jsonHeaders(version) },
  );

const expectedOrigin = (interaction: CandidateInteraction): CandidateOrigin => {
  switch (interaction.kind) {
    case "direct_typed":
      return "student_verbatim";
    case "direct_voice":
      return interaction.normalization === "speech_cleanup"
        ? "student_normalized"
        : "student_verbatim";
    case "guided_final":
      return "student_after_guidance";
    case "student_edit":
      return "student_edited";
    case "selected_rephrase":
      return "claros_rephrase";
  }
};

const assignmentProjection = (state: FixtureApiState) => ({
  id: fixtureAssignment.id,
  version: state.version,
  title: fixtureAssignment.title,
  filename: fixtureAssignment.filename,
  page_count: fixtureAssignment.pageCount,
  questions: fixtureAssignment.questions.map((question) => ({
    id: question.id,
    index: question.index,
    text: question.prompt,
    instruction: question.instruction,
    page_number: question.pageNumber,
    status: state.confirmed[question.id] ? "answered" : "unanswered",
  })),
  confirmed_answers: Object.values(state.confirmed),
});

function hasCurrentVersion(
  body: VersionedRequest,
  state: FixtureApiState,
): boolean {
  return body.assignment_version === state.version;
}

export function createGate2Handlers(
  options: Gate2FixtureOptions = {},
): HttpHandler[] {
  const initialVersion = options.assignmentVersion ?? fixtureAssignment.version;
  const now = new Date(options.now ?? "2026-09-04T12:00:00.000Z");
  const state: FixtureApiState = {
    version: initialVersion,
    candidate: null,
    originalCandidate: null,
    suggestion: null,
    reviewToken: null,
    reviewExpiresAt: null,
    confirmed: {},
    confirmationReplays: new Map(),
    exportsByVersion: new Map(),
  };
  const base = `*/api/v2/assignments/${fixtureAssignment.id}`;

  return [
    http.post("*/api/v2/assignments", () =>
      HttpResponse.json(assignmentProjection(state), {
        status: 201,
        headers: jsonHeaders(state.version),
      }),
    ),
    http.get(base, () =>
      HttpResponse.json(assignmentProjection(state), {
        headers: jsonHeaders(state.version),
      }),
    ),
    http.post(
      `${base}/questions/:questionId/candidates`,
      async ({ request, params }) => {
        const body = (await request.json()) as CandidateRequest;
        if (!hasCurrentVersion(body, state)) {
          return errorResponse(
            409,
            "assignment_version_conflict",
            "The assignment changed. Your words are still here; refresh the worksheet state and try again.",
            true,
            state.version,
          );
        }
        if (body.origin !== expectedOrigin(body.interaction)) {
          return errorResponse(
            422,
            "invalid_candidate_origin",
            "The answer source did not match this interaction.",
            true,
            state.version,
          );
        }
        if (
          body.interaction.kind === "selected_rephrase" &&
          (!state.suggestion ||
            body.interaction.rephrase_id !== "rephrase_fixture_01" ||
            body.interaction.suggestion_candidate_id !== state.suggestion.id ||
            body.text !== state.suggestion.text)
        ) {
          return errorResponse(
            422,
            "invalid_candidate_origin",
            "The selected wording did not match the available suggestion.",
            true,
            state.version,
          );
        }
        if (
          body.interaction.kind === "student_edit" &&
          (!state.candidate ||
            body.interaction.prior_candidate_id !== state.candidate.id ||
            body.interaction.prior_candidate_version !==
              state.candidate.version)
        ) {
          return errorResponse(
            422,
            "invalid_candidate_origin",
            "The edited answer did not match the current candidate.",
            true,
            state.version,
          );
        }
        const questionId = String(params.questionId);
        state.version += 1;
        state.candidate = candidateFor(
          questionId,
          body.text,
          body.origin,
          (state.candidate?.version ?? 0) + 1,
        );
        state.originalCandidate = null;
        state.suggestion = null;
        state.reviewToken = null;
        state.reviewExpiresAt = null;
        return HttpResponse.json(
          {
            candidate: state.candidate,
            attribution: attributionForOrigin(state.candidate.origin),
            version: state.version,
          },
          { headers: jsonHeaders(state.version) },
        );
      },
    ),
    http.post(`${base}/questions/:questionId/rephrase`, async ({ request }) => {
      const body = (await request.json()) as VersionedRequest;
      if (!hasCurrentVersion(body, state)) {
        return errorResponse(
          409,
          "assignment_version_conflict",
          "The assignment changed. Your words are still here; refresh the worksheet state and try again.",
          true,
          state.version,
        );
      }
      if (!state.candidate || !/\S/u.test(state.candidate.text)) {
        return errorResponse(
          422,
          "candidate_required",
          "Add your answer before requesting clearer wording.",
          true,
          state.version,
        );
      }
      state.version += 1;
      state.originalCandidate = state.candidate;
      state.suggestion = candidateFor(
        state.candidate.questionId,
        directSuggestionText,
        "claros_rephrase",
        state.candidate.version + 1,
      );
      return HttpResponse.json(
        {
          rephrase_id: "rephrase_fixture_01",
          original: state.originalCandidate,
          suggestion: state.suggestion,
          selected: null,
          version: state.version,
        },
        { headers: jsonHeaders(state.version) },
      );
    }),
    http.post(
      `${base}/questions/:questionId/review`,
      async ({ request, params }) => {
        const body = (await request.json()) as VersionedRequest & {
          candidate_id: string;
          candidate_version: number;
        };
        if (!hasCurrentVersion(body, state)) {
          return errorResponse(
            409,
            "assignment_version_conflict",
            "The assignment changed. Request a fresh review.",
            true,
            state.version,
          );
        }
        if (
          !state.candidate ||
          state.candidate.questionId !== String(params.questionId) ||
          body.candidate_id !== state.candidate.id ||
          body.candidate_version !== state.candidate.version
        ) {
          return errorResponse(
            409,
            "stale_candidate",
            "The answer changed. Request a fresh review.",
            true,
            state.version,
          );
        }
        const question = fixtureAssignment.questions.find(
          (item) => item.id === String(params.questionId),
        );
        state.reviewToken = `review_${state.candidate.id}_${state.candidate.version}_${state.version}`;
        state.reviewExpiresAt = new Date(
          now.getTime() + (options.reviewTtlMs ?? 10 * 60 * 1000),
        ).toISOString();
        return HttpResponse.json(
          {
            review_token: state.reviewToken,
            expires_at: state.reviewExpiresAt,
            candidate: state.candidate,
            exact_text: state.candidate.text,
            placement: question?.placement ?? "appendix",
            version: state.version,
          },
          { headers: jsonHeaders(state.version) },
        );
      },
    ),
    http.post(
      `${base}/questions/:questionId/confirm`,
      async ({ request, params }) => {
        const body = (await request.json()) as ConfirmRequest;
        const questionId = String(params.questionId);
        const replayKey = `${questionId}:${JSON.stringify(body)}`;
        const replay = state.confirmationReplays.get(replayKey);
        if (replay) {
          return HttpResponse.json(replay, {
            headers: jsonHeaders(state.version),
          });
        }
        if (!hasCurrentVersion(body, state)) {
          return errorResponse(
            409,
            "assignment_version_conflict",
            "The assignment changed. Request a fresh review.",
            true,
            state.version,
          );
        }
        if (
          !state.candidate ||
          !state.reviewToken ||
          !state.reviewExpiresAt ||
          new Date(state.reviewExpiresAt).getTime() <= now.getTime() ||
          state.candidate.questionId !== questionId ||
          body.review_token !== state.reviewToken ||
          body.candidate_id !== state.candidate.id ||
          body.candidate_version !== state.candidate.version ||
          body.exact_text !== state.candidate.text
        ) {
          return errorResponse(
            409,
            "stale_review",
            "This review is no longer current. Your answer was not changed.",
            true,
            state.version,
          );
        }
        const question = fixtureAssignment.questions.find(
          (item) => item.id === questionId,
        );
        const answer = {
          question_id: questionId,
          revision: (state.confirmed[questionId]?.revision ?? 0) + 1,
          exact_text: state.candidate.text,
          origin: state.candidate.origin,
          placement: question?.placement ?? ("appendix" as const),
        };
        state.confirmed[questionId] = answer;
        state.version += 1;
        const response = { answer, version: state.version };
        state.confirmationReplays.set(replayKey, response);
        return HttpResponse.json(response, {
          headers: jsonHeaders(state.version),
        });
      },
    ),
    http.patch(
      `${base}/questions/:questionId/answer`,
      async ({ request, params }) => {
        const body = (await request.json()) as VersionedRequest;
        if (!hasCurrentVersion(body, state)) {
          return errorResponse(
            409,
            "assignment_version_conflict",
            "The assignment changed. Refresh before editing this answer.",
            true,
            state.version,
          );
        }
        const questionId = String(params.questionId);
        const retainedAnswer = state.confirmed[questionId];
        if (!retainedAnswer) {
          return errorResponse(
            404,
            "confirmed_answer_not_found",
            "There is no confirmed answer to revise.",
            true,
            state.version,
          );
        }
        state.version += 1;
        state.candidate = candidateFor(
          questionId,
          retainedAnswer.exact_text,
          "student_edited",
          retainedAnswer.revision + 1,
        );
        state.reviewToken = null;
        state.reviewExpiresAt = null;
        return HttpResponse.json(
          {
            candidate: state.candidate,
            retained_answer: retainedAnswer,
            version: state.version,
          },
          { headers: jsonHeaders(state.version) },
        );
      },
    ),
    http.post(`${base}/exports`, async ({ request }) => {
      const body = (await request.json()) as VersionedRequest;
      if (!hasCurrentVersion(body, state)) {
        return errorResponse(
          409,
          "assignment_version_conflict",
          "The assignment changed. Review the latest answers before exporting.",
          true,
          state.version,
        );
      }
      if (Object.keys(state.confirmed).length === 0) {
        return errorResponse(
          409,
          "no_confirmed_answers",
          "Confirm at least one answer before creating the completed PDF.",
          true,
          state.version,
        );
      }
      const exportResult = state.exportsByVersion.get(state.version) ?? {
        ...fixtureExportResult,
        id: `export_fixture_v${state.version}`,
        downloadUrl: `/api/v2/assignments/${fixtureAssignment.id}/exports/export_fixture_v${state.version}/download`,
      };
      state.exportsByVersion.set(state.version, exportResult);
      return HttpResponse.json(
        {
          export_id: exportResult.id,
          filename: exportResult.filename,
          size_label: exportResult.sizeLabel,
          download_url: exportResult.downloadUrl,
          status: "complete",
          confirmed_answers: Object.values(state.confirmed),
          version: state.version,
        },
        { status: 201, headers: jsonHeaders(state.version) },
      );
    }),
    http.get(`${base}/exports/:exportId`, () =>
      HttpResponse.json(
        {
          export_id: fixtureExportResult.id,
          filename: fixtureExportResult.filename,
          size_label: fixtureExportResult.sizeLabel,
          download_url: fixtureExportResult.downloadUrl,
          status: "complete",
          version: state.version,
        },
        { headers: jsonHeaders(state.version) },
      ),
    ),
    http.get(`${base}/exports/:exportId/download`, ({ request }) =>
      HttpResponse.redirect(
        new URL("/api/v2/fixtures/biology/export", request.url),
        302,
      ),
    ),
  ];
}
