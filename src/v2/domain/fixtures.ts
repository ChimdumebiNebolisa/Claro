import type {
  Assignment,
  Candidate,
  ConfirmedAnswer,
  ConversationTurn,
  ExportResult,
} from "./contracts";

export const fixtureAssignment: Assignment = {
  id: "fixture-biology",
  version: 2,
  title: "Photosynthesis and plant cells",
  filename: "biology-short-answer.pdf",
  pageCount: 1,
  questions: [
    {
      id: "q_01",
      index: 1,
      prompt: "Why do plants need sunlight?",
      instruction: "Use evidence from the lesson in one or two sentences.",
      pageNumber: 1,
      placement: "inline",
    },
    {
      id: "q_02",
      index: 2,
      prompt: "How does sunlight help a plant make food?",
      instruction: "Describe the role of sunlight in your own words.",
      pageNumber: 1,
      placement: "inline",
    },
    {
      id: "q_03",
      index: 3,
      prompt: "How can photosynthesis support other living things?",
      instruction: "Give one clear connection to another living thing.",
      pageNumber: 1,
      placement: "appendix",
    },
  ],
};

export const directCandidateText =
  "Plants need sunlight because it helps them make their food.";
export const directSuggestionText =
  "Plants use sunlight to make food through photosynthesis.";
export const guidedCandidateText =
  "Sunlight gives a plant the energy it needs to make food from water and carbon dioxide.";
export const appendixCandidateText =
  "Photosynthesis supports other living things by making oxygen and by helping plants grow into food for animals.";

export const fixtureGuidedTurns: readonly ConversationTurn[] = [
  {
    id: "turn_01",
    speaker: "student",
    text: "I know sunlight matters, but I am not sure how to explain it.",
  },
  {
    id: "turn_02",
    speaker: "claros",
    text: "What does sunlight provide that helps the plant make food?",
  },
  {
    id: "turn_03",
    speaker: "student",
    text: "It gives the plant energy for the process.",
  },
  {
    id: "turn_04",
    speaker: "claros",
    text: "Good. State your final answer in your own words.",
  },
];

export function candidateFor(
  questionId: string,
  text: string,
  origin: Candidate["origin"],
  version = 1,
): Candidate {
  return {
    id: `candidate_${questionId}`,
    version,
    questionId,
    text,
    origin,
  };
}

export const fixtureConfirmedAnswer: ConfirmedAnswer = {
  questionId: "q_01",
  revision: 1,
  text: directCandidateText,
  origin: "student_normalized",
  placement: "inline",
};

export const fixtureAppendixAnswer: ConfirmedAnswer = {
  questionId: "q_03",
  revision: 1,
  text: appendixCandidateText,
  origin: "student_after_guidance",
  placement: "appendix",
};

export const fixtureExportResult: ExportResult = {
  id: "export_fixture_01",
  filename: "biology-short-answer-completed.pdf",
  sizeLabel: "5 KB",
  downloadUrl: "/api/v2/fixtures/biology/export",
};
