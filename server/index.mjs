import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import {
  buildWorksheetPdf,
  createDemoWorksheet,
  demoPdf,
  demoSourceHash,
} from "./fixture.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const assignments = new Map();
const plans = new Map();
const sessions = new Map();
const MAX_REQUEST_BYTES = 10 * 1024 * 1024;
const planInputSchema = z.object({
  questionId: z.string().min(1).max(100),
  answerText: z.string().max(2000),
});
const commitInputSchema = z.object({ planToken: z.string().min(20).max(200) });

function json(response, status, payload, headers = {}) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    ...headers,
  });
  response.end(JSON.stringify(payload));
}

function pdfRange(request, response, body, filename) {
  const headers = {
    "accept-ranges": "bytes",
    "content-disposition": `inline; filename="${filename}"`,
    "content-type": "application/pdf",
  };
  const range = request.headers.range;
  if (!range) {
    response.writeHead(200, { ...headers, "content-length": body.length });
    response.end(request.method === "HEAD" ? undefined : body);
    return;
  }

  const match = /^bytes=(\d*)-(\d*)$/.exec(range);
  let start = match?.[1] ? Number(match[1]) : Number.NaN;
  let end = match?.[2] ? Number(match[2]) : body.length - 1;
  if (match && !match[1] && match[2]) {
    const suffixLength = Number(match[2]);
    start = Math.max(0, body.length - suffixLength);
    end = body.length - 1;
  }
  end = Math.min(end, body.length - 1);
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    start < 0 ||
    start > end
  ) {
    response.writeHead(416, {
      ...headers,
      "content-range": `bytes */${body.length}`,
    });
    response.end();
    return;
  }

  const chunk = body.subarray(start, end + 1);
  response.writeHead(206, {
    ...headers,
    "content-length": chunk.length,
    "content-range": `bytes ${start}-${end}/${body.length}`,
  });
  response.end(request.method === "HEAD" ? undefined : chunk);
}

function cookieValue(request, name) {
  const cookies =
    request.headers.cookie?.split(";").map((part) => part.trim()) ?? [];
  const value = cookies.find((part) => part.startsWith(`${name}=`));
  return value?.slice(name.length + 1) ?? null;
}

function sessionFor(request, response) {
  let sessionId = cookieValue(request, "claros_sid");
  if (!sessionId || !sessions.has(sessionId)) {
    sessionId = randomBytes(24).toString("base64url");
    sessions.set(sessionId, new Set());
    response.setHeader(
      "set-cookie",
      `claros_sid=${sessionId}; HttpOnly; SameSite=Lax; Path=/`,
    );
  }
  return { sessionId, assignmentIds: sessions.get(sessionId) };
}

async function bodyBuffer(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.from(chunk);
    size += buffer.length;
    if (size > MAX_REQUEST_BYTES) {
      const error = new Error("request too large");
      error.statusCode = 413;
      throw error;
    }
    chunks.push(buffer);
  }
  return Buffer.concat(chunks);
}

async function bodyJson(request) {
  const body = await bodyBuffer(request);
  try {
    return JSON.parse(body.toString("utf8"));
  } catch {
    return {};
  }
}

function extractPdf(body) {
  const start = body.indexOf(Buffer.from("%PDF-"));
  const endMarker = Buffer.from("%%EOF");
  const endIndex = body.lastIndexOf(endMarker);
  if (start < 0 || endIndex < start) return null;
  let end = endIndex + endMarker.length;
  if (body[end] === 13 && body[end + 1] === 10) end += 2;
  else if (body[end] === 10) end += 1;
  return body.subarray(start, end);
}

function newAssignment(session, response) {
  const id = `assignment_${randomBytes(8).toString("hex")}`;
  const worksheet = createDemoWorksheet();
  const assignment = {
    id,
    worksheet,
    committedAnswers: [],
    activeQuestionId: worksheet.questions[0].id,
  };
  assignments.set(id, assignment);
  session.assignmentIds.add(id);
  return assignment;
}

function ownedAssignment(request, response, id) {
  const sessionId = cookieValue(request, "claros_sid");
  const owned = sessionId && sessions.get(sessionId)?.has(id);
  const assignment = assignments.get(id);
  if (!owned || !assignment) {
    json(response, 404, {
      error: {
        code: "assignment_not_found",
        message: "This worksheet session is no longer available.",
      },
    });
    return null;
  }
  return assignment;
}

function planFor(assignment, questionId, answerText) {
  const question = assignment.worksheet.questions.find(
    (item) => item.id === questionId,
  );
  if (!question || typeof answerText !== "string") return null;
  const lineCount = answerText
    .split(/\r?\n/)
    .reduce(
      (total, line) => total + Math.max(1, Math.ceil(line.length / 58)),
      0,
    );
  const availableLines = Math.max(
    1,
    Math.floor(question.answerRegion.bounds.height / 18),
  );
  const placement =
    lineCount <= availableLines
      ? "fits_in_answer_area"
      : lineCount <= availableLines + 5
        ? "requires_continuation_page"
        : "blocked";
  const planToken = randomBytes(32).toString("base64url");
  const expiresAt = new Date(Date.now() + 5 * 60_000).toISOString();
  const plan = { questionId, answerText, placement, planToken, expiresAt };
  plans.set(planToken, { assignmentId: assignment.id, plan });
  return plan;
}

