# Claros

**An AI agent primarily for students with typing difficulties — it reads assignments, guides reasoning through real-time voice conversation, and writes the final answer into the correct question field only after the student has worked it out or stated it.**

![Claros interface screenshot](images/image.png)

## The Problem

Students working through structured assignments typically juggle a worksheet, a help tool, and manual text entry. Each context switch slows them down and breaks their reasoning flow.

For students with typing difficulties — whether due to motor impairments, dyslexia, injury, or other conditions — the manual entry step is a significant barrier. The cognitive work of arriving at an answer is separate from the physical work of typing it, yet most tools treat them as the same step.

Existing AI tutors either give away answers immediately (undermining learning) or require typed input (excluding users who struggle with typing). There is a gap for a tool that preserves guided reasoning while removing the typing bottleneck for the final answer entry step.

Claros closes this gap. It operates directly on the worksheet: guiding the student through each question via voice, then writing the answer into the correct field only when the student is ready.

## How Claros Works

1. **Upload a worksheet PDF** — Claros parses the document and extracts individual questions into an editable worksheet view.
2. **Start a voice session** — Claros connects to a real-time audio session. The student speaks through their microphone and hears Claros respond naturally.
3. **Discuss a question** — Claros guides the student through the problem using Socratic questioning. It does not give the answer directly. Guided reasoning first, not answer generation.
4. **State the final answer** — The student says their answer out loud (e.g., "I think the answer is 42" or "My answer for question 1 is the Civil War").
5. **Ask Claros to write it** — The student says something like "Write my answer for question 1." Claros confirms, then writes the student's own answer into the correct field on the worksheet.
6. **Export as PDF** — Once finished, the student exports all questions and answers as a formatted PDF.

## Core Product Rule

Claros enforces a deliberate constraint: **it will not write an answer until the student has stated it first.**

- If the student asks Claros to write before they have given their answer, Claros responds: *"Tell me your final answer first, then I can write it into the worksheet."*
- This rule is enforced per question. Stating an answer for question 1 does not unlock writing for question 2.
- The answer readiness gate is enforced in the system prompt (Claros is instructed to refuse), the frontend (the write action is only triggered when the student has stated their answer for that question), and the backend (the write API returns 400 if `answer_candidate` is missing or empty).

This is an intentional product decision. Claros is designed to support learning, not to bypass it. The voice interface removes the typing barrier; the readiness gate preserves the reasoning requirement.

## Why This Matters

Many students can reason through a problem but struggle to record their answer in a structured format. Claros lets them do the hard part — thinking — with their voice, and handles the mechanical part — typing the answer into the right box — for them.

This is not about making assignments easier. It is about making them accessible to students who already know the material but are blocked by the input method.

## Features

- **PDF assignment ingestion** — Upload any PDF with "Question N:" formatting. Questions are extracted and rendered as an interactive worksheet.
- **Real-time voice conversation** — Bidirectional audio through Gemini Live. The student speaks and hears Claros respond with natural voice.
- **Socratic guidance** — Claros defaults to teaching mode, asking guiding questions rather than stating answers.
- **Per-question answer readiness tracking** — The frontend tracks whether the student has stated a final answer for each question before allowing a write.
- **Controlled answer writing** — When permitted, the frontend calls the backend write API; the answer is streamed into the correct question field via Gemini text generation.
- **Live transcript** — Both sides of the conversation are transcribed and displayed in real time (from Gemini Live in the browser).
- **PDF export** — Export all questions and current answers as a formatted PDF document.
- **Answer-stated indicator** — The UI shows a visual badge when the student has stated their answer for a given question.
 - **Barge-in / interruption** — If the student starts speaking while Claros is talking, Claros’ audio playback is stopped and the app returns to listening (frontend-level interruption, not full-duplex).
 - **Voice-enabled PDF export** — Saying phrases like “export pdf” or “export this as pdf” from within the voice session can trigger the same PDF export flow as the button.

## Architecture

