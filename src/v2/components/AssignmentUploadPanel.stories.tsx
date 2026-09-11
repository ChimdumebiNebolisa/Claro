import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { assignmentHandlers } from "@/mocks/handlers";
import { AssignmentUploadPanel } from "./AssignmentUploadPanel";

const meta = {
  title: "V2/Assignment/Upload panel",
  component: AssignmentUploadPanel,
  parameters: {
    layout: "centered",
  },
  decorators: [
    (Story) => (
      <main className="w-[min(680px,calc(100vw-32px))] bg-white p-6 font-sans text-[var(--claros-ink)]">
        <h1 className="sr-only">Assignment upload</h1>
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
} satisfies Meta<typeof AssignmentUploadPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: { state: { kind: "empty" } },
  parameters: { msw: assignmentHandlers.empty },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const chooseButton = canvas.getByRole("button", { name: "Choose a PDF" });
    await userEvent.tab();
    await expect(chooseButton).toHaveFocus();
    await expect(
      canvas.getByLabelText("Choose a PDF worksheet"),
    ).toHaveAttribute("accept", "application/pdf,.pdf");
  },
};

export const Loading: Story = {
  args: { state: { kind: "loading", message: "Checking your worksheet…" } },
  parameters: { msw: assignmentHandlers.loading },
};

export const Ready: Story = {
  args: {
    state: {
      kind: "ready",
      title: "Photosynthesis and plant cells",
      pageCount: 2,
      questionCount: 3,
      inlineCount: 2,
      answerPageCount: 1,
      warnings: [
        "One answer will use an attached answer page if it does not fit safely.",
      ],
    },
  },
  parameters: { msw: assignmentHandlers.ready },
};

export const Error: Story = {
  args: {
    state: {
      kind: "error",
      message:
        "This PDF appears to be scanned. Claros V2 supports PDFs with selectable text.",
      recoverable: true,
    },
  },
  parameters: { msw: assignmentHandlers.error },
};

export const DocumentViewer: Story = {
  args: {
    state: {
      kind: "ready",
      title: "Photosynthesis and plant cells",
      pageCount: 2,
      questionCount: 3,
      inlineCount: 2,
      answerPageCount: 1,
    },
  },
  parameters: { msw: assignmentHandlers.documentViewer },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole("button", { name: "View worksheet" }),
    ).toBeEnabled();
  },
};
