import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { directCandidateText, fixtureAssignment } from "../../domain/fixtures";
import { DirectAnswerPanel } from "./DirectAnswerPanel";

const meta = {
  title: "V2/Question/Direct answer",
  component: DirectAnswerPanel,
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
    question: fixtureAssignment.questions[0],
    totalQuestions: fixtureAssignment.questions.length,
    candidateText: "",
    voiceState: "ready",
    onCandidateChange: fn(),
    onTypeInstead: fn(),
    onMakeClearer: fn(),
    onReview: fn(),
    onStart: fn(),
    onStop: fn(),
    onRetry: fn(),
    onContinueByTyping: fn(),
    onToggleMute: fn(),
  },
} satisfies Meta<typeof DirectAnswerPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Ready: Story = {
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement);
    const editor = canvas.getByRole("textbox", { name: "Your words" });
    await userEvent.click(canvas.getByRole("button", { name: "Type instead" }));
    await expect(editor).toHaveFocus();
    await expect(args.onTypeInstead).toHaveBeenCalledOnce();
  },
};

export const Listening: Story = {
  args: { voiceState: "listening" },
};

export const Captured: Story = {
  args: {
    voiceState: "captured",
    candidateText: directCandidateText,
  },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole("textbox", { name: "Your words" }),
    ).toHaveValue(directCandidateText);
    await userEvent.click(
      canvas.getByRole("button", { name: /review answer/i }),
    );
    await expect(args.onReview).toHaveBeenCalledOnce();
  },
};

export const MicrophoneUnavailable: Story = {
  args: {
    voiceState: "microphone_unavailable",
    candidateText: "Plants need sunlight because",
  },
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement);
    const editor = canvas.getByRole("textbox", { name: "Your words" });
    await userEvent.click(
      canvas.getByRole("button", { name: "Continue by typing" }),
    );
    await expect(editor).toHaveFocus();
    await expect(editor).toHaveValue("Plants need sunlight because");
    await expect(args.onContinueByTyping).toHaveBeenCalledOnce();
  },
};

export const ConnectionLost: Story = {
  args: {
    voiceState: "disconnected",
    candidateText: "Plants need sunlight because",
  },
};

export const UnicodeCandidate: Story = {
  args: {
    voiceState: "captured",
    candidateText: "José’s café plant — “sunlight”",
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole("textbox", { name: "Your words" }),
    ).toHaveValue("José’s café plant — “sunlight”");
  },
};
