import {
  CANONICAL_CONFIRMATION_PHRASE,
  type AnswerPath,
  type VoiceState,
} from "../domain/contracts";

export { CANONICAL_CONFIRMATION_PHRASE };

export const fakeRealtimeScenarios = [
  "normal",
  "disconnect",
  "mic-denied",
  "casual",
  "confirm",
  "duplicate",
] as const;

export type FakeRealtimeScenario = (typeof fakeRealtimeScenarios)[number];
export type FakeRealtimeInteraction =
  | "direct-answer"
  | "guided-turn"
  | "guided-typed-turn"
  | "guided-final-answer"
  | "exact-review"
  | "playback";

export type RealtimeAvailability =
  { available: true } | { available: false; reason: "not_configured" };

export type RealtimeEvent =
  | { id: string; type: "voice_state"; state: VoiceState }
  | {
      id: string;
      type: "transcript";
      speaker: "student" | "claros";
      text: string;
      final: boolean;
    }
  | {
      id: string;
      type: "candidate";
      text: string;
      input: "typed" | "voice";
    }
  | { id: string; type: "confirmation_phrase"; phrase: string }
  | {
      id: string;
      type: "error";
      code: "microphone_unavailable" | "realtime_disconnected";
      message: string;
    }
  | { id: string; type: "playback_complete"; exactText: string };

export type RealtimeCommand =
  | "connect"
  | "listen"
  | "stop"
  | "interrupt"
  | "mute"
  | "typed_turn"
  | "hear_exact"
  | "retry"
  | "destroy";

export type RealtimeOperation = {
  id: string;
  command: RealtimeCommand;
  payload?: string | boolean;
};

export type FakeRealtimeScriptItem = {
  operationId?: string;
  event: RealtimeEvent;
};

export type FakeRealtimeScriptOptions = {
  interaction: FakeRealtimeInteraction;
  runId: string;
  scenario?: FakeRealtimeScenario;
  studentText?: string;
  clarosText?: string;
};

export type RealtimeConnectOptions = {
  assignmentId: string;
  questionId: string;
  assignmentVersion: number;
  mode: AnswerPath;
};

export type RealtimeListener = (event: RealtimeEvent) => void;

export interface RealtimeAdapter {
  subscribe(listener: RealtimeListener): () => void;
  connect(options: RealtimeConnectOptions): RealtimeOperation;
  startListening(): RealtimeOperation;
  stopListening(): RealtimeOperation;
  interrupt(): RealtimeOperation;
  setMuted(muted: boolean): RealtimeOperation;
  sendTypedTurn(text: string): RealtimeOperation;
  hearExact(exactText: string): RealtimeOperation;
  retry(): RealtimeOperation;
  destroy(): RealtimeOperation;
}

export function getRealtimeAvailability(): RealtimeAvailability {
  return { available: false, reason: "not_configured" };
}

const defaultDirectAnswer =
  "Plants need sunlight because light energy helps them make food.";
const defaultGuidedTurn = "Sunlight gives the plant energy for the process.";
const defaultGuidedReply = "Good. State your final answer in your own words.";
const defaultGuidedAnswer =
  "Plants use sunlight as energy to make their own food.";

/**
 * Builds finite, explicit Gate 2 scripts. A run ID keeps independent
 * interactions distinct while the duplicate scenario intentionally reuses one
 * event identity to exercise replay protection.
 */
