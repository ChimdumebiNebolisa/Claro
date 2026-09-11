import { FileCheck02 } from "@untitledui/icons";
import { FileUpload } from "@/components/application/file-upload/file-upload-base";
import { LoadingIndicator } from "@/components/application/loading-indicator/loading-indicator";
import { Button } from "@/components/base/buttons/button";
import { FeaturedIcon } from "@/components/foundations/featured-icon/featured-icon";
import { StatusNotice } from "./StatusNotice";

export const MAX_WORKSHEET_BYTES = 10 * 1024 * 1024;

export type UploadValidationError = "file_too_large" | "not_pdf";

export type UploadPanelState =
  | { kind: "empty" }
  | { kind: "loading"; message?: string }
  | {
      kind: "ready";
      title: string;
      pageCount: number;
      questionCount: number;
      inlineCount?: number;
      answerPageCount?: number;
      warnings?: readonly string[];
    }
  | { kind: "error"; message: string; recoverable: boolean };

type AssignmentUploadPanelProps = {
  state: UploadPanelState;
  onFileSelected: (file: File) => void;
  onValidationError: (error: UploadValidationError) => void;
  onTrySample: () => void;
  onStart?: () => void;
  onViewWorksheet?: () => void;
  onShowLimitations?: () => void;
  validationMessage?: string;
};

const uploadErrorId = "worksheet-upload-validation-error";

function UploadControl({
  onFileSelected,
  onValidationError,
  onTrySample,
  onShowLimitations,
  validationMessage,
}: Pick<
  AssignmentUploadPanelProps,
  | "onFileSelected"
  | "onValidationError"
  | "onTrySample"
  | "onShowLimitations"
  | "validationMessage"
>) {
  return (
    <FileUpload.Root>
      <FileUpload.DropZone
        accept="application/pdf,.pdf"
        allowsMultiple={false}
        maxSize={MAX_WORKSHEET_BYTES}
        buttonLabel="Choose a PDF"
        inputLabel="Choose a PDF worksheet"
        hint="PDF with selectable text, up to 10 MiB and 8 pages"
        isInvalid={Boolean(validationMessage)}
        errorMessageId={uploadErrorId}
        className="min-h-48 justify-center border border-dashed border-[var(--claros-line-strong)] bg-[var(--claros-soft)] px-6 py-8 ring-0"
        onDropFiles={(files) => {
          const file = files.item(0);
          if (file) onFileSelected(file);
        }}
        onDropUnacceptedFiles={() => onValidationError("not_pdf")}
        onSizeLimitExceed={() => onValidationError("file_too_large")}
      />
      {validationMessage ? (
        <p
          id={uploadErrorId}
          role="alert"
          className="m-0 text-sm text-error-primary"
        >
          {validationMessage}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <Button
          color="secondary"
          size="md"
          onPress={onTrySample}
          className="min-h-11"
        >
          Try the biology sample
        </Button>
        {onShowLimitations ? (
          <Button
            color="link-gray"
            size="md"
            onPress={onShowLimitations}
            className="min-h-11"
          >
            Which PDFs work?
          </Button>
        ) : (
          <p className="m-0 text-sm text-[var(--claros-muted)]">
            Native-text short-answer worksheets only.
          </p>
        )}
      </div>
    </FileUpload.Root>
  );
}

export function AssignmentUploadPanel(props: AssignmentUploadPanelProps) {
  const { state } = props;

  if (state.kind === "loading") {
    return (
      <section
        className="grid min-h-64 place-items-center rounded-2xl border border-[var(--claros-line)] bg-white p-8"
        aria-label="Worksheet check"
        aria-live="polite"
      >
        <LoadingIndicator
          type="line-spinner"
          size="md"
          label={state.message ?? "Checking your worksheet…"}
        />
      </section>
    );
  }

  if (state.kind === "ready") {
    return (
      <section
        className="rounded-2xl border border-[var(--claros-line)] bg-white p-6"
        aria-labelledby="worksheet-ready-title"
      >
        <div className="flex items-start gap-4">
          <FeaturedIcon
            icon={FileCheck02}
            color="success"
            theme="light"
            size="md"
            className="shrink-0"
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <p className="m-0 text-sm font-semibold text-[var(--claros-green)]">
              Worksheet ready
            </p>
            <h2
              id="worksheet-ready-title"
              className="mt-1 mb-0 text-xl font-semibold tracking-[-0.02em] text-[var(--claros-ink)]"
            >
              {state.title}
            </h2>
            <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
              <div>
                <dt className="text-[13px] font-medium text-[var(--claros-muted)]">
                  Pages
                </dt>
                <dd className="mt-1 mb-0 text-base font-semibold text-[var(--claros-ink)]">
                  {state.pageCount}
                </dd>
              </div>
              <div>
                <dt className="text-[13px] font-medium text-[var(--claros-muted)]">
                  Questions
                </dt>
                <dd className="mt-1 mb-0 text-base font-semibold text-[var(--claros-ink)]">
                  {state.questionCount}
                </dd>
              </div>
              {state.inlineCount !== undefined ? (
                <div>
                  <dt className="text-[13px] font-medium text-[var(--claros-muted)]">
                    Fit on worksheet
                  </dt>
                  <dd className="mt-1 mb-0 text-base font-semibold text-[var(--claros-ink)]">
                    {state.inlineCount}
                  </dd>
                </div>
              ) : null}
              {state.answerPageCount !== undefined ? (
                <div>
                  <dt className="text-[13px] font-medium text-[var(--claros-muted)]">
                    Use answer page
                  </dt>
                  <dd className="mt-1 mb-0 text-base font-semibold text-[var(--claros-ink)]">
                    {state.answerPageCount}
                  </dd>
                </div>
              ) : null}
            </dl>
          </div>
        </div>

        {state.warnings?.map((warning) => (
          <StatusNotice
            key={warning}
            tone="warning"
            title="Check before you begin"
            className="mt-5"
          >
            <p className="m-0">{warning}</p>
          </StatusNotice>
        ))}

        <div className="mt-6 flex flex-wrap gap-3">
          <Button
            color="primary"
            size="lg"
            onPress={props.onStart}
            isDisabled={!props.onStart}
            className="min-h-11"
          >
            Start Question 1
          </Button>
          <Button
            color="secondary"
            size="lg"
            onPress={props.onViewWorksheet}
            isDisabled={!props.onViewWorksheet}
            className="min-h-11"
          >
            View worksheet
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section aria-label="Worksheet upload" className="space-y-5">
      {state.kind === "error" ? (
        <StatusNotice
          tone="error"
          title={
            state.recoverable
              ? "Choose a different worksheet"
              : "This worksheet could not be opened"
          }
        >
          <p className="m-0">{state.message}</p>
        </StatusNotice>
      ) : null}
      <UploadControl {...props} />
    </section>
  );
}
