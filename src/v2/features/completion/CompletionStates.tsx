import {
  ArrowRight,
  CheckCircle,
  Download02,
  Edit03,
  FileCheck02,
  RefreshCw01,
  VolumeMax,
} from "@untitledui/icons";
import { LoadingIndicator } from "@/components/application/loading-indicator/loading-indicator";
import { Button } from "@/components/base/buttons/button";
import { StatusNotice } from "@/v2/components/StatusNotice";
import {
  answerAddedCopy,
  attributionForOrigin,
  destinationCopy,
  type Assignment,
  type Candidate,
  type ConfirmedAnswer,
  type ExportResult,
  type PlacementKind,
  type RecoverableError,
} from "@/v2/domain/contracts";
import styles from "./completion.module.css";

type Action = () => void;

export type RephrasingStateProps = {
  candidate: Candidate;
  error?: RecoverableError | null;
  onKeepOriginal: Action;
  onRetry?: Action;
};

export function RephrasingState({
  candidate,
  error,
  onKeepOriginal,
  onRetry,
}: RephrasingStateProps) {
  return (
    <section className={styles.surface} aria-labelledby="rephrasing-title">
      <p className={styles.eyebrow}>Suggested wording</p>
      <h1 id="rephrasing-title" className={styles.title}>
        {error
          ? "A suggestion wasn’t available"
          : "Preparing suggested wording"}
      </h1>
      <p className={styles.intro}>
        Your original answer stays here while Claros prepares another way to say
        it.
      </p>

      <AnswerTextCard candidate={candidate} />

      {error ? (
        <StatusNotice title="Your answer is unchanged" tone="error">
          {error.message}
        </StatusNotice>
      ) : (
        <div className={styles.loadingRegion} role="status" aria-live="polite">
          <LoadingIndicator
            type="line-simple"
            size="md"
            label="Preparing a clearer option…"
          />
        </div>
      )}

      <div className={styles.actions}>
        <Button
          color="secondary"
          size="lg"
          className={styles.control}
          onPress={onKeepOriginal}
        >
          Keep my wording
        </Button>
        {error && onRetry ? (
          <Button
            color="primary"
            size="lg"
            className={styles.control}
            iconLeading={RefreshCw01}
            onPress={onRetry}
          >
            Try again
          </Button>
        ) : null}
      </div>
    </section>
  );
}

export type WordingComparisonProps = {
  original: Candidate;
  suggestion: Candidate;
  selected?: "original" | "suggestion" | null;
  error?: RecoverableError | null;
  onKeepOriginal: Action;
  onUseSuggestion: Action;
  onChangeAnswer?: Action;
};

export function WordingComparison({
  original,
  suggestion,
  selected = null,
  error,
  onKeepOriginal,
  onUseSuggestion,
  onChangeAnswer,
}: WordingComparisonProps) {
  return (
    <section className={styles.surface} aria-labelledby="comparison-title">
      <p className={styles.eyebrow}>Wording comparison</p>
      <h1 id="comparison-title" className={styles.title}>
        Choose the wording you want
      </h1>
      <p className={styles.intro}>
        Both versions stay visible. Choosing a suggestion does not add it to the
        worksheet—you will review the exact text next.
      </p>

      <div className={styles.comparisonGrid}>
        <ComparisonCard
          candidate={original}
          label="Your words"
          actionLabel="Keep my wording"
          isSelected={selected === "original"}
          onSelect={onKeepOriginal}
        />
        <ComparisonCard
          candidate={suggestion}
          label="Suggested wording"
          actionLabel="Use suggestion"
          isSelected={selected === "suggestion"}
          onSelect={onUseSuggestion}
        />
      </div>

      {error ? (
        <StatusNotice title="The wording was not selected" tone="error">
          {error.message}
        </StatusNotice>
      ) : null}

      {onChangeAnswer ? (
        <div className={styles.secondaryAction}>
          <Button
            color="tertiary"
            size="lg"
            className={styles.control}
            iconLeading={Edit03}
            onPress={onChangeAnswer}
          >
            Change answer
          </Button>
        </div>
      ) : null}
    </section>
  );
}

type ComparisonCardProps = {
  candidate: Candidate;
  label: "Your words" | "Suggested wording";
  actionLabel: "Keep my wording" | "Use suggestion";
  isSelected: boolean;
  onSelect: Action;
};

