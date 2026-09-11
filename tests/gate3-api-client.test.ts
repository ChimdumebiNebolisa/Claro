import { describe, expect, it } from "vitest";
import {
  mapAssignment,
  mapExportState,
  type ApiAssignment,
  type ApiExport,
} from "../src/v2/api/client";

const createdAt = "2026-09-04T12:00:00Z";

function assignmentPayload(): ApiAssignment {
  return {
    assignment_id: "asgn_test",
    version: 7,
    status: "ready",
    title: "Dynamic worksheet",
    source: {
      filename: "dynamic.pdf",
      size_bytes: 2048,
      sha256: "a".repeat(64),
      page_count: 2,
    },
    question_count: 2,
    placement_summary: { inline_possible: 1, appendix_only: 1 },
    warnings: [
      {
        code: "appendix_conservative",
        message: "One answer will use an attached answer page.",
      },
    ],
    questions: [
      {
        question_id: "q_01",
        index: 1,
        prompt: "First question?",
        instruction: null,
        page_number: 1,
        placement_capability: "inline_possible",
        candidate: null,
        wording_comparison: null,
        confirmed_answer: {
          question_id: "q_01",
          revision: 1,
          candidate_id: "cand_01",
          candidate_version: 1,
          exact_text: "Confirmed exact text.",
          origin: "student_verbatim",
          attribution: "Your words",
          placement: "inline",
          confirmed_at: createdAt,
        },
      },
      {
        question_id: "q_02",
        index: 2,
        prompt: "Second question?",
        instruction: "Use one sentence.",
        page_number: 2,
        placement_capability: "appendix_only",
        candidate: {
          candidate_id: "cand_02",
          candidate_version: 3,
          question_id: "q_02",
          text: "  Café — 植物  ",
          origin: "student_edited",
          attribution: "Your words",
          created_at: createdAt,
        },
        wording_comparison: null,
        confirmed_answer: null,
      },
    ],
  };
}

describe("Gate 3 generated API mapping", () => {
  it("restores the first in-progress question without rewriting exact text", () => {
    const restored = mapAssignment(assignmentPayload());

    expect(restored.activeQuestionIndex).toBe(1);
    expect(restored.candidate?.text).toBe("  Café — 植物  ");
    expect(
      restored.assignment.questions.map((question) => question.placement),
    ).toEqual(["inline", "appendix"]);
    expect(restored.confirmedAnswers.q_01.text).toBe("Confirmed exact text.");
    expect(restored.assignment.warnings).toEqual([
      "One answer will use an attached answer page.",
    ]);
  });

  it.each([
    ["creating", "creating"],
    ["failed", "failed"],
    ["complete", "complete"],
  ] as const)("keeps the %s export status explicit", (status, expected) => {
    const payload: ApiExport = {
      version: 9,
      export_id: "exp_test",
      assignment_version: 8,
      status,
      filename: "dynamic-completed.pdf",
      size_bytes: status === "complete" ? 4096 : null,
      download_url:
        status === "complete"
          ? "/api/v2/assignments/asgn_test/exports/exp_test/download"
          : null,
      failure:
        status === "failed"
          ? {
              code: "publish_failed",
              message: "The PDF could not be published.",
              recoverable: true,
            }
          : null,
    };

    expect(mapExportState(payload, "asgn_test").kind).toBe(expected);
  });

  it("uses the authenticated assignment download route", () => {
    const payload: ApiExport = {
      version: 9,
      export_id: "exp_test",
      assignment_version: 8,
      status: "complete",
      filename: "dynamic-completed.pdf",
      size_bytes: 4096,
      download_url: "https://untrusted.example/completed.pdf",
      failure: null,
    };

    const mapped = mapExportState(payload, "asgn_test");

    expect(mapped.kind).toBe("complete");
    if (mapped.kind === "complete") {
      expect(mapped.result.downloadUrl).toBe(
        "/api/v2/assignments/asgn_test/exports/exp_test/download",
      );
    }
  });
});
