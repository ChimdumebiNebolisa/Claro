import type { Meta, StoryObj } from "@storybook/react-vite";
import { StatePreview, type AnswerState } from "./StatePreview";

const meta = {
  title: "Claros/Answer states",
  component: StatePreview,
  parameters: { layout: "centered" },
  decorators: [
    (Story) => (
      <div className="legacy-root">
        <Story />
      </div>
    ),
  ],
  argTypes: {
    state: {
      control: "select",
      options: [
        "draft",
        "review",
        "blocked",
        "committed",
        "unsupported",
        "expired",
      ] satisfies AnswerState[],
    },
  },
} satisfies Meta<typeof StatePreview>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Draft: Story = { args: { state: "draft" } };
export const Review: Story = { args: { state: "review" } };
export const Blocked: Story = { args: { state: "blocked" } };
export const Committed: Story = { args: { state: "committed" } };
