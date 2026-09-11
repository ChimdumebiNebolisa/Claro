import { assign, setup } from "xstate";
import type {
  AnswerPath,
  Assignment,
  Candidate,
  ConfirmedAnswer,
  ConversationTurn,
  ExportResult,
  RecoverableError,
  ReviewSnapshot,
  VoiceState,
} from "./contracts";
import { CANONICAL_CONFIRMATION_PHRASE } from "./contracts";
import {
  appendixCandidateText,
  candidateFor,
  directCandidateText,
  directSuggestionText,
  fixtureAssignment,
  fixtureConfirmedAnswer,
  fixtureExportResult,
  fixtureGuidedTurns,
  guidedCandidateText,
} from "./fixtures";

export const fixtureScenarios = [
  "upload",
  "checking",
  "ready",
  "unsupported",
  "question-choice",
  "direct-listening",
  "direct-captured",
  "guided-conversation",
  "wording-comparison",
  "exact-review-inline",
  "exact-review-appendix",
  "answer-added",
  "worksheet-review",
  "exporting",
  "export-failed",
  "export-complete",
  "voice-unavailable",
] as const;

export type FixtureScenario = (typeof fixtureScenarios)[number];

export type WorkspaceContext = {
  assignment: Assignment | null;
  activeQuestionIndex: number;
  path: AnswerPath | null;
  candidate: Candidate | null;
  originalCandidate: Candidate | null;
  suggestion: Candidate | null;
  rephraseId: string | null;
  review: ReviewSnapshot | null;
  confirmedAnswers: Readonly<Record<string, ConfirmedAnswer>>;
  guidedTurns: readonly ConversationTurn[];
  voiceState: VoiceState;
  muted: boolean;
  error: RecoverableError | null;
  exportResult: ExportResult | null;
};

export type WorkspaceEvent =
  | { type: "START_ANALYSIS" }
  | {
      type: "ANALYSIS_READY";
      assignment?: Assignment;
      confirmedAnswers?: Readonly<Record<string, ConfirmedAnswer>>;
      activeQuestionIndex?: number;
      candidate?: Candidate | null;
    }
  | { type: "ANALYSIS_FAILED"; error: RecoverableError }
  | { type: "REQUEST_FAILED"; error: RecoverableError }
  | { type: "START_QUESTION" }
  | { type: "CHOOSE_DIRECT" }
  | { type: "CHOOSE_GUIDED" }
  | { type: "TYPE_INSTEAD" }
  | { type: "VOICE_START" }
  | { type: "VOICE_CAPTURED"; text: string }
  | { type: "VOICE_STATE_CHANGED"; state: VoiceState }
  | { type: "VOICE_THINKING" }
  | { type: "VOICE_SPEAKING" }
  | { type: "MICROPHONE_UNAVAILABLE" }
  | { type: "VOICE_DISCONNECTED" }
  | { type: "RETRY_VOICE" }
  | { type: "CONTINUE_BY_TYPING" }
  | { type: "TOGGLE_MUTE" }
  | { type: "INTERRUPT" }
  | { type: "CANDIDATE_CHANGED"; value: string }
  | { type: "CANDIDATE_PERSISTED"; candidate: Candidate; version: number }
  | { type: "GUIDED_STUDENT_TURN"; text: string }
  | { type: "GUIDED_REPLY"; text: string }
  | { type: "GUIDED_READY_TO_ANSWER" }
  | { type: "REQUEST_REPHRASE" }
  | {
      type: "REPHRASE_READY";
      text: string;
      original?: Candidate;
      suggestion?: Candidate;
      rephraseId?: string;
      version?: number;
    }
  | { type: "REPHRASE_FAILED"; error: RecoverableError }
  | { type: "KEEP_MY_WORDING" }
  | { type: "USE_SUGGESTION" }
  | { type: "REQUEST_REVIEW" }
  | {
      type: "REVIEW_READY";
      review: ReviewSnapshot;
      candidate: Candidate;
      version: number;
    }
  | { type: "CHANGE_ANSWER" }
  | { type: "CONFIRM" }
  | { type: "VOICE_CONFIRMATION"; phrase: string }
  | {
      type: "CONFIRM_SUCCEEDED";
      answer?: ConfirmedAnswer;
      version?: number;
    }
  | { type: "CONFIRM_FAILED"; error: RecoverableError }
  | { type: "CONTINUE_TO_NEXT" }
  | { type: "OPEN_WORKSHEET_REVIEW" }
  | { type: "GO_TO_QUESTION"; questionId: string }
  | { type: "EDIT_ANSWER"; questionId: string }
  | {
      type: "REVISION_READY";
      questionId: string;
      editSeed: string;
      version: number;
    }
  | { type: "CREATE_EXPORT" }
  | { type: "EXPORT_PENDING"; version?: number }
  | { type: "EXPORT_SUCCEEDED"; result: ExportResult; version?: number }
  | { type: "EXPORT_RESTORED"; result: ExportResult; version?: number }
  | { type: "EXPORT_FAILED"; error: RecoverableError; version?: number }
  | { type: "RETRY_EXPORT" }
  | { type: "REVIEW_ANSWERS" }
  | { type: "RESET" }
  | { type: "OPEN_ASSIGNMENT_ROUTE" }
  | { type: "OPEN_REVIEW_ROUTE" }
  | { type: "OPEN_EXPORT_ROUTE" }
  | { type: "LOAD_FIXTURE_SCENARIO"; scenario: FixtureScenario };

