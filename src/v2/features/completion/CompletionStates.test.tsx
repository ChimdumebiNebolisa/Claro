// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  candidateFor,
  directCandidateText,
  directSuggestionText,
  fixtureAssignment,
  fixtureConfirmedAnswer,
  fixtureExportResult,
} from "@/v2/domain/fixtures";
import {
  ExactAnswerReview,
  ExportCompleteState,
  RephrasingState,
  WordingComparison,
  WorksheetReview,
} from "./CompletionStates";

const candidate = candidateFor(
  fixtureAssignment.questions[0].id,
  `Plants need sunlight—it’s how they make café-ready sugar.`,
  "student_edited",
);
const suggestion = candidateFor(
  fixtureAssignment.questions[0].id,
  directSuggestionText,
  "claros_rephrase",
  2,
);

afterEach(cleanup);

describe("Gate 2 completion states", () => {
  it("keeps exact Unicode and approval separate in exact review", async () => {
    const user = userEvent.setup();
    const onHear = vi.fn();
    const onChangeAnswer = vi.fn();
    const onConfirm = vi.fn();

    render(
      <ExactAnswerReview
        candidate={candidate}
        placement="appendix"
        onHear={onHear}
        onChangeAnswer={onChangeAnswer}
        onConfirm={onConfirm}
      />,
    );

    expect(screen.getByText(candidate.text)).toHaveTextContent(
      `Plants need sunlight—it’s how they make café-ready sugar.`,
    );
    expect(screen.getByText("Your words")).toBeVisible();
    expect(
      screen.getByText("This answer will appear on an attached answer page."),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Hear it" }));
    expect(onHear).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", { name: "Use this exact answer" }),
    );
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("shows both wording options and reports selection without hiding either", async () => {
    const user = userEvent.setup();
    const onUseSuggestion = vi.fn();

    render(
      <WordingComparison
        original={candidateFor(
          fixtureAssignment.questions[0].id,
          directCandidateText,
          "student_normalized",
        )}
        suggestion={suggestion}
        selected="suggestion"
        onKeepOriginal={vi.fn()}
        onUseSuggestion={onUseSuggestion}
      />,
    );

    expect(screen.getByText(directCandidateText)).toBeVisible();
    expect(screen.getByText(directSuggestionText)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Use suggestion" }),
    ).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Use suggestion" }));
    expect(onUseSuggestion).toHaveBeenCalledOnce();
  });

  it("preserves the current answer when a rephrase fails", () => {
    render(
      <RephrasingState
        candidate={candidate}
        error={{
          code: "rephrase_unavailable",
          message: "A clearer option could not be prepared.",
          recoverable: true,
        }}
        onKeepOriginal={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText(candidate.text)).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Your answer is unchanged",
    );
  });

  it("allows partial export and identifies unanswered questions", async () => {
    const user = userEvent.setup();
    const onExport = vi.fn();

    render(
      <WorksheetReview
        assignment={fixtureAssignment}
        confirmedAnswers={{ q_01: fixtureConfirmedAnswer }}
        onEdit={vi.fn()}
        onGoToQuestion={vi.fn()}
        onExport={onExport}
      />,
    );

    expect(
      screen.getByText(
        "1 of 3 answered. Unanswered questions will stay blank.",
      ),
    ).toBeVisible();
    expect(screen.getAllByText("Unanswered")).toHaveLength(2);

    await user.click(
      screen.getByRole("button", { name: "Download completed PDF" }),
    );
    expect(onExport).toHaveBeenCalledOnce();
  });

  it("renders the completed artifact as a real download link", () => {
    render(
      <ExportCompleteState
        result={fixtureExportResult}
        onReviewAnswers={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("link", { name: "Download completed PDF" }),
    ).toHaveAttribute("href", fixtureExportResult.downloadUrl);
    expect(
      screen.getByRole("link", { name: "Download completed PDF" }),
    ).toHaveAttribute("download", fixtureExportResult.filename);
  });
});