function ComparisonCard({
  candidate,
  label,
  actionLabel,
  isSelected,
  onSelect,
}: ComparisonCardProps) {
  return (
    <article
      className={`${styles.comparisonCard}${isSelected ? ` ${styles.comparisonCardSelected}` : ""}`}
      data-selected={isSelected || undefined}
    >
      <div className={styles.cardHeader}>
        <span className={styles.provenance}>{label}</span>
        {isSelected ? (
          <span className={styles.selectedLabel}>
            <CheckCircle aria-hidden="true" /> Selected
          </span>
        ) : null}
      </div>
      <blockquote className={styles.comparisonText}>
        {candidate.text}
      </blockquote>
      <Button
        color={isSelected ? "primary" : "secondary"}
        size="lg"
        className={`${styles.control} ${styles.cardAction}`}
        aria-pressed={isSelected}
        onPress={onSelect}
      >
        {actionLabel}
      </Button>
    </article>
  );
}

export type ExactAnswerReviewProps = {
  candidate: Candidate;
  placement: PlacementKind;
  isHearing?: boolean;
  error?: RecoverableError | null;
  onHear: Action;
  onChangeAnswer: Action;
  onConfirm: Action;
};

export function ExactAnswerReview({
  candidate,
  placement,
  isHearing = false,
  error,
  onHear,
  onChangeAnswer,
  onConfirm,
}: ExactAnswerReviewProps) {
  return (
    <section className={styles.reviewSurface} aria-labelledby="review-title">
      <p className={styles.eyebrow}>Exact answer review</p>
      <h1 id="review-title" className={styles.title}>
        Review your exact answer
      </h1>
      <p className={styles.reviewInstruction}>
        Read every word before it reaches the worksheet.
      </p>

      <div className={styles.exactAnswerCard}>
        <span className={styles.provenance}>
          {attributionForOrigin(candidate.origin)}
        </span>
        <blockquote className={styles.exactText}>{candidate.text}</blockquote>
        <Button
          color="secondary"
          size="lg"
          className={styles.control}
          iconLeading={VolumeMax}
          isLoading={isHearing}
          showTextWhileLoading
          onPress={onHear}
        >
          Hear it
        </Button>
      </div>

      <DestinationStatus placement={placement} />

      {error ? (
        <StatusNotice title="The answer was not added" tone="error">
          {error.message}
        </StatusNotice>
      ) : null}

      <div className={styles.approvalActions}>
        <Button
          color="secondary"
          size="lg"
          className={styles.control}
          iconLeading={Edit03}
          onPress={onChangeAnswer}
        >
          Change answer
        </Button>
        <Button
          color="primary"
          size="lg"
          className={styles.control}
          iconTrailing={ArrowRight}
          onPress={onConfirm}
        >
          Use this exact answer
        </Button>
      </div>
    </section>
  );
}

export type DestinationStatusProps = {
  placement: PlacementKind;
};

export function DestinationStatus({ placement }: DestinationStatusProps) {
  return (
    <div
      className={`${styles.destination} ${placement === "appendix" ? styles.destinationAppendix : styles.destinationInline}`}
      role="status"
    >
      <FileCheck02 aria-hidden="true" />
      <div>
        <strong>
          {placement === "inline"
            ? "Original worksheet"
            : "Attached answer page"}
        </strong>
        <span>{destinationCopy(placement)}</span>
      </div>
    </div>
  );
}

export type ConfirmingAnswerStateProps = {
  candidate: Candidate;
  placement: PlacementKind;
};

export function ConfirmingAnswerState({
  candidate,
  placement,
}: ConfirmingAnswerStateProps) {
  return (
    <section
      className={styles.reviewSurface}
      aria-labelledby="confirming-title"
      aria-busy="true"
    >
      <p className={styles.eyebrow}>Exact answer review</p>
      <h1 id="confirming-title" className={styles.title}>
        Adding your exact answer
      </h1>
      <p className={styles.intro}>This may take a moment.</p>
      <AnswerTextCard candidate={candidate} emphasized />
      <DestinationStatus placement={placement} />
      <div className={styles.loadingRegion} role="status" aria-live="polite">
        <LoadingIndicator
          type="line-simple"
          size="md"
          label="Adding your answer…"
        />
      </div>
    </section>
  );
}

