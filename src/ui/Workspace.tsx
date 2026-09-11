import { useCallback, useEffect, useState, type ButtonHTMLAttributes, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { useMachine } from "@xstate/react";
import { Document, Page, pdfjs } from "react-pdf";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { ArrowRight, Check, Download, FileText, Headphones, LoaderCircle, Mic, ShieldCheck, UploadCloud, Volume2, X } from "lucide-react";
import "react-pdf/dist/Page/TextLayer.css";
import { commitAnswer, exportAssignment, loadDemoAssignment, planAnswer, uploadWorksheet } from "../adapters/api";
import { Progress } from "../components/ui/progress";
import { placementLabel } from "../domain/placement";
import type { Assignment, CommittedAnswer, Question } from "../domain/contracts";
import { rejectionCopy, type PlacementPlan } from "../domain/contracts";
import { workspaceMachine as machine } from "../domain/workspace-machine";
import { Wordmark } from "./Brand";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

type VoiceMode = "off" | "tutoring" | "dictating" | "failed";
type MobileView = "worksheet" | "answer";
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  onresult: (event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void;
  onerror: () => void;
  start: () => void;
};

function Button({ className = "", type = "button", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type={type} className={`button ${className}`} {...props} />;
}

function UploadSurface({ onLoad, busy, error }: { onLoad: (file: File | null) => void; busy: boolean; error: string | null }) {
  const onDrop = useCallback((accepted: File[]) => onLoad(accepted[0] ?? null), [onLoad]);
  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: false,
    noClick: true,
  });

  return (
    <section className="upload-layout page-width" aria-labelledby="upload-title">
      <div className="upload-intro">
        <p className="eyebrow">Claros workspace</p>
        <h1 id="upload-title">Bring one worksheet into focus.</h1>
        <p>Upload a native-text short-answer PDF. Claros checks the whole document before it creates an assignment.</p>
        <div className="upload-rules">
          <p><FileText size={17} /> Selectable PDF text</p>
          <p><Check size={17} /> One local answer area per question</p>
          <p><ShieldCheck size={17} /> No source-page mutation</p>
        </div>
      </div>
      <div {...getRootProps()} className={`upload-card ${isDragActive ? "is-dragging" : ""}`}>
        <input {...getInputProps()} />
        <div className="upload-icon"><UploadCloud size={25} /></div>
        <h2>{isDragActive ? "Drop the worksheet here" : "Upload a worksheet"}</h2>
        <p>Short-answer PDFs with a clear answer area directly below each question.</p>
        <div className="upload-actions">
          <Button className="button-primary" onClick={open} disabled={busy}>
            {busy ? <><LoaderCircle className="spin" size={16} /> Checking worksheet</> : <>Choose PDF <ArrowRight size={16} /></>}
          </Button>
          <Button className="button-ghost" onClick={() => onLoad(null)} disabled={busy}>Try sample worksheet</Button>
        </div>
        {error && <div className="error-inline" role="alert"><X size={16} /><span>{error}</span></div>}
        <p className="upload-footnote">Scans, multiple choice, tables, drawings, and essays are not supported yet.</p>
      </div>
    </section>
  );
}

