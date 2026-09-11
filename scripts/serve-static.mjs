import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";

const directory = resolve(process.argv[2] ?? "storybook-static");
const port = Number(process.argv[3] ?? 6006);

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".wasm": "application/wasm",
  ".woff2": "font/woff2",
};

function sendPdf(request, response, body) {
  const headers = {
    "accept-ranges": "bytes",
    "content-type": "application/pdf",
  };
  const match = /^bytes=(\d*)-(\d*)$/.exec(request.headers.range ?? "");
  if (!request.headers.range) {
    response.writeHead(200, { ...headers, "content-length": body.length });
    response.end(request.method === "HEAD" ? undefined : body);
    return;
  }

  let start = match?.[1] ? Number(match[1]) : Number.NaN;
  let end = match?.[2] ? Number(match[2]) : body.length - 1;
  if (match && !match[1] && match[2]) {
    start = Math.max(0, body.length - Number(match[2]));
    end = body.length - 1;
  }
  end = Math.min(end, body.length - 1);
  if (!Number.isSafeInteger(start) || start < 0 || start > end) {
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

createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", "http://localhost");
    if (url.pathname === "/api/v2/fixtures/biology/source") {
      const body = await readFile(
        resolve("public", "fixtures", "claros-biology-short-answer.pdf"),
      );
      sendPdf(request, response, body);
      return;
    }
    if (url.pathname === "/api/v2/fixtures/biology/export") {
      const body = await readFile(
        resolve(
          "public",
          "fixtures",
          "claros-biology-short-answer-completed.pdf",
        ),
      );
      sendPdf(request, response, body);
      return;
    }
    if (url.pathname === "/api/v2/fixtures/biology/page-context") {
      const questionId = url.searchParams.get("question_id") ?? "q_01";
      const questionContexts = {
        q_01: {
          question_index: 1,
          rect: {
            origin: { x: 36, y: 195 },
            size: { width: 540, height: 180 },
          },
        },
        q_02: {
          question_index: 2,
          rect: {
            origin: { x: 36, y: 355 },
            size: { width: 540, height: 180 },
          },
        },
        q_03: {
          question_index: 3,
          rect: {
            origin: { x: 36, y: 515 },
            size: { width: 540, height: 150 },
          },
        },
      };
      const context = questionContexts[questionId];
      if (!context) {
        response.writeHead(404).end();
        return;
      }
      const isConfirmedPreview =
        url.searchParams.get("preview") === "confirmed";
      const body = Buffer.from(
        JSON.stringify({
          assignment_id: "fixture-biology",
          assignment_version: 2,
          question_id: questionId,
          question_index: context.question_index,
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
            rect: context.rect,
          },
        }),
      );
      response.writeHead(200, {
        "cache-control": "no-store",
        "content-length": body.length,
        "content-type": "application/json; charset=utf-8",
      });
      response.end(body);
      return;
    }
    const requested = decodeURIComponent(
      url.pathname === "/" ? "/index.html" : url.pathname,
    );
    const filePath = resolve(directory, `.${requested}`);
    if (!filePath.startsWith(`${directory}${sep}`)) {
      response.writeHead(403).end();
      return;
    }
    const fileStat = await stat(filePath);
    if (!fileStat.isFile()) throw new Error("not a file");
    const body = await readFile(filePath);
    response.writeHead(200, {
      "content-length": body.length,
      "content-type":
        contentTypes[extname(filePath)] ?? "application/octet-stream",
    });
    response.end(request.method === "HEAD" ? undefined : body);
  } catch {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
  }
}).listen(port, "127.0.0.1", () => {
  console.log(`Serving ${directory} at http://127.0.0.1:${port}`);
});