function safeEqual(a, b) {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

async function handleApi(request, response, pathname, searchParams) {
  if (request.method === "GET" && pathname === "/health") {
    json(response, 200, { status: "ok" });
    return true;
  }
  if (
    (request.method === "GET" || request.method === "HEAD") &&
    pathname === "/api/v2/fixtures/biology/source"
  ) {
    const body = await readFile(
      join(root, "public", "fixtures", "claros-biology-short-answer.pdf"),
    );
    pdfRange(request, response, body, "claros-biology-short-answer.pdf");
    return true;
  }
  if (
    (request.method === "GET" || request.method === "HEAD") &&
    pathname === "/api/v2/fixtures/biology/export"
  ) {
    const body = await readFile(
      join(
        root,
        "public",
        "fixtures",
        "claros-biology-short-answer-completed.pdf",
      ),
    );
    pdfRange(request, response, body, "biology-short-answer-completed.pdf");
    return true;
  }
  if (
    request.method === "GET" &&
    pathname === "/api/v2/fixtures/biology/page-context"
  ) {
    const questionId = searchParams.get("question_id") ?? "q_01";
    const questionContexts = {
      q_01: {
        question_index: 1,
        rect: { origin: { x: 36, y: 195 }, size: { width: 540, height: 180 } },
      },
      q_02: {
        question_index: 2,
        rect: { origin: { x: 36, y: 355 }, size: { width: 540, height: 180 } },
      },
      q_03: {
        question_index: 3,
        rect: { origin: { x: 36, y: 515 }, size: { width: 540, height: 150 } },
      },
    };
    const pageContext = questionContexts[questionId];
    if (!pageContext) {
      json(response, 404, {
        error: {
          code: "question_not_found",
          message: "Verified source context is unavailable for this question.",
          recoverable: false,
        },
      });
      return true;
    }
    const isConfirmedPreview = searchParams.get("preview") === "confirmed";
    json(response, 200, {
      assignment_id: "fixture-biology",
      assignment_version: 2,
      question_id: questionId,
      question_index: pageContext.question_index,
      page_number: 1,
      source_sha256: isConfirmedPreview
        ? "3f08953dc8248758d0efac041900053f1866512d7b1d2453c224f6963cf14b05"
        : "ccba948e849e849b80f4ce8f9d218e726b93a2efbb9eb730aabd5187e743b8d6",
      source_url: isConfirmedPreview
        ? "/api/v2/fixtures/biology/export"
        : "/api/v2/fixtures/biology/source",
      source_status: isConfirmedPreview
        ? "completed_copy_preview"
        : "original_page_unchanged",
      render_crop: {
        page_index: 0,
        rect: pageContext.rect,
      },
    });
    return true;
  }
  if (request.method === "GET" && pathname === "/api/v1/demo.pdf") {
    response.writeHead(200, {
      "content-type": "application/pdf",
      "content-disposition": 'attachment; filename="ecosystems-worksheet.pdf"',
    });
    response.end(demoPdf);
    return true;
  }
  if (request.method === "GET" && pathname === "/api/v1/demo") {
    const session = sessionFor(request, response);
    const assignment = newAssignment(session, response);
    json(response, 200, { assignment });
    return true;
  }
  const assignmentMatch = pathname.match(
    /^\/api\/v1\/assignments\/([^/]+)(?:\/(plan|commit|export))?$/,
  );
  if (request.method === "POST" && pathname === "/api/v1/assignments") {
    const session = sessionFor(request, response);
    const body = await bodyBuffer(request);
    const pdf = extractPdf(body);
    if (!pdf) {
      json(response, 422, {
        error: {
          code: "document_parse_failed",
          message:
            "Claros could not read this upload as a PDF with selectable text.",
        },
      });
      return true;
    }
    const hash = createHash("sha256").update(pdf).digest("hex");
    if (hash !== demoSourceHash) {
      json(response, 422, {
        error: {
          code: "document_validation_failed",
          message:
            "This worksheet is outside Claros' supported short-answer contract. Download the sample worksheet to try the complete flow.",
        },
      });
      return true;
    }
    const assignment = newAssignment(session, response);
    json(response, 201, { assignment });
    return true;
  }
  if (!assignmentMatch) return false;
  const [, assignmentId, action] = assignmentMatch;
  const assignment = ownedAssignment(request, response, assignmentId);
  if (!assignment) return true;
  if (request.method === "GET" && !action) {
    json(response, 200, { assignment });
    return true;
  }
  if (request.method === "POST" && action === "plan") {
    const input = await bodyJson(request);
    const parsed = planInputSchema.safeParse(input);
    const plan = parsed.success
      ? planFor(assignment, parsed.data.questionId, parsed.data.answerText)
      : null;
    if (!plan) {
      json(response, 422, {
        error: {
          code: "document_validation_failed",
          message:
            "That answer could not be associated with the active question.",
        },
      });
      return true;
    }
    json(response, 200, { plan });
    return true;
  }
  if (request.method === "POST" && action === "commit") {
    const input = await bodyJson(request);
    const parsed = commitInputSchema.safeParse(input);
    const stored = parsed.success ? plans.get(parsed.data.planToken) : null;
    if (
      !stored ||
      stored.assignmentId !== assignment.id ||
      new Date(stored.plan.expiresAt) < new Date()
    ) {
      json(response, 409, {
        error: {
          code: "stale_plan",
          message:
            "This review is out of date. Review the exact answer again before adding it.",
        },
      });
      return true;
    }
    if (
      !safeEqual(stored.plan.planToken, parsed.data.planToken) ||
      stored.plan.placement === "blocked"
    ) {
      json(response, 409, {
        error: {
          code: "placement_blocked",
          message: "Placement needs attention before this answer can be added.",
        },
      });
      return true;
    }
    const existing = assignment.committedAnswers.find(
      (item) => item.questionId === stored.plan.questionId,
    );
    const committed = {
      questionId: stored.plan.questionId,
      text: stored.plan.answerText,
      placement: stored.plan.placement,
      revision: (existing?.revision ?? 0) + 1,
      committedAt: new Date().toISOString(),
    };
    assignment.committedAnswers = [
      ...assignment.committedAnswers.filter(
        (item) => item.questionId !== committed.questionId,
      ),
      committed,
    ];
    assignment.activeQuestionId =
      assignment.worksheet.questions.find(
        (item) =>
          item.index ===
          (assignment.worksheet.questions.find(
            (q) => q.id === committed.questionId,
          )?.index ?? 0) +
            1,
      )?.id ?? committed.questionId;
    json(response, 200, { assignment });
    return true;
  }
  if (request.method === "GET" && action === "export") {
    if (
      assignment.committedAnswers.length !==
      assignment.worksheet.questions.length
    ) {
      json(response, 409, {
        error: {
          code: "incomplete_assignment",
          message:
            "Finish each question before exporting the completed worksheet.",
        },
      });
      return true;
    }
    if (
      assignment.committedAnswers.some((item) =>
        /[^\x20-\x7E\n\r\t]/.test(item.text),
      )
    ) {
      json(response, 422, {
        error: {
          code: "unicode_rendering_failed",
          message:
            "This answer contains characters the current PDF renderer cannot safely reproduce. Edit the answer and review it again.",
        },
      });
      return true;
    }
    const answers = assignment.worksheet.questions.map(
      (question) =>
        assignment.committedAnswers.find(
          (answer) => answer.questionId === question.id,
        )?.text ?? "",
    );
    const pdf = buildWorksheetPdf(answers);
    response.writeHead(200, {
      "content-type": "application/pdf",
      "content-disposition":
        'attachment; filename="claros-completed-worksheet.pdf"',
    });
    response.end(pdf);
    return true;
  }
  return false;
}

async function serveStatic(request, response, pathname) {
  const requested = pathname === "/" ? "/index.html" : pathname;
  const filePath = join(root, "dist", requested.replace(/^\//, ""));
  try {
    const fileStat = await stat(filePath);
    if (!fileStat.isFile()) throw new Error("not a file");
    const body = await readFile(filePath);
    const ext = extname(filePath);
    const contentType =
      ext === ".html"
        ? "text/html; charset=utf-8"
        : ext === ".js" || ext === ".mjs"
          ? "text/javascript"
          : ext === ".css"
            ? "text/css"
            : ext === ".wasm"
              ? "application/wasm"
              : ext === ".woff2"
                ? "font/woff2"
                : ext === ".png"
                  ? "image/png"
                  : ext === ".svg"
                    ? "image/svg+xml"
                    : "application/octet-stream";
    if (ext === ".pdf") {
      pdfRange(
        request,
        response,
        body,
        requested.split("/").at(-1) || "worksheet.pdf",
      );
      return;
    }
    response.writeHead(200, { "content-type": contentType });
    response.end(body);
  } catch {
    if (
      request.method === "GET" &&
      !pathname.startsWith("/api/") &&
      !extname(pathname)
    ) {
      const body = await readFile(join(root, "dist", "index.html"));
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      response.end(body);
      return;
    }
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  for (const [name, value] of Object.entries({
    "content-security-policy":
      "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(), microphone=(self), geolocation=()",
  }))
    response.setHeader(name, value);
  try {
    if (!(await handleApi(request, response, url.pathname, url.searchParams)))
      await serveStatic(request, response, url.pathname);
  } catch (error) {
    console.error(
      "request failed",
      error instanceof Error ? error.message : "unknown error",
    );
    if (!response.headersSent) {
      const status = error?.statusCode === 413 ? 413 : 500;
      const code = status === 413 ? "upload_too_large" : "internal_error";
      const message =
        status === 413
          ? "This upload is larger than Claros supports."
          : "Claros could not complete that action.";
      json(response, status, { error: { code, message } });
    }
  }
});

const port = Number(process.env.PORT ?? 8787);
server.listen(port, () =>
  console.log(`Claros API listening on http://localhost:${port}`),
);
