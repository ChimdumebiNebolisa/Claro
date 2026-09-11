import { ArrowRight, Eye, Lightbulb02, Microphone01 } from "@untitledui/icons";
import { Button } from "@/components/base/buttons/button";
import { FeaturedIcon } from "@/components/foundations/featured-icon/featured-icon";
import type { Question } from "../../domain/contracts";
import { QuestionHeader } from "./QuestionHeader";
import styles from "./answer-paths.module.css";

export type EntryPathChoiceProps = {
  question: Question;
  totalQuestions: number;
  onChooseDirect: () => void;
  onChooseGuided: () => void;
  onTypeInstead: () => void;
  onViewWorksheet?: () => void;
};

export function EntryPathChoice({
  question,
  totalQuestions,
  onChooseDirect,
  onChooseGuided,
  onTypeInstead,
  onViewWorksheet,
}: EntryPathChoiceProps) {
  return (
    <section className={styles.flow} aria-label="Choose how to answer">
      <QuestionHeader question={question} totalQuestions={totalQuestions} />

      <div className={styles.pathGrid}>
        <article className={styles.pathCard}>
          <FeaturedIcon
            icon={Microphone01}
            color="brand"
            theme="light"
            size="md"
            aria-hidden="true"
          />
          <div className={styles.pathCopy}>
            <h2>Say my answer</h2>
            <p>Speak or type what you already know.</p>
          </div>
          <Button
            color="link-color"
            size="lg"
            iconTrailing={ArrowRight}
            onPress={onChooseDirect}
            className={styles.pathAction}
          >
            Start answering
          </Button>
        </article>

        <article className={styles.pathCard}>
          <FeaturedIcon
            icon={Lightbulb02}
            color="brand"
            theme="light"
            size="md"
            aria-hidden="true"
          />
          <div className={styles.pathCopy}>
            <h2>Help me think it through</h2>
            <p>Work through the question with Claros, one step at a time.</p>
          </div>
          <Button
            color="link-color"
            size="lg"
            iconTrailing={ArrowRight}
            onPress={onChooseGuided}
            className={styles.pathAction}
          >
            Start a guided conversation
          </Button>
        </article>
      </div>

      <div className={styles.utilityActions} aria-label="Other ways to begin">
        <Button
          color="secondary"
          size="lg"
          onPress={onTypeInstead}
          className={styles.minimumTarget}
        >
          Type instead
        </Button>
        {onViewWorksheet ? (
          <Button
            color="link-gray"
            size="lg"
            iconLeading={Eye}
            onPress={onViewWorksheet}
            className={styles.minimumTarget}
          >
            View worksheet
          </Button>
        ) : null}
      </div>
    </section>
  );
}
