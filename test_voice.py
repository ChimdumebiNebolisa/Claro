"""
Milestone 1 — Minimal voice test: Gemini Live API.
Streams microphone audio to Gemini, plays response through speakers.
Interruption (barge-in) works because we keep sending mic; API handles it.
Reconnects automatically on connection drop; keepalive prevents ping timeout.
Run: python test_voice.py   (Ctrl+C to exit)
"""
import asyncio
import sys
from pathlib import Path

# Load .env from project root (parent of script location)
import os
script_dir = Path(__file__).resolve().parent
env_path = script_dir / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

from google import genai
from google.genai import types
import sounddevice as sd
import numpy as np

try:
    from websockets.exceptions import ConnectionClosedError as WsConnectionClosedError
except ImportError:
    WsConnectionClosedError = None  # fallback to name check

# Gemini Live: input PCM 16-bit 16kHz mono, output PCM 16-bit 24kHz mono
SAMPLE_RATE_IN = 16000
SAMPLE_RATE_OUT = 24000
CHANNELS = 1
DTYPE = np.int16
BYTES_PER_SAMPLE = 2
# ~20ms frames
BLOCK_SAMPLES_IN = 320  # 20ms at 16kHz
BLOCK_BYTES_IN = BLOCK_SAMPLES_IN * BYTES_PER_SAMPLE
# Keepalive: send silent PCM every N seconds to prevent WebSocket ping timeout
KEEPALIVE_INTERVAL = 5
SILENT_CHUNK = (np.zeros(BLOCK_SAMPLES_IN, dtype=np.int16)).tobytes()


def get_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key or key.strip() == "":
        print("Error: GEMINI_API_KEY not set. Add it to .env (and do not commit .env).")
        sys.exit(1)
    return key.strip()


async def send_mic_to_session(session, stream):
    """Read mic in executor and send to Gemini (PCM 16-bit 16kHz)."""
    loop = asyncio.get_event_loop()
    try:
        while True:
            # Blocking read in thread so we don't block the event loop
            block, _ = await loop.run_in_executor(
                None,
                lambda: stream.read(BLOCK_SAMPLES_IN),
            )
            if block.size == 0:
                break
            chunk = (block * 32767).astype(np.int16).tobytes()
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )
    except asyncio.CancelledError:
        pass


async def keepalive_loop(session):
    """Send a silent audio chunk every KEEPALIVE_INTERVAL seconds to prevent WebSocket ping timeout."""
    try:
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            await session.send_realtime_input(
                audio=types.Blob(data=SILENT_CHUNK, mime_type="audio/pcm;rate=16000")
            )
    except asyncio.CancelledError:
        pass


def play_audio_sync(data: bytes):
    """Play raw PCM 16-bit 24kHz mono (blocking)."""
    if not data:
        return
    arr = np.frombuffer(data, dtype=np.int16)
    sd.play(arr, samplerate=SAMPLE_RATE_OUT, blocking=False)
    # Allow overlap; we'll rely on sd.wait() only when we want to block
    # For streaming we don't block - just queue
    sd.wait()


async def receive_and_play(session):
    """Consume session.receive() and play audio parts."""
    try:
        async for response in session.receive():
            if not response.server_content or not response.server_content.model_turn:
                continue
            for part in response.server_content.model_turn.parts:
                if part.inline_data and part.inline_data.data:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None, play_audio_sync, part.inline_data.data
                    )
    except asyncio.CancelledError:
        pass


def _is_connection_error(e: BaseException) -> bool:
    """True if the exception indicates a dropped connection (reconnect is appropriate)."""
    if WsConnectionClosedError is not None and isinstance(e, WsConnectionClosedError):
        return True
    if isinstance(e, (TimeoutError, OSError, ConnectionError)):
        return True
    msg = str(e).lower()
    return "connection" in msg or "timeout" in msg or "closed" in msg or "1011" in msg


async def run_one_session(client, model, config, stream):
    """Run a single Gemini Live session. Raises on connection drop or CancelledError."""
    async with client.aio.live.connect(model=model, config=config) as session:
        send_task = asyncio.create_task(send_mic_to_session(session, stream))
        recv_task = asyncio.create_task(receive_and_play(session))
        keepalive_task = asyncio.create_task(keepalive_loop(session))
        try:
            await asyncio.gather(send_task, recv_task, keepalive_task)
        finally:
            for t in (send_task, recv_task, keepalive_task):
                t.cancel()
            await asyncio.gather(send_task, recv_task, keepalive_task, return_exceptions=True)


async def main():
    api_key = get_api_key()
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
    model = "gemini-2.5-flash-native-audio-preview-12-2025"
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text="You are a helpful voice assistant. Keep replies concise. Say hello and ask how you can help.")]
        ),
    )

    print("Starting Gemini Live session. Speak into your mic. Ctrl+C to exit.")
    print("(Interruption: speak over the assistant; it will stop and listen.)")
    print("(Connection drops will auto-reconnect.)")

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE_IN,
        channels=CHANNELS,
        dtype="float32",
        blocksize=BLOCK_SAMPLES_IN,
    )
    stream.start()

    try:
        while True:
            try:
                await run_one_session(client, model, config, stream)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if _is_connection_error(e):
                    print(f"Connection dropped: {e}. Reconnecting in 2s...")
                    await asyncio.sleep(2)
                else:
                    raise
    finally:
        stream.stop()
        stream.close()
        print("Session ended.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
