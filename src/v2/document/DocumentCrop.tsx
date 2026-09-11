import { createPluginRegistration } from "@embedpdf/core";
import { EmbedPDF } from "@embedpdf/core/react";
import { usePdfiumEngine } from "@embedpdf/engines/react";
import { ConsoleLogger } from "@embedpdf/models";
import {
  DocumentContent,
  DocumentManagerPluginPackage,
} from "@embedpdf/plugin-document-manager/react";
import {
  RenderPluginPackage,
  useRenderCapability,
} from "@embedpdf/plugin-render/react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../../components/base/buttons/button";
import styles from "./document.module.css";
import {
  type AuthorizedPageContext,
  parseAuthorizedPageContext,
  PDFIUM_WASM_URL,
  WORKSHEET_PAGE_CONTEXT_URL,
} from "./viewerConfig";

const debugLogger = new ConsoleLogger();

function createCropPlugins(context: AuthorizedPageContext) {
  const documentId = `fixture-crop-${context.assignmentId}-${context.assignmentVersion}-${context.questionId}`;
  return {
    documentId,
    plugins: [
      createPluginRegistration(DocumentManagerPluginPackage, {
        initialDocuments: [
          {
            url: context.sourceUrl,
            documentId,
            name: "Biology worksheet.pdf",
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
      }),
      createPluginRegistration(RenderPluginPackage, {
        withAnnotations: false,
        withForms: false,
        defaultImageType: "image/png",
      }),
    ],
  };
}

type CropRendererProps = {
  context: AuthorizedPageContext;
  documentId: string;
  onRetry: () => void;
};

function CropRenderer({ context, documentId, onRetry }: CropRendererProps) {
  const { provides: renderCapability } = useRenderCapability();
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [renderError, setRenderError] = useState(false);

  useEffect(() => {
    if (!renderCapability) return;

    let active = true;
    let ownedUrl: string | null = null;
    const task = renderCapability.forDocument(documentId).renderPageRect({
      pageIndex: context.renderCrop.pageIndex,
      rect: context.renderCrop.rect,
      options: {
        scaleFactor: 1.5,
        dpr: Math.min(window.devicePixelRatio || 1, 2),
        imageType: "image/png",
        withAnnotations: false,
        withForms: false,
      },
    });

    void task.toPromise().then(
      (blob) => {
        const nextUrl = URL.createObjectURL(blob);
        if (!active) {
          URL.revokeObjectURL(nextUrl);
          return;
        }
        ownedUrl = nextUrl;
        setImageUrl(nextUrl);
      },
      () => {
        if (active) setRenderError(true);
      },
    );

    return () => {
      active = false;
      if (ownedUrl) URL.revokeObjectURL(ownedUrl);
    };
  }, [context, documentId, renderCapability]);

  if (renderError) {
    return <CropError onRetry={onRetry} />;
  }

  if (!imageUrl) {
    return (
      <div className={styles.cropState} role="status">
        Rendering the original question…
      </div>
    );
  }

  return (
    <figure className={styles.cropFigure}>
      <img
        className={styles.cropImage}
        src={imageUrl}
        alt={`${context.sourceStatus === "completed_copy_preview" ? "Completed PDF preview" : "Original worksheet excerpt"} showing question ${context.questionIndex} and its answer area`}
        draggable={false}
      />
      <figcaption>
        Page {context.pageNumber} ·{" "}
        {context.sourceStatus === "completed_copy_preview"
          ? "Confirmed answer preview"
          : "Verified source context"}
      </figcaption>
    </figure>
  );
}

function CropError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className={styles.cropError} role="alert">
      <strong>The source preview could not be rendered.</strong>
      <span>Your answer area is still available.</span>
      <Button color="secondary" size="sm" onPress={onRetry}>
        Try preview again
      </Button>
    </div>
  );
}

function CropRuntime({
  context,
  onRetry,
}: {
  context: AuthorizedPageContext;
  onRetry: () => void;
}) {
  const { documentId, plugins } = useMemo(
    () => createCropPlugins(context),
    [context],
  );
  const { engine, isLoading, error } = usePdfiumEngine({
    wasmUrl: PDFIUM_WASM_URL,
    worker: true,
    fontFallback: null,
    logger: debugLogger,
  });

  if (isLoading) {
    return (
      <div className={styles.cropState} role="status">
        Starting the secure document renderer…
      </div>
    );
  }

  if (error || !engine) {
    return <CropError onRetry={onRetry} />;
  }

  return (
    <EmbedPDF
      engine={engine}
      plugins={plugins}
      config={{
        logger: debugLogger,
        permissions: {
          overrides: {
            print: false,
            modifyContents: false,
            modifyAnnotations: false,
            fillForms: false,
            assembleDocument: false,
          },
        },
      }}
    >
      {({ activeDocumentId }) => (
        <DocumentContent documentId={activeDocumentId}>
          {({ isLoading: isDocumentLoading, isError, isLoaded }) => {
            if (isError) return <CropError onRetry={onRetry} />;
            if (isDocumentLoading || !isLoaded || !activeDocumentId) {
              return (
                <div className={styles.cropState} role="status">
                  Loading the original page…
                </div>
              );
            }
            return (
              <CropRenderer
                context={context}
                documentId={documentId}
                onRetry={onRetry}
              />
            );
          }}
        </DocumentContent>
      )}
    </EmbedPDF>
  );
}

function DocumentCropAttempt({
  contextUrl,
  onRetry,
}: {
  contextUrl: string;
  onRetry: () => void;
}) {
  const [context, setContext] = useState<AuthorizedPageContext | null>(null);
  const [contextError, setContextError] = useState(false);
  const [canMountRenderer, setCanMountRenderer] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    void fetch(contextUrl, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("page context unavailable");
        const parsed = parseAuthorizedPageContext(await response.json());
        if (!parsed) throw new Error("page context invalid");
        setContext(parsed);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setContextError(true);
        }
      });

    return () => controller.abort();
  }, [contextUrl]);

  // Keep the task-first shell responsive while the PDFium chunk initializes.
  useEffect(() => {
    const timer = window.setTimeout(() => setCanMountRenderer(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  if (contextError) return <CropError onRetry={onRetry} />;
  if (!context) {
    return (
      <div className={styles.cropState} role="status">
        Loading verified source context…
      </div>
    );
  }
  if (!canMountRenderer) {
    return (
      <div className={styles.cropState} role="status">
        Preparing the source preview…
      </div>
    );
  }

  return <CropRuntime context={context} onRetry={onRetry} />;
}

export default function DocumentCrop({
  contextUrl = WORKSHEET_PAGE_CONTEXT_URL,
}: {
  contextUrl?: string;
}) {
  const [attempt, setAttempt] = useState(0);

  return (
    <div className={styles.cropRoot} data-testid="document-crop">
      <DocumentCropAttempt
        key={`${contextUrl}:${attempt}`}
        contextUrl={contextUrl}
        onRetry={() => setAttempt((value) => value + 1)}
      />
    </div>
  );
}
