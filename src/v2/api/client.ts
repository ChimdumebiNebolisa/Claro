import type { components } from "./generated";
import type {
  Assignment,
  Candidate,
  ConfirmedAnswer,
  ExportResult,
  RecoverableError,
  ReviewSnapshot,
} from "../domain/contracts";

type ApiSchemas = components["schemas"];
export type ApiAssignment = ApiSchemas["AssignmentResponse"];
export type ApiCandidate = ApiSchemas["Candidate"];
export type ApiCandidateRequest = ApiSchemas["CandidateRequest"];
export type ApiReview = ApiSchemas["ReviewResponse"];
export type ApiConfirmation = ApiSchemas["ConfirmResponse"];
export type ApiRevision = ApiSchemas["BeginRevisionResponse"];
export type ApiExport = ApiSchemas["ExportResponse"];
export type ApiRephrase = ApiSchemas["RephraseResponse"];

export class ClarosApiError extends Error {
  readonly detail: RecoverableError;
  readonly version?: number;
  readonly status: number;

  constructor(
    detail: RecoverableError,
    status: number,
    version?: number | null,
  ) {
    super(detail.message);
    this.name = "ClarosApiError";
    this.detail = detail;
    this.status = status;
    this.version = version ?? undefined;
  }
}

const fallbackError: RecoverableError = {
  code: "request_failed",
  message: "Claros could not complete that action. Try again.",
  recoverable: true,
};

async function requestJson<T>(
  input: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, {
      ...init,
      credentials: "same-origin",
      headers:
        init.body instanceof FormData
          ? init.headers
          : { "content-type": "application/json", ...init.headers },
    });
  } catch (error) {
    if (
      typeof error === "object" &&
      error !== null &&
      "name" in error &&
      error.name === "AbortError"
    ) {
      throw error;
    }
    throw new ClarosApiError(fallbackError, 0);
  }

  const payload = (await response.json().catch(() => null)) as
    T | ApiSchemas["ErrorEnvelope"] | null;
  if (!response.ok) {
    if (
      payload &&
      typeof payload === "object" &&
      "error" in payload &&
      payload.error
    ) {
      throw new ClarosApiError(payload.error, response.status, payload.version);
    }
    throw new ClarosApiError(fallbackError, response.status);
  }
  if (payload === null)
    throw new ClarosApiError(fallbackError, response.status);
  return payload as T;
}

export const toRecoverableError = (error: unknown): RecoverableError =>
  error instanceof ClarosApiError ? error.detail : fallbackError;

export const mapCandidate = (candidate: ApiCandidate): Candidate => ({
  id: candidate.candidate_id,
  version: candidate.candidate_version,
  questionId: candidate.question_id,
  text: candidate.text,
  origin: candidate.origin,
});

const mapConfirmedAnswer = (
  answer: ApiSchemas["ConfirmedAnswer"],
): ConfirmedAnswer => ({
  questionId: answer.question_id,
  revision: answer.revision,
  text: answer.exact_text,
  origin: answer.origin,
  placement: answer.placement,
});

export type HydratedAssignment = {
  assignment: Assignment;
  confirmedAnswers: Readonly<Record<string, ConfirmedAnswer>>;
  activeQuestionIndex: number;
  candidate: Candidate | null;
  status: ApiAssignment["status"];
};

export function mapAssignment(payload: ApiAssignment): HydratedAssignment {
  if (payload.status !== "ready" || payload.source.page_count == null) {
    throw new ClarosApiError(
      {
        code: "invalid_assignment_state",
        message: "This worksheet is not ready to answer yet.",
        recoverable: true,
      },
      409,
      payload.version,
    );
  }
  const confirmedAnswers: Record<string, ConfirmedAnswer> = {};
  const questionPayloads = payload.questions ?? [];
  const questions = questionPayloads.map((question) => {
    if (question.confirmed_answer) {
      confirmedAnswers[question.question_id] = mapConfirmedAnswer(
        question.confirmed_answer,
      );
    }
    return {
      id: question.question_id,
      index: question.index,
      prompt: question.prompt,
      instruction: question.instruction ?? "",
      pageNumber: question.page_number,
      placement:
        question.placement_capability === "inline_possible"
          ? ("inline" as const)
          : ("appendix" as const),
    };
  });
  let activeQuestionIndex = questionPayloads.findIndex(
    (question) => question.candidate && !question.confirmed_answer,
  );
  if (activeQuestionIndex < 0) {
    activeQuestionIndex = questionPayloads.findIndex(
      (question) => !question.confirmed_answer,
    );
  }
  if (activeQuestionIndex < 0) activeQuestionIndex = 0;
  const activeQuestionPayload = questionPayloads[activeQuestionIndex];
  const activeCandidate = activeQuestionPayload?.confirmed_answer
    ? null
    : activeQuestionPayload?.candidate;

  return {
    assignment: {
      id: payload.assignment_id,
      version: payload.version,
      title: payload.title,
      filename: payload.source.filename,
      pageCount: payload.source.page_count,
      questions,
      warnings: payload.warnings?.map((warning) => warning.message) ?? [],
    },
    confirmedAnswers,
    activeQuestionIndex,
    candidate: activeCandidate ? mapCandidate(activeCandidate) : null,
    status: payload.status,
  };
}

export async function createAssignment(input: {
  file?: File;
  sampleId?: string;
}): Promise<ApiAssignment> {
  const form = new FormData();
  if (input.file) form.set("file", input.file, input.file.name);
  if (input.sampleId) form.set("sample_id", input.sampleId);
  return requestJson<ApiAssignment>("/api/v2/assignments", {
    method: "POST",
    body: form,
  });
}

