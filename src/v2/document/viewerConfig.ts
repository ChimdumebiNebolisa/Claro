import type { PDFViewerConfig } from "@embedpdf/react-pdf-viewer";
import pdfiumWasmUrl from "@embedpdf/pdfium/pdfium.wasm?url";

export const WORKSHEET_SOURCE_URL = "/api/v2/fixtures/biology/source";
export const WORKSHEET_PAGE_CONTEXT_URL =
  "/api/v2/fixtures/biology/page-context";

export type AuthorizedPageContext = {
  assignmentId: string;
  assignmentVersion: number;
  questionId: string;
  questionIndex: number;
  pageNumber: number;
  sourceSha256: string;
  sourceUrl: string;
  sourceStatus: "original_page_unchanged" | "completed_copy_preview";
  renderCrop: {
    pageIndex: number;
    rect: {
      origin: { x: number; y: number };
      size: { width: number; height: number };
    };
  };
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isSafeInteger = (value: unknown): value is number =>
  isFiniteNumber(value) && Number.isSafeInteger(value);

export function parseAuthorizedPageContext(
  value: unknown,
): AuthorizedPageContext | null {
  if (!isRecord(value)) return null;
  if (isRecord(value.crop)) {
    const crop = value.crop;
    const sourceStatus =
      value.source_status === "original"
        ? "original_page_unchanged"
        : value.source_status;
    const valid =
      isSafeInteger(value.version) &&
      typeof value.question_id === "string" &&
      isSafeInteger(value.question_index) &&
      (value.question_index as number) > 0 &&
      isSafeInteger(value.page_number) &&
      typeof value.source_sha256 === "string" &&
      /^[a-f0-9]{64}$/i.test(value.source_sha256) &&
      typeof value.source_url === "string" &&
      value.source_url.startsWith("/api/v2/") &&
      (sourceStatus === "original_page_unchanged" ||
        sourceStatus === "completed_copy_preview") &&
      isSafeInteger(crop.x_mpt) &&
      (crop.x_mpt as number) >= 0 &&
      isSafeInteger(crop.y_mpt) &&
      (crop.y_mpt as number) >= 0 &&
      isSafeInteger(crop.width_mpt) &&
      (crop.width_mpt as number) > 0 &&
      isSafeInteger(crop.height_mpt) &&
      (crop.height_mpt as number) > 0;
    if (!valid) return null;
    const sourceUrl = value.source_url as string;
    return {
      assignmentId:
        /\/assignments\/([^/]+)/.exec(sourceUrl)?.[1] ?? "authorized-source",
      assignmentVersion: value.version as number,
      questionId: value.question_id as string,
      questionIndex: value.question_index as number,
      pageNumber: value.page_number as number,
      sourceSha256: value.source_sha256 as string,
      sourceUrl,
      sourceStatus: sourceStatus as AuthorizedPageContext["sourceStatus"],
      renderCrop: {
        pageIndex: (value.page_number as number) - 1,
        rect: {
          origin: {
            x: (crop.x_mpt as number) / 1_000,
            y: (crop.y_mpt as number) / 1_000,
          },
          size: {
            width: (crop.width_mpt as number) / 1_000,
            height: (crop.height_mpt as number) / 1_000,
          },
        },
      },
    };
  }
  if (!isRecord(value.render_crop)) return null;
  const renderCrop = value.render_crop;
  if (!isRecord(renderCrop.rect)) return null;
  const rect = renderCrop.rect;
  if (!isRecord(rect.origin) || !isRecord(rect.size)) return null;

  const valid =
    typeof value.assignment_id === "string" &&
    isSafeInteger(value.assignment_version) &&
    typeof value.question_id === "string" &&
    isSafeInteger(value.question_index) &&
    (value.question_index as number) > 0 &&
    isSafeInteger(value.page_number) &&
    typeof value.source_sha256 === "string" &&
    /^[a-f0-9]{64}$/i.test(value.source_sha256) &&
    typeof value.source_url === "string" &&
    value.source_url.startsWith("/api/v2/") &&
    (value.source_status === "original_page_unchanged" ||
      value.source_status === "completed_copy_preview") &&
    isSafeInteger(renderCrop.page_index) &&
    isFiniteNumber(rect.origin.x) &&
    isFiniteNumber(rect.origin.y) &&
    isFiniteNumber(rect.size.width) &&
    rect.size.width > 0 &&
    isFiniteNumber(rect.size.height) &&
    rect.size.height > 0;
  if (!valid) return null;

  return {
    assignmentId: value.assignment_id as string,
    assignmentVersion: value.assignment_version as number,
    questionId: value.question_id as string,
    questionIndex: value.question_index as number,
    pageNumber: value.page_number as number,
    sourceSha256: value.source_sha256 as string,
    sourceUrl: value.source_url as string,
    sourceStatus: value.source_status as AuthorizedPageContext["sourceStatus"],
    renderCrop: {
      pageIndex: renderCrop.page_index as number,
      rect: {
        origin: {
          x: rect.origin.x as number,
          y: rect.origin.y as number,
        },
        size: {
          width: rect.size.width as number,
          height: rect.size.height as number,
        },
      },
    },
  };
}

export const READ_ONLY_VIEWER_CATEGORIES = [
  "document",
  "annotation",
  "panel-comment",
  "form",
  "redaction",
  "insert",
  "security",
  "document-print",
  "document-export",
  "document-capture",
  "document-open",
  "document-close",
  "capture",
] as const;

// The PDFium worker is created from a blob URL, so it needs an absolute URL
// rather than Vite's root-relative asset path to fetch the WASM binary.
export const PDFIUM_WASM_URL = new URL(pdfiumWasmUrl, import.meta.url).href;

export const createWorksheetViewerConfig = (
  sourceUrl = WORKSHEET_SOURCE_URL,
  filename = "Biology worksheet.pdf",
): PDFViewerConfig => ({
  src: sourceUrl,
  wasmUrl: PDFIUM_WASM_URL,
  worker: true,
  fontFallback: null,
  fonts: { ui: null, signature: null },
  tabBar: "never",
  disabledCategories: [...READ_ONLY_VIEWER_CATEGORIES],
  documentManager: {
    initialDocuments: [
      {
        url: sourceUrl,
        documentId: `worksheet-source-${sourceUrl}`,
        name: filename,
        mode: "range-request",
        requestOptions: { credentials: "same-origin" },
        permissions: {
          overrides: {
            print: false,
            modifyContents: false,
            modifyAnnotations: false,
            fillForms: false,
            assembleDocument: false,
          },
        },
      },
    ],
  },
  permissions: {
    overrides: {
      print: false,
      modifyContents: false,
      modifyAnnotations: false,
      fillForms: false,
      assembleDocument: false,
    },
  },
  render: { withAnnotations: false, withForms: false },
  stamp: { defaultLibrary: false, libraries: [], manifests: [] },
  theme: {
    preference: "light",
    light: {
      accent: { primary: "#075ee8" },
    },
  },
});

export const WORKSHEET_VIEWER_CONFIG = createWorksheetViewerConfig();
