"""
Claros backend: FastAPI app with PDF upload, WebSocket voice session, and Gemini Live.
"""
import asyncio
import base64
import json
import os
import tempfile
import uuid
from pathlib import Path

# Load .env from project root
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

from fastapi import FastAPI, UploadFile, File, WebSocket, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi import Query

from exporter import build_export_pdf

from parser import parse_pdf, Question
from agent import build_system_prompt, WriteTokenParser

from google import genai
from google.genai import types

try:
    from websockets.exceptions import ConnectionClosedError as WsConnectionClosedError
except ImportError:
    WsConnectionClosedError = None

# Same as test_voice.py
SAMPLE_RATE_IN = 16000
KEEPALIVE_INTERVAL = 5
BLOCK_SAMPLES_IN = 320
SILENT_CHUNK = b"\x00" * (BLOCK_SAMPLES_IN * 2)

app = FastAPI()
ROOT = Path(__file__).resolve().parent


def get_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not key.strip():
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    return key.strip()


def get_gcs_bucket():
    bucket_name = os.environ.get("GCS_BUCKET_NAME", "").strip()
    if not bucket_name:
        raise RuntimeError("GCS_BUCKET_NAME not set in .env")
    from google.cloud import storage
    client = storage.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    return client.bucket(bucket_name)


def upload_pdf_to_gcs(assignment_id: str, pdf_bytes: bytes, filename: str = "assignment.pdf") -> str:
    """Upload PDF to GCS at assignments/{assignment_id}/{filename}. Returns gs:// path."""
    bucket = get_gcs_bucket()
    blob = bucket.blob(f"assignments/{assignment_id}/{filename}")
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")
    return f"gs://{bucket.name}/assignments/{assignment_id}/{filename}"


def load_assignment_from_gcs(assignment_id: str) -> tuple[str, list]:
    """Load PDF from GCS, parse, return (title, questions) where questions = [{"id": n, "text": "..."}]."""
    bucket = get_gcs_bucket()
    prefix = f"assignments/{assignment_id}/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    if not blobs:
        raise ValueError(f"No PDF found for assignment {assignment_id}")
    blob = blobs[0]
    pdf_bytes = blob.download_as_bytes()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        title, questions = parse_pdf(tmp_path)
        return title, [{"id": q.id, "text": q.text} for q in questions]
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def load_assignment_text_from_gcs(assignment_id: str) -> str:
    """Load PDF from GCS, parse, return assignment text for system prompt."""
    title, questions = load_assignment_from_gcs(assignment_id)
    return title + "\n\n" + "\n\n".join(
        f"Question {q['id']}: {q['text']}" for q in questions
    )


@app.get("/export/{assignment_id}")
async def export_assignment(assignment_id: str, answers: str = Query(..., alias="answers")):
    """Generate PDF of questions and answers. Query param 'answers' = JSON array of {question_id, answer_text}."""
    try:
        answers_list = json.loads(answers)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid answers JSON")
    try:
        title, questions = load_assignment_from_gcs(assignment_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    pdf_bytes = build_export_pdf(title, questions, answers_list)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="claros-{assignment_id}.pdf"'},
    )