```
Browser (frontend/index.html)
  │
  ├── GET /api/session-config/{id}  → ephemeral token + system prompt + model
  ├── Direct WebSocket to Gemini Live API (voice: audio in/out, transcription)
  │     via bundled @google/genai JS SDK (served from app; no runtime CDN), ephemeral token from backend
  └── POST /api/write/{id} (streaming) → answer text for a question

FastAPI backend (main.py)
  │
  ├── Ephemeral token creation (auth_tokens.create) for browser–Gemini Live
  ├── Gemini 2.5 Flash (text) for answer writing via generate_content_stream()
  ├── PDF parser (parser.py — PyMuPDF)
  ├── PDF exporter (exporter.py — ReportLab)
  └── Google Cloud Storage (assignment PDF persistence)
```

**Real-time voice** uses **Gemini Live directly from the browser**. The backend does not proxy audio. On "Start Session", the frontend loads the Gemini SDK from the app’s own asset (`/genai.bundle.js`, built from `@google/genai` and checked in), fetches an ephemeral token and session config from `GET /api/session-config/{assignment_id}`, then connects to Gemini Live. The browser captures mic at 16 kHz PCM, sends audio to Gemini, and plays back responses. Transcripts are handled in the client; write detection (e.g. "write my answer for question N") and answer-stated detection run in the frontend.

**Answer writing** is triggered when the user (or Claros) asks to write and the student has already stated their answer for that question. The frontend calls `POST /api/write/{assignment_id}` with conversation context and receives a streaming text response, which is appended into the correct question field.

**Barge-in / interruption** is implemented entirely in the frontend audio playback layer. When new user mic transcription arrives from Gemini Live while Claros audio is playing, the browser stops any scheduled audio buffers, clears the local playback queue, and returns the UI to a listening state. This interrupts current playback; it does not provide overlapping, full-duplex conversation.

**Voice-enabled PDF export** is detected on the user speech path in the browser. When a user utterance for a completed turn clearly matches export-intent phrases (e.g., “export pdf”, “export as pdf”, “export this as pdf”, “download pdf”, “download the pdf”, “save as pdf”, “save this as pdf”, “save it as pdf”), the frontend triggers the same `/export/{assignment_id}` route used by the Export button, as long as at least one answer is non-empty. If no answers are present, the voice export request is blocked with a clear on-screen message instead of calling the backend. Voice export depends on the quality of the transcript; background noise or unusual phrasing may prevent detection.

**Answer readiness gating** is enforced in the frontend (UI and write flow only allow writing once the student has stated their answer, detected via phrase patterns) and in the backend (the write endpoint returns 400 if `answer_candidate` is missing or empty).

**PDF pipeline**: Uploaded PDFs are stored in Google Cloud Storage, parsed with PyMuPDF to extract questions matching a `Question N:` pattern, and can be exported back as formatted PDFs with answers using ReportLab.

## Google Cloud Deployment

Claros is deployed on **Google Cloud Run** as a containerized service.

- **Container image** is built from the project `Dockerfile` (Python 3.11, FastAPI/Uvicorn).
- **Assignment PDFs** are stored in a **Google Cloud Storage** bucket. The upload, session-config, write, and export endpoints use GCS where needed.
- **Gemini API**: The backend holds the Gemini API key and uses it only to (1) create ephemeral tokens for the browser–Gemini Live connection and (2) run the text model for answer writing. The browser never receives the API key; it uses a short-lived token for Live only.
- Cloud Run provides automatic HTTPS, scaling, and a public URL for the frontend.

**Deploying:**

1. **Ensure the Gemini SDK bundle exists** (no runtime CDN). From project root, run once (requires Node 18+):

   ```bash
   npm install && npm run build:genai
   ```

   This writes `frontend/genai.bundle.js`. Commit it so the Docker image includes it. If the bundle is missing, the app will return 503 when the frontend requests it.

2. **Build and push the container** (from project root):

```bash
gcloud builds submit --tag gcr.io/<PROJECT_ID>/claros

# Deploy to Cloud Run
gcloud run deploy claros \
  --image gcr.io/<PROJECT_ID>/claros \
  --platform managed \
  --region <REGION> \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=<key>,GCS_BUCKET_NAME=<bucket>,GOOGLE_CLOUD_PROJECT=<project>
```

Replace `<PROJECT_ID>`, `<REGION>`, `<key>`, `<bucket>`, and `<project>` with your values.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, Uvicorn |
| Voice AI | Gemini Live API (direct from browser via bundled @google/genai; SDK served from app; ephemeral token from backend) |
| Text AI | Gemini 2.5 Flash (backend, for answer writing) |
| PDF parsing | PyMuPDF (fitz) |
| PDF export | ReportLab |
| Storage | Google Cloud Storage |
| Frontend | HTML, CSS, vanilla JavaScript |
| Deployment | Docker, Google Cloud Run |