export type AnswerAddedStateProps = {
  answer: ConfirmedAnswer;
  nextQuestionNumber?: number;
  onEdit: Action;
  onContinue: Action;
};

export function AnswerAddedState({
  answer,
  nextQuestionNumber,
  onEdit,
  onContinue,
}: AnswerAddedStateProps) {
  const destination =
    answer.placement === "inline"
      ? "Original worksheet"
      : "Attached answer page";

  return (
    <section className={styles.surface} aria-labelledby="answer-added-title">
      <div className={styles.successMark} aria-hidden="true">
        <CheckCircle />
      </div>
      <h1 id="answer-added-title" className={styles.title}>
        {answerAddedCopy(answer.placement)}
      </h1>
      <p className={styles.srOnly} role="status" aria-live="polite">
        {answerAddedCopy(answer.placement)}
      </p>
      <p className={styles.intro}>
        The exact answer you approved is now in the completed copy.
      </p>

      <div className={styles.handoff}>
        <div className={styles.handoffAnswer}>
          <span className={styles.provenance}>
            {attributionForOrigin(answer.origin)}
          </span>
          <p>{answer.text}</p>
        </div>
        <ArrowRight className={styles.handoffArrow} aria-hidden="true" />
        <div className={styles.handoffDestination}>
          <FileCheck02 aria-hidden="true" />
          <span>{destination}</span>
        </div>
      </div>

      <div className={styles.approvalActions}>
        <Button
          color="secondary"
          size="lg"
          className={styles.control}
          iconLeading={Edit03}
          onPress={onEdit}
        >
          Edit answer
        </Button>
        <Button
          color="primary"
          size="lg"
          className={styles.control}
          iconTrailing={ArrowRight}
          onPress={onContinue}
        >
          {nextQuestionNumber
            ? `Continue to Question ${nextQuestionNumber}`
            : "Review answers"}
        </Button>
      </div>
    </section>
  );
}

export type WorksheetReviewProps = {
  assignment: Assignment;
  confirmedAnswers: Readonly<Record<string, ConfirmedAnswer>>;
  isExporting?: boolean;
  onEdit: (questionId: string) => void;
  onGoToQuestion: (questionId: string) => void;
  onExport: Action;
};

