"""
Claros backend: FastAPI app with PDF upload, session config (ephemeral token), and write/export.
Real-time voice uses Gemini Live directly from the browser.
"""
import datetime
import json
import os
import tempfile
import traceback
import uuid
from pathlib import Path

# Load .env from project root
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi import Query
from pydantic import BaseModel

from exporter import build_export_pdf

from parser import parse_pdf, Question
from agent import build_system_prompt

from google import genai
from google.genai import types

LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

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


class WriteRequest(BaseModel):
    question_id: int
    conversation: list[dict]
    answer_candidate: str = ""


@app.get("/api/session-config/{assignment_id}")
def get_session_config(assignment_id: str):
    """Return ephemeral token + system prompt + model for browser-side Gemini Live. API key stays on server."""
    try:
        title, questions = load_assignment_from_gcs(assignment_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    assignment_text = title + "\n\n" + "\n\n".join(
        f"Question {q['id']}: {q['text']}" for q in questions
    )
    system_prompt = build_system_prompt(assignment_text)
    api_key = get_api_key()
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version="v1alpha"))
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    # Ephemeral token for browser Live; frontend must use same LIVE_MODEL and v1alpha.
    try:
        token = client.auth_tokens.create(
            config=types.CreateAuthTokenConfig(
                uses=1,
                expire_time=now_utc + datetime.timedelta(minutes=30),
                new_session_expire_time=now_utc + datetime.timedelta(minutes=2),
                http_options=types.HttpOptions(api_version="v1alpha"),
            )
        )
        token_value = token.name if token and getattr(token, "name", None) else None
    except Exception as e:
        print(f"[session-config] Ephemeral token creation failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Ephemeral token creation failed; check backend logs.")
    if not token_value:
        raise HTTPException(status_code=500, detail="No token returned.")
    return {
        "token": token_value,
        "model": LIVE_MODEL,
        "system_prompt": system_prompt,
        "title": title,
        "questions": questions,
    }


@app.post("/api/write/{assignment_id}")
async def stream_write(assignment_id: str, body: WriteRequest):
    """Stream generated answer text for a question. Frontend calls this when write is triggered."""
    try:
        title, questions = load_assignment_from_gcs(assignment_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    assignment_text = title + "\n\n" + "\n\n".join(
        f"Question {q['id']}: {q['text']}" for q in questions
    )
    qids = [q["id"] for q in questions]
    if body.question_id not in qids:
        raise HTTPException(status_code=400, detail=f"Unknown question id: {body.question_id}")
    candidate = body.answer_candidate or ""
    candidate_empty = not bool(candidate.strip())
    print(
        "[write] Incoming request.",
        "question_id=", body.question_id,
        "candidate_empty=", candidate_empty,
        "candidate_preview=", repr(candidate[:120]),
    )
    if candidate_empty:
        raise HTTPException(status_code=400, detail="Student must state the answer before writing is allowed.")
    conv_str = "\n".join(
        f"{'User' if c.get('speaker') == 'user' else 'Claros'}: {c.get('text', '')}"
        for c in (body.conversation or [])
    )
    answer_line = (
        f'The student stated their answer as: "{body.answer_candidate}"'
        if body.answer_candidate
        else ""
    )
    prompt = f"""You are helping a student with their assignment. Below is the assignment and a transcript of the voice conversation so far.

Assignment:
{assignment_text}

Conversation so far:
{conv_str}

The student has asked to have their answer for Question {body.question_id} written down.
{answer_line}
Based on what was discussed, write only the answer text for Question {body.question_id}. Do not include the question number, labels, or preamble. Output only the answer content that should appear in the answer box. Write the student's own answer, cleaned up for clarity. Do not invent a different answer."""
    api_key = get_api_key()
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version="v1alpha"))
    text_model = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash").strip()

    async def generate():
        try:
            stream = await client.aio.models.generate_content_stream(
                model=text_model,
                contents=prompt,
            )
            async for chunk in stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
        except Exception as e:
            print(f"[stream_write] {type(e).__name__}: {e}")
            traceback.print_exc()
            yield f"\n[Error: {e}]"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


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
        payload = [{"id": q.id, "text": q.text} for q in questions]
        print(f"[POST /upload] Parsed questions before return: title={title!r}, count={len(payload)}, questions={payload}")
        return {
            "assignment_id": assignment_id,
            "title": title,
            "questions": payload,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF parse failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.get("/debug-gemini")
async def debug_gemini():
    """Temporary: verify backend can reach Gemini text API with current API key."""
    try:
        api_key = get_api_key()
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version="v1alpha"))
        text_model = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash").strip()
        print(f"[debug-gemini] Attempting text call with model={text_model!r}, key_len={len(api_key)}")
        response = await client.aio.models.generate_content(
            model=text_model,
            contents="Reply with exactly one word: ok",
        )
        result_text = response.text.strip() if response.text else "(empty)"
        print(f"[debug-gemini] SUCCESS: {result_text!r}")
        return {"status": "ok", "model": text_model, "response": result_text}
    except Exception as e:
        print(f"[debug-gemini] FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


@app.get("/test-assignment.pdf")
async def serve_test_assignment():
    """Serve the test assignment PDF from the project root."""
    path = ROOT / "test_assignment.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="test_assignment.pdf not found. Run test_assignment.py to generate it.")
    return FileResponse(path, media_type="application/pdf")



@app.get("/genai.bundle.js", response_class=Response)
async def serve_genai_bundle():
    """Serve the bundled @google/genai SDK for browser (no runtime CDN)."""
    path = ROOT / "frontend" / "genai.bundle.js"
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="Gemini SDK bundle missing. Run: npm install && npm run build:genai, then commit frontend/genai.bundle.js",
        )
    return FileResponse(path, media_type="application/javascript; charset=utf-8")


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
