import { describe, expect, it, vi } from "vitest";
import {
  CANONICAL_CONFIRMATION_PHRASE,
  createFakeRealtimeAdapter,
  createFakeRealtimeScript,
  type FakeRealtimeScriptItem,
} from "../src/v2/realtime/realtime-adapter";

const script: readonly FakeRealtimeScriptItem[] = [
  {
    operationId: "listen-operation",
    event: { id: "evt-listening", type: "voice_state", state: "listening" },
  },
  {
    operationId: "candidate-operation",
    event: {
      id: "evt-candidate",
      type: "candidate",
      text: "Café plants use CO₂ — exactly.",
      input: "voice",
    },
  },
  {
    event: {
      id: "evt-disconnected",
      type: "error",
      code: "realtime_disconnected",
      message: "Connection lost",
    },
  },
];

describe("Gate 2 fake Realtime adapter", () => {
  it("does not emit until the fixture explicitly advances it", () => {
    const adapter = createFakeRealtimeAdapter(
      createFakeRealtimeScript({
        interaction: "direct-answer",
        runId: "manual",
      }),
    );
    const listener = vi.fn();
    adapter.subscribe(listener);

    adapter.connect({
      assignmentId: "fixture-biology",
      questionId: "q_01",
      assignmentVersion: 2,
      mode: "direct",
    });
    adapter.startListening();

    expect(listener).not.toHaveBeenCalled();
    expect(adapter.advance()).toMatchObject({
      type: "voice_state",
      state: "listening",
    });
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("advances scripted events manually and preserves exact Unicode", () => {
    const adapter = createFakeRealtimeAdapter(script);
    const listener = vi.fn();
    adapter.subscribe(listener);

    const connect = adapter.connect({
      assignmentId: "fixture-biology",
      questionId: "q_01",
      assignmentVersion: 2,
      mode: "direct",
    });
    const listen = adapter.startListening();

    expect(connect.id).toBe("fixture-operation-1");
    expect(listen.id).toBe("fixture-operation-2");
    expect(adapter.advance("candidate-operation")).toMatchObject({
      text: "Café plants use CO₂ — exactly.",
    });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(adapter.getPendingCount()).toBe(2);
  });

  it("deduplicates replayed event IDs", () => {
    const duplicate = script[0];
    const adapter = createFakeRealtimeAdapter([duplicate, duplicate]);
    const listener = vi.fn();
    adapter.subscribe(listener);

    expect(adapter.advance()).not.toBeNull();
    expect(adapter.advance()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("scripts captions and every guided voice state without changing text", () => {
    const events = createFakeRealtimeScript({
      interaction: "guided-turn",
      runId: "guided",
      studentText: "Café plants use CO₂ — exactly.",
      clarosText: "Keep your wording and explain the energy step.",
    }).map(({ event }) => event);

    expect(events).toEqual([
      expect.objectContaining({ type: "voice_state", state: "listening" }),
      expect.objectContaining({
        type: "transcript",
        speaker: "student",
        text: "Café plants use CO₂ — exactly.",
      }),
      expect.objectContaining({ type: "voice_state", state: "thinking" }),
      expect.objectContaining({
        type: "transcript",
        speaker: "claros",
        text: "Keep your wording and explain the energy step.",
      }),
      expect.objectContaining({ type: "voice_state", state: "speaking" }),
      expect.objectContaining({ type: "voice_state", state: "ready" }),
    ]);
  });

  it("scripts microphone denial and disconnect as recoverable transport events", () => {
    const microphoneDenied = createFakeRealtimeScript({
      interaction: "direct-answer",
      runId: "microphone",
      scenario: "mic-denied",
    }).map(({ event }) => event);
    const disconnected = createFakeRealtimeScript({
      interaction: "guided-turn",
      runId: "disconnect",
      scenario: "disconnect",
    }).map(({ event }) => event);

    expect(microphoneDenied).toEqual([
      expect.objectContaining({
        type: "error",
        code: "microphone_unavailable",
      }),
    ]);
    expect(disconnected).toEqual([
      expect.objectContaining({ type: "voice_state", state: "listening" }),
      expect.objectContaining({
        type: "error",
        code: "realtime_disconnected",
      }),
    ]);
  });

  it("distinguishes casual agreement from the literal review phrase", () => {
    const casual = createFakeRealtimeScript({
      interaction: "exact-review",
      runId: "casual",
      scenario: "casual",
    });
    const confirmation = createFakeRealtimeScript({
      interaction: "exact-review",
      runId: "confirmation",
      scenario: "confirm",
    });

    expect(casual[1].event).toMatchObject({
      type: "confirmation_phrase",
      phrase: "okay",
    });
    expect(confirmation[1].event).toMatchObject({
      type: "confirmation_phrase",
      phrase: CANONICAL_CONFIRMATION_PHRASE,
    });
  });

  it("delivers a duplicated canonical confirmation event only once", () => {
    const adapter = createFakeRealtimeAdapter(
      createFakeRealtimeScript({
        interaction: "exact-review",
        runId: "duplicate-confirmation",
        scenario: "duplicate",
      }),
    );
    const listener = vi.fn();
    adapter.subscribe(listener);

    while (adapter.getPendingCount() > 0) adapter.advance();

    const confirmationEvents = listener.mock.calls.filter(
      ([event]) => event.type === "confirmation_phrase",
    );
    expect(confirmationEvents).toHaveLength(1);
    expect(confirmationEvents[0][0]).toMatchObject({
      phrase: CANONICAL_CONFIRMATION_PHRASE,
    });
  });

  it("records typed fallback, mute, interruption, retry, and exact playback", () => {
    const adapter = createFakeRealtimeAdapter();
    adapter.sendTypedTurn("My answer stays here.");
    adapter.setMuted(true);
    adapter.interrupt();
    adapter.retry();
    adapter.hearExact("Use the exact displayed answer.");

    expect(
      adapter.getRecordedOperations().map(({ command }) => command),
    ).toEqual(["typed_turn", "mute", "interrupt", "retry", "hear_exact"]);
    expect(adapter.getRecordedOperations()[0].payload).toBe(
      "My answer stays here.",
    );
  });

  it("tears down listeners and scripted work deterministically", () => {
    const adapter = createFakeRealtimeAdapter(script);
    const listener = vi.fn();
    adapter.subscribe(listener);

    adapter.destroy();

    expect(adapter.advance()).toBeNull();
    expect(adapter.getPendingCount()).toBe(0);
    expect(adapter.startListening()).toMatchObject({ command: "listen" });
    expect(listener).not.toHaveBeenCalled();
  });
});