export function createInitialWorkspaceContext(): WorkspaceContext {
  return {
    assignment: null,
    activeQuestionIndex: 0,
    path: null,
    candidate: null,
    originalCandidate: null,
    suggestion: null,
    rephraseId: null,
    review: null,
    confirmedAnswers: {},
    guidedTurns: [],
    voiceState: "ready",
    muted: false,
    error: null,
    exportResult: null,
  };
}

const cloneAssignment = (version = fixtureAssignment.version): Assignment => ({
  ...fixtureAssignment,
  version,
  questions: fixtureAssignment.questions.map((question) => ({ ...question })),
});

const createReview = (
  context: WorkspaceContext,
  candidate: Candidate,
): ReviewSnapshot => {
  const question = context.assignment?.questions[context.activeQuestionIndex];
  return {
    token: `review_${question?.id ?? "unknown"}_${candidate.version}`,
    expiresAt: "2099-01-01T00:00:00.000Z",
    questionId: candidate.questionId,
    candidateId: candidate.id,
    candidateVersion: candidate.version,
    exactText: candidate.text,
    placement: question?.placement ?? "appendix",
    assignmentVersion: context.assignment?.version ?? 0,
  };
};

function contextForScenario(scenario: FixtureScenario): WorkspaceContext {
  const context = createInitialWorkspaceContext();
  const direct = candidateFor(
    fixtureAssignment.questions[0].id,
    directCandidateText,
    "student_normalized",
  );
  const appendix = candidateFor(
    fixtureAssignment.questions[2].id,
    appendixCandidateText,
    "student_after_guidance",
  );

  if (scenario === "upload" || scenario === "checking") return context;
  if (scenario === "unsupported") {
    return {
      ...context,
      error: {
        code: "requires_ocr",
        message:
          "This PDF appears to be scanned. Claros supports PDFs with selectable text.",
        recoverable: true,
      },
    };
  }

  context.assignment = cloneAssignment();
  if (scenario === "ready" || scenario === "question-choice") return context;

  if (scenario === "direct-listening") {
    return { ...context, path: "direct", voiceState: "listening" };
  }
  if (scenario === "direct-captured") {
    return {
      ...context,
      path: "direct",
      voiceState: "captured",
      candidate: direct,
    };
  }
  if (scenario === "voice-unavailable") {
    return {
      ...context,
      path: "direct",
      voiceState: "microphone_unavailable",
      candidate: candidateFor(
        fixtureAssignment.questions[0].id,
        "Plants need sunlight because",
        "student_verbatim",
      ),
      error: {
        code: "microphone_unavailable",
        message: "Microphone unavailable",
        recoverable: true,
      },
    };
  }
  if (scenario === "guided-conversation") {
    return {
      ...context,
      activeQuestionIndex: 1,
      path: "guided",
      guidedTurns: fixtureGuidedTurns,
      voiceState: "ready",
    };
  }
  if (scenario === "wording-comparison") {
    return {
      ...context,
      path: "direct",
      candidate: direct,
      originalCandidate: direct,
      suggestion: candidateFor(
        direct.questionId,
        directSuggestionText,
        "claros_rephrase",
        2,
      ),
      voiceState: "captured",
    };
  }
  if (scenario === "exact-review-inline") {
    return {
      ...context,
      path: "direct",
      candidate: direct,
      review: createReview(context, direct),
      voiceState: "captured",
    };
  }
  if (scenario === "exact-review-appendix") {
    const appendixContext = {
      ...context,
      activeQuestionIndex: 2,
      path: "guided" as const,
      candidate: appendix,
      guidedTurns: fixtureGuidedTurns,
      voiceState: "captured" as const,
    };
    return {
      ...appendixContext,
      review: createReview(appendixContext, appendix),
    };
  }
  if (scenario === "answer-added") {
    return {
      ...context,
      path: "direct",
      candidate: direct,
      review: createReview(context, direct),
      confirmedAnswers: { q_01: fixtureConfirmedAnswer },
      voiceState: "captured",
    };
  }

  const reviewContext = {
    ...context,
    confirmedAnswers: { q_01: fixtureConfirmedAnswer },
  };
  if (scenario === "worksheet-review" || scenario === "exporting") {
    return reviewContext;
  }
  if (scenario === "export-failed") {
    return {
      ...reviewContext,
      error: {
        code: "export_timed_out",
        message:
          "The completed PDF took too long to prepare. Your confirmed answers are safe.",
        recoverable: true,
      },
    };
  }
  return { ...reviewContext, exportResult: fixtureExportResult };
}

