import { Eye } from "@untitledui/icons";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/base/buttons/button";
import { Brand } from "./Brand";
import {
  beginRevision,
  confirmAnswer as confirmAnswerRequest,
  createAssignment,
  createCandidate as createCandidateRequest,
  createExport as createExportRequest,
  createReview as createReviewRequest,
  getAssignment,
  getExport,
  mapAssignment,
  mapCandidate,
  mapExportState,
  requestRephrase as requestRephraseMutation,
  toRecoverableError,
  type ApiCandidateRequest,
} from "./api/client";
import { useWorkspaceActor, useWorkspaceSnapshot } from "./domain/useWorkspace";
import {
  appendixCandidateText,
  directCandidateText,
  directSuggestionText,
  fixtureExportResult,
  guidedCandidateText,
} from "./domain/fixtures";
import {
  fixtureScenarios,
  type FixtureScenario,
} from "./domain/workspaceMachine";
import type { Candidate } from "./domain/contracts";
import {
  DirectAnswerPanel,
  EntryPathChoice,
  GuidedReasoningPanel,
} from "./features/answer-paths";
import {
  AnswerAddedState,
  ConfirmingAnswerState,
  ExactAnswerReview,
  ExportCompleteState,
  ExportFailureState,
  ExportProgressState,
  RephrasingState,
  WordingComparison,
  WorksheetReview,
} from "./features/completion";
import { IntakeFlow } from "./features/intake";
import { StatusNotice } from "./components/StatusNotice";
import { loadRealtimeAdapter } from "./realtime/loadRealtime";
import type {
  FakeRealtimeAdapter,
  FakeRealtimeInteraction,
  FakeRealtimeScenario,
  RealtimeEvent,
} from "./realtime/realtime-adapter";
import answerPathStyles from "./features/answer-paths/answer-paths.module.css";

const DocumentCrop = lazy(() => import("./document/DocumentCrop"));
const WorksheetDialog = lazy(() => import("./document/WorksheetDialog"));

type WorkspaceShellProps = {
  mode?: "upload" | "question" | "review" | "export";
};

const isFixtureScenario = (value: string | null): value is FixtureScenario =>
  fixtureScenarios.some((scenario) => scenario === value);

const realtimeFixtureScenarios = [
  "disconnect",
  "mic-denied",
  "casual",
  "confirm",
  "duplicate",
] as const satisfies readonly FakeRealtimeScenario[];

const isRealtimeFixtureScenario = (
  value: string | null,
): value is (typeof realtimeFixtureScenarios)[number] =>
  realtimeFixtureScenarios.some((scenario) => scenario === value);

const isAbortError = (error: unknown) =>
  typeof error === "object" &&
  error !== null &&
  "name" in error &&
  error.name === "AbortError";

const waitForPoll = (signal: AbortSignal, delay = 750) =>
  new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, delay);
    signal.addEventListener("abort", onAbort, { once: true });
  });

