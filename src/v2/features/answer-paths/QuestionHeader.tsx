import type { Question } from "../../domain/contracts";
import styles from "./answer-paths.module.css";

export type QuestionHeaderProps = {
  question: Question;
  totalQuestions: number;
};

export function QuestionHeader({
  question,
  totalQuestions,
}: QuestionHeaderProps) {
  return (
    <header className={styles.questionHeader}>
      <p className={styles.questionProgress}>
        Question {question.index} of {totalQuestions}
      </p>
      <h1 className={styles.questionText} tabIndex={-1}>
        {question.prompt}
      </h1>
      {question.instruction ? (
        <p className={styles.questionInstruction}>{question.instruction}</p>
      ) : null}
    </header>
  );
}