const scenarioTarget = (scenario: FixtureScenario) => {
  const targets: Record<FixtureScenario, string> = {
    upload: "#claros-v2-upload",
    checking: "#claros-v2-checking",
    ready: "#claros-v2-ready",
    unsupported: "#claros-v2-rejected",
    "question-choice": "#claros-v2-question-choice",
    "direct-listening": "#claros-v2-direct-listening",
    "direct-captured": "#claros-v2-direct-captured",
    "guided-conversation": "#claros-v2-guided-ready",
    "wording-comparison": "#claros-v2-comparison",
    "exact-review-inline": "#claros-v2-exact-review",
    "exact-review-appendix": "#claros-v2-exact-review",
    "answer-added": "#claros-v2-answer-added",
    "worksheet-review": "#claros-v2-worksheet-review",
    exporting: "#claros-v2-exporting",
    "export-failed": "#claros-v2-export-failed",
    "export-complete": "#claros-v2-export-complete",
    "voice-unavailable": "#claros-v2-direct-voice-unavailable",
  };
  return targets[scenario];
};

type FixtureScenarioEvent = Extract<
  WorkspaceEvent,
  { type: "LOAD_FIXTURE_SCENARIO" }
>;

const fixtureTransitions = fixtureScenarios.map((scenario) => ({
  guard: ({ event }: { event: FixtureScenarioEvent }) =>
    event.scenario === scenario,
  target: scenarioTarget(scenario),
  actions: "loadFixtureScenario" as const,
}));

