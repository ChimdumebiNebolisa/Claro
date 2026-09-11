import type { Assignment } from "../../domain/contracts";
import {
  AssignmentUploadPanel,
  type UploadValidationError,
} from "../../components/AssignmentUploadPanel";
import styles from "./intake.module.css";

export type IntakeViewState =
  | { kind: "upload" }
  | { kind: "checking"; message?: string }
  | { kind: "unsupported"; message: string; recoverable: boolean }
  | {
      kind: "ready";
      assignment: Assignment;
      inlineCount?: number;
      answerPageCount?: number;
      warnings?: readonly string[];
    };

export type IntakeFlowProps = {
  state: IntakeViewState;
  onFileSelected: (file: File) => void;
  onValidationError: (error: UploadValidationError) => void;
  onTrySample: () => void;
  onStart?: () => void;
  onViewWorksheet?: () => void;
  onShowLimitations?: () => void;
  validationMessage?: string;
};

const copyForState = (state: IntakeViewState) => {
  if (state.kind === "checking") {
    return {
      eyebrow: "Document check",
      title: "Checking your worksheet.",
      description:
        "Claros is reading the selectable text, finding questions, and checking where answers can go.",
    };
  }

  if (state.kind === "ready") {
    return {
      eyebrow: "Ready to answer",
      title: "Your worksheet is ready.",
      description:
        "Choose how you want to answer each question. You will review every word before anything reaches the completed PDF.",
    };
  }

  if (state.kind === "unsupported") {
    return {
      eyebrow: "This PDF needs a different format",
      title: "Bring in a worksheet.",
      description:
        "Claros supports native-text short-answer PDFs with selectable text, up to 8 pages and 40 questions.",
    };
  }

  return {
    eyebrow: "New assignment",
    title: "Bring in a worksheet.",
    description:
      "Use a native-text short-answer PDF with selectable text, up to 8 pages and 40 questions.",
  };
};

export function IntakeFlow({ state, ...actions }: IntakeFlowProps) {
  const copy = copyForState(state);

  return (
    <section className={styles.flow} aria-labelledby="intake-title">
      <header className={styles.header}>
        <p className={styles.eyebrow}>{copy.eyebrow}</p>
        <h1 id="intake-title" className={styles.title} tabIndex={-1}>
          {copy.title}
        </h1>
        <p className={styles.description}>{copy.description}</p>
      </header>

      <div className={styles.panel}>
        {state.kind === "upload" ? (
          <AssignmentUploadPanel state={{ kind: "empty" }} {...actions} />
        ) : null}

        {state.kind === "checking" ? (
          <AssignmentUploadPanel
            state={{
              kind: "loading",
              message: state.message ?? "Checking your worksheet…",
            }}
            {...actions}
          />
        ) : null}

        {state.kind === "unsupported" ? (
          <AssignmentUploadPanel
            state={{
              kind: "error",
              message: state.message,
              recoverable: state.recoverable,
            }}
            {...actions}
          />
        ) : null}

        {state.kind === "ready" ? (
          <AssignmentUploadPanel
            state={{
              kind: "ready",
              title: state.assignment.title,
              pageCount: state.assignment.pageCount,
              questionCount: state.assignment.questions.length,
              inlineCount: state.inlineCount,
              answerPageCount: state.answerPageCount,
              warnings: state.warnings,
            }}
            {...actions}
          />
        ) : null}
      </div>
    </section>
  );
}
