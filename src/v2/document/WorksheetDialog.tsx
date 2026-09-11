import { XClose } from "@untitledui/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  DocumentManagerCapability,
  DocumentManagerPlugin,
} from "@embedpdf/plugin-document-manager";
import { PDFViewer } from "@embedpdf/react-pdf-viewer";
import type { PluginRegistry } from "@embedpdf/core";
import {
  Dialog,
  Modal,
  ModalOverlay,
} from "../../components/application/modals/modal";
import { Button } from "../../components/base/buttons/button";
import styles from "./document.module.css";
import { createWorksheetViewerConfig } from "./viewerConfig";

type WorksheetDialogProps = {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  sourceUrl?: string;
  filename?: string;
};

type ViewerState =
  | { kind: "loading"; message: string }
  | { kind: "ready"; message: string }
  | { kind: "error"; message: string };

function repairEmbedPdfAccessibility(host: HTMLElement) {
  const container = host.querySelector(
    "embedpdf-container",
  ) as HTMLElement | null;
  const root = container?.shadowRoot;
  if (!root) return null;

  root.querySelectorAll("img:not([alt])").forEach((image) => {
    image.setAttribute("alt", "");
  });
  root.querySelectorAll('svg[role="img"]').forEach((icon) => {
    icon.removeAttribute("role");
    icon.setAttribute("aria-hidden", "true");
  });
  root.querySelectorAll<HTMLElement>(".bg-bg-app").forEach((viewport) => {
    if (!viewport.hasAttribute("tabindex")) viewport.tabIndex = 0;
    if (!viewport.hasAttribute("aria-label")) {
      viewport.setAttribute("aria-label", "Worksheet pages");
    }
    if (!viewport.hasAttribute("role")) viewport.setAttribute("role", "region");
  });

  return root;
}

export default function WorksheetDialog({
  isOpen,
  onOpenChange,
  sourceUrl,
  filename,
}: WorksheetDialogProps) {
  const viewerConfig = useMemo(
    () => createWorksheetViewerConfig(sourceUrl, filename),
    [filename, sourceUrl],
  );
  const [viewerState, setViewerState] = useState<ViewerState>({
    kind: "loading",
    message: "Opening the original worksheet…",
  });
  const unsubscribeRef = useRef<Array<() => void>>([]);
  const viewerHostRef = useRef<HTMLDivElement>(null);

  useEffect(
    () => () => {
      unsubscribeRef.current.forEach((unsubscribe) => unsubscribe());
      unsubscribeRef.current = [];
    },
    [],
  );

  useEffect(() => {
    const host = viewerHostRef.current;
    if (!isOpen || !host) return;

    let shadowObserver: MutationObserver | null = null;
    let renderPoll: number | null = null;
    const repair = () => {
      const shadowRoot = repairEmbedPdfAccessibility(host);
      const hasRenderedPage = Boolean(
        shadowRoot &&
        [...shadowRoot.querySelectorAll("img")].some(
          (image) =>
            image.complete &&
            image.naturalWidth > 0 &&
            image.getBoundingClientRect().height > 100,
        ),
      );
      if (hasRenderedPage) {
        if (renderPoll !== null) {
          window.clearInterval(renderPoll);
          renderPoll = null;
        }
        setViewerState((current) =>
          current.kind === "ready"
            ? current
            : {
                kind: "ready",
                message: "Original worksheet ready. Read only.",
              },
        );
      }
      if (shadowRoot && !shadowObserver) {
        shadowObserver = new MutationObserver(repair);
        shadowObserver.observe(shadowRoot, { childList: true, subtree: true });
      }
    };
    const hostObserver = new MutationObserver(repair);
    hostObserver.observe(host, { childList: true, subtree: true });
    renderPoll = window.setInterval(repair, 100);
    repair();

    return () => {
      if (renderPoll !== null) window.clearInterval(renderPoll);
      hostObserver.disconnect();
      shadowObserver?.disconnect();
    };
  }, [isOpen]);

  const handleReady = (registry: PluginRegistry) => {
    unsubscribeRef.current.forEach((unsubscribe) => unsubscribe());
    const plugin =
      registry.getPlugin<DocumentManagerPlugin>("document-manager");
    const manager = plugin?.provides?.() as
      DocumentManagerCapability | undefined;

    if (!manager) {
      setViewerState({
        kind: "error",
        message:
          "The worksheet viewer could not connect to the source document.",
      });
      return;
    }

    const activeDocument = manager.getActiveDocument();
    if (activeDocument) {
      setViewerState({
        kind: "loading",
        message: "Rendering the original worksheet…",
      });
    }

    unsubscribeRef.current = [
      manager.onDocumentOpened(() => {
        setViewerState({
          kind: "loading",
          message: "Rendering the original worksheet…",
        });
      }),
      manager.onDocumentError(() => {
        setViewerState({
          kind: "error",
          message:
            "The original worksheet could not be opened. Close this view and try again.",
        });
      }),
    ];
  };

  return (
    <ModalOverlay
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      isDismissable
      className={styles.dialogOverlay}
    >
      <Modal className={styles.dialogModal}>
        <Dialog
          aria-labelledby="worksheet-dialog-title"
          className={styles.dialog}
        >
          <header className={styles.dialogHeader}>
            <div>
              <h2 id="worksheet-dialog-title">Original worksheet</h2>
              <p
                className={
                  viewerState.kind === "error"
                    ? styles.statusError
                    : styles.status
                }
                role={viewerState.kind === "error" ? "alert" : "status"}
              >
                {viewerState.message}
              </p>
            </div>
            <Button
              color="tertiary"
              size="sm"
              className="min-h-11 min-w-11"
              iconLeading={XClose}
              aria-label="Close worksheet"
              onPress={() => onOpenChange(false)}
            />
          </header>
          <div
            ref={viewerHostRef}
            className={styles.viewerFrame}
            role="region"
            aria-label="Read-only worksheet viewer"
          >
            <PDFViewer
              config={viewerConfig}
              className={styles.viewer}
              onReady={handleReady}
            />
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