export function WorksheetReview({
  assignment,
  confirmedAnswers,
  isExporting = false,
  onEdit,
  onGoToQuestion,
  onExport,
}: WorksheetReviewProps) {
  const answeredCount = Object.keys(confirmedAnswers).length;

  return (
    <section
      className={styles.surface}
      aria-labelledby="worksheet-review-title"
    >
      <p className={styles.eyebrow}>Worksheet review</p>
      <h1 id="worksheet-review-title" className={styles.title}>
        Review answers
      </h1>
      <p className={styles.intro} role="status">
        {answeredCount} of {assignment.questions.length} answered. Unanswered
        questions will stay blank.
      </p>

      <ol className={styles.questionList} aria-label="Worksheet questions">
        {assignment.questions.map((question) => {
          const answer = confirmedAnswers[question.id];
          return (
            <li key={question.id} className={styles.questionRow}>
              <div className={styles.questionNumber} aria-hidden="true">
                {question.index}
              </div>
              <div className={styles.questionBody}>
                <div className={styles.questionHeading}>
                  <h2>{question.prompt}</h2>
                  <span
                    className={`${styles.stateLabel} ${answer ? styles.stateAnswered : styles.stateUnanswered}`}
                  >
                    {answer ? "Answered" : "Unanswered"}
                  </span>
                </div>
                {answer ? (
                  <>
                    <p className={styles.answerPreview}>{answer.text}</p>
                    <div className={styles.answerMeta}>
                      <span>{attributionForOrigin(answer.origin)}</span>
                      <span aria-hidden="true">·</span>
                      <span>
                        {answer.placement === "inline"
                          ? "Original worksheet"
                          : "Attached answer page"}
                      </span>
                    </div>
                  </>
                ) : (
                  <p className={styles.unansweredCopy}>
                    No answer has been approved for this question.
                  </p>
                )}
                <div className={styles.rowActions}>
                  {answer ? (
                    <Button
                      color="link-color"
                      size="md"
                      className={styles.rowControl}
                      onPress={() => onEdit(question.id)}
                    >
                      Edit answer
                    </Button>
                  ) : (
                    <Button
                      color="link-color"
                      size="md"
                      className={styles.rowControl}
                      onPress={() => onGoToQuestion(question.id)}
                    >
                      Answer question
                    </Button>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <div className={styles.exportBar}>
        <div>
          <strong>Completed PDF</strong>
          <span>Includes confirmed answers only.</span>
        </div>
        <Button
          color="primary"
          size="lg"
          className={styles.control}
          iconLeading={Download02}
          isDisabled={answeredCount === 0}
          isLoading={isExporting}
          showTextWhileLoading
          onPress={onExport}
        >
          Download completed PDF
        </Button>
      </div>
    </section>
  );
}

export function ExportProgressState() {
  return (
    <section
      className={styles.centeredSurface}
      aria-labelledby="export-progress-title"
      aria-busy="true"
    >
      <p className={styles.eyebrow}>Completed PDF</p>
      <h1 id="export-progress-title" className={styles.title}>
        Preparing your completed PDF
      </h1>
      <p className={styles.intro}>
        Claros is adding only the answers you approved. Unanswered questions
        stay blank.
      </p>
      <div className={styles.exportLoader} role="status" aria-live="polite">
        <LoadingIndicator
          type="line-simple"
          size="lg"
          label="Building your completed copy…"
        />
      </div>
    </section>
  );
}

export type ExportFailureStateProps = {
  error: RecoverableError;
  onRetry: Action;
  onReviewAnswers: Action;
};

export function ExportFailureState({
  error,
  onRetry,
  onReviewAnswers,
}: ExportFailureStateProps) {
  return (
    <section
      className={styles.centeredSurface}
      aria-labelledby="export-failed-title"
    >
      <p className={styles.eyebrow}>Completed PDF</p>
      <h1 id="export-failed-title" className={styles.title}>
        The PDF could not be prepared
      </h1>
      <StatusNotice title="Your confirmed answers are safe" tone="error">
        {error.message}
      </StatusNotice>
      <div className={styles.approvalActions}>
        <Button
          color="secondary"
          size="lg"
          className={styles.control}
          onPress={onReviewAnswers}
        >
          Review answers
        </Button>
        <Button
          color="primary"
          size="lg"
          className={styles.control}
          iconLeading={RefreshCw01}
          onPress={onRetry}
        >
          Retry export
        </Button>
      </div>
    </section>
  );
}

export type ExportCompleteStateProps = {
  result: ExportResult;
  onReviewAnswers: Action;
};

export function ExportCompleteState({
  result,
  onReviewAnswers,
}: ExportCompleteStateProps) {
  return (
    <section
      className={styles.centeredSurface}
      aria-labelledby="export-complete-title"
    >
      <div className={styles.successMark} aria-hidden="true">
        <CheckCircle />
      </div>
      <p className={styles.eyebrow}>Completed PDF</p>
      <h1 id="export-complete-title" className={styles.title}>
        Your completed PDF is ready
      </h1>
      <p className={styles.srOnly} role="status" aria-live="polite">
        Your completed PDF is ready.
      </p>
      <p className={styles.intro}>
        Your original worksheet is unchanged. This download is a new completed
        copy.
      </p>

      <div className={styles.fileCard}>
        <FileCheck02 aria-hidden="true" />
        <div>
          <strong>{result.filename}</strong>
          <span>{result.sizeLabel}</span>
        </div>
      </div>

      <div className={styles.approvalActions}>
        <Button
          color="secondary"
          size="lg"
          className={styles.control}
          onPress={onReviewAnswers}
        >
          Review answers
        </Button>
        <Button
          href={result.downloadUrl}
          download={result.filename}
          color="primary"
          size="lg"
          className={styles.control}
          iconLeading={Download02}
        >
          Download completed PDF
        </Button>
      </div>
    </section>
  );
}

type AnswerTextCardProps = {
  candidate: Candidate;
  emphasized?: boolean;
};

function AnswerTextCard({
  candidate,
  emphasized = false,
}: AnswerTextCardProps) {
  return (
    <div
      className={`${styles.answerCard}${emphasized ? ` ${styles.answerCardEmphasized}` : ""}`}
    >
      <span className={styles.provenance}>
        {attributionForOrigin(candidate.origin)}
      </span>
      <blockquote>{candidate.text}</blockquote>
    </div>
  );
}