function PaperPreview({ assignment, currentQuestion, committedAnswers, sourceUrl }: {
  assignment: Assignment;
  currentQuestion: Question;
  committedAnswers: CommittedAnswer[];
  sourceUrl: string | null;
}) {
  const [pageSize, setPageSize] = useState({ width: 612, height: 792 });

  return (
    <div className="document-column">
      <div className="document-toolbar">
        <span><FileText size={15} /> {assignment.worksheet.title}</span>
        <span>Page 1 of {assignment.worksheet.pageCount}</span>
      </div>
      <div className="paper-shell pdf-shell">
        {sourceUrl ? (
          <Document
            file={sourceUrl}
            loading={<p className="pdf-status">Loading original worksheet…</p>}
            error={<p className="pdf-status">The original worksheet could not be rendered.</p>}
          >
            <div className="pdf-page-wrap" aria-hidden="true">
              <Page
                pageNumber={1}
                width={720}
                renderTextLayer
                renderAnnotationLayer={false}
                onLoadSuccess={(page) => {
                  const viewport = page.getViewport({ scale: 1 });
                  setPageSize({ width: viewport.width, height: viewport.height });
                }}
              />
              {assignment.worksheet.questions
                .filter((question) => question.pageIndex === 0)
                .map((question) => {
                  const answer = committedAnswers.find((item) => item.questionId === question.id);
                  const bounds = question.answerRegion.bounds;
                  const style: CSSProperties = {
                    left: `${(bounds.x / pageSize.width) * 100}%`,
                    top: `${((pageSize.height - bounds.y - bounds.height) / pageSize.height) * 100}%`,
                    width: `${(bounds.width / pageSize.width) * 100}%`,
                    height: `${(bounds.height / pageSize.height) * 100}%`,
                  };
                  return (
                    <div
                      key={question.id}
                      className={`pdf-answer-region ${question.id === currentQuestion.id ? "is-current" : ""} ${answer ? "is-committed" : ""}`}
                      style={style}
                    >
                      {answer && <span><Check size={12} /> {answer.text}</span>}
                    </div>
                  );
                })}
            </div>
          </Document>
        ) : <p className="pdf-status">Preparing original worksheet…</p>}
      </div>
      <p className="document-caption">Original worksheet preview. Committed answers appear as an overlay; the source PDF changes only during export.</p>
      <section className="sr-only" aria-labelledby="worksheet-transcript-title">
        <h2 id="worksheet-transcript-title">{assignment.worksheet.title} transcript</h2>
        <ol>
          {assignment.worksheet.questions.map((question) => {
            const answer = committedAnswers.find((item) => item.questionId === question.id);
            return (
              <li key={question.id}>
                <p>Question {question.index}: {question.prompt}</p>
                <p>{answer ? `Committed answer: ${answer.text}` : "Answer area is blank."}</p>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}

function VoiceControls({ mode, setMode, onDictation }: {
  mode: VoiceMode;
  setMode: (mode: VoiceMode) => void;
  onDictation: (text: string) => void;
}) {
  const startDictation = () => {
    const browserWindow = window as Window & {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const Recognition = browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition;
    if (!Recognition) {
      setMode("failed");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      onDictation(event.results[0]?.[0]?.transcript ?? "");
      setMode("off");
    };
    recognition.onerror = () => setMode("failed");
    setMode("dictating");
    recognition.start();
  };

  return (
    <div className="voice-block">
      <div className="voice-heading">
        <span className="field-label">OPTIONAL VOICE ASSISTANCE</span>
        {mode === "tutoring" && <span className="voice-live"><span /> Live</span>}
      </div>
      <div className="voice-actions">
        <Button
          className={mode === "tutoring" ? "button-active" : "button-ghost"}
          aria-pressed={mode === "tutoring"}
          onClick={() => setMode(mode === "tutoring" ? "off" : "tutoring")}
        >
          <Headphones size={15} /> Talk it through
        </Button>
        <Button className={mode === "dictating" ? "button-active" : "button-ghost"} onClick={startDictation}>
          <Mic size={15} /> {mode === "dictating" ? "Listening…" : "Dictate final answer"}
        </Button>
      </div>
      {mode === "tutoring" && (
        <div className="transcript">
          <p><strong>Claros</strong> Think about what plants make for themselves using light. Keep the idea in your own words, then review it in the final-answer field.</p>
          <p className="transcript-note">Conversation stays separate from the final answer.</p>
        </div>
      )}
      {mode === "failed" && <p className="voice-error" role="status"><Volume2 size={14} /> Voice is unavailable. Typed input is still ready.</p>}
    </div>
  );
}

function QuestionPanel({ assignment, currentQuestion, stateValue, draft, plan, onDraft, onReview, onEdit, onCommit, onNext, onExport, voiceMode, setVoiceMode, committedAnswers, error, planning, committing, exporting }: {
  assignment: Assignment;
  currentQuestion: Question;
  stateValue: string;
  draft: string;
  plan: PlacementPlan | null;
  onDraft: (value: string) => void;
  onReview: () => void;
  onEdit: () => void;
  onCommit: () => void;
  onNext: () => void;
  onExport: () => void;
  voiceMode: VoiceMode;
  setVoiceMode: (mode: VoiceMode) => void;
  committedAnswers: CommittedAnswer[];
  error: string | null;
  planning: boolean;
  committing: boolean;
  exporting: boolean;
}) {
  const committed = committedAnswers.find((item) => item.questionId === currentQuestion.id);
  const isReview = stateValue === "review";
  const isCommitted = stateValue === "committed";
  const isComplete = stateValue === "complete";
  const currentIndex = currentQuestion.index;

  return (
    <aside className="question-column" aria-labelledby="active-question-heading">
      <div className="question-progress">
        <span>QUESTION {currentIndex} OF {assignment.worksheet.questions.length}</span>
        <Progress value={(currentIndex / assignment.worksheet.questions.length) * 100} aria-label={`Question ${currentIndex} of ${assignment.worksheet.questions.length}`} />
      </div>
      {isReview ? (
        <div className="review-panel">
          <p className="eyebrow">Review your final answer</p>
          <h1 id="active-question-heading">Is this exactly what you want to add?</h1>
          <div className="review-question"><span className="field-label">QUESTION {currentQuestion.index}</span><p>{currentQuestion.prompt}</p></div>
          <div className="exact-answer"><span className="field-label">FINAL ANSWER</span><p>{plan?.answerText ?? draft}</p></div>
          <div className={`placement-row placement-${plan?.placement ?? "blocked"}`}>
            <span className="placement-dot" />
            <div><span className="field-label">PLACEMENT</span><p>{plan ? placementLabel(plan.placement) : "Checking the detected answer area…"}</p></div>
          </div>
          <div className="panel-actions">
            <Button className="button-ghost" onClick={onEdit}>Edit</Button>
            <Button className="button-primary" disabled={!plan || plan.placement === "blocked" || committing} onClick={onCommit}>
              {committing ? <><LoaderCircle className="spin" size={16} /> Adding answer</> : <>Confirm &amp; add <Check size={16} /></>}
            </Button>
          </div>
        </div>
      ) : isCommitted ? (
        <div className="committed-panel">
          <div className="status-mark"><Check size={18} /></div>
          <p className="eyebrow">Committed answer</p>
          <h1 id="active-question-heading">Answer added.</h1>
          <div className="committed-copy"><span className="field-label">FINAL ANSWER</span><p>{committed?.text}</p></div>
          <p className="quiet-copy">This is a browser preview. The original worksheet stays unchanged until export.</p>
          <div className="panel-actions">
            <Button className="button-ghost" onClick={onEdit}>Edit answer</Button>
            {currentIndex < assignment.worksheet.questions.length ? (
              <Button className="button-primary" onClick={onNext}>Next question <ArrowRight size={16} /></Button>
            ) : (
              <Button className="button-primary" onClick={onExport} disabled={exporting}>
                {exporting ? <><LoaderCircle className="spin" size={16} /> Exporting</> : <>Export PDF <Download size={16} /></>}
              </Button>
            )}
          </div>
        </div>
      ) : isComplete ? (
        <div className="committed-panel">
          <div className="status-mark"><Check size={18} /></div>
          <p className="eyebrow">Export complete</p>
          <h1 id="active-question-heading">Your completed PDF is ready.</h1>
          <p className="quiet-copy">Every answer was explicitly approved and the original worksheet remains unchanged.</p>
          <Button className="button-primary button-wide" onClick={onExport} disabled={exporting}>
            {exporting ? <><LoaderCircle className="spin" size={16} /> Exporting</> : <>Export again <Download size={16} /></>}
          </Button>
        </div>
      ) : (
        <div className="draft-panel">
          <p className="eyebrow">Question {currentQuestion.index}</p>
          <h1 id="active-question-heading">{currentQuestion.prompt}</h1>
          <VoiceControls mode={voiceMode} setMode={setVoiceMode} onDictation={onDraft} />
          <label className="final-answer-label" htmlFor="final-answer">Final answer</label>
          <textarea
            id="final-answer"
            value={draft}
            onChange={(event) => onDraft(event.target.value)}
            placeholder="Type the exact answer you want to review…"
            rows={5}
          />
          <div className="draft-footer">
            <span>{draft ? "Draft · editable" : "Nothing is committed yet"}</span>
            <Button className="button-primary" disabled={!draft || planning} onClick={onReview}>
              {planning ? <><LoaderCircle className="spin" size={16} /> Checking placement</> : <>Review answer <ArrowRight size={16} /></>}
            </Button>
          </div>
        </div>
      )}
      {error && <p className="panel-error" role="alert">{error}</p>}
    </aside>
  );
}

export default function Workspace() {
  const [state, send] = useMachine(machine);
  const [currentQuestionId, setCurrentQuestionId] = useState<string | null>(null);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [isNarrow, setIsNarrow] = useState(false);
  const [mobileView, setMobileView] = useState<MobileView>("worksheet");
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("off");
  const [planning, setPlanning] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const assignment = state.context.assignment;
  const currentQuestion = assignment?.worksheet.questions.find((question) => question.id === currentQuestionId) ?? assignment?.worksheet.questions[0];

  useEffect(() => {
    if (assignment && !currentQuestionId) setCurrentQuestionId(assignment.activeQuestionId);
  }, [assignment, currentQuestionId]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const media = window.matchMedia("(max-width: 820px)");
    const update = () => setIsNarrow(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => () => {
    if (sourceUrl?.startsWith("blob:")) URL.revokeObjectURL(sourceUrl);
  }, [sourceUrl]);

  const load = async (file: File | null) => {
    send({ type: "LOAD" });
    try {
      const next = file ? await uploadWorksheet(file) : await loadDemoAssignment();
      setSourceUrl(file ? URL.createObjectURL(file) : "/api/v1/demo.pdf");
      send({ type: "LOADED", assignment: next });
      setCurrentQuestionId(next.worksheet.questions[0].id);
      setMobileView("worksheet");
    } catch (error) {
      send({ type: "FAILED", message: error instanceof Error ? error.message : rejectionCopy.document_validation_failed });
    }
  };

  const review = async () => {
    if (!assignment || !currentQuestion) return;
    setPlanning(true);
    try {
      const plan = await planAnswer(assignment.id, currentQuestion.id, state.context.draft);
      send({ type: "REVIEW" });
      send({ type: "PLAN_READY", plan });
    } catch (error) {
      send({ type: "FAILED", message: error instanceof Error ? error.message : "Placement could not be checked." });
    } finally {
      setPlanning(false);
    }
  };

  const commit = async () => {
    if (!assignment || !state.context.plan) return;
    setCommitting(true);
    send({ type: "COMMIT" });
    try {
      const next = await commitAnswer(assignment.id, state.context.plan.planToken);
      send({ type: "COMMITTED", assignment: next });
    } catch (error) {
      send({ type: "FAILED", message: error instanceof Error ? error.message : "The answer was not added." });
    } finally {
      setCommitting(false);
    }
  };

  const nextQuestion = () => {
    if (!assignment || !currentQuestion) return;
    const next = assignment.worksheet.questions.find((question) => question.index === currentQuestion.index + 1);
    if (next) {
      setCurrentQuestionId(next.id);
      setMobileView("answer");
      send({ type: "NEXT" });
    }
  };

  const edit = () => {
    if (!currentQuestion) return;
    const committed = assignment?.committedAnswers.find((answer) => answer.questionId === currentQuestion.id);
    send({ type: "EDIT" });
    if (committed) send({ type: "DRAFT_CHANGED", value: committed.text });
  };

  const exportPdf = async () => {
    if (!assignment) return;
    setExporting(true);
    send({ type: "EXPORT" });
    try {
      const blob = await exportAssignment(assignment.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "claros-completed-worksheet.pdf";
      link.click();
      URL.revokeObjectURL(url);
      send({ type: "EXPORTED" });
    } catch (error) {
      send({ type: "FAILED", message: error instanceof Error ? error.message : "Export failed." });
    } finally {
      setExporting(false);
    }
  };

  if (!assignment || !currentQuestion) {
    return (
      <div className="workspace">
        <header className="app-bar page-width">
          <Wordmark />
          <span className="app-bar-context">Student workspace</span>
          <Link className="app-bar-link" to="/legacy">Exit</Link>
        </header>
        <main><UploadSurface onLoad={load} busy={state.value === "analyzing"} error={state.context.error} /></main>
      </div>
    );
  }

  const documentPane = (
    <PaperPreview
      assignment={assignment}
      currentQuestion={currentQuestion}
      committedAnswers={assignment.committedAnswers}
      sourceUrl={sourceUrl}
    />
  );
  const questionPane = (
    <QuestionPanel
      assignment={assignment}
      currentQuestion={currentQuestion}
      stateValue={String(state.value)}
      draft={state.context.draft}
      plan={state.context.plan}
      onDraft={(value) => send({ type: "DRAFT_CHANGED", value })}
      onReview={review}
      onEdit={edit}
      onCommit={commit}
      onNext={nextQuestion}
      onExport={exportPdf}
      voiceMode={voiceMode}
      setVoiceMode={setVoiceMode}
      committedAnswers={assignment.committedAnswers}
      error={state.context.error}
      planning={planning}
      committing={committing}
      exporting={exporting}
    />
  );
  const workspaceHeader = (
    <header className="app-bar">
      <Wordmark />
      <span className="app-bar-file">{assignment.worksheet.title}</span>
      <span className="app-bar-progress">Question {currentQuestion.index} of {assignment.worksheet.questions.length}</span>
      <Link className="app-bar-link" to="/legacy">Exit</Link>
    </header>
  );

  if (isNarrow) {
    return (
      <div className="workspace">
        {workspaceHeader}
        <main className="workspace-mobile-main">
          <div className="mobile-view-switch" role="group" aria-label="Workspace view">
            <button type="button" aria-pressed={mobileView === "worksheet"} onClick={() => setMobileView("worksheet")}>Worksheet</button>
            <button type="button" aria-pressed={mobileView === "answer"} onClick={() => setMobileView("answer")}>Answer</button>
          </div>
          <div className="workspace-mobile-pane">
            {mobileView === "worksheet" ? documentPane : questionPane}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="workspace">
      {workspaceHeader}
      <main>
        <PanelGroup direction="horizontal" className="workspace-panels">
          <Panel defaultSize={60} minSize={45} maxSize={70} className="workspace-panel">{documentPane}</Panel>
          <PanelResizeHandle className="panel-resize-handle" aria-label="Resize worksheet and answer panels" />
          <Panel defaultSize={40} minSize={30} maxSize={55} className="workspace-panel">{questionPane}</Panel>
        </PanelGroup>
      </main>
    </div>
  );
}
