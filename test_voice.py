"""
Milestone 1 — Minimal voice test: Gemini Live API.
Streams microphone audio to Gemini, plays response through speakers.
Interruption (barge-in) works because we keep sending mic; API handles it.
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

# Gemini Live: input PCM 16-bit 16kHz mono, output PCM 16-bit 24kHz mono
SAMPLE_RATE_IN = 16000
SAMPLE_RATE_OUT = 24000
CHANNELS = 1
DTYPE = np.int16
BYTES_PER_SAMPLE = 2
# ~20ms frames
BLOCK_SAMPLES_IN = 320  # 20ms at 16kHz
BLOCK_BYTES_IN = BLOCK_SAMPLES_IN * BYTES_PER_SAMPLE


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

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE_IN,
        channels=CHANNELS,
        dtype="float32",
        blocksize=BLOCK_SAMPLES_IN,
    )
    stream.start()

    async with client.aio.live.connect(model=model, config=config) as session:
        send_task = asyncio.create_task(send_mic_to_session(session, stream))
        recv_task = asyncio.create_task(receive_and_play(session))
        try:
            await asyncio.gather(send_task, recv_task)
        except asyncio.CancelledError:
            send_task.cancel()
            recv_task.cancel()
            await asyncio.gather(send_task, recv_task, return_exceptions=True)

    stream.stop()
    stream.close()
    print("Session ended.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
