// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { assignmentFixtures, fixtureAssignmentId } from "../src/mocks/fixtures";
import { assignmentHandlers } from "../src/mocks/handlers";
import {
  AssignmentUploadPanel,
  MAX_WORKSHEET_BYTES,
} from "../src/v2/components/AssignmentUploadPanel";

class DataTransferMock {
  readonly filesStore: File[] = [];

  readonly items = {
    add: (file: File) => {
      this.filesStore.push(file);
      return {} as DataTransferItem;
    },
  };

  get files(): FileList {
    const files = [...this.filesStore] as File[] & {
      item: (index: number) => File | null;
    };
    files.item = (index) => files[index] ?? null;
    return files as unknown as FileList;
  }
}

Object.defineProperty(globalThis, "DataTransfer", {
  configurable: true,
  value: DataTransferMock,
});

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

const requiredProps = {
  onFileSelected: vi.fn(),
  onValidationError: vi.fn(),
  onTrySample: vi.fn(),
  onStart: vi.fn(),
  onViewWorksheet: vi.fn(),
  onShowLimitations: vi.fn(),
};

describe("AssignmentUploadPanel", () => {
  it("exposes one keyboard-operable file action and a labelled PDF input", async () => {
    const user = userEvent.setup();
    const inputClick = vi
      .spyOn(HTMLInputElement.prototype, "click")
      .mockImplementation(() => undefined);
    render(
      <AssignmentUploadPanel {...requiredProps} state={{ kind: "empty" }} />,
    );

    const chooseButton = screen.getByRole("button", { name: "Choose a PDF" });
    const input = screen.getByLabelText("Choose a PDF worksheet");

    expect(input).toHaveAttribute("accept", "application/pdf,.pdf");
    expect(input).toHaveAttribute("tabindex", "-1");

    await user.tab();
    expect(chooseButton).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(inputClick).toHaveBeenCalledOnce();
  });

  it("reports immediate type and size failures through controlled callbacks", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const onValidationError = vi.fn();
    render(
      <AssignmentUploadPanel
        {...requiredProps}
        onValidationError={onValidationError}
        state={{ kind: "empty" }}
      />,
    );

    const input = screen.getByLabelText(
      "Choose a PDF worksheet",
    ) as HTMLInputElement;
    await user.upload(
      input,
      new File(["plain text"], "notes.txt", { type: "text/plain" }),
    );
    expect(onValidationError).toHaveBeenCalledWith("not_pdf");

    await user.upload(
      input,
      new File([new Uint8Array(MAX_WORKSHEET_BYTES + 1)], "too-large.pdf", {
        type: "application/pdf",
      }),
    );
    expect(onValidationError).toHaveBeenCalledWith("file_too_large");
  });

  it("associates a persistent validation message with the file controls", () => {
    render(
      <AssignmentUploadPanel
        {...requiredProps}
        state={{ kind: "empty" }}
        validationMessage="Choose a PDF file."
      />,
    );

    const message = screen.getByRole("alert");
    const input = screen.getByLabelText("Choose a PDF worksheet");
    const button = screen.getByRole("button", { name: "Choose a PDF" });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", message.id);
    expect(button).toHaveAttribute("aria-describedby", message.id);
  });

  it("announces truthful loading, ready, and recoverable error states", async () => {
    const { rerender } = render(
      <AssignmentUploadPanel
        {...requiredProps}
        state={{ kind: "loading", message: "Checking your worksheet…" }}
      />,
    );
    expect(screen.getByText("Checking your worksheet…")).toBeVisible();

    rerender(
      <AssignmentUploadPanel
        {...requiredProps}
        state={{
          kind: "ready",
          title: "Photosynthesis and plant cells",
          pageCount: 2,
          questionCount: 3,
          inlineCount: 2,
          answerPageCount: 1,
        }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Photosynthesis and plant cells" }),
    ).toBeVisible();
    expect(screen.getByText("Use answer page")).toBeVisible();

    rerender(
      <AssignmentUploadPanel
        {...requiredProps}
        state={{
          kind: "error",
          message: assignmentFixtures.error.error.message,
          recoverable: true,
        }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("selectable text");
    expect(
      screen.getByRole("button", { name: "Try the biology sample" }),
    ).toBeEnabled();
  });
});

describe("Gate 1 MSW fixtures", () => {
  it.each([
    ["empty", assignmentHandlers.empty, 404],
    ["loading", assignmentHandlers.loading, 200],
    ["ready", assignmentHandlers.ready, 200],
    ["error", assignmentHandlers.error, 422],
  ] as const)(
    "serves the %s assignment state deterministically",
    async (_, handlers, expectedStatus) => {
      server.use(...handlers);
      const response = await fetch(
        `http://localhost/api/v2/assignments/${fixtureAssignmentId}`,
      );
      expect(response.status).toBe(expectedStatus);
      expect(await response.json()).toBeDefined();
    },
  );

  it("serves a verified display crop without exposing placement geometry", async () => {
    server.use(...assignmentHandlers.documentViewer);
    const response = await fetch(
      `http://localhost/api/v2/assignments/${fixtureAssignmentId}/pages/1/context`,
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toEqual(assignmentFixtures.documentViewer);
    expect(payload.render_crop).toEqual(
      assignmentFixtures.documentViewer.render_crop,
    );
    expect(payload).not.toHaveProperty("answer_region");
  });
});