@app.post("/upload")
async def upload_assignment(file: UploadFile = File(...)):
    """Accept PDF, upload to GCS, parse questions. Returns assignment_id, title, questions."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    assignment_id = str(uuid.uuid4())
    content = await file.read()
    try:
        upload_pdf_to_gcs(assignment_id, content, file.filename or "assignment.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GCS upload failed: {e}")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        title, questions = parse_pdf(tmp_path)
        return {
            "assignment_id": assignment_id,
            "title": title,
            "questions": [{"id": q.id, "text": q.text} for q in questions],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF parse failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.websocket("/session/{assignment_id}")
async def ws_session(websocket: WebSocket, assignment_id: str):
    """Assignment-aware voice session: loads assignment, injects into prompt, emits write events."""
    await websocket.accept()
    try:
        assignment_text = load_assignment_text_from_gcs(assignment_id)
    except Exception as e:
        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        await websocket.close()
        return
    system_prompt = build_system_prompt(assignment_text)
    write_parser = WriteTokenParser()

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
        system_instruction=types.Content(parts=[types.Part(text=system_prompt)]),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    async def send_json(obj: dict):
        try:
            await websocket.send_text(json.dumps(obj))
        except Exception:
            pass

    audio_queue = asyncio.Queue()
    recv_task = None
    send_task = None
    keepalive_task = None

    async def forward_audio_to_gemini(session):
        nonlocal send_task
        try:
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await send_json({"type": "error", "message": str(e)})

    async def keepalive_loop(session):
        nonlocal keepalive_task
        try:
            while True:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                await session.send_realtime_input(
                    audio=types.Blob(data=SILENT_CHUNK, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.CancelledError:
            raise

    async def receive_from_gemini_and_forward(session):
        nonlocal recv_task
        while True:
            try:
                async for response in session.receive():
                    if not response.server_content:
                        continue
                    sc = response.server_content
                    if sc.input_transcription and sc.input_transcription.text:
                        await send_json({"type": "transcript", "speaker": "user", "text": sc.input_transcription.text})
                    if sc.output_transcription and sc.output_transcription.text:
                        text = sc.output_transcription.text
                        await send_json({"type": "transcript", "speaker": "claros", "text": text})
                        for ev in write_parser.feed(text):
                            if ev["event"] == "write_start":
                                await send_json({"type": "status", "mode": "writing"})
                                await send_json({"type": "write_start", "question_id": ev["question_id"]})
                            elif ev["event"] == "write_token":
                                await send_json({"type": "write_token", "question_id": ev["question_id"], "text": ev["text"]})
                            elif ev["event"] == "write_end":
                                await send_json({"type": "write_end", "question_id": ev["question_id"]})
                                await send_json({"type": "status", "mode": "teaching"})
                    if sc.model_turn and sc.model_turn.parts:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                await send_json({"type": "audio", "data": base64.b64encode(part.inline_data.data).decode()})
                    if getattr(sc, "turn_complete", False):
                        await send_json({"type": "status", "mode": "teaching"})
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await send_json({"type": "error", "message": str(e)})
                await asyncio.sleep(1)

    try:
        await send_json({"type": "status", "mode": "connecting"})
        async with client.aio.live.connect(model=model, config=config) as session:
            await send_json({"type": "status", "mode": "teaching"})
            recv_task = asyncio.create_task(receive_from_gemini_and_forward(session))
            send_task = asyncio.create_task(forward_audio_to_gemini(session))
            keepalive_task = asyncio.create_task(keepalive_loop(session))
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.receive(), timeout=60.0)
                except asyncio.TimeoutError:
                    continue
                if msg.get("type") == "websocket.disconnect":
                    break
                if "bytes" in msg:
                    audio_queue.put_nowait(msg["bytes"])
    except Exception as e:
        if not _is_connection_error(e):
            await send_json({"type": "error", "message": str(e)})
    finally:
        audio_queue.put_nowait(None)
        for t in (recv_task, send_task, keepalive_task):
            if t is not None:
                t.cancel()
        for t in (recv_task, send_task, keepalive_task):
            if t is not None:
                await asyncio.gather(t, return_exceptions=True)


def _is_connection_error(e: BaseException) -> bool:
    if WsConnectionClosedError is not None and isinstance(e, WsConnectionClosedError):
        return True
    if isinstance(e, (TimeoutError, OSError, ConnectionError)):
        return True
    msg = str(e).lower()
    return "connection" in msg or "timeout" in msg or "closed" in msg or "1011" in msg


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the Claros app (frontend/index.html)."""
    path = ROOT / "frontend" / "index.html"
    if not path.exists():
        path = ROOT / "test_voice.html"
    if not path.exists():
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    return FileResponse(path, media_type="text/html")


@app.get("/test", response_class=HTMLResponse)
async def test_voice_page():
    """Serve the voice debug test page."""
    path = ROOT / "test_voice.html"
    if not path.exists():
        return HTMLResponse("<h1>Not found</h1><p>test_voice.html missing</p>", status_code=404)
    return FileResponse(path, media_type="text/html")


