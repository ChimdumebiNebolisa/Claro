export const candidateOrigins = [
  "student_verbatim",
  "student_normalized",
  "claros_rephrase",
  "student_after_guidance",
  "student_edited",
] as const;

export const CANONICAL_CONFIRMATION_PHRASE = "Use this exact answer";

export type CandidateOrigin = (typeof candidateOrigins)[number];
export type StudentAttribution = "Your words" | "Suggested wording";
export type AnswerPath = "direct" | "guided";
export type PlacementKind = "inline" | "appendix";
export type VoiceState =
  | "ready"
  | "listening"
  | "captured"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "microphone_unavailable"
  | "disconnected";

export type Question = {
  id: string;
  index: number;
  prompt: string;
  instruction: string;
  pageNumber: number;
  placement: PlacementKind;
};

export type Assignment = {
  id: string;
  version: number;
  title: string;
  filename: string;
  pageCount: number;
  questions: readonly Question[];
  warnings?: readonly string[];
};

export type Candidate = {
  id: string;
  version: number;
  questionId: string;
  text: string;
  origin: CandidateOrigin;
};

export type ConversationTurn = {
  id: string;
  speaker: "student" | "claros";
  text: string;
};

export type ReviewSnapshot = {
  token: string;
  expiresAt: string;
  questionId: string;
  candidateId: string;
  candidateVersion: number;
  exactText: string;
  placement: PlacementKind;
  assignmentVersion: number;
};

export type ConfirmedAnswer = {
  questionId: string;
  revision: number;
  text: string;
  origin: CandidateOrigin;
  placement: PlacementKind;
};

export type ExportResult = {
  id: string;
  filename: string;
  sizeLabel: string;
  downloadUrl: string;
};

export type RecoverableError = {
  code: string;
  message: string;
  recoverable: boolean;
};

export const attributionForOrigin = (
  origin: CandidateOrigin,
): StudentAttribution =>
  origin === "claros_rephrase" ? "Suggested wording" : "Your words";

export const destinationCopy = (placement: PlacementKind) =>
  placement === "inline"
    ? "Your answer fits on the original worksheet."
    : "This answer will appear on an attached answer page.";

export const answerAddedCopy = (placement: PlacementKind) =>
  placement === "inline"
    ? "Answer added to the worksheet."
    : "Answer added to the attached answer page.";
