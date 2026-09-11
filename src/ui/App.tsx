import { lazy, Suspense } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Check, Download, Mic, ShieldCheck, X } from "lucide-react";
import { Wordmark } from "./Brand";
import "../styles/tokens.css";
import "../styles/app.css";

const Workspace = lazy(() => import("./Workspace"));

function Landing() {
  return (
    <main className="marketing-page">
      <nav className="marketing-nav page-width">
        <Wordmark />
        <div className="marketing-links">
          <a href="#journey">Follow one answer</a>
          <a href="#supported">Supported PDFs</a>
          <Link className="button button-ghost" to="/legacy/app">
            Open workspace <ArrowRight size={16} />
          </Link>
        </div>
      </nav>

      <section className="collage-hero">
        <div className="collage-wash" aria-hidden="true" />
        <div className="collage-hero-inner page-width">
          <div className="collage-copy">
            <h1>The answer is yours.<br /><span>Getting it onto the page can be easier.</span></h1>
            <p className="collage-lede">
              Talk it through, dictate or type the final answer, then review every word and where it will go before you confirm it.
            </p>
            <div className="collage-actions">
              <Link className="button button-primary" to="/legacy/app">
                Open workspace <ArrowRight size={17} />
              </Link>
              <a className="collage-text-link" href="#journey">Follow one answer <ArrowRight size={15} /></a>
            </div>
            <p className="collage-note"><ShieldCheck size={15} /> Nothing is added until you confirm the exact text.</p>
          </div>

          <div className="product-collage" role="img" aria-label="Question 2 moves from optional voice discussion to exact final-answer review, then to confirmed placement directly below the worksheet question">
            <div className="collage-page" aria-hidden="true">
              <div className="collage-page-heading">
                <span>ECOSYSTEMS</span>
                <span>PAGE 1</span>
              </div>
              <p><strong>1.</strong> Name one producer in a food chain.</p>
              <div className="collage-answer committed"><Check size={13} /> grass</div>
              <div className="collage-question-active">
                <p><strong>2.</strong> Why do plants need sunlight?</p>
                <div className="collage-rule" />
                <div className="collage-rule" />
              </div>
              <p><strong>3.</strong> Give one example of a decomposer.</p>
              <div className="collage-rule" />
            </div>

            <div className="voice-chip" aria-hidden="true">
              <span className="sequence-number">1</span>
              <Mic size={15} />
              <span className="voice-bars"><i /><i /><i /><i /><i /></span>
              <strong>Talk it through</strong>
            </div>

            <div className="review-card" aria-hidden="true">
              <div className="review-card-top">
                <span>2 &nbsp; EXACT REVIEW</span>
                <span>QUESTION 2 OF 3</span>
              </div>
              <h2>Read every word before it goes on the page.</h2>
              <span className="review-label">FINAL ANSWER</span>
              <div className="review-answer">Plants use sunlight to make food.</div>
              <div className="review-fit"><Check size={14} /> Fits in answer area</div>
              <div className="review-action">Confirm &amp; add <ArrowRight size={15} /></div>
            </div>
          </div>
        </div>
      </section>

      <section className="journey page-width" id="journey">
        <div className="journey-heading">
          <h2>One answer, from thought to page.</h2>
          <p>Question 2 stays visible while the student decides exactly what the completed worksheet should say.</p>
        </div>
        <ol className="journey-list">
          <li><span>1</span><div><strong>Think it through.</strong><p className="journey-quote">“Plants need sunlight because… it helps them make their own food.”</p><small>Voice is optional. Spoken reasoning never becomes the answer by itself.</small></div></li>
          <li><span>2</span><div><strong>Choose the final words.</strong><p className="journey-answer">Plants use sunlight to make food.</p><small>The student can dictate or type, then edit the exact text.</small></div></li>
          <li><span>3</span><div><strong>Check where they will go.</strong><p className="journey-placement"><Check size={15} /> Fits directly below Question 2</p><small>The answer and authorized placement are visible before confirmation.</small></div></li>
          <li><span>4</span><div><strong>Confirm the completed copy.</strong><p>Only approved answers appear in the exported PDF. The original worksheet remains unchanged.</p></div></li>
        </ol>
      </section>

      <section className="supported-editorial" id="supported">
        <div className="page-width supported-editorial-grid">
          <div>
            <h2>One question.<br />One clear answer space.</h2>
            <a className="button button-primary" href="/api/v1/demo.pdf" download>
              Download sample PDF <Download size={16} />
            </a>
          </div>
          <div className="supported-contract">
            <p className="supported-intro">Claros supports a focused worksheet format so it never has to guess where an answer belongs.</p>
            <div><Check size={16} /><span><strong>Selectable PDF text</strong>Native text, not a scan</span></div>
            <div><Check size={16} /><span><strong>Sequential short answers</strong>Questions in normal reading order</span></div>
            <div><Check size={16} /><span><strong>One clear answer space</strong>Directly below its question on the same page</span></div>
            <div className="unsupported-row"><X size={16} /><span><strong>Rejected rather than guessed</strong>Multiple choice, tables, drawings, essays, and ambiguous layouts</span></div>
          </div>
        </div>
      </section>

      <section className="closing-cta page-width">
        <div>
          <h2>Put your next answer on the page.</h2>
        </div>
        <div className="hero-actions">
            <Link className="button button-primary" to="/legacy/app">
              Open workspace <ArrowRight size={17} />
            </Link>
          </div>
      </section>

      <footer className="marketing-footer page-width">
        <Wordmark />
        <span>The original worksheet stays unchanged until export.</span>
        <Link to="/legacy/app">Open workspace <ArrowRight size={14} /></Link>
      </footer>
    </main>
  );
}

function WorkspaceFallback() {
  return <main className="route-loading" role="status">Opening workspace…</main>;
}

export default function App() {
  const location = useLocation();
  const showWorkspace = location.pathname === "/legacy/app";

  return (
    <div className="legacy-root">
      {showWorkspace ? (
        <Suspense fallback={<WorkspaceFallback />}>
          <Workspace />
        </Suspense>
      ) : (
        <Landing />
      )}
    </div>
  );
}