@app.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket):
    """Bridge browser mic ↔ Gemini Live: receive binary audio, send back status/transcript/audio."""
    await websocket.accept()
    print("[WebSocket] Client connected to /ws/voice")
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
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    async def send_json(obj: dict):
        try:
            await websocket.send_text(json.dumps(obj))
        except Exception:
            pass

    audio_queue = asyncio.Queue()
    recv_task = None
    send_task = None
    keepalive_task = None

    async def forward_audio_to_gemini(session):
        nonlocal send_task
        print("[forward_audio_to_gemini] Task started; will exit only when poison pill (None) received.")
        try:
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    print("[forward_audio_to_gemini] Exiting: received poison pill (None) from main loop (client disconnected).")
                    break
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.CancelledError:
            print("[forward_audio_to_gemini] Exiting: task was cancelled.")
            raise
        except Exception as e:
            print("[forward_audio_to_gemini] Exiting: exception:", type(e).__name__, e)
            await send_json({"type": "error", "message": str(e)})

    async def keepalive_loop(session):
        nonlocal keepalive_task
        print("[keepalive_loop] Task started; will exit only when cancelled (client disconnected).")
        try:
            while True:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                await session.send_realtime_input(
                    audio=types.Blob(data=SILENT_CHUNK, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.CancelledError:
            print("[keepalive_loop] Exiting: task was cancelled.")
            raise
        except Exception as e:
            print("[keepalive_loop] Exception (will keep running):", type(e).__name__, e)

    async def receive_from_gemini_and_forward(session):
        nonlocal recv_task
        print("[receive_from_gemini_and_forward] Task started; will run until client disconnects (task cancelled).")
        while True:
            try:
                print("[receive_from_gemini_and_forward] Entering session.receive() iterator...")
                async for response in session.receive():
                    if not response.server_content:
                        continue
                    sc = response.server_content
                    if sc.input_transcription and sc.input_transcription.text:
                        await send_json({"type": "transcript", "speaker": "user", "text": sc.input_transcription.text})
                    if sc.output_transcription and sc.output_transcription.text:
                        await send_json({"type": "transcript", "speaker": "claros", "text": sc.output_transcription.text})
                    if sc.model_turn and sc.model_turn.parts:
                        await send_json({"type": "status", "value": "speaking"})
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                await send_json({"type": "audio", "data": base64.b64encode(part.inline_data.data).decode()})
                    if getattr(sc, "turn_complete", False):
                        await send_json({"type": "status", "value": "listening"})
                        print("[receive] turn_complete received; session stays open.")
                print("[receive_from_gemini_and_forward] session.receive() iterator ended (no more items); re-entering in 1s to keep task alive.")
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                print("[receive_from_gemini_and_forward] Exiting: task was cancelled (client disconnected).")
                raise
            except Exception as e:
                print("[receive_from_gemini_and_forward] Exception in receive loop:", type(e).__name__, e)
                await send_json({"type": "error", "message": str(e)})
                await asyncio.sleep(1)

    try:
        await send_json({"type": "status", "value": "connecting"})
        async with client.aio.live.connect(model=model, config=config) as session:
            await send_json({"type": "status", "value": "listening"})
            recv_task = asyncio.create_task(receive_from_gemini_and_forward(session))
            send_task = asyncio.create_task(forward_audio_to_gemini(session))
            keepalive_task = asyncio.create_task(keepalive_loop(session))

            # Keep session open: only exit when client disconnects. Mic audio flows until then.
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.receive(), timeout=60.0)
                except asyncio.TimeoutError:
                    continue
                if msg.get("type") == "websocket.disconnect":
                    print("[main] Client sent disconnect; breaking out of session loop.")
                    break
                if "bytes" in msg:
                    audio_queue.put_nowait(msg["bytes"])
    except Exception as e:
        if _is_connection_error(e):
            await send_json({"type": "status", "value": "reconnecting"})
            await send_json({"type": "error", "message": str(e)})
        else:
            await send_json({"type": "error", "message": str(e)})
    finally:
        print("[main] In finally: sending poison pill and cancelling recv/send/keepalive tasks.")
        audio_queue.put_nowait(None)
        for t in (recv_task, send_task, keepalive_task):
            if t is not None:
                t.cancel()
        if recv_task:
            await asyncio.gather(recv_task, return_exceptions=True)
            print("[main] recv_task gathered (finished).")
        if send_task:
            await asyncio.gather(send_task, return_exceptions=True)
            print("[main] send_task gathered (finished).")
        if keepalive_task:
            await asyncio.gather(keepalive_task, return_exceptions=True)
            print("[main] keepalive_task gathered (finished).")
        print("[main] WebSocket handler done.")
