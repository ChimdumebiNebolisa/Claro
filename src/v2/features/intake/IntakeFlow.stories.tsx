import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { fixtureAssignment } from "../../domain/fixtures";
import { IntakeFlow } from "./IntakeFlow";

const meta = {
  title: "V2/Flow/Intake",
  component: IntakeFlow,
  parameters: { layout: "centered" },
  decorators: [
    (Story) => (
      <main
        style={{
          width: "min(720px, calc(100vw - 32px))",
          padding: 24,
          background: "white",
        }}
      >
        <Story />
      </main>
    ),
  ],
  args: {
    onFileSelected: fn(),
    onValidationError: fn(),
    onTrySample: fn(),
    onStart: fn(),
    onViewWorksheet: fn(),
    onShowLimitations: fn(),
  },
} satisfies Meta<typeof IntakeFlow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Upload: Story = {
  args: { state: { kind: "upload" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole("heading", { name: "Bring in a worksheet." }),
    ).toBeVisible();
    await userEvent.tab();
    await expect(
      canvas.getByRole("button", { name: "Choose a PDF" }),
    ).toHaveFocus();
  },
};

export const Checking: Story = {
  args: { state: { kind: "checking" } },
};

export const Unsupported: Story = {
  args: {
    state: {
      kind: "unsupported",
      message:
        "This PDF appears to be scanned. Claros supports PDFs with selectable text.",
      recoverable: true,
    },
  },
};

export const Ready: Story = {
  args: {
    state: {
      kind: "ready",
      assignment: fixtureAssignment,
      inlineCount: 2,
      answerPageCount: 1,
      warnings: [
        "One answer will use an attached answer page if it does not fit safely.",
      ],
    },
  },
};