export const workspaceMachine = setup({
  types: {
    context: {} as WorkspaceContext,
    events: {} as WorkspaceEvent,
  },
  guards: {
    hasCandidate: ({ context }) =>
      Boolean(context.candidate?.text.match(/\S/u)),
    hasCurrentReview: ({ context }) =>
      Boolean(
        context.review &&
        context.candidate &&
        context.review.candidateId === context.candidate.id &&
        context.review.candidateVersion === context.candidate.version &&
        context.review.exactText === context.candidate.text &&
        context.review.assignmentVersion === context.assignment?.version,
      ),
    hasConfirmedAnswer: ({ context }) =>
      Object.keys(context.confirmedAnswers).length > 0,
    hasNextQuestion: ({ context }) =>
      Boolean(
        context.assignment &&
        context.activeQuestionIndex < context.assignment.questions.length - 1,
      ),
    cameFromGuided: ({ context }) => context.path === "guided",
    isExactVoiceConfirmation: ({ event }) =>
      event.type === "VOICE_CONFIRMATION" &&
      event.phrase === CANONICAL_CONFIRMATION_PHRASE,
    reportedVoiceIsReady: ({ event }) =>
      event.type === "VOICE_STATE_CHANGED" && event.state === "ready",
    hasCurrentExactVoiceConfirmation: ({ context, event }) =>
      event.type === "VOICE_CONFIRMATION" &&
      event.phrase === CANONICAL_CONFIRMATION_PHRASE &&
      Boolean(
        context.review &&
        context.candidate &&
        context.review.candidateId === context.candidate.id &&
        context.review.candidateVersion === context.candidate.version &&
        context.review.exactText === context.candidate.text &&
        context.review.assignmentVersion === context.assignment?.version,
      ),
  },
  actions: {
    loadFixtureScenario: assign(({ event }) =>
      event.type === "LOAD_FIXTURE_SCENARIO"
        ? contextForScenario(event.scenario)
        : {},
    ),
    clearForAnalysis: assign(() => createInitialWorkspaceContext()),
    setAnalysisReady: assign(({ event }) =>
      event.type === "ANALYSIS_READY" && event.assignment
        ? {
            assignment: event.assignment,
            confirmedAnswers: event.confirmedAnswers ?? {},
            activeQuestionIndex: event.activeQuestionIndex ?? 0,
            candidate: event.candidate ?? null,
            error: null,
          }
        : { assignment: cloneAssignment(), error: null },
    ),
    setError: assign({
      error: ({ event }) => ("error" in event ? event.error : null),
    }),
    chooseDirect: assign({
      path: () => "direct" as const,
      voiceState: () => "ready" as const,
      error: () => null,
    }),
    chooseGuided: assign({
      path: () => "guided" as const,
      voiceState: () => "ready" as const,
      guidedTurns: ({ context }) =>
        context.guidedTurns.length
          ? context.guidedTurns
          : [
              {
                id: "turn_prompt_01",
                speaker: "claros" as const,
                text: "What do you already know about this question?",
              },
            ],
      error: () => null,
    }),
    setVoiceReady: assign({
      voiceState: () => "ready" as const,
      error: () => null,
    }),
    setVoiceListening: assign({
      voiceState: () => "listening" as const,
      error: () => null,
    }),
    setVoiceThinking: assign({ voiceState: () => "thinking" as const }),
    setVoiceSpeaking: assign({ voiceState: () => "speaking" as const }),
    setReportedVoiceState: assign(({ event }) =>
      event.type === "VOICE_STATE_CHANGED" ? { voiceState: event.state } : {},
    ),
    setVoiceInterrupted: assign({
      voiceState: () => "interrupted" as const,
    }),
    setMicrophoneUnavailable: assign({
      voiceState: () => "microphone_unavailable" as const,
      error: () => ({
        code: "microphone_unavailable",
        message: "Microphone unavailable",
        recoverable: true,
      }),
    }),
    setVoiceDisconnected: assign({
      voiceState: () => "disconnected" as const,
      error: () => ({
        code: "realtime_disconnected",
        message: "Voice disconnected. Your work is still here.",
        recoverable: true,
      }),
    }),
    toggleMute: assign({ muted: ({ context }) => !context.muted }),
    updateCandidate: assign(({ context, event }) => {
      if (event.type !== "CANDIDATE_CHANGED") return {};
      const question =
        context.assignment?.questions[context.activeQuestionIndex];
      if (!question) return {};
      const changed = context.candidate?.text !== event.value;
      const origin = context.candidate
        ? changed
          ? "student_edited"
          : context.candidate.origin
        : context.path === "guided"
          ? "student_after_guidance"
          : "student_verbatim";
      return {
        candidate: candidateFor(
          question.id,
          event.value,
          origin,
          (context.candidate?.version ?? 0) + (changed ? 1 : 0),
        ),
        review: null,
        suggestion: null,
        originalCandidate: null,
        rephraseId: null,
        error: null,
        voiceState: "captured" as const,
      };
    }),
    setPersistedCandidate: assign(({ context, event }) =>
      event.type === "CANDIDATE_PERSISTED"
        ? {
            candidate: event.candidate,
            assignment: context.assignment
              ? { ...context.assignment, version: event.version }
              : null,
            review: null,
            error: null,
          }
        : {},
    ),
    captureVoiceCandidate: assign(({ context, event }) => {
      if (event.type !== "VOICE_CAPTURED") return {};
      const question =
        context.assignment?.questions[context.activeQuestionIndex];
      if (!question) return {};
      return {
        candidate: candidateFor(
          question.id,
          event.text,
          context.path === "guided"
            ? "student_after_guidance"
            : "student_normalized",
          (context.candidate?.version ?? 0) + 1,
        ),
        review: null,
        originalCandidate: null,
        suggestion: null,
        rephraseId: null,
        voiceState: "captured" as const,
        error: null,
      };
    }),
    appendStudentTurn: assign(({ context, event }) =>
      event.type === "GUIDED_STUDENT_TURN"
        ? {
            guidedTurns: [
              ...context.guidedTurns,
              {
                id: `turn_${context.guidedTurns.length + 1}`,
                speaker: "student" as const,
                text: event.text,
              },
            ],
          }
        : {},
    ),
    appendClarosTurn: assign(({ context, event }) =>
      event.type === "GUIDED_REPLY"
        ? {
            guidedTurns: [
              ...context.guidedTurns,
              {
                id: `turn_${context.guidedTurns.length + 1}`,
                speaker: "claros" as const,
                text: event.text,
              },
            ],
            voiceState: "ready" as const,
          }
        : {},
    ),
    setRephrase: assign(({ context, event }) => {
      if (event.type !== "REPHRASE_READY" || !context.candidate) return {};
      return {
        originalCandidate: event.original ?? context.candidate,
        suggestion:
          event.suggestion ??
          candidateFor(
            context.candidate.questionId,
            event.text,
            "claros_rephrase",
            context.candidate.version + 1,
          ),
        rephraseId: event.rephraseId ?? null,
        assignment:
          event.version && context.assignment
            ? { ...context.assignment, version: event.version }
            : context.assignment,
        error: null,
      };
    }),
    setServerReview: assign(({ context, event }) =>
      event.type === "REVIEW_READY"
        ? {
            candidate: event.candidate,
            review: event.review,
            originalCandidate: null,
            suggestion: null,
            rephraseId: null,
            assignment: context.assignment
              ? { ...context.assignment, version: event.version }
              : null,
            error: null,
          }
        : {},
    ),
    selectOriginalAndReview: assign(({ context }) => {
      const selected = context.originalCandidate ?? context.candidate;
      if (!selected) return {};
      return {
        candidate: selected,
        review: createReview(context, selected),
        suggestion: context.suggestion,
      };
    }),
    selectSuggestionAndReview: assign(({ context }) => {
      if (!context.suggestion) return {};
      return {
        candidate: context.suggestion,
        review: createReview(context, context.suggestion),
      };
    }),
    createCurrentReview: assign(({ context }) =>
      context.candidate
        ? { review: createReview(context, context.candidate), error: null }
        : {},
    ),
    clearReview: assign({ review: () => null, error: () => null }),
    confirmCurrentAnswer: assign(({ context, event }) => {
      const candidate = context.candidate;
      const question =
        context.assignment?.questions[context.activeQuestionIndex];
      if (!candidate || !question) return {};
      const previous = context.confirmedAnswers[question.id];
      const confirmed =
        event.type === "CONFIRM_SUCCEEDED" && event.answer
          ? event.answer
          : {
              questionId: question.id,
              revision: (previous?.revision ?? 0) + 1,
              text: candidate.text,
              origin: candidate.origin,
              placement: question.placement,
            };
      return {
        confirmedAnswers: {
          ...context.confirmedAnswers,
          [question.id]: confirmed,
        },
        assignment: context.assignment
          ? {
              ...context.assignment,
              version:
                event.type === "CONFIRM_SUCCEEDED" && event.version
                  ? event.version
                  : context.assignment.version + 1,
            }
          : null,
        error: null,
      };
    }),
    continueToNext: assign(({ context }) => ({
      activeQuestionIndex: Math.min(
        context.activeQuestionIndex + 1,
        Math.max((context.assignment?.questions.length ?? 1) - 1, 0),
      ),
      path: null,
      candidate: null,
      originalCandidate: null,
      suggestion: null,
      rephraseId: null,
      review: null,
      guidedTurns: [],
      voiceState: "ready" as const,
      muted: false,
      error: null,
    })),
    goToQuestion: assign(({ context, event }) => {
      if (event.type !== "GO_TO_QUESTION") return {};
      const index =
        context.assignment?.questions.findIndex(
          (question) => question.id === event.questionId,
        ) ?? -1;
      return index < 0
        ? {}
        : {
            activeQuestionIndex: index,
            path: null,
            candidate: null,
            originalCandidate: null,
            suggestion: null,
            rephraseId: null,
            review: null,
            guidedTurns: [],
            voiceState: "ready" as const,
            error: null,
          };
    }),
    beginRevision: assign(({ context, event }) => {
      if (event.type !== "EDIT_ANSWER") return {};
      const index =
        context.assignment?.questions.findIndex(
          (question) => question.id === event.questionId,
        ) ?? -1;
      const answer = context.confirmedAnswers[event.questionId];
      if (index < 0 || !answer) return {};
      return {
        activeQuestionIndex: index,
        path: "direct" as const,
        candidate: candidateFor(
          event.questionId,
          answer.text,
          "student_edited",
          answer.revision + 1,
        ),
        originalCandidate: null,
        suggestion: null,
        rephraseId: null,
        review: null,
        guidedTurns: [],
        voiceState: "captured" as const,
        error: null,
      };
    }),
    applyServerRevision: assign(({ context, event }) => {
      if (event.type !== "REVISION_READY") return {};
      const index =
        context.assignment?.questions.findIndex(
          (question) => question.id === event.questionId,
        ) ?? -1;
      const answer = context.confirmedAnswers[event.questionId];
      if (index < 0 || !answer) return {};
      return {
        activeQuestionIndex: index,
        path: "direct" as const,
        candidate: candidateFor(
          event.questionId,
          event.editSeed,
          "student_edited",
          answer.revision + 1,
        ),
        assignment: context.assignment
          ? { ...context.assignment, version: event.version }
          : null,
        originalCandidate: null,
        suggestion: null,
        rephraseId: null,
        review: null,
        guidedTurns: [],
        voiceState: "captured" as const,
        error: null,
      };
    }),
    setExportResult: assign(({ context, event }) =>
      event.type === "EXPORT_SUCCEEDED" || event.type === "EXPORT_RESTORED"
        ? {
            exportResult: event.result,
            assignment:
              event.version && context.assignment
                ? { ...context.assignment, version: event.version }
                : context.assignment,
            error: null,
          }
        : {},
    ),
    setExportPending: assign(({ context, event }) =>
      event.type === "EXPORT_PENDING"
        ? {
            exportResult: null,
            assignment:
              event.version && context.assignment
                ? { ...context.assignment, version: event.version }
                : context.assignment,
            error: null,
          }
        : {},
    ),
    setExportError: assign(({ context, event }) =>
      event.type === "EXPORT_FAILED"
        ? {
            error: event.error,
            exportResult: null,
            assignment:
              event.version && context.assignment
                ? { ...context.assignment, version: event.version }
                : context.assignment,
          }
        : {},
    ),
    clearError: assign({ error: () => null }),
    clearExportError: assign({ error: () => null }),
    openAssignmentRoute: assign(({ context }) => ({
      ...context,
      assignment: context.assignment ?? cloneAssignment(),
      activeQuestionIndex: context.assignment ? context.activeQuestionIndex : 0,
      path: null,
      candidate: null,
      originalCandidate: null,
      suggestion: null,
      rephraseId: null,
      review: null,
      guidedTurns: [],
      voiceState: "ready" as const,
      error: null,
      exportResult: null,
    })),
    openReviewRoute: assign(({ context }) => ({
      ...context,
      error: null,
    })),
    openExportRoute: assign(({ context }) => ({
      ...context,
      error: null,
    })),
  },
}).createMachine({
  id: "claros-v2-workspace",
  initial: "upload",
  context: createInitialWorkspaceContext,
  on: {
    RESET: { target: ".upload", actions: "clearForAnalysis" },
    OPEN_ASSIGNMENT_ROUTE: {
      target: ".questionChoice",
      actions: "openAssignmentRoute",
    },
    OPEN_REVIEW_ROUTE: {
      target: ".worksheetReview",
      actions: "openReviewRoute",
    },
    OPEN_EXPORT_ROUTE: {
      target: ".exportComplete",
      actions: "openExportRoute",
    },
    LOAD_FIXTURE_SCENARIO: fixtureTransitions,
    REQUEST_FAILED: { actions: "setError" },
    CANDIDATE_PERSISTED: { actions: "setPersistedCandidate" },
    REVIEW_READY: { target: ".exactReview", actions: "setServerReview" },
    REVISION_READY: {
      target: ".direct.captured",
      actions: "applyServerRevision",
    },
    EXPORT_RESTORED: {
      target: ".exportComplete",
      actions: "setExportResult",
    },
    EXPORT_PENDING: {
      target: ".exporting",
      actions: "setExportPending",
    },
    EXPORT_FAILED: {
      target: ".exportFailed",
      actions: "setExportError",
    },
    VOICE_STATE_CHANGED: { actions: "setReportedVoiceState" },
  },
  states: {
    upload: {
      id: "claros-v2-upload",
      on: {
        START_ANALYSIS: { target: "checking", actions: "clearForAnalysis" },
      },
    },
    checking: {
      id: "claros-v2-checking",
      on: {
        ANALYSIS_READY: { target: "ready", actions: "setAnalysisReady" },
        ANALYSIS_FAILED: { target: "rejected", actions: "setError" },
      },
    },
    rejected: {
      id: "claros-v2-rejected",
      on: {
        START_ANALYSIS: { target: "checking", actions: "clearForAnalysis" },
      },
    },
    ready: {
      id: "claros-v2-ready",
      on: { START_QUESTION: "questionChoice" },
    },
    questionChoice: {
      id: "claros-v2-question-choice",
      on: {
        CHOOSE_DIRECT: { target: "direct", actions: "chooseDirect" },
        TYPE_INSTEAD: { target: "direct.captured", actions: "chooseDirect" },
        CHOOSE_GUIDED: { target: "guided", actions: "chooseGuided" },
        OPEN_WORKSHEET_REVIEW: "worksheetReview",
      },
    },
    direct: {
      initial: "ready",
      states: {
        ready: {
          on: {
            VOICE_START: { target: "listening", actions: "setVoiceListening" },
            CANDIDATE_CHANGED: {
              target: "captured",
              actions: "updateCandidate",
            },
            MICROPHONE_UNAVAILABLE: {
              target: "voiceUnavailable",
              actions: "setMicrophoneUnavailable",
            },
          },
        },
        listening: {
          id: "claros-v2-direct-listening",
          on: {
            VOICE_CAPTURED: {
              target: "captured",
              actions: "captureVoiceCandidate",
            },
            CANDIDATE_CHANGED: {
              target: "captured",
              actions: "updateCandidate",
            },
            MICROPHONE_UNAVAILABLE: {
              target: "voiceUnavailable",
              actions: "setMicrophoneUnavailable",
            },
            VOICE_DISCONNECTED: {
              target: "voiceUnavailable",
              actions: "setVoiceDisconnected",
            },
          },
        },
        captured: {
          id: "claros-v2-direct-captured",
          on: {
            VOICE_START: { target: "listening", actions: "setVoiceListening" },
            CANDIDATE_CHANGED: { actions: "updateCandidate" },
            MICROPHONE_UNAVAILABLE: {
              target: "voiceUnavailable",
              actions: "setMicrophoneUnavailable",
            },
            VOICE_DISCONNECTED: {
              target: "voiceUnavailable",
              actions: "setVoiceDisconnected",
            },
          },
        },
        voiceUnavailable: {
          id: "claros-v2-direct-voice-unavailable",
          on: {
            RETRY_VOICE: { target: "ready", actions: "setVoiceReady" },
            CONTINUE_BY_TYPING: { target: "captured" },
            CANDIDATE_CHANGED: {
              target: "captured",
              actions: "updateCandidate",
            },
          },
        },
      },
      on: {
        TOGGLE_MUTE: { actions: "toggleMute" },
        INTERRUPT: { actions: "setVoiceInterrupted" },
        REQUEST_REPHRASE: {
          guard: "hasCandidate",
          target: "rephrasing",
        },
        REQUEST_REVIEW: {
          guard: "hasCandidate",
          target: "exactReview",
          actions: "createCurrentReview",
        },
      },
    },
    guided: {
      initial: "ready",
      states: {
        ready: {
          id: "claros-v2-guided-ready",
          on: {
            VOICE_START: { target: "listening", actions: "setVoiceListening" },
            GUIDED_STUDENT_TURN: {
              target: "thinking",
              actions: ["appendStudentTurn", "setVoiceThinking"],
            },
            GUIDED_READY_TO_ANSWER: "finalizing",
            MICROPHONE_UNAVAILABLE: {
              target: "voiceUnavailable",
              actions: "setMicrophoneUnavailable",
            },
          },
        },
        listening: {
          on: {
            GUIDED_STUDENT_TURN: {
              target: "thinking",
              actions: ["appendStudentTurn", "setVoiceThinking"],
            },
            VOICE_DISCONNECTED: {
              target: "voiceUnavailable",
              actions: "setVoiceDisconnected",
            },
          },
        },
        thinking: {
          on: {
            GUIDED_REPLY: {
              target: "ready",
              actions: "appendClarosTurn",
            },
            VOICE_DISCONNECTED: {
              target: "voiceUnavailable",
              actions: "setVoiceDisconnected",
            },
          },
        },
        speaking: {
          on: {
            INTERRUPT: { target: "ready", actions: "setVoiceInterrupted" },
            VOICE_STATE_CHANGED: [
              {
                guard: "reportedVoiceIsReady",
                target: "ready",
                actions: "setReportedVoiceState",
              },
              { actions: "setReportedVoiceState" },
            ],
            GUIDED_READY_TO_ANSWER: "finalizing",
          },
        },
        finalizing: {
          on: {
            CANDIDATE_CHANGED: { actions: "updateCandidate" },
            VOICE_CAPTURED: { actions: "captureVoiceCandidate" },
          },
        },
        voiceUnavailable: {
          on: {
            RETRY_VOICE: { target: "ready", actions: "setVoiceReady" },
            CONTINUE_BY_TYPING: { target: "finalizing" },
            GUIDED_READY_TO_ANSWER: "finalizing",
            CANDIDATE_CHANGED: {
              target: "finalizing",
              actions: "updateCandidate",
            },
          },
        },
      },
      on: {
        TOGGLE_MUTE: { actions: "toggleMute" },
        VOICE_SPEAKING: { target: ".speaking", actions: "setVoiceSpeaking" },
        MICROPHONE_UNAVAILABLE: {
          target: ".voiceUnavailable",
          actions: "setMicrophoneUnavailable",
        },
        VOICE_DISCONNECTED: {
          target: ".voiceUnavailable",
          actions: "setVoiceDisconnected",
        },
        CANDIDATE_CHANGED: {
          target: ".finalizing",
          actions: "updateCandidate",
        },
        REQUEST_REPHRASE: {
          guard: "hasCandidate",
          target: "rephrasing",
        },
        REQUEST_REVIEW: {
          guard: "hasCandidate",
          target: "exactReview",
          actions: "createCurrentReview",
        },
      },
    },
    rephrasing: {
      on: {
        REPHRASE_READY: { target: "comparison", actions: "setRephrase" },
        REPHRASE_FAILED: { actions: "setError" },
        REQUEST_REPHRASE: { actions: "clearError" },
        KEEP_MY_WORDING: {
          target: "exactReview",
          actions: "createCurrentReview",
        },
      },
    },
    comparison: {
      id: "claros-v2-comparison",
      on: {
        KEEP_MY_WORDING: {
          target: "exactReview",
          actions: "selectOriginalAndReview",
        },
        USE_SUGGESTION: {
          target: "exactReview",
          actions: "selectSuggestionAndReview",
        },
        CHANGE_ANSWER: [
          {
            guard: "cameFromGuided",
            target: "guided.finalizing",
            actions: "clearReview",
          },
          { target: "direct.captured", actions: "clearReview" },
        ],
      },
    },
    exactReview: {
      id: "claros-v2-exact-review",
      on: {
        CHANGE_ANSWER: [
          {
            guard: "cameFromGuided",
            target: "guided.finalizing",
            actions: "clearReview",
          },
          { target: "direct.captured", actions: "clearReview" },
        ],
        CONFIRM: { guard: "hasCurrentReview", target: "confirming" },
        VOICE_CONFIRMATION: {
          guard: "hasCurrentExactVoiceConfirmation",
          target: "confirming",
        },
      },
    },
    confirming: {
      on: {
        CONFIRM_SUCCEEDED: {
          target: "answerAdded",
          actions: "confirmCurrentAnswer",
        },
        CONFIRM_FAILED: { target: "exactReview", actions: "setError" },
      },
    },
    answerAdded: {
      id: "claros-v2-answer-added",
      on: {
        CONTINUE_TO_NEXT: [
          {
            guard: "hasNextQuestion",
            target: "questionChoice",
            actions: "continueToNext",
          },
          { target: "worksheetReview" },
        ],
        CHANGE_ANSWER: [
          {
            guard: "cameFromGuided",
            target: "guided.finalizing",
            actions: "clearReview",
          },
          { target: "direct.captured", actions: "clearReview" },
        ],
        OPEN_WORKSHEET_REVIEW: "worksheetReview",
      },
    },
    worksheetReview: {
      id: "claros-v2-worksheet-review",
      on: {
        GO_TO_QUESTION: { target: "questionChoice", actions: "goToQuestion" },
        EDIT_ANSWER: { target: "direct.captured", actions: "beginRevision" },
        CREATE_EXPORT: {
          guard: "hasConfirmedAnswer",
          target: "exporting",
          actions: "clearExportError",
        },
      },
    },
    exporting: {
      id: "claros-v2-exporting",
      on: {
        EXPORT_SUCCEEDED: {
          target: "exportComplete",
          actions: "setExportResult",
        },
      },
    },
    exportFailed: {
      id: "claros-v2-export-failed",
      on: {
        RETRY_EXPORT: { target: "exporting", actions: "clearExportError" },
        REVIEW_ANSWERS: "worksheetReview",
      },
    },
    exportComplete: {
      id: "claros-v2-export-complete",
      on: { REVIEW_ANSWERS: "worksheetReview" },
    },
  },
});

export const fixtureMachineValues: Record<FixtureScenario, string> =
  Object.fromEntries(
    fixtureScenarios.map((scenario) => [scenario, scenarioTarget(scenario)]),
  ) as Record<FixtureScenario, string>;

export const fixtureRephraseText = directSuggestionText;
export const fixtureGuidedCandidateText = guidedCandidateText;
export const fixtureExport = fixtureExportResult;
