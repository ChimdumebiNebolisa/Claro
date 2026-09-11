import { createActor } from "xstate";
import { describe, expect, it } from "vitest";
import {
  fixtureExport,
  fixtureRephraseText,
  workspaceMachine,
} from "../src/v2/domain/workspaceMachine";

const startAssignment = () => {
  const actor = createActor(workspaceMachine).start();
  actor.send({ type: "OPEN_ASSIGNMENT_ROUTE" });
  return actor;
};

describe("Claros V2 workspace machine", () => {
  it("preserves exact Unicode and makes exact review unavoidable", () => {
    const actor = startAssignment();
    const exact = "  Café’s leaves use CO₂ — not ASCII.\nSecond line.  ";

    actor.send({ type: "TYPE_INSTEAD" });
    actor.send({ type: "CANDIDATE_CHANGED", value: exact });
    actor.send({ type: "CONFIRM" });
    expect(actor.getSnapshot().matches({ direct: "captured" })).toBe(true);
    expect(actor.getSnapshot().context.confirmedAnswers).toEqual({});
    expect(actor.getSnapshot().context.candidate?.text).toBe(exact);

    actor.send({ type: "REQUEST_REVIEW" });
    expect(actor.getSnapshot().matches("exactReview")).toBe(true);
    expect(actor.getSnapshot().context.review?.exactText).toBe(exact);
    actor.send({ type: "CONFIRM" });
    expect(actor.getSnapshot().matches("confirming")).toBe(true);
    actor.send({ type: "CONFIRM_SUCCEEDED" });

    expect(actor.getSnapshot().matches("answerAdded")).toBe(true);
    expect(actor.getSnapshot().context.confirmedAnswers.q_01.text).toBe(exact);
    expect(actor.getSnapshot().context.assignment?.version).toBe(3);
    actor.stop();
  });

  it("accepts only the canonical voice phrase and only during exact review", () => {
    const actor = startAssignment();
    actor.send({ type: "CHOOSE_DIRECT" });
    actor.send({ type: "VOICE_START" });
    actor.send({
      type: "VOICE_CAPTURED",
      text: "Plants need sunlight to make food.",
    });

    actor.send({ type: "VOICE_CONFIRMATION", phrase: "Use this exact answer" });
    expect(actor.getSnapshot().matches({ direct: "captured" })).toBe(true);
    actor.send({ type: "REQUEST_REVIEW" });
    actor.send({ type: "VOICE_CONFIRMATION", phrase: "okay" });
    expect(actor.getSnapshot().matches("exactReview")).toBe(true);
    actor.send({
      type: "VOICE_CONFIRMATION",
      phrase: "Use this exact answer.",
    });
    expect(actor.getSnapshot().matches("exactReview")).toBe(true);
    actor.send({ type: "VOICE_CONFIRMATION", phrase: "Use this exact answer" });
    expect(actor.getSnapshot().matches("confirming")).toBe(true);
    actor.stop();
  });

  it("exposes speaking, interruption, and a deterministic return to ready", () => {
    const actor = startAssignment();
    actor.send({ type: "CHOOSE_GUIDED" });
    const preservedTurns = actor.getSnapshot().context.guidedTurns;

    actor.send({ type: "VOICE_SPEAKING" });
    expect(actor.getSnapshot().matches({ guided: "speaking" })).toBe(true);
    expect(actor.getSnapshot().context.voiceState).toBe("speaking");
    actor.send({ type: "INTERRUPT" });
    expect(actor.getSnapshot().matches({ guided: "ready" })).toBe(true);
    expect(actor.getSnapshot().context.voiceState).toBe("interrupted");
    expect(actor.getSnapshot().context.guidedTurns).toEqual(preservedTurns);

    actor.send({ type: "VOICE_START" });
    expect(actor.getSnapshot().matches({ guided: "listening" })).toBe(true);
    actor.send({
      type: "GUIDED_STUDENT_TURN",
      text: "Light gives the plant energy.",
    });
    actor.send({
      type: "GUIDED_REPLY",
      text: "Now say the complete answer in your words.",
    });
    actor.send({ type: "VOICE_SPEAKING" });
    actor.send({ type: "VOICE_STATE_CHANGED", state: "ready" });
    expect(actor.getSnapshot().matches({ guided: "ready" })).toBe(true);
    expect(actor.getSnapshot().context.voiceState).toBe("ready");
    actor.stop();
  });

  it("captures a guided voice answer only after the student enters finalizing", () => {
    const actor = startAssignment();
    actor.send({ type: "CHOOSE_GUIDED" });
    actor.send({
      type: "GUIDED_STUDENT_TURN",
      text: "Sunlight supplies energy.",
    });
    actor.send({
      type: "GUIDED_REPLY",
      text: "Use that idea in your final answer.",
    });
    actor.send({ type: "GUIDED_READY_TO_ANSWER" });
    actor.send({ type: "VOICE_STATE_CHANGED", state: "listening" });
    actor.send({
      type: "VOICE_CAPTURED",
      text: "Plants use sunlight as energy to make their own food.",
    });

    expect(actor.getSnapshot().matches({ guided: "finalizing" })).toBe(true);
    expect(actor.getSnapshot().context.candidate).toMatchObject({
      origin: "student_after_guidance",
      text: "Plants use sunlight as energy to make their own food.",
    });
    expect(actor.getSnapshot().context.voiceState).toBe("captured");
    actor.stop();
  });

  it("cannot double-confirm when a canonical voice event is replayed", () => {
    const actor = startAssignment();
    actor.send({ type: "TYPE_INSTEAD" });
    actor.send({
      type: "CANDIDATE_CHANGED",
      value: "Plants use light energy to make food.",
    });
    actor.send({ type: "REQUEST_REVIEW" });
    actor.send({ type: "VOICE_CONFIRMATION", phrase: "Use this exact answer" });
    actor.send({ type: "VOICE_CONFIRMATION", phrase: "Use this exact answer" });

    expect(actor.getSnapshot().matches("confirming")).toBe(true);
    expect(actor.getSnapshot().context.confirmedAnswers).toEqual({});
    actor.send({ type: "CONFIRM_SUCCEEDED" });
    expect(actor.getSnapshot().context.confirmedAnswers.q_01.revision).toBe(1);
    actor.send({ type: "CONFIRM_SUCCEEDED" });
    expect(actor.getSnapshot().context.confirmedAnswers.q_01.revision).toBe(1);
    actor.stop();
  });

  it("keeps both wording versions and requires explicit selection", () => {
    const actor = startAssignment();
    actor.send({ type: "TYPE_INSTEAD" });
    actor.send({
      type: "CANDIDATE_CHANGED",
      value: "Plants need sunlight because it helps them make their food.",
    });
    actor.send({ type: "REQUEST_REPHRASE" });
    expect(actor.getSnapshot().matches("rephrasing")).toBe(true);
    actor.send({ type: "REPHRASE_READY", text: fixtureRephraseText });

    const comparison = actor.getSnapshot();
    expect(comparison.matches("comparison")).toBe(true);
    expect(comparison.context.originalCandidate?.text).toContain("their food");
    expect(comparison.context.suggestion?.origin).toBe("claros_rephrase");
    expect(comparison.context.confirmedAnswers).toEqual({});

    actor.send({ type: "USE_SUGGESTION" });
    expect(actor.getSnapshot().matches("exactReview")).toBe(true);
    expect(actor.getSnapshot().context.candidate?.origin).toBe(
      "claros_rephrase",
    );
    expect(actor.getSnapshot().context.confirmedAnswers).toEqual({});
    actor.send({ type: "CHANGE_ANSWER" });
    actor.send({
      type: "CANDIDATE_CHANGED",
      value: `${fixtureRephraseText} Exactly.`,
    });
    expect(actor.getSnapshot().context.candidate?.origin).toBe(
      "student_edited",
    );
    expect(actor.getSnapshot().context.review).toBeNull();
    actor.stop();
  });

  it("keeps guided turns through voice failure and requires a final candidate", () => {
    const actor = startAssignment();
    actor.send({ type: "CHOOSE_GUIDED" });
    actor.send({
      type: "GUIDED_STUDENT_TURN",
      text: "I know sunlight gives the plant energy.",
    });
    const turnsBeforeDisconnect = actor.getSnapshot().context.guidedTurns;
    actor.send({ type: "VOICE_DISCONNECTED" });

    expect(actor.getSnapshot().context.guidedTurns).toEqual(
      turnsBeforeDisconnect,
    );
    expect(actor.getSnapshot().context.candidate).toBeNull();
    actor.send({ type: "REQUEST_REVIEW" });
    expect(actor.getSnapshot().matches({ guided: "voiceUnavailable" })).toBe(
      true,
    );

    actor.send({ type: "CONTINUE_BY_TYPING" });
    actor.send({
      type: "CANDIDATE_CHANGED",
      value: "Sunlight gives a plant energy to make food.",
    });
    expect(actor.getSnapshot().context.candidate?.origin).toBe(
      "student_after_guidance",
    );
    actor.send({ type: "REQUEST_REVIEW" });
    expect(actor.getSnapshot().matches("exactReview")).toBe(true);
    actor.stop();
  });

  it("recovers from guided microphone denial without losing conversation", () => {
    const actor = startAssignment();
    actor.send({ type: "CHOOSE_GUIDED" });
    const turnsBeforeDenial = actor.getSnapshot().context.guidedTurns;
    actor.send({ type: "VOICE_START" });
    actor.send({ type: "MICROPHONE_UNAVAILABLE" });

    expect(actor.getSnapshot().matches({ guided: "voiceUnavailable" })).toBe(
      true,
    );
    expect(actor.getSnapshot().context.voiceState).toBe(
      "microphone_unavailable",
    );
    expect(actor.getSnapshot().context.guidedTurns).toEqual(turnsBeforeDenial);
    actor.send({ type: "RETRY_VOICE" });
    expect(actor.getSnapshot().matches({ guided: "ready" })).toBe(true);
    expect(actor.getSnapshot().context.voiceState).toBe("ready");
    actor.stop();
  });

  it("does not invent a guided final answer when the student is ready", () => {
    const actor = startAssignment();
    actor.send({ type: "CHOOSE_GUIDED" });
    actor.send({
      type: "GUIDED_STUDENT_TURN",
      text: "I know sunlight gives the plant energy.",
    });
    actor.send({
      type: "GUIDED_REPLY",
      text: "How does the plant use that energy?",
    });
    actor.send({ type: "GUIDED_READY_TO_ANSWER" });

    expect(actor.getSnapshot().matches({ guided: "finalizing" })).toBe(true);
    expect(actor.getSnapshot().context.candidate).toBeNull();
    actor.send({ type: "REQUEST_REVIEW" });
    expect(actor.getSnapshot().matches({ guided: "finalizing" })).toBe(true);
    actor.stop();
  });

  it("preserves the original candidate when rephrasing fails", () => {
    const actor = startAssignment();
    const original = "Plants use light energy to make their own food.";
    actor.send({ type: "TYPE_INSTEAD" });
    actor.send({ type: "CANDIDATE_CHANGED", value: original });
    actor.send({ type: "REQUEST_REPHRASE" });
    actor.send({
      type: "REPHRASE_FAILED",
      error: {
        code: "rephrase_unavailable",
        message: "Suggested wording is unavailable right now.",
        recoverable: true,
      },
    });

    expect(actor.getSnapshot().matches("rephrasing")).toBe(true);
    expect(actor.getSnapshot().context.candidate?.text).toBe(original);
    expect(actor.getSnapshot().context.error?.code).toBe(
      "rephrase_unavailable",
    );
    actor.send({ type: "REQUEST_REPHRASE" });
    expect(actor.getSnapshot().context.error).toBeNull();
    actor.stop();
  });

  it("permits partial export but not export with zero confirmed answers", () => {
    const empty = startAssignment();
    empty.send({ type: "OPEN_WORKSHEET_REVIEW" });
    empty.send({ type: "CREATE_EXPORT" });
    expect(empty.getSnapshot().matches("worksheetReview")).toBe(true);
    empty.stop();

    const partial = startAssignment();
    partial.send({ type: "TYPE_INSTEAD" });
    partial.send({
      type: "CANDIDATE_CHANGED",
      value: "Plants need sunlight to make food.",
    });
    partial.send({ type: "REQUEST_REVIEW" });
    partial.send({ type: "CONFIRM" });
    partial.send({ type: "CONFIRM_SUCCEEDED" });
    partial.send({ type: "OPEN_WORKSHEET_REVIEW" });
    partial.send({ type: "CREATE_EXPORT" });
    expect(partial.getSnapshot().matches("exporting")).toBe(true);
    expect(Object.keys(partial.getSnapshot().context.confirmedAnswers)).toEqual(
      ["q_01"],
    );
    partial.send({ type: "EXPORT_SUCCEEDED", result: fixtureExport });
    expect(partial.getSnapshot().matches("exportComplete")).toBe(true);
    partial.stop();
  });

  it("retains the last confirmed answer while a revision is edited", () => {
    const actor = createActor(workspaceMachine).start();
    actor.send({ type: "LOAD_FIXTURE_SCENARIO", scenario: "answer-added" });
    actor.send({ type: "OPEN_WORKSHEET_REVIEW" });
    actor.send({ type: "EDIT_ANSWER", questionId: "q_01" });

    expect(actor.getSnapshot().matches({ direct: "captured" })).toBe(true);
    expect(actor.getSnapshot().context.confirmedAnswers.q_01.revision).toBe(1);
    actor.send({
      type: "CANDIDATE_CHANGED",
      value: "Revised exact answer.",
    });
    expect(actor.getSnapshot().context.confirmedAnswers.q_01.text).not.toBe(
      "Revised exact answer.",
    );
    actor.send({ type: "REQUEST_REVIEW" });
    actor.send({ type: "CONFIRM" });
    actor.send({ type: "CONFIRM_SUCCEEDED" });
    expect(actor.getSnapshot().context.confirmedAnswers.q_01).toMatchObject({
      revision: 2,
      text: "Revised exact answer.",
    });
    actor.stop();
  });

  it("hydrates every deterministic visual scenario", () => {
    const expectations = {
      upload: "upload",
      checking: "checking",
      ready: "ready",
      unsupported: "rejected",
      "question-choice": "questionChoice",
      "direct-listening": { direct: "listening" },
      "direct-captured": { direct: "captured" },
      "guided-conversation": { guided: "ready" },
      "wording-comparison": "comparison",
      "exact-review-inline": "exactReview",
      "exact-review-appendix": "exactReview",
      "answer-added": "answerAdded",
      "worksheet-review": "worksheetReview",
      exporting: "exporting",
      "export-failed": "exportFailed",
      "export-complete": "exportComplete",
      "voice-unavailable": { direct: "voiceUnavailable" },
    } as const;

    for (const [scenario, expected] of Object.entries(expectations)) {
      const actor = createActor(workspaceMachine).start();
      actor.send({
        type: "LOAD_FIXTURE_SCENARIO",
        scenario: scenario as keyof typeof expectations,
      });
      expect(actor.getSnapshot().matches(expected)).toBe(true);
      actor.stop();
    }
  });
});
