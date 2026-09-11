import { ArrowRight, MagicWand02, Send01 } from "@untitledui/icons";
import { useId, useRef } from "react";
import { Button } from "@/components/base/buttons/button";
import { TextArea } from "@/components/base/textarea/textarea";
import type {
  ConversationTurn as ConversationTurnType,
  Question,
  VoiceState,
} from "../../domain/contracts";
import { QuestionHeader } from "./QuestionHeader";
import {
  VoiceStateControl,
  type VoiceStateControlProps,
} from "./VoiceStateControl";
import styles from "./answer-paths.module.css";

export type GuidedReasoningPanelProps = {
  question: Question;
  totalQuestions: number;
  turns: readonly ConversationTurnType[];
  draft: string;
  voiceState: VoiceState;
  muted?: boolean;
  mode?: "conversation" | "final-answer";
  onDraftChange: (value: string) => void;
  onSendTypedTurn?: () => void;
  onReadyToAnswer: () => void;
  onMakeClearer?: () => void;
  onReview?: () => void;
} & Pick<
  VoiceStateControlProps,
  | "onStart"
  | "onStop"
  | "onRetry"
  | "onContinueByTyping"
  | "onInterrupt"
  | "onToggleMute"
>;

function ConversationTurn({ turn }: { turn: ConversationTurnType }) {
  return (
    <li
      className={
        turn.speaker === "student" ? styles.studentTurn : styles.clarosTurn
      }
    >
      <p className={styles.turnSpeaker}>
        {turn.speaker === "student" ? "You" : "Claros"}
      </p>
      <p>{turn.text}</p>
    </li>
  );
}

function ConversationHistory({
  turns,
}: {
  turns: readonly ConversationTurnType[];
}) {
  const collapsedTurns = turns.length > 4 ? turns.slice(0, -3) : [];
  const visibleTurns = turns.length > 4 ? turns.slice(-3) : turns;

  return (
    <div className={styles.conversation} aria-label="Guided conversation">
      {collapsedTurns.length ? (
        <details className={styles.earlierTurns}>
          <summary>
            Show {collapsedTurns.length} earlier conversation
            {collapsedTurns.length === 1 ? " turn" : " turns"}
          </summary>
          <ol className={styles.turnList}>
            {collapsedTurns.map((turn) => (
              <ConversationTurn key={turn.id} turn={turn} />
            ))}
          </ol>
        </details>
      ) : null}
      <ol
        className={styles.turnList}
        aria-live="polite"
        aria-relevant="additions"
      >
        {visibleTurns.map((turn) => (
          <ConversationTurn key={turn.id} turn={turn} />
        ))}
      </ol>
    </div>
  );
}

export function GuidedReasoningPanel({
  question,
  totalQuestions,
  turns,
  draft,
  voiceState,
  muted,
  mode = "conversation",
  onDraftChange,
  onSendTypedTurn,
  onReadyToAnswer,
  onMakeClearer,
  onReview,
  onStart,
  onStop,
  onRetry,
  onContinueByTyping,
  onInterrupt,
  onToggleMute,
}: GuidedReasoningPanelProps) {
  const helpId = useId();
  const textAreaRef = useRef<HTMLTextAreaElement>(null);
  const hasDraft = /\S/u.test(draft);
  const isFinalAnswer = mode === "final-answer";

  return (
    <section className={styles.flow} aria-label="Guided reasoning">
      <QuestionHeader question={question} totalQuestions={totalQuestions} />

      {!isFinalAnswer ? <ConversationHistory turns={turns} /> : null}

      <VoiceStateControl
        state={voiceState}
        muted={muted}
        onStart={onStart}
        onStop={onStop}
        onRetry={onRetry}
        onContinueByTyping={() => {
          onContinueByTyping?.();
          textAreaRef.current?.focus();
        }}
        onInterrupt={onInterrupt}
        onToggleMute={onToggleMute}
      />

      <div className={styles.answerEditor}>
        <p className={styles.provenance}>
          {isFinalAnswer ? "Your final answer" : "Your response"}
        </p>
        <p id={helpId} className={styles.editorHint}>
          {isFinalAnswer
            ? "State the answer in your own words. You will review it next."
            : "Respond to the active prompt by speaking or typing."}
        </p>
        <TextArea
          aria-label={isFinalAnswer ? "Your final answer" : "Your response"}
          aria-describedby={helpId}
          value={draft}
          onChange={onDraftChange}
          textAreaRef={textAreaRef}
          rows={isFinalAnswer ? 6 : 4}
          placeholder={
            isFinalAnswer
              ? "State your final answer."
              : "Type what you want to say."
          }
          textAreaClassName={styles.answerTextArea}
        />
      </div>

      <div className={styles.answerActions}>
        {!isFinalAnswer ? (
          <>
            <Button
              color="secondary"
              size="lg"
              iconTrailing={Send01}
              onPress={onSendTypedTurn}
              isDisabled={!hasDraft || !onSendTypedTurn}
              className={styles.minimumTarget}
            >
              Send response
            </Button>
            <Button
              color="primary"
              size="lg"
              iconTrailing={ArrowRight}
              onPress={onReadyToAnswer}
              className={styles.minimumTarget}
            >
              I am ready to answer
            </Button>
          </>
        ) : (
          <>
            {hasDraft && onMakeClearer ? (
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
              isDisabled={!hasDraft || !onReview}
              className={styles.minimumTarget}
            >
              Review answer
            </Button>
          </>
        )}
      </div>
    </section>
  );
}
