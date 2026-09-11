import { createActor } from "xstate";
import { describe, expect, it } from "vitest";
import {
  candidateFor,
  fixtureAssignment,
  fixtureExportResult,
} from "../src/v2/domain/fixtures";
import { workspaceMachine } from "../src/v2/domain/workspaceMachine";

describe("Gate 3 server-owned workspace transitions", () => {
  it("hydrates the active draft and applies candidate persistence immediately", () => {
    const actor = createActor(workspaceMachine).start();
    const draft = candidateFor(
      fixtureAssignment.questions[1].id,
      "Exact restored draft.",
      "student_verbatim",
      2,
    );
    actor.send({ type: "START_ANALYSIS" });
    actor.send({
      type: "ANALYSIS_READY",
      assignment: { ...fixtureAssignment, version: 7 },
      activeQuestionIndex: 1,
      candidate: draft,
    });

    expect(actor.getSnapshot().context.activeQuestionIndex).toBe(1);
    expect(actor.getSnapshot().context.candidate).toEqual(draft);

    const persisted = { ...draft, id: "cand_server", version: 4 };
    actor.send({
      type: "CANDIDATE_PERSISTED",
      candidate: persisted,
      version: 8,
    });
    expect(actor.getSnapshot().context.candidate).toEqual(persisted);
    expect(actor.getSnapshot().context.assignment?.version).toBe(8);
    actor.stop();
  });

  it("keeps pending, failed, and complete export states distinct", () => {
    const actor = createActor(workspaceMachine).start();
    actor.send({ type: "LOAD_FIXTURE_SCENARIO", scenario: "worksheet-review" });
    actor.send({ type: "CREATE_EXPORT" });
    actor.send({ type: "EXPORT_PENDING", version: 8 });
    expect(actor.getSnapshot().matches("exporting")).toBe(true);

    actor.send({
      type: "EXPORT_FAILED",
      version: 9,
      error: {
        code: "publish_failed",
        message: "The PDF could not be published.",
        recoverable: true,
      },
    });
    expect(actor.getSnapshot().matches("exportFailed")).toBe(true);
    expect(actor.getSnapshot().context.assignment?.version).toBe(9);

    actor.send({ type: "RETRY_EXPORT" });
    actor.send({
      type: "EXPORT_RESTORED",
      result: fixtureExportResult,
      version: 10,
    });
    expect(actor.getSnapshot().matches("exportComplete")).toBe(true);
    expect(actor.getSnapshot().context.exportResult).toEqual(
      fixtureExportResult,
    );
    actor.send({
      type: "EXPORT_FAILED",
      error: {
        code: "export_stale",
        message: "The export is no longer current.",
        recoverable: true,
      },
    });
    expect(actor.getSnapshot().context.exportResult).toBeNull();
    actor.stop();
  });
});