## Local Setup

**Prerequisites:**
- Python 3.11+
- A Google Cloud project with Cloud Storage enabled
- A Gemini API key
- A GCS bucket for storing uploaded assignments

**Steps:**

```bash
# Clone the repository
git clone <repo-url>
cd Claros

# Install dependencies
pip install -r requirements-server.txt

# Create .env file
cp .env.example .env  # or create manually (see Environment Variables below)

# Generate a test PDF (optional)
python test_assignment.py

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in a browser. Upload a PDF or click "Use Test PDF" to load the test assignment, then click "Start Session" to begin a voice conversation.

**Gemini SDK bundle:** The frontend loads the Gemini SDK from `/genai.bundle.js` (same origin). That file is produced by `npm run build:genai` and checked in under `frontend/genai.bundle.js`. There is no runtime dependency on esm.sh or any other CDN.

**Note:** The browser will request microphone access. Use Chrome or a Chromium-based browser for best WebSocket and audio API support.

## Environment Variables

Create a `.env` file in the project root:

```
GEMINI_API_KEY=<your-gemini-api-key>
GCS_BUCKET_NAME=<your-gcs-bucket-name>
GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
GEMINI_TEXT_MODEL=gemini-2.5-flash
```

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | API key for Google Gemini models (voice and text) |
| `GCS_BUCKET_NAME` | Google Cloud Storage bucket name for storing uploaded PDFs |
| `GOOGLE_CLOUD_PROJECT` | Google Cloud project ID |
| `GEMINI_TEXT_MODEL` | Text model used for answer generation (default: `gemini-2.5-flash`) |

Local development may also require Google Cloud application credentials for GCS access (e.g., `GOOGLE_APPLICATION_CREDENTIALS` or `gcloud auth application-default login`).

## Current Limitations

- **Worksheet-focused scope** — Claros works with structured assignments that follow a "Question N:" format. It is not a general-purpose document editor.
- **Heuristic answer detection** — Answer readiness is determined in the frontend by matching common phrasing patterns (e.g., "my answer is…", "I think it's…"). Unusual phrasings may not be detected.
- **Single-session state** — Conversation and answer readiness are held in memory in the browser. Refreshing the page starts a new session.
- **PDF format dependency** — Question extraction relies on "Question N:" line patterns. PDFs with different formatting may fall back to single-block extraction.
- **Voice model compliance** — The system prompt instructs Claros to follow specific rules, but LLM compliance is not guaranteed. The product rule (write only after answer stated) is enforced in the frontend and backend (write API requires non-empty answer_candidate).
- **Direct Gemini Live** — Voice runs browser → Gemini Live. The frontend loads the `@google/genai` SDK from the app’s own asset (`/genai.bundle.js`); no runtime CDN. The bundle must be built once with `npm run build:genai` and committed.
- **Ephemeral tokens** — Session config uses the Gemini API to create short-lived tokens. If token creation fails (e.g. API or region limitation), the backend returns 500 and the user must retry or check logs.
- **Basic barge-in** — When the user starts speaking while Claros is talking, frontend playback is stopped, the local audio queue is cleared, and the app returns to listening. This improves perceived responsiveness but is still not full-duplex.
- **Heuristic voice export intent** — Voice-triggered export is based on normalized phrase matching (e.g., “export pdf”, “export as pdf”, “download pdf”, “save as pdf”). It only fires when at least one answer is present and may not catch all phrasing variations; it also depends on transcript quality in noisy environments.
- **Browser audio processing** — The browser is asked (via getUserMedia constraints) to enable echo cancellation, noise suppression, automatic gain control, and mono capture. Actual behavior depends on the user’s device and browser support.
- **Browser compatibility** — Requires a modern browser with WebSocket, AudioContext, and getUserMedia. Tested primarily on Chrome.

## Future Improvements

- Richer answer detection using a lightweight classifier instead of regex heuristics
- Session persistence so students can resume interrupted sessions
- Multi-format PDF support beyond "Question N:" patterns
- Accessibility audit with assistive technology users
- Full-duplex interruption handling for smoother barge-in
