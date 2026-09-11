import type { Meta, StoryObj } from "@storybook/react-vite";
import DocumentCrop from "./DocumentCrop";
import WorksheetDialog from "./WorksheetDialog";

const meta = {
  title: "V2/Document/Authentic viewer",
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <main className="min-h-screen bg-white p-6 font-sans text-[var(--claros-ink)]">
        <h1 className="sr-only">Authentic worksheet source viewer</h1>
        <Story />
      </main>
    ),
  ],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const AuthorizedCrop: Story = {
  render: () => (
    <section className="mx-auto max-w-xl" aria-label="Authorized page crop">
      <DocumentCrop />
    </section>
  ),
};

export const ReadOnlyWorksheetDialog: Story = {
  render: () => <WorksheetDialog isOpen onOpenChange={() => undefined} />,
};
