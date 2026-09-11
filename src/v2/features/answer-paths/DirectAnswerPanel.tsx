import { ArrowRight, MagicWand02 } from "@untitledui/icons";
import { useId, useRef } from "react";
import { Button } from "@/components/base/buttons/button";
import { TextArea } from "@/components/base/textarea/textarea";
import type { Question, VoiceState } from "../../domain/contracts";
import { QuestionHeader } from "./QuestionHeader";
import {
  VoiceStateControl,
  type VoiceStateControlProps,
} from "./VoiceStateControl";
import styles from "./answer-paths.module.css";

export type DirectAnswerPanelProps = {
  question: Question;
  totalQuestions: number;
  candidateText: string;
  voiceState: VoiceState;
  muted?: boolean;
  onCandidateChange: (value: string) => void;
  onTypeInstead?: () => void;
  onMakeClearer: () => void;
  onReview: () => void;
} & Pick<
  VoiceStateControlProps,
  "onStart" | "onStop" | "onRetry" | "onContinueByTyping" | "onToggleMute"
>;

export function DirectAnswerPanel({
  question,
  totalQuestions,
  candidateText,
  voiceState,
  muted,
  onCandidateChange,
  onTypeInstead,
  onMakeClearer,
  onReview,
  onStart,
  onStop,
  onRetry,
  onContinueByTyping,
  onToggleMute,
}: DirectAnswerPanelProps) {
  const descriptionId = useId();
  const textAreaRef = useRef<HTMLTextAreaElement>(null);
  const hasCandidate = /\S/u.test(candidateText);
  const focusTypedAnswer = (announcePathChange = true) => {
    if (announcePathChange) onTypeInstead?.();
    textAreaRef.current?.focus();
  };

  return (
    <section className={styles.flow} aria-label="Direct answer">
      <QuestionHeader question={question} totalQuestions={totalQuestions} />

      <VoiceStateControl
        state={voiceState}
        muted={muted}
        onStart={onStart}
        onStop={onStop}
        onRetry={onRetry}
        onContinueByTyping={() => {
          onContinueByTyping?.();
          focusTypedAnswer(false);
        }}
        onToggleMute={onToggleMute}
      />

      <div className={styles.answerEditor}>
        <div className={styles.answerEditorHeading}>
          <div>
            <p className={styles.provenance}>Your words</p>
            <p id={descriptionId} className={styles.editorHint}>
              The transcript and typed answer are one editable draft.
            </p>
          </div>
          <Button
            color="link-color"
            size="lg"
            onPress={() => focusTypedAnswer()}
            className={styles.minimumTarget}
          >
            Type instead
          </Button>
        </div>
        <TextArea
          aria-label="Your words"
          aria-describedby={descriptionId}
          value={candidateText}
          onChange={onCandidateChange}
          textAreaRef={textAreaRef}
          rows={6}
          placeholder="Speak or type what you already know."
          textAreaClassName={styles.answerTextArea}
        />
      </div>

      <div className={styles.answerActions}>
        {hasCandidate ? (
          <Button
            color="secondary"
            size="lg"
            iconLeading={MagicWand02}
            onPress={onMakeClearer}
            className={styles.minimumTarget}
          >
            Make it clearer
          </Button>
        ) : null}
        <Button
          color="primary"
          size="lg"
          iconTrailing={ArrowRight}
          onPress={onReview}
          isDisabled={!hasCandidate}
          className={styles.minimumTarget}
        >
          Review answer
        </Button>
      </div>
    </section>
  );
}
