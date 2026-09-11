// @vitest-environment jsdom

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const embedPdfMocks = vi.hoisted(() => ({
  renderPageRect: vi.fn(),
  viewer: vi.fn(),
}));

vi.mock("@embedpdf/pdfium/pdfium.wasm?url", () => ({
  default: "/assets/pdfium.wasm",
}));

vi.mock("@embedpdf/core", () => ({
  createPluginRegistration: (plugin: unknown, config: unknown) => ({
    plugin,
    config,
  }),
}));

vi.mock("@embedpdf/core/react", () => ({
  EmbedPDF: ({
    children,
  }: {
    children: (state: { activeDocumentId: string }) => unknown;
  }) => children({ activeDocumentId: "fixture-biology-crop" }),
}));

vi.mock("@embedpdf/engines/react", () => ({
  usePdfiumEngine: () => ({ engine: {}, isLoading: false, error: null }),
}));

vi.mock("@embedpdf/plugin-document-manager/react", () => ({
  DocumentManagerPluginPackage: { id: "document-manager" },
  DocumentContent: ({
    children,
  }: {
    children: (state: {
      isLoading: boolean;
      isError: boolean;
      isLoaded: boolean;
    }) => unknown;
  }) => children({ isLoading: false, isError: false, isLoaded: true }),
}));

vi.mock("@embedpdf/plugin-render/react", () => ({
  RenderPluginPackage: { id: "render" },
  useRenderCapability: () => ({
    provides: {
      forDocument: () => ({ renderPageRect: embedPdfMocks.renderPageRect }),
    },
  }),
}));

vi.mock("@embedpdf/react-pdf-viewer", () => ({
  PDFViewer: (props: unknown) => {
    embedPdfMocks.viewer(props);
    return <div data-testid="embedpdf-full-viewer" />;
  },
}));

import DocumentCrop from "../src/v2/document/DocumentCrop";
import WorksheetDialog from "../src/v2/document/WorksheetDialog";
import {
  READ_ONLY_VIEWER_CATEGORIES,
  WORKSHEET_PAGE_CONTEXT_URL,
  WORKSHEET_VIEWER_CONFIG,
} from "../src/v2/document/viewerConfig";

const serverPageContext = {
  assignment_id: "fixture-biology",
  assignment_version: 7,
  question_id: "q_01",
  question_index: 1,
  page_number: 1,
  source_sha256:
    "ccba948e849e849b80f4ce8f9d218e726b93a2efbb9eb730aabd5187e743b8d6",
  source_url: "/api/v2/fixtures/biology/source",
  source_status: "original_page_unchanged",
  render_crop: {
    page_index: 0,
    rect: {
      origin: { x: 36, y: 28 },
      size: { width: 540, height: 270 },
    },
  },
};

describe("Gate 1 EmbedPDF integration", () => {
  beforeEach(() => {
    embedPdfMocks.renderPageRect.mockReset();
    embedPdfMocks.viewer.mockReset();
    embedPdfMocks.renderPageRect.mockReturnValue({
      toPromise: () =>
        Promise.resolve(new Blob(["png"], { type: "image/png" })),
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:worksheet-crop"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => serverPageContext,
      }),
    );
  });

  it("renders only the server-authorized rectangle with forms and annotations off", async () => {
    render(<DocumentCrop />);

    await screen.findByRole("img", {
      name: /original worksheet excerpt showing question 1/i,
    });

    expect(fetch).toHaveBeenCalledWith(
      WORKSHEET_PAGE_CONTEXT_URL,
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(embedPdfMocks.renderPageRect).toHaveBeenCalledWith({
      pageIndex: serverPageContext.render_crop.page_index,
      rect: serverPageContext.render_crop.rect,
      options: expect.objectContaining({
        imageType: "image/png",
        withAnnotations: false,
        withForms: false,
      }),
    });
  });

  it("keeps the crop bound to the active question and preview source", async () => {
    const questionTwoContext = {
      ...serverPageContext,
      question_id: "q_02",
      question_index: 2,
      source_sha256:
        "3f08953dc8248758d0efac041900053f1866512d7b1d2453c224f6963cf14b05",
      source_url: "/api/v2/fixtures/biology/export",
      source_status: "completed_copy_preview",
      render_crop: {
        page_index: 0,
        rect: {
          origin: { x: 36, y: 355 },
          size: { width: 540, height: 180 },
        },
      },
    };
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => questionTwoContext,
    } as Response);
    const contextUrl = `${WORKSHEET_PAGE_CONTEXT_URL}?question_id=q_02&preview=confirmed`;

    render(<DocumentCrop contextUrl={contextUrl} />);

    await screen.findByRole("img", {
      name: /completed pdf preview showing question 2/i,
    });
    expect(fetch).toHaveBeenCalledWith(
      contextUrl,
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(embedPdfMocks.renderPageRect).toHaveBeenCalledWith(
      expect.objectContaining({ rect: questionTwoContext.render_crop.rect }),
    );
  });

  it("configures the complete viewer as range-requested and read only", () => {
    const initialDocument =
      WORKSHEET_VIEWER_CONFIG.documentManager?.initialDocuments?.[0];

    expect(initialDocument).toMatchObject({
      mode: "range-request",
      requestOptions: { credentials: "same-origin" },
    });
    expect(WORKSHEET_VIEWER_CONFIG.disabledCategories).toEqual(
      expect.arrayContaining([...READ_ONLY_VIEWER_CATEGORIES]),
    );
    expect(WORKSHEET_VIEWER_CONFIG.render).toMatchObject({
      withAnnotations: false,
      withForms: false,
    });
  });

  it("keeps the full viewer inside a modal and restores focus when closed", async () => {
    const user = userEvent.setup();

    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            View worksheet
          </button>
          {open ? <WorksheetDialog isOpen onOpenChange={setOpen} /> : null}
        </>
      );
    }

    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "View worksheet" });
    await user.click(trigger);

    expect(
      await screen.findByRole("dialog", { name: "Original worksheet" }),
    ).toBeTruthy();
    expect(screen.getByTestId("embedpdf-full-viewer")).toBeTruthy();
    expect(embedPdfMocks.viewer).toHaveBeenCalledWith(
      expect.objectContaining({ config: WORKSHEET_VIEWER_CONFIG }),
    );

    await user.click(screen.getByRole("button", { name: "Close worksheet" }));
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("keeps a visible loading status while the viewer initializes", async () => {
    render(<WorksheetDialog isOpen onOpenChange={vi.fn()} />);

    await act(async () => undefined);
    expect(screen.getByRole("status").textContent).toMatch(
      /opening the original worksheet/i,
    );
  });
});