export function createFakeRealtimeScript({
  interaction,
  runId,
  scenario = "normal",
  studentText,
  clarosText,
}: FakeRealtimeScriptOptions): readonly FakeRealtimeScriptItem[] {
  const id = (suffix: string) => `fixture-${runId}-${suffix}`;
  const item = (event: RealtimeEvent): FakeRealtimeScriptItem => ({ event });
  const microphoneDenied = item({
    id: id("microphone-unavailable"),
    type: "error",
    code: "microphone_unavailable",
    message: "Microphone unavailable",
  });
  const disconnected = item({
    id: id("connection-lost"),
    type: "error",
    code: "realtime_disconnected",
    message: "Connection lost",
  });

  if (interaction === "playback") {
    return [
      item({
        id: id("playback-complete"),
        type: "playback_complete",
        exactText: studentText ?? "",
      }),
    ];
  }

  if (interaction === "exact-review") {
    const phrase =
      scenario === "confirm" || scenario === "duplicate"
        ? CANONICAL_CONFIRMATION_PHRASE
        : "okay";
    const confirmation = item({
      id: id("confirmation"),
      type: "confirmation_phrase",
      phrase,
    });
    const script = [
      item({
        id: id("confirmation-caption"),
        type: "transcript",
        speaker: "student",
        text: phrase,
        final: true,
      }),
      confirmation,
    ];
    return scenario === "duplicate" ? [...script, confirmation] : script;
  }

  if (scenario === "mic-denied") return [microphoneDenied];

  const listening = item({
    id: id("listening"),
    type: "voice_state",
    state: "listening",
  });
  if (scenario === "disconnect") return [listening, disconnected];

  if (interaction === "guided-typed-turn") {
    return [
      item({
        id: id("thinking"),
        type: "voice_state",
        state: "thinking",
      }),
      item({
        id: id("claros-caption"),
        type: "transcript",
        speaker: "claros",
        text: clarosText ?? defaultGuidedReply,
        final: true,
      }),
      item({
        id: id("speaking"),
        type: "voice_state",
        state: "speaking",
      }),
      item({
        id: id("ready"),
        type: "voice_state",
        state: "ready",
      }),
    ];
  }

  if (interaction === "guided-turn") {
    const text = studentText ?? defaultGuidedTurn;
    const script: FakeRealtimeScriptItem[] = [
      listening,
      item({
        id: id("student-caption"),
        type: "transcript",
        speaker: "student",
        text,
        final: true,
      }),
      item({
        id: id("thinking"),
        type: "voice_state",
        state: "thinking",
      }),
      item({
        id: id("claros-caption"),
        type: "transcript",
        speaker: "claros",
        text: clarosText ?? defaultGuidedReply,
        final: true,
      }),
      item({
        id: id("speaking"),
        type: "voice_state",
        state: "speaking",
      }),
      item({
        id: id("ready"),
        type: "voice_state",
        state: "ready",
      }),
    ];
    if (scenario === "casual") {
      script.push(
        item({
          id: id("casual-agreement"),
          type: "confirmation_phrase",
          phrase: "okay",
        }),
      );
    }
    return script;
  }

  const text =
    studentText ??
    (interaction === "guided-final-answer"
      ? defaultGuidedAnswer
      : defaultDirectAnswer);
  const candidate = item({
    id: id("candidate"),
    type: "candidate",
    text,
    input: "voice",
  });
  const script: FakeRealtimeScriptItem[] = [
    listening,
    item({
      id: id("student-caption"),
      type: "transcript",
      speaker: "student",
      text,
      final: true,
    }),
    candidate,
    item({
      id: id("captured"),
      type: "voice_state",
      state: "captured",
    }),
  ];

  if (scenario === "casual") {
    script.push(
      item({
        id: id("casual-agreement"),
        type: "confirmation_phrase",
        phrase: "okay",
      }),
    );
  }
  if (scenario === "duplicate") script.push(candidate);
  return script;
}

/**
 * Deterministic Gate 2 transport. It has no timers, media devices, or network
 * access: tests and stories advance a finite script explicitly.
 */
export class FakeRealtimeAdapter implements RealtimeAdapter {
  private readonly listeners = new Set<RealtimeListener>();
  private readonly pending: FakeRealtimeScriptItem[];
  private readonly deliveredEventIds = new Set<string>();
  private readonly operations: RealtimeOperation[] = [];
  private operationSequence = 0;
  private destroyed = false;

  constructor(script: readonly FakeRealtimeScriptItem[] = []) {
    this.pending = [...script];
  }

  subscribe(listener: RealtimeListener): () => void {
    if (this.destroyed) return () => undefined;
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  connect(options: RealtimeConnectOptions): RealtimeOperation {
    return this.record(
      "connect",
      `${options.assignmentId}:${options.questionId}:${options.assignmentVersion}:${options.mode}`,
    );
  }

  startListening(): RealtimeOperation {
    return this.record("listen");
  }

  stopListening(): RealtimeOperation {
    return this.record("stop");
  }

  interrupt(): RealtimeOperation {
    return this.record("interrupt");
  }

  setMuted(muted: boolean): RealtimeOperation {
    return this.record("mute", muted);
  }

  sendTypedTurn(text: string): RealtimeOperation {
    return this.record("typed_turn", text);
  }

  hearExact(exactText: string): RealtimeOperation {
    return this.record("hear_exact", exactText);
  }

  retry(): RealtimeOperation {
    return this.record("retry");
  }

  destroy(): RealtimeOperation {
    const operation = this.record("destroy");
    this.destroyed = true;
    this.pending.length = 0;
    this.listeners.clear();
    return operation;
  }

  enqueue(...items: readonly FakeRealtimeScriptItem[]): void {
    if (!this.destroyed) this.pending.push(...items);
  }

  advance(operationId?: string): RealtimeEvent | null {
    if (this.destroyed) return null;
    const index = operationId
      ? this.pending.findIndex((item) => item.operationId === operationId)
      : 0;
    if (index < 0 || this.pending.length === 0) return null;
    const [item] = this.pending.splice(index, 1);
    if (this.deliveredEventIds.has(item.event.id)) return null;
    this.deliveredEventIds.add(item.event.id);
    for (const listener of this.listeners) listener(item.event);
    return item.event;
  }

  getRecordedOperations(): readonly RealtimeOperation[] {
    return [...this.operations];
  }

  getPendingCount(): number {
    return this.pending.length;
  }

  private record(
    command: RealtimeCommand,
    payload?: string | boolean,
  ): RealtimeOperation {
    this.operationSequence += 1;
    const operation: RealtimeOperation = {
      id: `fixture-operation-${this.operationSequence}`,
      command,
      ...(payload === undefined ? {} : { payload }),
    };
    this.operations.push(operation);
    return operation;
  }
}

export const createFakeRealtimeAdapter = (
  script: readonly FakeRealtimeScriptItem[] = [],
) => new FakeRealtimeAdapter(script);