export const getAssignment = (assignmentId: string, signal?: AbortSignal) =>
  requestJson<ApiAssignment>(
    `/api/v2/assignments/${encodeURIComponent(assignmentId)}`,
    { signal },
  );

export async function createCandidate(
  assignmentId: string,
  questionId: string,
  body: ApiCandidateRequest,
): Promise<{ version: number; candidate: Candidate }> {
  const payload = await requestJson<ApiSchemas["CandidateResponse"]>(
    `/api/v2/assignments/${encodeURIComponent(assignmentId)}/questions/${encodeURIComponent(questionId)}/candidates`,
    { method: "POST", body: JSON.stringify(body) },
  );
  return {
    version: payload.version,
    candidate: mapCandidate(payload.candidate),
  };
}

export const requestRephrase = (
  assignmentId: string,
  questionId: string,
  body: ApiSchemas["RephraseRequest"],
) =>
  requestJson<ApiRephrase>(
    `/api/v2/assignments/${encodeURIComponent(assignmentId)}/questions/${encodeURIComponent(questionId)}/rephrase`,
    { method: "POST", body: JSON.stringify(body) },
  );

export async function createReview(
  assignmentId: string,
  questionId: string,
  body: ApiSchemas["ReviewRequest"],
): Promise<{ version: number; candidate: Candidate; review: ReviewSnapshot }> {
  const payload = await requestJson<ApiReview>(
    `/api/v2/assignments/${encodeURIComponent(assignmentId)}/questions/${encodeURIComponent(questionId)}/review`,
    { method: "POST", body: JSON.stringify(body) },
  );
  const candidate = mapCandidate(payload.candidate);
  return {
    version: payload.version,
    candidate,
    review: {
      token: payload.review_token,
      expiresAt: payload.expires_at,
      questionId: payload.question_id,
      candidateId: candidate.id,
      candidateVersion: candidate.version,
      exactText: candidate.text,
      placement: payload.placement,
      assignmentVersion: payload.version,
    },
  };
}

export async function confirmAnswer(
  assignmentId: string,
  questionId: string,
  body: ApiSchemas["ConfirmRequest"],
): Promise<{ version: number; answer: ConfirmedAnswer }> {
  const payload = await requestJson<ApiConfirmation>(
    `/api/v2/assignments/${encodeURIComponent(assignmentId)}/questions/${encodeURIComponent(questionId)}/confirm`,
    { method: "POST", body: JSON.stringify(body) },
  );
  return {
    version: payload.version,
    answer: mapConfirmedAnswer(payload.confirmed_answer),
  };
}

export const beginRevision = (
  assignmentId: string,
  questionId: string,
  assignmentVersion: number,
) =>
  requestJson<ApiRevision>(
    `/api/v2/assignments/${encodeURIComponent(assignmentId)}/questions/${encodeURIComponent(questionId)}/answer`,
    {
      method: "PATCH",
      body: JSON.stringify({ assignment_version: assignmentVersion }),
    },
  );

const sizeLabel = (sizeBytes: number | null | undefined) =>
  sizeBytes
    ? new Intl.NumberFormat(undefined, {
        style: "unit",
        unit: sizeBytes >= 1024 * 1024 ? "megabyte" : "kilobyte",
        maximumFractionDigits: 1,
      }).format(sizeBytes / (sizeBytes >= 1024 * 1024 ? 1024 * 1024 : 1024))
    : "PDF";

export const mapExport = (
  payload: ApiExport,
  assignmentId: string,
): ExportResult => ({
  id: payload.export_id,
  filename: payload.filename,
  sizeLabel: sizeLabel(payload.size_bytes),
  downloadUrl: `/api/v2/assignments/${encodeURIComponent(assignmentId)}/exports/${encodeURIComponent(payload.export_id)}/download`,
});

export type MappedExportState =
  | {
      kind: "creating";
      exportId: string;
      version: number;
    }
  | {
      kind: "failed";
      exportId: string;
      version: number;
      error: RecoverableError;
    }
  | {
      kind: "complete";
      version: number;
      result: ExportResult;
    };

export function mapExportState(
  payload: ApiExport,
  assignmentId: string,
): MappedExportState {
  if (payload.status === "complete") {
    return {
      kind: "complete",
      version: payload.version,
      result: mapExport(payload, assignmentId),
    };
  }
  if (payload.status === "failed") {
    return {
      kind: "failed",
      exportId: payload.export_id,
      version: payload.version,
      error: payload.failure ?? {
        code: "export_failed",
        message: "The completed PDF could not be prepared. Try again.",
        recoverable: true,
      },
    };
  }
  return {
    kind: "creating",
    exportId: payload.export_id,
    version: payload.version,
  };
}

export const createExport = (
  assignmentId: string,
  assignmentVersion: number,
  idempotencyKey: string,
) =>
  requestJson<ApiExport>(
    `/api/v2/assignments/${encodeURIComponent(assignmentId)}/exports`,
    {
      method: "POST",
      body: JSON.stringify({
        assignment_version: assignmentVersion,
        idempotency_key: idempotencyKey,
      }),
    },
  );

export const getExport = (
  assignmentId: string,
  exportId: string,
  signal?: AbortSignal,
) =>
  requestJson<ApiExport>(
    `/api/v2/assignments/${encodeURIComponent(assignmentId)}/exports/${encodeURIComponent(exportId)}`,
    { signal },
  );