export default function WorkspaceShell({
  mode = "upload",
}: WorkspaceShellProps) {
  const { assignmentId, exportId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const actor = useWorkspaceActor();
  const snapshot = useWorkspaceSnapshot();
  const { context } = snapshot;
  const taskRef = useRef<HTMLElement>(null);
  const editorFocusRequested = useRef(false);
  const realtimeAdapterRef = useRef<FakeRealtimeAdapter | null>(null);
  const realtimeConnectionKeyRef = useRef<string | null>(null);
  const realtimeUnsubscribeRef = useRef<(() => void) | null>(null);
  const realtimeAdvanceTimerRef = useRef<number | null>(null);
  const realtimeRunSequenceRef = useRef(0);
  const exactReviewFixtureRef = useRef<string | null>(null);
  const routeLoadSequenceRef = useRef(0);
  const mutationPendingRef = useRef(false);
  const exportPollRetryRef = useRef(false);
  const analysisPollControllerRef = useRef<AbortController | null>(null);
  const exportIdempotencyRef = useRef<{
    assignmentId: string;
    requestVersion: number;
    currentVersion: number;
    key: string;
  } | null>(null);
  const persistedCandidateRef = useRef<{
    assignmentId: string;
    assignmentVersion: number;
    candidate: Candidate;
  } | null>(null);
  const revisionSourceRef = useRef<{
    questionId: string;
    candidateId: string;
    candidateVersion: number;
  } | null>(null);
  const [isWorksheetOpen, setWorksheetOpen] = useState(false);
  const [validationMessage, setValidationMessage] = useState<string>();
  const [guidedDraft, setGuidedDraft] = useState("");
  const [isHearing, setHearing] = useState(false);
  const [autoAdvance, setAutoAdvance] = useState(false);
  const [captionsVisible, setCaptionsVisible] = useState(true);
  const [captions, setCaptions] = useState({ student: "", claros: "" });
  const [exportPollAttempt, setExportPollAttempt] = useState(0);

  const fixtureScenario = useMemo(() => {
    const value = new URLSearchParams(location.search).get("fixture");
    return isFixtureScenario(value) ? value : null;
  }, [location.search]);
  const realtimeFixtureScenario = useMemo(() => {
    if (!import.meta.env.DEV) return null;
    const value = new URLSearchParams(location.search).get("realtime");
    return isRealtimeFixtureScenario(value) ? value : null;
  }, [location.search]);
  const usesRealApi =
    !import.meta.env.DEV ||
    new URLSearchParams(location.search).get("runtime") === "api";
  const routeKey = `${usesRealApi ? "api" : "fixture"}:${mode}:${assignmentId ?? ""}:${exportId ?? ""}:${fixtureScenario ?? ""}:${exportPollAttempt}`;

  useEffect(() => {
    const current = actor.getSnapshot();
    if (mode !== "export") exportPollRetryRef.current = false;
    if (!usesRealApi) {
      persistedCandidateRef.current = null;
      if (fixtureScenario) {
        actor.send({
          type: "LOAD_FIXTURE_SCENARIO",
          scenario: fixtureScenario,
        });
        return;
      }
      if (mode === "review") {
        actor.send(
          current.context.assignment
            ? { type: "OPEN_REVIEW_ROUTE" }
            : { type: "LOAD_FIXTURE_SCENARIO", scenario: "worksheet-review" },
        );
        return;
      }
      if (mode === "export") {
        actor.send(
          current.context.assignment && current.context.exportResult
            ? { type: "OPEN_EXPORT_ROUTE" }
            : { type: "LOAD_FIXTURE_SCENARIO", scenario: "export-complete" },
        );
        return;
      }
      if (mode === "question" && !current.context.assignment) {
        actor.send({ type: "OPEN_ASSIGNMENT_ROUTE" });
        return;
      }
      if (mode === "question") return;
    }

    if (mode === "upload" || !assignmentId) {
      persistedCandidateRef.current = null;
      if (
        !current.matches("upload") &&
        !current.matches("checking") &&
        !current.matches("ready") &&
        !current.matches("rejected")
      ) {
        actor.send({ type: "RESET" });
      }
      return;
    }

    const controller = new AbortController();
    const requestSequence = ++routeLoadSequenceRef.current;
    const isCurrentRequest = () =>
      !controller.signal.aborted &&
      routeLoadSequenceRef.current === requestSequence;

    const applyExportStatus = async () => {
      if (!exportId) return;
      const rememberExportVersion = (version: number) => {
        const attempt = exportIdempotencyRef.current;
        if (attempt?.assignmentId === assignmentId) {
          exportIdempotencyRef.current = {
            ...attempt,
            currentVersion: version,
          };
        }
      };
      actor.send({ type: "EXPORT_PENDING" });
      let payload = await getExport(assignmentId, exportId, controller.signal);
      exportPollRetryRef.current = false;
      let mapped = mapExportState(payload, assignmentId);
      rememberExportVersion(mapped.version);
      while (mapped.kind === "creating" && isCurrentRequest()) {
        actor.send({ type: "EXPORT_PENDING", version: mapped.version });
        await waitForPoll(controller.signal);
        payload = await getExport(assignmentId, exportId, controller.signal);
        mapped = mapExportState(payload, assignmentId);
        rememberExportVersion(mapped.version);
      }
      if (!isCurrentRequest()) return;
      if (mapped.kind === "complete") {
        exportIdempotencyRef.current = null;
        actor.send({
          type: "EXPORT_RESTORED",
          result: mapped.result,
          version: mapped.version,
        });
      } else if (mapped.kind === "failed") {
        exportIdempotencyRef.current = null;
        actor.send({
          type: "EXPORT_FAILED",
          error: mapped.error,
          version: mapped.version,
        });
      }
    };

    const loadedAssignment = current.context.assignment;
    if (loadedAssignment?.id === assignmentId) {
      if (mode === "review" && !current.matches("worksheetReview")) {
        actor.send({ type: "OPEN_REVIEW_ROUTE" });
      } else if (
        mode === "question" &&
        (current.matches("worksheetReview") ||
          current.matches("exporting") ||
          current.matches("exportFailed") ||
          current.matches("exportComplete"))
      ) {
        actor.send({ type: "OPEN_ASSIGNMENT_ROUTE" });
      } else if (
        mode === "export" &&
        exportId &&
        !(
          current.matches("exportComplete") &&
          current.context.exportResult?.id === exportId
        )
      ) {
        void applyExportStatus().catch((error: unknown) => {
          if (!isAbortError(error) && isCurrentRequest()) {
            exportPollRetryRef.current = true;
            actor.send({
              type: "EXPORT_FAILED",
              error: toRecoverableError(error),
            });
          }
        });
      }
    } else {
      persistedCandidateRef.current = null;
      actor.send({ type: "RESET" });
      actor.send({ type: "START_ANALYSIS" });
      void (async () => {
        try {
          let payload = await getAssignment(assignmentId, controller.signal);
          while (payload.status === "analyzing" && isCurrentRequest()) {
            await waitForPoll(controller.signal);
            payload = await getAssignment(assignmentId, controller.signal);
          }
          if (!isCurrentRequest()) return;
          if (payload.status === "analysis_failed") {
            actor.send({
              type: "ANALYSIS_FAILED",
              error: {
                code: "analysis_failed",
                message:
                  "This worksheet could not be checked. Try another PDF.",
                recoverable: true,
              },
            });
            return;
          }
          const restored = mapAssignment(payload);
          persistedCandidateRef.current = restored.candidate
            ? {
                assignmentId: restored.assignment.id,
                assignmentVersion: restored.assignment.version,
                candidate: restored.candidate,
              }
            : null;
          actor.send({
            type: "ANALYSIS_READY",
            assignment: restored.assignment,
            confirmedAnswers: restored.confirmedAnswers,
            activeQuestionIndex: restored.activeQuestionIndex,
            candidate: restored.candidate,
          });
          if (mode === "question") {
            actor.send({ type: "START_QUESTION" });
            if (restored.candidate) actor.send({ type: "TYPE_INSTEAD" });
          } else if (mode === "review") {
            actor.send({ type: "OPEN_REVIEW_ROUTE" });
          } else if (mode === "export") {
            await applyExportStatus();
          }
        } catch (error) {
          if (!isAbortError(error) && isCurrentRequest()) {
            const latest = actor.getSnapshot();
            if (latest.context.assignment?.id === assignmentId) {
              exportPollRetryRef.current = true;
            }
            actor.send(
              latest.context.assignment?.id === assignmentId
                ? {
                    type: "EXPORT_FAILED",
                    error: toRecoverableError(error),
                  }
                : {
                    type: "ANALYSIS_FAILED",
                    error: toRecoverableError(error),
                  },
            );
          }
        }
      })();
    }

    return () => controller.abort();
  }, [
    actor,
    assignmentId,
    exportId,
    fixtureScenario,
    mode,
    routeKey,
    usesRealApi,
  ]);

  useEffect(() => {
    if (usesRealApi || fixtureScenario || !autoAdvance) return;
    if (snapshot.matches("checking")) {
      const timer = window.setTimeout(
        () => actor.send({ type: "ANALYSIS_READY" }),
        450,
      );
      return () => window.clearTimeout(timer);
    }
    if (snapshot.matches("rephrasing") && !context.error) {
      const timer = window.setTimeout(
        () =>
          actor.send({
            type: "REPHRASE_READY",
            text: directSuggestionText,
          }),
        350,
      );
      return () => window.clearTimeout(timer);
    }
    if (snapshot.matches("confirming")) {
      const timer = window.setTimeout(
        () => actor.send({ type: "CONFIRM_SUCCEEDED" }),
        350,
      );
      return () => window.clearTimeout(timer);
    }
    if (snapshot.matches("exporting")) {
      const timer = window.setTimeout(() => {
        actor.send({ type: "EXPORT_SUCCEEDED", result: fixtureExportResult });
        navigate(
          `/app/${context.assignment?.id ?? assignmentId ?? "fixture-biology"}/export/${fixtureExportResult.id}`,
        );
      }, 450);
      return () => window.clearTimeout(timer);
    }
  }, [
    actor,
    assignmentId,
    autoAdvance,
    context.assignment?.id,
    context.error,
    fixtureScenario,
    navigate,
    snapshot,
    usesRealApi,
  ]);

  const stateKey = JSON.stringify(snapshot.value);
  useLayoutEffect(() => {
    if (editorFocusRequested.current) {
      editorFocusRequested.current = false;
      const editor = taskRef.current?.querySelector("textarea");
      if (editor) {
        editor.focus({ preventScroll: true });
        return;
      }
    }
    const heading = taskRef.current?.querySelector("h1");
    if (!heading) return;
    if (!heading.hasAttribute("tabindex"))
      heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
  }, [stateKey, context.review?.placement]);

  const assignment = context.assignment;
  const question = assignment?.questions[context.activeQuestionIndex];
  const hasWorksheet = Boolean(assignment);
  const answeredCount = Object.keys(context.confirmedAnswers).length;
  const showsCompletedPreview = usesRealApi
    ? snapshot.matches("exportComplete") && Boolean(context.exportResult)
    : answeredCount > 0 &&
      (snapshot.matches("answerAdded") ||
        snapshot.matches("worksheetReview") ||
        snapshot.matches("exporting") ||
        snapshot.matches("exportFailed") ||
        snapshot.matches("exportComplete"));
  const inlineCount =
    assignment?.questions.filter((item) => item.placement === "inline")
      .length ?? 0;
  const answerPageCount =
    assignment?.questions.filter((item) => item.placement === "appendix")
      .length ?? 0;
  const isVoiceInlineError =
    context.error?.code === "microphone_unavailable" ||
    context.error?.code === "realtime_disconnected";
  const showsStandaloneRequestError =
    Boolean(context.error) &&
    !isVoiceInlineError &&
    (snapshot.matches("direct") ||
      snapshot.matches("guided") ||
      snapshot.matches("answerAdded") ||
      snapshot.matches("worksheetReview"));

  const handleRealtimeEvent = useCallback(
    (event: RealtimeEvent) => {
      const current = actor.getSnapshot();

      if (event.type === "voice_state") {
        if (event.state === "speaking" && current.matches("guided")) {
          actor.send({ type: "VOICE_SPEAKING" });
        } else {
          actor.send({ type: "VOICE_STATE_CHANGED", state: event.state });
        }
        return;
      }

      if (event.type === "transcript") {
        setCaptions((previous) => ({
          ...previous,
          [event.speaker]: event.final
            ? event.text
            : `${previous[event.speaker]}${event.text}`,
        }));
        if (!event.final) return;

        if (
          event.speaker === "student" &&
          current.matches({ guided: "listening" })
        ) {
          actor.send({ type: "GUIDED_STUDENT_TURN", text: event.text });
        }
        if (
          event.speaker === "claros" &&
          current.matches({ guided: "thinking" })
        ) {
          actor.send({ type: "GUIDED_REPLY", text: event.text });
        }
        return;
      }

      if (event.type === "candidate") {
        actor.send({ type: "VOICE_CAPTURED", text: event.text });
        return;
      }

      if (event.type === "confirmation_phrase") {
        actor.send({ type: "VOICE_CONFIRMATION", phrase: event.phrase });
        return;
      }

      if (event.type === "error") {
        actor.send({
          type:
            event.code === "microphone_unavailable"
              ? "MICROPHONE_UNAVAILABLE"
              : "VOICE_DISCONNECTED",
        });
        return;
      }

      setHearing(false);
    },
    [actor],
  );

  const clearRealtimeAdvanceTimer = useCallback(() => {
    if (realtimeAdvanceTimerRef.current === null) return;
    window.clearTimeout(realtimeAdvanceTimerRef.current);
    realtimeAdvanceTimerRef.current = null;
  }, []);

  const releaseRealtimeAdapter = useCallback(() => {
    clearRealtimeAdvanceTimer();
    realtimeUnsubscribeRef.current?.();
    realtimeUnsubscribeRef.current = null;
    realtimeAdapterRef.current?.destroy();
    realtimeAdapterRef.current = null;
    realtimeConnectionKeyRef.current = null;
  }, [clearRealtimeAdvanceTimer]);

  const ensureRealtimeAdapter = useCallback(
    async (answerPath: "direct" | "guided") => {
      if (usesRealApi) return null;
      const realtime = await loadRealtimeAdapter();
      const current = actor.getSnapshot().context;
      const currentAssignment = current.assignment;
      const currentQuestion =
        currentAssignment?.questions[current.activeQuestionIndex];
      if (!currentAssignment || !currentQuestion) return null;

      const connectionKey = `${currentAssignment.id}:${currentQuestion.id}:${currentAssignment.version}:${answerPath}`;
      if (
        realtimeAdapterRef.current &&
        realtimeConnectionKeyRef.current === connectionKey
      ) {
        return { adapter: realtimeAdapterRef.current, realtime };
      }

      releaseRealtimeAdapter();
      const adapter = realtime.createFakeRealtimeAdapter();
      realtimeUnsubscribeRef.current = adapter.subscribe(handleRealtimeEvent);
      adapter.connect({
        assignmentId: currentAssignment.id,
        questionId: currentQuestion.id,
        assignmentVersion: currentAssignment.version,
        mode: answerPath,
      });
      if (current.muted) adapter.setMuted(true);
      realtimeAdapterRef.current = adapter;
      realtimeConnectionKeyRef.current = connectionKey;
      setCaptions({ student: "", claros: "" });
      return { adapter, realtime };
    },
    [actor, handleRealtimeEvent, releaseRealtimeAdapter, usesRealApi],
  );

  const nextRealtimeRunId = useCallback(() => {
    realtimeRunSequenceRef.current += 1;
    return String(realtimeRunSequenceRef.current);
  }, []);

  const advanceRealtimeNow = useCallback(
    (adapter: FakeRealtimeAdapter) => {
      clearRealtimeAdvanceTimer();
      while (adapter.getPendingCount() > 0) adapter.advance();
    },
    [clearRealtimeAdvanceTimer],
  );

  const advanceRealtimeSequence = useCallback(
    (adapter: FakeRealtimeAdapter) => {
      clearRealtimeAdvanceTimer();
      const advance = () => {
        if (realtimeAdapterRef.current !== adapter) return;
        const event = adapter.advance();
        if (adapter.getPendingCount() === 0) {
          realtimeAdvanceTimerRef.current = null;
          return;
        }
        const delay =
          event?.type === "voice_state" && event.state === "speaking"
            ? 1_000
            : 180;
        realtimeAdvanceTimerRef.current = window.setTimeout(advance, delay);
      };
      advance();
    },
    [clearRealtimeAdvanceTimer],
  );

  useEffect(() => {
    return () => releaseRealtimeAdapter();
  }, [assignment?.id, question?.id, releaseRealtimeAdapter]);

  useEffect(
    () => () => {
      analysisPollControllerRef.current?.abort();
    },
    [],
  );

  const startAnalysis = async (input: { file?: File; sampleId?: string }) => {
    setValidationMessage(undefined);
    persistedCandidateRef.current = null;
    actor.send({ type: "START_ANALYSIS" });
    if (!usesRealApi) {
      setAutoAdvance(true);
      return;
    }
    analysisPollControllerRef.current?.abort();
    const analysisController = new AbortController();
    analysisPollControllerRef.current = analysisController;
    try {
      let payload = await createAssignment(input);
      if (analysisController.signal.aborted) return;
      for (
        let pollAttempt = 0;
        payload.status === "analyzing";
        pollAttempt += 1
      ) {
        if (pollAttempt >= 400) {
          actor.send({
            type: "ANALYSIS_FAILED",
            error: {
              code: "analysis_timeout",
              message: "Worksheet checking took too long. Try again.",
              recoverable: true,
            },
          });
          return;
        }
        await waitForPoll(analysisController.signal);
        payload = await getAssignment(
          payload.assignment_id,
          analysisController.signal,
        );
      }
      if (payload.status !== "ready") {
        actor.send({
          type: "ANALYSIS_FAILED",
          error: {
            code: "analysis_failed",
            message: "This worksheet could not be checked. Try another PDF.",
            recoverable: true,
          },
        });
        return;
      }
      const restored = mapAssignment(payload);
      persistedCandidateRef.current = restored.candidate
        ? {
            assignmentId: restored.assignment.id,
            assignmentVersion: restored.assignment.version,
            candidate: restored.candidate,
          }
        : null;
      actor.send({
        type: "ANALYSIS_READY",
        assignment: restored.assignment,
        confirmedAnswers: restored.confirmedAnswers,
        activeQuestionIndex: restored.activeQuestionIndex,
        candidate: restored.candidate,
      });
    } catch (error) {
      if (isAbortError(error)) return;
      actor.send({
        type: "ANALYSIS_FAILED",
        error: toRecoverableError(error),
      });
    } finally {
      if (analysisPollControllerRef.current === analysisController) {
        analysisPollControllerRef.current = null;
      }
    }
  };

  const candidateRequestForCurrentState = (): ApiCandidateRequest | null => {
    const current = actor.getSnapshot().context;
    const currentAssignment = current.assignment;
    const currentQuestion =
      currentAssignment?.questions[current.activeQuestionIndex];
    const candidate = current.candidate;
    if (!currentAssignment || !currentQuestion || !candidate) return null;

    const revision = revisionSourceRef.current;
    if (revision?.questionId === currentQuestion.id) {
      return {
        assignment_version: currentAssignment.version,
        text: candidate.text,
        origin: "student_edited",
        interaction: {
          kind: "student_edit",
          prior_candidate_id: revision.candidateId,
          prior_candidate_version: revision.candidateVersion,
        },
      };
    }

    return {
      assignment_version: currentAssignment.version,
      text: candidate.text,
      origin: "student_verbatim",
      interaction: { kind: "direct_typed" },
    };
  };

  const persistCurrentCandidate = async () => {
    const current = actor.getSnapshot().context;
    const currentAssignment = current.assignment;
    const currentQuestion =
      currentAssignment?.questions[current.activeQuestionIndex];
    const candidate = current.candidate;
    if (!currentAssignment || !currentQuestion || !candidate) {
      throw new Error("A complete candidate is required before review.");
    }
    const remembered = persistedCandidateRef.current;
    if (
      remembered?.assignmentId === currentAssignment.id &&
      remembered.assignmentVersion === currentAssignment.version &&
      remembered.candidate.id === candidate.id &&
      remembered.candidate.version === candidate.version &&
      remembered.candidate.text === candidate.text
    ) {
      return { version: currentAssignment.version, candidate };
    }
    const request = candidateRequestForCurrentState();
    if (!request) {
      throw new Error("A complete candidate is required before review.");
    }
    const persisted = await createCandidateRequest(
      currentAssignment.id,
      currentQuestion.id,
      request,
    );
    const latest = actor.getSnapshot().context;
    const latestQuestion =
      latest.assignment?.questions[latest.activeQuestionIndex];
    if (
      latest.assignment?.id !== currentAssignment.id ||
      latestQuestion?.id !== currentQuestion.id
    ) {
      throw new DOMException("Assignment changed", "AbortError");
    }
    persistedCandidateRef.current = {
      assignmentId: currentAssignment.id,
      assignmentVersion: persisted.version,
      candidate: persisted.candidate,
    };
    if (revisionSourceRef.current?.questionId === currentQuestion.id) {
      revisionSourceRef.current = {
        questionId: currentQuestion.id,
        candidateId: persisted.candidate.id,
        candidateVersion: persisted.candidate.version,
      };
    }
    actor.send({ type: "CANDIDATE_PERSISTED", ...persisted });
    return persisted;
  };

  const beginVoice = async () => {
    if (usesRealApi) {
      actor.send({ type: "MICROPHONE_UNAVAILABLE" });
      return;
    }
    const current = actor.getSnapshot();
    const answerPath = current.matches("guided") ? "guided" : "direct";
    const interaction: FakeRealtimeInteraction = current.matches({
      guided: "finalizing",
    })
      ? "guided-final-answer"
      : answerPath === "guided"
        ? "guided-turn"
        : "direct-answer";
    const session = await ensureRealtimeAdapter(answerPath);
    if (!session) return;

    session.adapter.enqueue(
      ...session.realtime.createFakeRealtimeScript({
        interaction,
        runId: nextRealtimeRunId(),
        scenario: realtimeFixtureScenario ?? "normal",
        ...(interaction === "direct-answer"
          ? {
              studentText:
                question?.id === "q_03"
                  ? appendixCandidateText
                  : question?.id === "q_02"
                    ? directSuggestionText
                    : directCandidateText,
            }
          : interaction === "guided-final-answer"
            ? { studentText: guidedCandidateText }
            : {}),
      }),
    );
    session.adapter.startListening();
    actor.send({ type: "VOICE_START" });
    session.adapter.advance();
  };

  const stopVoice = () => {
    const adapter = realtimeAdapterRef.current;
    if (!adapter) return;
    adapter.stopListening();
    advanceRealtimeSequence(adapter);
  };

  const requestRephrase = async () => {
    if (usesRealApi && mutationPendingRef.current) return;
    actor.send({ type: "REQUEST_REPHRASE" });
    if (!usesRealApi) {
      setAutoAdvance(true);
      return;
    }
    mutationPendingRef.current = true;
    try {
      const current = actor.getSnapshot().context;
      const assignment = current.assignment;
      const question = assignment?.questions[current.activeQuestionIndex];
      if (!assignment || !question) throw new Error("Assignment unavailable");
      const persisted = await persistCurrentCandidate();
      const comparison = await requestRephraseMutation(
        assignment.id,
        question.id,
        {
          assignment_version: persisted.version,
          candidate_id: persisted.candidate.id,
          candidate_version: persisted.candidate.version,
        },
      );
      persistedCandidateRef.current = {
        assignmentId: assignment.id,
        assignmentVersion: comparison.version,
        candidate: persisted.candidate,
      };
      actor.send({
        type: "REPHRASE_READY",
        text: comparison.suggestion.text,
        original: mapCandidate(comparison.original),
        suggestion: mapCandidate(comparison.suggestion),
        rephraseId: comparison.rephrase_id,
        version: comparison.version,
      });
    } catch (error) {
      if (isAbortError(error)) return;
      actor.send({
        type: "REPHRASE_FAILED",
        error: toRecoverableError(error),
      });
    } finally {
      mutationPendingRef.current = false;
    }
  };

  const requestReview = async () => {
    if (!usesRealApi) {
      actor.send({ type: "REQUEST_REVIEW" });
      return;
    }
    if (mutationPendingRef.current) return;
    mutationPendingRef.current = true;
    try {
      const current = actor.getSnapshot().context;
      const assignment = current.assignment;
      const question = assignment?.questions[current.activeQuestionIndex];
      if (!assignment || !question) throw new Error("Assignment unavailable");
      const persisted = await persistCurrentCandidate();
      const reviewed = await createReviewRequest(assignment.id, question.id, {
        assignment_version: persisted.version,
        candidate_id: persisted.candidate.id,
        candidate_version: persisted.candidate.version,
      });
      persistedCandidateRef.current = {
        assignmentId: assignment.id,
        assignmentVersion: reviewed.version,
        candidate: reviewed.candidate,
      };
      actor.send({ type: "REVIEW_READY", ...reviewed });
    } catch (error) {
      if (isAbortError(error)) return;
      actor.send({
        type: "REQUEST_FAILED",
        error: toRecoverableError(error),
      });
    } finally {
      mutationPendingRef.current = false;
    }
  };

  const reviewComparisonSelection = async (
    selection: "original" | "suggestion",
  ) => {
    if (!usesRealApi) {
      actor.send({
        type: selection === "suggestion" ? "USE_SUGGESTION" : "KEEP_MY_WORDING",
      });
      return;
    }
    if (mutationPendingRef.current) return;
    mutationPendingRef.current = true;
    try {
      const current = actor.getSnapshot().context;
      const assignment = current.assignment;
      const question = assignment?.questions[current.activeQuestionIndex];
      let selected =
        selection === "suggestion"
          ? current.suggestion
          : (current.originalCandidate ?? current.candidate);
      let version = assignment?.version;
      if (!assignment || !question || !selected || version === undefined) {
        throw new Error("Wording selection unavailable");
      }

      if (selection === "suggestion") {
        if (!current.rephraseId) throw new Error("Rephrase unavailable");
        const remembered = persistedCandidateRef.current;
        if (
          remembered?.assignmentId === assignment.id &&
          remembered.assignmentVersion === version &&
          remembered.candidate.origin === "claros_rephrase" &&
          remembered.candidate.text === selected.text
        ) {
          selected = remembered.candidate;
        } else {
          const persisted = await createCandidateRequest(
            assignment.id,
            question.id,
            {
              assignment_version: version,
              text: selected.text,
              origin: "claros_rephrase",
              interaction: {
                kind: "selected_rephrase",
                rephrase_id: current.rephraseId,
                suggestion_candidate_id: selected.id,
              },
            },
          );
          persistedCandidateRef.current = {
            assignmentId: assignment.id,
            assignmentVersion: persisted.version,
            candidate: persisted.candidate,
          };
          if (revisionSourceRef.current?.questionId === question.id) {
            revisionSourceRef.current = {
              questionId: question.id,
              candidateId: persisted.candidate.id,
              candidateVersion: persisted.candidate.version,
            };
          }
          actor.send({ type: "CANDIDATE_PERSISTED", ...persisted });
          selected = persisted.candidate;
          version = persisted.version;
        }
      }

      const reviewed = await createReviewRequest(assignment.id, question.id, {
        assignment_version: version,
        candidate_id: selected.id,
        candidate_version: selected.version,
      });
      persistedCandidateRef.current = {
        assignmentId: assignment.id,
        assignmentVersion: reviewed.version,
        candidate: reviewed.candidate,
      };
      actor.send({ type: "REVIEW_READY", ...reviewed });
    } catch (error) {
      if (!isAbortError(error)) {
        actor.send({
          type: "REQUEST_FAILED",
          error: toRecoverableError(error),
        });
      }
    } finally {
      mutationPendingRef.current = false;
    }
  };

  const confirmAnswer = () => {
    actor.send({ type: "CONFIRM" });
    if (!usesRealApi) {
      setAutoAdvance(true);
    }
  };

  useEffect(() => {
    if (
      !usesRealApi ||
      !snapshot.matches("confirming") ||
      mutationPendingRef.current
    ) {
      return;
    }
    const current = actor.getSnapshot().context;
    const assignment = current.assignment;
    const review = current.review;
    const candidate = current.candidate;
    if (!assignment || !review || !candidate) return;
    mutationPendingRef.current = true;
    void confirmAnswerRequest(assignment.id, review.questionId, {
      assignment_version: review.assignmentVersion,
      review_token: review.token,
      candidate_id: candidate.id,
      candidate_version: candidate.version,
    })
      .then((confirmed) => {
        if (actor.getSnapshot().context.assignment?.id !== assignment.id)
          return;
        revisionSourceRef.current = null;
        persistedCandidateRef.current = null;
        exportIdempotencyRef.current = null;
        actor.send({ type: "CONFIRM_SUCCEEDED", ...confirmed });
      })
      .catch((error: unknown) => {
        if (actor.getSnapshot().context.assignment?.id !== assignment.id)
          return;
        actor.send({
          type: "CONFIRM_FAILED",
          error: toRecoverableError(error),
        });
      })
      .finally(() => {
        mutationPendingRef.current = false;
      });
  }, [actor, snapshot, usesRealApi]);

  const editAnswer = async (questionId: string, navigateAfter = false) => {
    const current = actor.getSnapshot().context;
    const assignment = current.assignment;
    if (!usesRealApi || !assignment) {
      actor.send({ type: "EDIT_ANSWER", questionId });
      if (navigateAfter) navigate(`/app/${assignment?.id ?? assignmentId}`);
      return;
    }
    if (mutationPendingRef.current) return;
    mutationPendingRef.current = true;
    try {
      const revision = await beginRevision(
        assignment.id,
        questionId,
        assignment.version,
      );
      revisionSourceRef.current = {
        questionId,
        candidateId: revision.prior_confirmed_answer.candidate_id,
        candidateVersion: revision.prior_confirmed_answer.candidate_version,
      };
      persistedCandidateRef.current = null;
      actor.send({
        type: "REVISION_READY",
        questionId,
        editSeed: revision.edit_seed,
        version: revision.version,
      });
      if (navigateAfter) navigate(`/app/${assignment.id}`);
    } catch (error) {
      actor.send({
        type: "REQUEST_FAILED",
        error: toRecoverableError(error),
      });
    } finally {
      mutationPendingRef.current = false;
    }
  };

  const exportAssignment = async () => {
    if (
      usesRealApi &&
      mode === "export" &&
      exportId &&
      exportPollRetryRef.current
    ) {
      exportPollRetryRef.current = false;
      actor.send({ type: "EXPORT_PENDING" });
      setExportPollAttempt((attempt) => attempt + 1);
      return;
    }
    if (actor.getSnapshot().matches("exportFailed")) {
      actor.send({ type: "RETRY_EXPORT" });
    } else {
      actor.send({ type: "CREATE_EXPORT" });
    }
    if (!usesRealApi) {
      setAutoAdvance(true);
      return;
    }
    const current = actor.getSnapshot().context;
    const assignment = current.assignment;
    if (!assignment || mutationPendingRef.current) return;
    mutationPendingRef.current = true;
    let exportAttempt = exportIdempotencyRef.current;
    if (
      exportAttempt?.assignmentId !== assignment.id ||
      exportAttempt.currentVersion !== assignment.version
    ) {
      exportAttempt = {
        assignmentId: assignment.id,
        requestVersion: assignment.version,
        currentVersion: assignment.version,
        key: crypto.randomUUID(),
      };
      exportIdempotencyRef.current = exportAttempt;
    }
    try {
      const exported = await createExportRequest(
        assignment.id,
        exportAttempt.requestVersion,
        exportAttempt.key,
      );
      const mapped = mapExportState(exported, assignment.id);
      exportIdempotencyRef.current = {
        ...exportAttempt,
        currentVersion: mapped.version,
      };
      if (mapped.kind === "complete") {
        exportIdempotencyRef.current = null;
        actor.send({
          type: "EXPORT_SUCCEEDED",
          result: mapped.result,
          version: mapped.version,
        });
        navigate(`/app/${assignment.id}/export/${exported.export_id}`);
      } else if (mapped.kind === "failed") {
        exportIdempotencyRef.current = null;
        actor.send({
          type: "EXPORT_FAILED",
          error: mapped.error,
          version: mapped.version,
        });
      } else {
        actor.send({ type: "EXPORT_PENDING", version: mapped.version });
        navigate(`/app/${assignment.id}/export/${exported.export_id}`);
      }
    } catch (error) {
      actor.send({
        type: "EXPORT_FAILED",
        error: toRecoverableError(error),
      });
    } finally {
      mutationPendingRef.current = false;
    }
  };

  const hearExact = async () => {
    if (!context.candidate) return;
    if (usesRealApi) return;
    const answerPath = context.path ?? "direct";
    const session = await ensureRealtimeAdapter(answerPath);
    if (!session) return;

    setHearing(true);
    session.adapter.hearExact(context.candidate.text);
    session.adapter.enqueue(
      ...session.realtime.createFakeRealtimeScript({
        interaction: "playback",
        runId: nextRealtimeRunId(),
        studentText: context.candidate.text,
      }),
    );
    clearRealtimeAdvanceTimer();
    realtimeAdvanceTimerRef.current = window.setTimeout(() => {
      advanceRealtimeNow(session.adapter);
    }, 300);
  };

  const sendGuidedTurn = async () => {
    if (!/\S/u.test(guidedDraft)) return;
    const text = guidedDraft;
    actor.send({ type: "GUIDED_STUDENT_TURN", text });
    setGuidedDraft("");
    if (usesRealApi) {
      actor.send({ type: "MICROPHONE_UNAVAILABLE" });
      return;
    }
    const session = await ensureRealtimeAdapter("guided");
    if (!session) return;
    session.adapter.sendTypedTurn(text);
    session.adapter.enqueue(
      ...session.realtime.createFakeRealtimeScript({
        interaction: "guided-typed-turn",
        runId: nextRealtimeRunId(),
        scenario: realtimeFixtureScenario ?? "normal",
        clarosText:
          "What does sunlight provide that helps the plant make food?",
      }),
    );
    advanceRealtimeSequence(session.adapter);
  };

  const retryVoice = async () => {
    actor.send({ type: "RETRY_VOICE" });
    if (usesRealApi) {
      actor.send({ type: "MICROPHONE_UNAVAILABLE" });
      return;
    }
    const current = actor.getSnapshot();
    const answerPath = current.matches("guided") ? "guided" : "direct";
    const session = await ensureRealtimeAdapter(answerPath);
    if (!session) return;
    session.adapter.retry();
    session.adapter.enqueue({
      event: {
        id: `fixture-${nextRealtimeRunId()}-retry-ready`,
        type: "voice_state",
        state: "ready",
      },
    });
    advanceRealtimeNow(session.adapter);
  };

  const toggleMute = () => {
    const nextMuted = !actor.getSnapshot().context.muted;
    realtimeAdapterRef.current?.setMuted(nextMuted);
    actor.send({ type: "TOGGLE_MUTE" });
  };

  const interruptVoice = () => {
    clearRealtimeAdvanceTimer();
    realtimeAdapterRef.current?.interrupt();
    actor.send({ type: "INTERRUPT" });
    releaseRealtimeAdapter();
  };

  useEffect(() => {
    if (
      !realtimeFixtureScenario ||
      !["casual", "confirm", "duplicate"].includes(realtimeFixtureScenario) ||
      !snapshot.matches("exactReview") ||
      !context.candidate
    ) {
      return;
    }

    const fixtureKey = `${context.candidate.id}:${context.candidate.version}:${realtimeFixtureScenario}`;
    if (exactReviewFixtureRef.current === fixtureKey) return;
    exactReviewFixtureRef.current = fixtureKey;
    let cancelled = false;
    let dispatched = false;

    void (async () => {
      const session = await ensureRealtimeAdapter(context.path ?? "direct");
      if (!session || cancelled) return;
      session.adapter.enqueue(
        ...session.realtime.createFakeRealtimeScript({
          interaction: "exact-review",
          runId: nextRealtimeRunId(),
          scenario: realtimeFixtureScenario,
        }),
      );
      if (
        realtimeFixtureScenario === "confirm" ||
        realtimeFixtureScenario === "duplicate"
      ) {
        setAutoAdvance(true);
      }
      advanceRealtimeNow(session.adapter);
      dispatched = true;
    })();

    return () => {
      cancelled = true;
      if (!dispatched && exactReviewFixtureRef.current === fixtureKey) {
        exactReviewFixtureRef.current = null;
      }
    };
  }, [
    advanceRealtimeNow,
    context.candidate,
    context.path,
    ensureRealtimeAdapter,
    nextRealtimeRunId,
    realtimeFixtureScenario,
    snapshot,
  ]);

  const liveCaptions = (
    <section
      className={answerPathStyles.liveCaptions}
      aria-label="Live captions"
    >
      <div className={answerPathStyles.liveCaptionsHeader}>
        <strong>Live captions</strong>
        <Button
          color="link-gray"
          size="sm"
          onPress={() => setCaptionsVisible((visible) => !visible)}
          aria-expanded={captionsVisible}
          aria-controls="v2-live-captions"
          className={answerPathStyles.minimumTarget}
        >
          {captionsVisible ? "Hide live captions" : "View live captions"}
        </Button>
      </div>
      {captionsVisible ? (
        <div
          id="v2-live-captions"
          className={answerPathStyles.captionList}
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {captions.student ? (
            <p className={answerPathStyles.captionLine}>
              <strong>You</strong>
              <span>{captions.student}</span>
            </p>
          ) : null}
          {captions.claros ? (
            <p className={answerPathStyles.captionLine}>
              <strong>Claros</strong>
              <span>{captions.claros}</span>
            </p>
          ) : null}
          {!captions.student && !captions.claros ? (
            <p className={answerPathStyles.captionPlaceholder}>
              Spoken words will appear here without changing your answer.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );

  const openReview = () => {
    actor.send({ type: "OPEN_WORKSHEET_REVIEW" });
    navigate(
      `/app/${assignment?.id ?? assignmentId ?? "fixture-biology"}/review`,
    );
  };

  const taskContent = (() => {
    if (snapshot.matches("upload")) {
      return (
        <IntakeFlow
          state={{ kind: "upload" }}
          validationMessage={validationMessage}
          onFileSelected={(file) => void startAnalysis({ file })}
          onValidationError={(error) =>
            setValidationMessage(
              error === "file_too_large"
                ? "Choose a PDF smaller than 10 MiB."
                : "Choose a PDF file.",
            )
          }
          onTrySample={() =>
            void startAnalysis({ sampleId: "biology-short-answer" })
          }
          onShowLimitations={() => navigate("/#accessibility")}
        />
      );
    }
    if (snapshot.matches("checking")) {
      return (
        <IntakeFlow
          state={{ kind: "checking", message: "Checking your worksheet…" }}
          onFileSelected={(file) => void startAnalysis({ file })}
          onValidationError={() => undefined}
          onTrySample={() =>
            void startAnalysis({ sampleId: "biology-short-answer" })
          }
        />
      );
    }
    if (snapshot.matches("rejected")) {
      return (
        <IntakeFlow
          state={{
            kind: "unsupported",
            message:
              context.error?.message ??
              "This PDF needs selectable text before Claros can find its questions.",
            recoverable: context.error?.recoverable ?? true,
          }}
          onFileSelected={(file) => void startAnalysis({ file })}
          onValidationError={() => undefined}
          onTrySample={() =>
            void startAnalysis({ sampleId: "biology-short-answer" })
          }
          onShowLimitations={() => navigate("/#accessibility")}
        />
      );
    }
    if (snapshot.matches("ready") && assignment) {
      return (
        <IntakeFlow
          state={{
            kind: "ready",
            assignment,
            inlineCount,
            answerPageCount,
            warnings:
              assignment.warnings ??
              (answerPageCount > 0
                ? [
                    `${answerPageCount} ${answerPageCount === 1 ? "answer" : "answers"} will use an attached answer page.`,
                  ]
                : []),
          }}
          onFileSelected={(file) => void startAnalysis({ file })}
          onValidationError={() => undefined}
          onTrySample={() =>
            void startAnalysis({ sampleId: "biology-short-answer" })
          }
          onStart={() => {
            actor.send({ type: "START_QUESTION" });
            navigate(`/app/${assignment.id}`);
          }}
          onViewWorksheet={() => setWorksheetOpen(true)}
        />
      );
    }
    if (!assignment || !question) return null;

    if (snapshot.matches("questionChoice")) {
      return (
        <EntryPathChoice
          question={question}
          totalQuestions={assignment.questions.length}
          onChooseDirect={() => actor.send({ type: "CHOOSE_DIRECT" })}
          onChooseGuided={() => actor.send({ type: "CHOOSE_GUIDED" })}
          onTypeInstead={() => {
            editorFocusRequested.current = true;
            actor.send({ type: "TYPE_INSTEAD" });
          }}
          onViewWorksheet={() => setWorksheetOpen(true)}
        />
      );
    }
    if (snapshot.matches("direct")) {
      return (
        <>
          <DirectAnswerPanel
            question={question}
            totalQuestions={assignment.questions.length}
            candidateText={context.candidate?.text ?? ""}
            voiceState={context.voiceState}
            muted={context.muted}
            onCandidateChange={(value) =>
              actor.send({ type: "CANDIDATE_CHANGED", value })
            }
            onStart={beginVoice}
            onStop={stopVoice}
            onRetry={retryVoice}
            onContinueByTyping={() => {
              editorFocusRequested.current = true;
              actor.send({ type: "CONTINUE_BY_TYPING" });
            }}
            onToggleMute={toggleMute}
            onMakeClearer={() => void requestRephrase()}
            onReview={() => void requestReview()}
          />
          {liveCaptions}
        </>
      );
    }
    if (snapshot.matches("guided")) {
      const isFinal = snapshot.matches({ guided: "finalizing" });
      return (
        <>
          <GuidedReasoningPanel
            question={question}
            totalQuestions={assignment.questions.length}
            turns={context.guidedTurns}
            draft={isFinal ? (context.candidate?.text ?? "") : guidedDraft}
            voiceState={context.voiceState}
            muted={context.muted}
            mode={isFinal ? "final-answer" : "conversation"}
            onDraftChange={(value) => {
              if (isFinal) {
                actor.send({ type: "CANDIDATE_CHANGED", value });
              } else {
                setGuidedDraft(value);
              }
            }}
            onSendTypedTurn={sendGuidedTurn}
            onReadyToAnswer={() => {
              editorFocusRequested.current = true;
              actor.send({ type: "GUIDED_READY_TO_ANSWER" });
            }}
            onStart={beginVoice}
            onStop={stopVoice}
            onRetry={retryVoice}
            onContinueByTyping={() => {
              editorFocusRequested.current = true;
              actor.send({ type: "CONTINUE_BY_TYPING" });
            }}
            onInterrupt={interruptVoice}
            onToggleMute={toggleMute}
            onMakeClearer={() => void requestRephrase()}
            onReview={() => void requestReview()}
          />
          {liveCaptions}
        </>
      );
    }
    if (snapshot.matches("rephrasing") && context.candidate) {
      return (
        <RephrasingState
          candidate={context.candidate}
          error={context.error}
          onKeepOriginal={() => void reviewComparisonSelection("original")}
          onRetry={() => void requestRephrase()}
        />
      );
    }
    if (
      snapshot.matches("comparison") &&
      context.originalCandidate &&
      context.suggestion
    ) {
      return (
        <WordingComparison
          original={context.originalCandidate}
          suggestion={context.suggestion}
          error={context.error}
          onKeepOriginal={() => void reviewComparisonSelection("original")}
          onUseSuggestion={() => void reviewComparisonSelection("suggestion")}
          onChangeAnswer={() => actor.send({ type: "CHANGE_ANSWER" })}
        />
      );
    }
    if (snapshot.matches("exactReview") && context.candidate) {
      return (
        <>
          <ExactAnswerReview
            candidate={context.candidate}
            placement={context.review?.placement ?? question.placement}
            isHearing={isHearing}
            error={context.error}
            onHear={hearExact}
            onChangeAnswer={() => actor.send({ type: "CHANGE_ANSWER" })}
            onConfirm={() => void confirmAnswer()}
          />
          {liveCaptions}
        </>
      );
    }
    if (snapshot.matches("confirming") && context.candidate) {
      return (
        <ConfirmingAnswerState
          candidate={context.candidate}
          placement={context.review?.placement ?? question.placement}
        />
      );
    }
    if (snapshot.matches("answerAdded")) {
      const answer = context.confirmedAnswers[question.id];
      if (!answer) return null;
      const nextQuestionNumber =
        context.activeQuestionIndex < assignment.questions.length - 1
          ? question.index + 1
          : undefined;
      return (
        <AnswerAddedState
          answer={answer}
          nextQuestionNumber={nextQuestionNumber}
          onEdit={() => {
            if (usesRealApi) void editAnswer(question.id);
            else actor.send({ type: "CHANGE_ANSWER" });
          }}
          onContinue={() => {
            actor.send({ type: "CONTINUE_TO_NEXT" });
            if (!nextQuestionNumber) {
              navigate(`/app/${assignment.id}/review`);
            }
          }}
        />
      );
    }
    if (snapshot.matches("worksheetReview")) {
      return (
        <WorksheetReview
          assignment={assignment}
          confirmedAnswers={context.confirmedAnswers}
          onEdit={(questionId) => {
            void editAnswer(questionId, true);
          }}
          onGoToQuestion={(questionId) => {
            actor.send({ type: "GO_TO_QUESTION", questionId });
            navigate(`/app/${assignment.id}`);
          }}
          onExport={() => void exportAssignment()}
        />
      );
    }
    if (snapshot.matches("exporting")) return <ExportProgressState />;
    if (snapshot.matches("exportFailed") && context.error) {
      return (
        <ExportFailureState
          error={context.error}
          onRetry={() => void exportAssignment()}
          onReviewAnswers={() => actor.send({ type: "REVIEW_ANSWERS" })}
        />
      );
    }
    if (snapshot.matches("exportComplete") && context.exportResult) {
      return (
        <ExportCompleteState
          result={context.exportResult}
          onReviewAnswers={openReview}
        />
      );
    }
    return null;
  })();

  const progress = !assignment
    ? snapshot.matches("checking")
      ? "Checking worksheet"
      : "Start"
    : snapshot.matches("worksheetReview")
      ? `${answeredCount} of ${assignment.questions.length} answered`
      : snapshot.matches("exporting") ||
          snapshot.matches("exportFailed") ||
          snapshot.matches("exportComplete")
        ? "Completed PDF"
        : `Question ${question?.index ?? 1} of ${assignment.questions.length}`;

  return (
    <main className="v2-app-shell">
      <header className="v2-topbar">
        <Brand />
        <span className="v2-topbar-title">
          {assignment?.title ?? "New worksheet"}
        </span>
        <span className="v2-topbar-progress" role="status">
          {progress}
        </span>
        {assignment && !snapshot.matches("worksheetReview") ? (
          <Link
            className="v2-topbar-action"
            to={`/app/${assignment.id}/review`}
            onClick={() => actor.send({ type: "OPEN_WORKSHEET_REVIEW" })}
          >
            Review answers
          </Link>
        ) : null}
      </header>

      <div
        className={`v2-workspace-grid${hasWorksheet ? "" : " v2-workspace-grid--task-only"}`}
      >
        <section ref={taskRef} className="v2-task" aria-label="Answer task">
          <div className="v2-task-inner">
            {taskContent}
            {showsStandaloneRequestError && context.error ? (
              <StatusNotice title="That action did not finish" tone="error">
                {context.error.message}
              </StatusNotice>
            ) : null}
            {hasWorksheet ? (
              <div className="v2-mobile-document-action">
                <Button
                  color="secondary"
                  size="lg"
                  iconLeading={Eye}
                  onPress={() => setWorksheetOpen(true)}
                >
                  View worksheet
                </Button>
              </div>
            ) : null}
          </div>
        </section>

        {hasWorksheet ? (
          <aside
            className="v2-source-pane"
            aria-label="Worksheet source context"
          >
            <div className="v2-source-heading">
              <div>
                <strong>
                  {showsCompletedPreview
                    ? "Completed copy preview"
                    : "Original worksheet"}
                </strong>
                <span>
                  {showsCompletedPreview
                    ? "Source page preserved · confirmed answer shown"
                    : "Verified source · unchanged"}
                </span>
              </div>
              <Button
                color="secondary"
                size="sm"
                iconLeading={Eye}
                onPress={() => setWorksheetOpen(true)}
              >
                {showsCompletedPreview ? "View original" : "View worksheet"}
              </Button>
            </div>
            <Suspense
              fallback={
                <div className="v2-document-loading" role="status">
                  Rendering source page…
                </div>
              }
            >
              <DocumentCrop
                contextUrl={
                  usesRealApi && assignment && question
                    ? `/api/v2/assignments/${encodeURIComponent(assignment.id)}/pages/${question.pageNumber}/context?question_id=${encodeURIComponent(question.id)}${showsCompletedPreview ? "&preview=confirmed" : ""}`
                    : `/api/v2/fixtures/biology/page-context?question_id=${encodeURIComponent(question?.id ?? "q_01")}${showsCompletedPreview ? "&preview=confirmed" : ""}`
                }
              />
            </Suspense>
          </aside>
        ) : null}
      </div>

      {hasWorksheet && isWorksheetOpen ? (
        <Suspense
          fallback={
            <div className="v2-document-loading" role="status">
              Opening worksheet…
            </div>
          }
        >
          <WorksheetDialog
            isOpen
            onOpenChange={setWorksheetOpen}
            sourceUrl={
              usesRealApi && assignment
                ? `/api/v2/assignments/${encodeURIComponent(assignment.id)}/source`
                : undefined
            }
            filename={assignment?.filename}
          />
        </Suspense>
      ) : null}
    </main>
  );
}
