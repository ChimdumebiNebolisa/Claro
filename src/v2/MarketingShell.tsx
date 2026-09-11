import {
  ArrowRight,
  CheckCircle,
  FileCheck02,
  Keyboard01,
  Lightbulb02,
  Microphone01,
} from "@untitledui/icons";
import { Link } from "react-router-dom";
import { Brand } from "./Brand";
import styles from "./marketing/marketing.module.css";

const guarantees = [
  "Choose your route",
  "See every wording change",
  "Approve the exact text",
  "Keep the source pages",
] as const;

export default function MarketingShell() {
  return (
    <main className={styles.page}>
      <nav className={styles.nav} aria-label="Primary navigation">
        <Brand />
        <div className={styles.navLinks}>
          <a href="#how-it-works">How it works</a>
          <a href="#accessibility">Accessibility</a>
          <Link className={styles.primaryLink} to="/app">
            Try Claros <ArrowRight aria-hidden="true" />
          </Link>
        </div>
      </nav>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>
            Accessibility-first worksheet workspace
          </p>
          <h1>
            The answer is yours. <em>Getting it onto the page</em> can be
            easier.
          </h1>
          <p className={styles.lede}>
            Say what you know or talk through what you do not. Claros turns your
            input into a reviewable answer and places only the version you
            approve onto the worksheet.
          </p>
          <div className={styles.heroActions}>
            <Link className={styles.primaryLink} to="/app">
              Try Claros <ArrowRight aria-hidden="true" />
            </Link>
            <span>
              <Keyboard01 aria-hidden="true" /> Typing is always available
            </span>
          </div>
          <p className={styles.trustLine}>
            <CheckCircle aria-hidden="true" /> Nothing is written to the
            completed PDF until you approve the exact text.
          </p>
        </div>

        <figure className={styles.preview}>
          <div className={styles.previewFrame}>
            <img
              src="/images/claros-workspace-preview.png"
              alt="The running Claros workspace showing a student reviewing the exact wording of a biology answer beside its original PDF source."
              width="1440"
              height="1000"
            />
          </div>
          <figcaption>
            Running Claros fixture · exact answer review beside the original PDF
          </figcaption>
        </figure>
      </section>

      <section className={styles.paths} id="how-it-works">
        <div className={styles.sectionIntro}>
          <p className={styles.eyebrow}>Two ways to answer</p>
          <h2>Start where your thinking is.</h2>
          <p>
            Give the answer you already know, or work it through one step at a
            time. Both routes end at the same exact review.
          </p>
        </div>
        <div className={styles.pathGrid}>
          <article className={styles.pathCard}>
            <Microphone01 aria-hidden="true" />
            <h3>Say my answer</h3>
            <p>Speak or type what you already know.</p>
          </article>
          <article className={styles.pathCard}>
            <Lightbulb02 aria-hidden="true" />
            <h3>Help me think it through</h3>
            <p>Work through the question with Claros, one step at a time.</p>
          </article>
        </div>
        <div className={styles.convergence} aria-label="Shared completion path">
          <span>Your words</span>
          <ArrowRight aria-hidden="true" />
          <strong>Exact answer review</strong>
          <ArrowRight aria-hidden="true" />
          <span>
            <FileCheck02 aria-hidden="true" /> Completed PDF
          </span>
        </div>
      </section>

      <section className={styles.guarantees} aria-labelledby="control-title">
        <div>
          <p className={styles.darkEyebrow}>Student control</p>
          <h2 id="control-title">You decide what reaches the page.</h2>
        </div>
        <ul>
          {guarantees.map((guarantee) => (
            <li key={guarantee}>
              <CheckCircle aria-hidden="true" /> {guarantee}
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.details} id="accessibility">
        <article>
          <p className={styles.eyebrow}>Accessibility</p>
          <h2>Voice-first, never voice-only.</h2>
          <p>
            Speak, type, or move between both. If the microphone or connection
            stops working, your current words stay put and the typed path stays
            available.
          </p>
          <h3>Does Claros answer the worksheet for me?</h3>
          <p>
            Claros can transcribe what you say, help you think through a
            question, and suggest clearer wording. You choose the final answer
            and review the exact text before Claros writes it onto the
            worksheet.
          </p>
        </article>
        <aside aria-labelledby="supported-pdfs-title">
          <p className={styles.eyebrow}>Supported PDFs</p>
          <h2 id="supported-pdfs-title">A focused first release.</h2>
          <p>
            Claros supports native-text, sequential short-answer worksheets with
            selectable text: 1–8 pages and up to 40 questions.
          </p>
          <p>
            Scanned pages, complex layouts, and ungrounded questions are not
            supported yet. When an answer cannot fit safely inline, Claros uses
            an attached answer page.
          </p>
        </aside>
      </section>

      <section className={styles.finalCta}>
        <p className={styles.eyebrow}>Your next worksheet</p>
        <h2>
          Put your next answer on the page. <em>Speaking, typing, or both.</em>
        </h2>
        <Link className={styles.primaryLink} to="/app">
          Try Claros <ArrowRight aria-hidden="true" />
        </Link>
      </section>
    </main>
  );
}
