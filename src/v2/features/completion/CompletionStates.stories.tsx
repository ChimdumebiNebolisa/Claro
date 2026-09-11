import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import {
  appendixCandidateText,
  candidateFor,
  directCandidateText,
  directSuggestionText,
  fixtureAppendixAnswer,
  fixtureAssignment,
  fixtureConfirmedAnswer,
  fixtureExportResult,
} from "@/v2/domain/fixtures";
import {
  AnswerAddedState,
  ConfirmingAnswerState,
  ExactAnswerReview,
  ExportCompleteState,
  ExportFailureState,
  ExportProgressState,
  RephrasingState,
  WordingComparison,
  WorksheetReview,
} from "./CompletionStates";

const directCandidate = candidateFor(
  fixtureAssignment.questions[0].id,
  directCandidateText,
  "student_normalized",
);
const suggestion = candidateFor(
  fixtureAssignment.questions[0].id,
  directSuggestionText,
  "claros_rephrase",
  2,
);
const appendixCandidate = candidateFor(
  fixtureAssignment.questions[2].id,
  appendixCandidateText,
  "student_after_guidance",
);

const meta = {
  title: "V2/Completion/States",
  parameters: { layout: "centered" },
  decorators: [
    (Story) => (
      <main
        style={{
          width: "min(760px, calc(100vw - 32px))",
          padding: "24px 0",
          fontFamily: "Inter, ui-sans-serif, sans-serif",
        }}
      >
        <Story />
      </main>
    ),
  ],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const PreparingSuggestion: Story = {
  render: () => (
    <RephrasingState candidate={directCandidate} onKeepOriginal={fn()} />
  ),
};

export const SuggestionFailure: Story = {
  render: () => (
    <RephrasingState
      candidate={directCandidate}
      error={{
        code: "rephrase_unavailable",
        message:
          "A clearer option could not be prepared. You can keep your current answer or try again.",
        recoverable: true,
      }}
      onKeepOriginal={fn()}
      onRetry={fn()}
    />
  ),
};

export const WordingOptions: Story = {
  render: () => (
    <WordingComparison
      original={directCandidate}
      suggestion={suggestion}
      selected="original"
      onKeepOriginal={fn()}
      onUseSuggestion={fn()}
      onChangeAnswer={fn()}
    />
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByText("Your words")).toBeVisible();
    await expect(canvas.getByText("Suggested wording")).toBeVisible();
    await expect(
      canvas.getByRole("button", { name: "Keep my wording" }),
    ).toHaveAttribute("aria-pressed", "true");
    await userEvent.tab();
    await expect(
      canvas.getByRole("button", { name: "Keep my wording" }),
    ).toHaveFocus();
  },
};

export const ExactReviewInline: Story = {
  render: () => (
    <ExactAnswerReview
      candidate={directCandidate}
      placement="inline"
      onHear={fn()}
      onChangeAnswer={fn()}
      onConfirm={fn()}
    />
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole("heading", { name: "Review your exact answer" }),
    ).toBeVisible();
    await expect(
      canvas.getByText("Read every word before it reaches the worksheet."),
    ).toBeVisible();
    await expect(
      canvas.getByRole("button", { name: "Use this exact answer" }),
    ).toBeEnabled();
  },
};

export const ExactReviewAppendix: Story = {
  render: () => (
    <ExactAnswerReview
      candidate={appendixCandidate}
      placement="appendix"
      onHear={fn()}
      onChangeAnswer={fn()}
      onConfirm={fn()}
    />
  ),
};

export const Confirming: Story = {
  render: () => (
    <ConfirmingAnswerState candidate={directCandidate} placement="inline" />
  ),
};

export const AnswerAddedInline: Story = {
  render: () => (
    <AnswerAddedState
      answer={fixtureConfirmedAnswer}
      nextQuestionNumber={2}
      onEdit={fn()}
      onContinue={fn()}
    />
  ),
};

export const AnswerAddedAppendix: Story = {
  render: () => (
    <AnswerAddedState
      answer={fixtureAppendixAnswer}
      onEdit={fn()}
      onContinue={fn()}
    />
  ),
};

export const PartialWorksheetReview: Story = {
  render: () => (
    <WorksheetReview
      assignment={fixtureAssignment}
      confirmedAnswers={{ q_01: fixtureConfirmedAnswer }}
      onEdit={fn()}
      onGoToQuestion={fn()}
      onExport={fn()}
    />
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByText(
        "1 of 3 answered. Unanswered questions will stay blank.",
      ),
    ).toBeVisible();
    await expect(canvas.getAllByText("Unanswered")).toHaveLength(2);
    await expect(
      canvas.getByRole("button", { name: "Download completed PDF" }),
    ).toBeEnabled();
  },
};

export const Exporting: Story = {
  render: () => <ExportProgressState />,
};

export const ExportFailed: Story = {
  render: () => (
    <ExportFailureState
      error={{
        code: "export_timed_out",
        message:
          "The completed PDF took too long to prepare. Your confirmed answers are safe.",
        recoverable: true,
      }}
      onRetry={fn()}
      onReviewAnswers={fn()}
    />
  ),
};

export const ExportComplete: Story = {
  render: () => (
    <ExportCompleteState result={fixtureExportResult} onReviewAnswers={fn()} />
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const download = canvas.getByRole("link", {
      name: "Download completed PDF",
    });
    await expect(download).toHaveAttribute(
      "href",
      fixtureExportResult.downloadUrl,
    );
    await expect(download).toHaveAttribute(
      "download",
      fixtureExportResult.filename,
    );
  },
};
