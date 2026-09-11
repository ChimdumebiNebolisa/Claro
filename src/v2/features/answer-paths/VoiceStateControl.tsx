import {
  Microphone01,
  MicrophoneOff01,
  RefreshCw01,
  StopCircle,
  VolumeMax,
  VolumeX,
} from "@untitledui/icons";
import { Button } from "@/components/base/buttons/button";
import type { VoiceState } from "../../domain/contracts";
import styles from "./answer-paths.module.css";

export type VoiceStateControlProps = {
  state: VoiceState;
  muted?: boolean;
  onStart?: () => void;
  onStop?: () => void;
  onRetry?: () => void;
  onContinueByTyping?: () => void;
  onInterrupt?: () => void;
  onToggleMute?: () => void;
};

const voiceLabels: Record<VoiceState, string> = {
  ready: "Ready",
  listening: "Listening",
  captured: "Captured",
  thinking: "Thinking",
  speaking: "Speaking",
  interrupted: "Interrupted",
  microphone_unavailable: "Microphone unavailable",
  disconnected: "Connection lost",
};

const helpForState: Record<VoiceState, string> = {
  ready: "Start speaking when you are ready, or type your answer below.",
  listening: "Claros is listening. Your words will remain editable.",
  captured: "Your words are ready to edit before review.",
  thinking: "Claros is considering your last response.",
  speaking: "Claros is speaking. You can interrupt at any time.",
  interrupted:
    "Claros stopped speaking. Your text and conversation are still available.",
  microphone_unavailable:
    "Your current text is safe. Retry voice or continue by typing.",
  disconnected:
    "Your current text and conversation are safe. Retry voice or continue by typing.",
};

export function VoiceStateControl({
  state,
  muted = false,
  onStart,
  onStop,
  onRetry,
  onContinueByTyping,
  onInterrupt,
  onToggleMute,
}: VoiceStateControlProps) {
  const isFailure =
    state === "microphone_unavailable" || state === "disconnected";

  return (
    <section
      className={`${styles.voiceControl} ${
        isFailure ? styles.voiceControlFailure : ""
      }`}
      aria-label="Voice controls"
    >
      <div className={styles.voiceStatusRow} role="status" aria-live="polite">
        <span
          className={`${styles.voiceSignal} ${
            state === "listening" || state === "speaking"
              ? styles.voiceSignalActive
              : ""
          }`}
          aria-hidden="true"
        >
          <span />
          <span />
          <span />
        </span>
        <span>
          <strong>{voiceLabels[state]}</strong>
          <small>{helpForState[state]}</small>
        </span>
      </div>

      <div className={styles.voiceActions}>
        {state === "ready" ||
        state === "captured" ||
        state === "interrupted" ? (
          <Button
            color="primary"
            size="lg"
            iconLeading={Microphone01}
            onPress={onStart}
            isDisabled={!onStart}
            className={styles.voicePrimary}
          >
            Start speaking
          </Button>
        ) : null}

        {state === "listening" ? (
          <Button
            color="primary"
            size="lg"
            iconLeading={StopCircle}
            onPress={onStop}
            isDisabled={!onStop}
            className={styles.voicePrimary}
          >
            Stop listening
          </Button>
        ) : null}

        {state === "speaking" ? (
          <Button
            color="primary"
            size="lg"
            iconLeading={StopCircle}
            onPress={onInterrupt}
            isDisabled={!onInterrupt}
            className={styles.voicePrimary}
          >
            Interrupt Claros
          </Button>
        ) : null}

        {state === "thinking" ? (
          <Button
            color="secondary"
            size="lg"
            isLoading
            showTextWhileLoading
            isDisabled
            className={styles.voicePrimary}
          >
            Thinking
          </Button>
        ) : null}

        {isFailure ? (
          <>
            <Button
              color="secondary"
              size="lg"
              iconLeading={RefreshCw01}
              onPress={onRetry}
              isDisabled={!onRetry}
              className={styles.minimumTarget}
            >
              Retry voice
            </Button>
            <Button
              color="primary"
              size="lg"
              iconLeading={MicrophoneOff01}
              onPress={onContinueByTyping}
              isDisabled={!onContinueByTyping}
              className={styles.minimumTarget}
            >
              Continue by typing
            </Button>
          </>
        ) : null}

        {onToggleMute && !isFailure ? (
          <Button
            color="link-gray"
            size="lg"
            iconLeading={muted ? VolumeX : VolumeMax}
            onPress={onToggleMute}
            className={styles.minimumTarget}
          >
            {muted ? "Unmute spoken output" : "Mute spoken output"}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
