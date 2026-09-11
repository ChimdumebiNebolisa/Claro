import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import process from "node:process";
import { chromium } from "playwright";

if (process.argv.length !== 4) {
  throw new Error("Usage: node validate-pdfjs.mjs <cases.json> <results.json>");
}

const casesPath = resolve(process.argv[2]);
const resultsPath = resolve(process.argv[3]);
const cases = JSON.parse(await readFile(casesPath, "utf8"));
const pdfModule = resolve("../../node_modules/pdfjs-dist/build/pdf.mjs");
const pdfWorker = resolve("../../node_modules/pdfjs-dist/build/pdf.worker.mjs");

const routes = new Map([
  ["/pdfjs/pdf.mjs", { path: pdfModule, type: "text/javascript" }],
  ["/pdfjs/pdf.worker.mjs", { path: pdfWorker, type: "text/javascript" }],
]);
for (const [index, item] of cases.entries()) {
  routes.set(`/case/${index}.pdf`, { path: item.path, type: "application/pdf" });
}

const server = createServer(async (request, response) => {
  if (request.url === "/") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end("<!doctype html><meta charset=utf-8><title>PDF.js validator</title>");
    return;
  }
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
  } catch (error) {
    response.writeHead(500, { "content-type": "text/plain" });
    response.end(error instanceof Error ? error.message : "read failed");
  }
});

await new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
const address = server.address();
if (!address || typeof address === "string") {
  throw new Error("Could not start local PDF.js validation server");
}
const baseUrl = `http://127.0.0.1:${address.port}`;
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

const results = [];
try {
  for (const [index, item] of cases.entries()) {
    try {
      const rendered = await page.evaluate(
        async ({
          moduleUrl,
          workerUrl,
          pdfUrl,
          password,
          overlayPage,
          expectedOverlayTexts,
        }) => {
          const pdfjs = await import(moduleUrl);
          pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
          const loadingTask = pdfjs.getDocument({ url: pdfUrl, password: password || undefined });
          const document = await loadingTask.promise;
          let renderedPages = 0;
          let nonBlankSamples = 0;
          let overlayText = "";
          for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
            const pdfPage = await document.getPage(pageNumber);
            if (pageNumber === overlayPage) {
              const textContent = await pdfPage.getTextContent();
              overlayText = textContent.items
                .map((entry) => "str" in entry ? entry.str : "")
                .join("");
            }
            const viewport = pdfPage.getViewport({ scale: 1 });
            const canvas = window.document.createElement("canvas");
            canvas.width = Math.ceil(viewport.width);
            canvas.height = Math.ceil(viewport.height);
            const context = canvas.getContext("2d", { alpha: false, willReadFrequently: true });
            if (!context) throw new Error("Canvas 2D context unavailable");
            await pdfPage.render({ canvasContext: context, viewport }).promise;
            const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
            const stride = Math.max(4, Math.floor(pixels.length / 4096 / 4) * 4);
            for (let offset = 0; offset < pixels.length; offset += stride) {
              if (pixels[offset] < 250 || pixels[offset + 1] < 250 || pixels[offset + 2] < 250) {
                nonBlankSamples += 1;
              }
            }
            renderedPages += 1;
            pdfPage.cleanup();
          }
          const missingOverlayTexts = expectedOverlayTexts
            .filter((expectedText) => !overlayText.includes(expectedText));
          await document.destroy();
          return {
            pageCount: document.numPages,
            renderedPages,
            nonBlankSamples,
            overlayTextPresent: missingOverlayTexts.length === 0,
            missingOverlayTexts,
            extractedOverlayText: overlayText,
          };
        },
        {
          moduleUrl: `${baseUrl}/pdfjs/pdf.mjs`,
          workerUrl: `${baseUrl}/pdfjs/pdf.worker.mjs`,
          pdfUrl: `${baseUrl}/case/${index}.pdf`,
          password: item.password,
          overlayPage: item.overlayPage,
          expectedOverlayTexts: item.expectedOverlayTexts,
        },
      );
      const expected = item.expectedPages;
      const pass = rendered.pageCount === expected
        && rendered.renderedPages === expected
        && rendered.nonBlankSamples > 0;
      results.push({
        fixture: item.fixture,
        status: pass ? "PASS" : "FAIL",
        pageCount: rendered.pageCount,
        renderedPages: rendered.renderedPages,
        overlayTextPresent: rendered.overlayTextPresent,
        extractedOverlayText: rendered.extractedOverlayText,
        detail: pass
          ? `${rendered.renderedPages}/${expected} pages rendered to canvas; exact overlay extraction ${rendered.overlayTextPresent ? "PASS" : `FAIL (${rendered.missingOverlayTexts.join(", ")})`}`
          : `expected ${expected}; loaded ${rendered.pageCount}; rendered ${rendered.renderedPages}; nonblank samples ${rendered.nonBlankSamples}`,
      });
    } catch (error) {
      results.push({
        fixture: item.fixture,
        status: "FAIL",
        pageCount: 0,
        renderedPages: 0,
        overlayTextPresent: false,
        extractedOverlayText: "",
        detail: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
      });
    }
  }
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.close((error) => error ? rejectClose(error) : resolveClose()));
}

await import("node:fs/promises").then(({ writeFile }) =>
  writeFile(resultsPath, `${JSON.stringify(results, null, 2)}\n`, "utf8"),
);
console.log(`PDF.js rendered ${results.filter((item) => item.status === "PASS").length}/${results.length} derivatives`);
