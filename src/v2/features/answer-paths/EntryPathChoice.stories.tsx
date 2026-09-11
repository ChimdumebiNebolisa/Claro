import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { fixtureAssignment } from "../../domain/fixtures";
import { EntryPathChoice } from "./EntryPathChoice";

const meta = {
  title: "V2/Question/Choose answer path",
  component: EntryPathChoice,
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
    onChooseDirect: fn(),
    onChooseGuided: fn(),
    onTypeInstead: fn(),
    onViewWorksheet: fn(),
  },
} satisfies Meta<typeof EntryPathChoice>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole("heading", { name: "Why do plants need sunlight?" }),
    ).toBeVisible();
    await userEvent.click(
      canvas.getByRole("button", { name: /start answering/i }),
    );
    await expect(args.onChooseDirect).toHaveBeenCalledOnce();
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile1", isRotated: false } },
};
