import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import {
  fixtureAssignment,
  fixtureGuidedTurns,
  guidedCandidateText,
} from "../../domain/fixtures";
import { GuidedReasoningPanel } from "./GuidedReasoningPanel";

const meta = {
  title: "V2/Question/Guided reasoning",
  component: GuidedReasoningPanel,
  parameters: { layout: "centered" },
  decorators: [
    (Story) => (
      <main
        style={{
          width: "min(760px, calc(100vw - 32px))",
          padding: 24,
          background: "white",
        }}
      >
        <Story />
      </main>
    ),
  ],
  args: {
    question: fixtureAssignment.questions[1],
    totalQuestions: fixtureAssignment.questions.length,
    turns: fixtureGuidedTurns,
    draft: "",
    voiceState: "ready",
    onDraftChange: fn(),
    onSendTypedTurn: fn(),
    onReadyToAnswer: fn(),
    onMakeClearer: fn(),
    onReview: fn(),
    onStart: fn(),
    onStop: fn(),
    onRetry: fn(),
    onContinueByTyping: fn(),
    onInterrupt: fn(),
    onToggleMute: fn(),
  },
} satisfies Meta<typeof GuidedReasoningPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Conversation: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByText("Good. State your final answer in your own words."),
    ).toBeVisible();
    await expect(
      canvas.getByRole("textbox", { name: "Your response" }),
    ).toBeEnabled();
  },
};

export const Thinking: Story = {
  args: { voiceState: "thinking" },
};

export const Speaking: Story = {
  args: { voiceState: "speaking" },
};

export const VoiceUnavailable: Story = {
  args: {
    voiceState: "microphone_unavailable",
    draft: "It gives the plant energy",
  },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement);
    const editor = canvas.getByRole("textbox", { name: "Your response" });
    await userEvent.click(
      canvas.getByRole("button", { name: "Continue by typing" }),
    );
    await expect(editor).toHaveFocus();
    await expect(editor).toHaveValue("It gives the plant energy");
    await expect(args.onContinueByTyping).toHaveBeenCalledOnce();
  },
};

export const FinalAnswer: Story = {
  args: {
    mode: "final-answer",
    draft: guidedCandidateText,
    voiceState: "captured",
  },
};
