import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";
import { chromium } from "playwright";

if (process.argv.length !== 3) process.exit(2);

const jobRoot = resolve(process.argv[2]);
const scriptRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptRoot, "../../..");
const job = JSON.parse(await readFile(resolve(jobRoot, "job.json"), "utf8"));
const pdfPath = resolve(jobRoot, "quarantine", "derivative.pdf");
const resultPath = resolve(jobRoot, "pdfjs-status.json");
const pdfModule = resolve(repoRoot, "node_modules/pdfjs-dist/build/pdf.mjs");
const pdfWorker = resolve(repoRoot, "node_modules/pdfjs-dist/build/pdf.worker.mjs");

const routes = new Map([
  ["/pdfjs/pdf.mjs", { path: pdfModule, type: "text/javascript" }],
  ["/pdfjs/pdf.worker.mjs", { path: pdfWorker, type: "text/javascript" }],
  ["/document.pdf", { path: pdfPath, type: "application/pdf" }],
]);
const server = createServer(async (request, response) => {
  const route = routes.get(request.url ?? "");
  if (!route) {
    response.writeHead(404).end();
    return;
  }
  try {
    const payload = await readFile(route.path);
    response.writeHead(200, {
      "content-type": route.type,
      "content-length": payload.length,
      "cache-control": "no-store",
    });
    response.end(payload);
  } catch {
    response.writeHead(500).end();
  }
});

let browser;
try {
  await new Promise((accept) => server.listen(0, "127.0.0.1", accept));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("listen failed");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(`${baseUrl}/pdfjs/pdf.mjs`, { waitUntil: "domcontentloaded" }).catch(() => {});
  const result = await page.evaluate(async ({ moduleUrl, workerUrl, pdfUrl, answers, sourcePages }) => {
    const pdfjs = await import(moduleUrl);
    pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
    const document = await pdfjs.getDocument({ url: pdfUrl }).promise;
    const pageText = [];
    let renderedPages = 0;
    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
      const pdfPage = await document.getPage(pageNumber);
      const text = await pdfPage.getTextContent();
      pageText.push(text.items.map((item) => "str" in item ? item.str : "").join(" "));
      const viewport = pdfPage.getViewport({ scale: 0.5 });
      const canvas = window.document.createElement("canvas");
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("canvas unavailable");
      await pdfPage.render({ canvasContext: context, viewport }).promise;
      renderedPages += 1;
      pdfPage.cleanup();
    }
    let exact = true;
    for (const answer of answers) {
      if (answer.placement_classification === "inline") {
        const actual = pageText[answer.page_number - 1] ?? "";
        for (const line of answer.lines) {
          if (!actual.includes(line.text)) exact = false;
        }
      } else {
        const actual = pageText.slice(sourcePages).join("\n");
        if (!tokensInOrderInner(answer.committed_text, actual)) exact = false;
      }
    }
    await document.destroy();
    return { pageCount: pageText.length, renderedPages, exact };

    function tokensInOrderInner(expected, actual) {
      const wanted = expected.trim().split(/\s+/u);
      const found = actual.trim().split(/\s+/u);
      let cursor = 0;
      for (const token of wanted) {
        while (cursor < found.length && found[cursor] !== token) cursor += 1;
        if (cursor >= found.length) return false;
        cursor += 1;
      }
      return true;
    }
  }, {
    moduleUrl: `${baseUrl}/pdfjs/pdf.mjs`,
    workerUrl: `${baseUrl}/pdfjs/pdf.worker.mjs`,
    pdfUrl: `${baseUrl}/document.pdf`,
    answers: job.answers,
    sourcePages: job.source.page_count,
  });
  if (!result.exact || result.renderedPages !== result.pageCount) throw new Error("validation failed");
  await writeFile(resultPath, JSON.stringify({
    schema_version: 1,
    status: "ok",
    job_id: job.job_id,
    validator: "pdfjs",
    page_count: result.pageCount,
    generated_text_exact: true,
    placement_exact: null,
    source_preserved: null,
    rendered_pages: result.renderedPages,
  }));
} catch {
  await writeFile(resultPath, JSON.stringify({ schema_version: 1, status: "fail", code: "pdfjs_validation" }));
} finally {
  if (browser) await browser.close();
  await new Promise((accept) => server.close(() => accept()));
}
