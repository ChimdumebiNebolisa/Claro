import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const args = process.argv.slice(2);
let outputPath;
if (args[0] === "--output") {
  if (args.length < 3) {
    throw new Error("Usage: node extract-pdfjs.mjs [--output <json>] <pdf> [pdf ...]");
  }
  args.shift();
  outputPath = resolve(args.shift());
}
if (args.length === 0) {
  throw new Error("Usage: node extract-pdfjs.mjs [--output <json>] <pdf> [pdf ...]");
}

const pdfs = args.map((path) => resolve(path));
const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const pdfModule = resolve(scriptDirectory, "../../../node_modules/pdfjs-dist/build/pdf.mjs");
const pdfWorker = resolve(scriptDirectory, "../../../node_modules/pdfjs-dist/build/pdf.worker.mjs");
const routes = new Map([
  ["/pdfjs/pdf.mjs", { path: pdfModule, type: "text/javascript" }],
  ["/pdfjs/pdf.worker.mjs", { path: pdfWorker, type: "text/javascript" }],
]);
pdfs.forEach((path, index) => {
  routes.set(`/case/${index}.pdf`, { path, type: "application/pdf" });
});

const server = createServer(async (request, response) => {
  if (request.url === "/") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end("<!doctype html><meta charset=utf-8><title>PDF.js text extractor</title>");
    return;
  }
  const route = routes.get(request.url ?? "");
  if (!route) {
    response.writeHead(404).end();
    return;
  }
  const payload = await readFile(route.path);
  response.writeHead(200, {
    "content-type": route.type,
    "content-length": payload.length,
    "cache-control": "no-store",
  });
  response.end(payload);
});

await new Promise((done) => server.listen(0, "127.0.0.1", done));
const address = server.address();
if (!address || typeof address === "string") {
  throw new Error("Could not start PDF.js extraction server");
}
const baseUrl = `http://127.0.0.1:${address.port}`;
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

const results = [];
try {
  for (const [index, path] of pdfs.entries()) {
    const pageTexts = await page.evaluate(async ({ moduleUrl, workerUrl, pdfUrl }) => {
      const pdfjs = await import(moduleUrl);
      pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
      const document = await pdfjs.getDocument({ url: pdfUrl }).promise;
      const texts = [];
      for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
        const pdfPage = await document.getPage(pageNumber);
        const textContent = await pdfPage.getTextContent();
        texts.push(textContent.items
          .map((item) => "str" in item ? item.str : "")
          .join(""));
        pdfPage.cleanup();
      }
      await document.destroy();
      return texts;
    }, {
      moduleUrl: `${baseUrl}/pdfjs/pdf.mjs`,
      workerUrl: `${baseUrl}/pdfjs/pdf.worker.mjs`,
      pdfUrl: `${baseUrl}/case/${index}.pdf`,
    });
    results.push({ file: basename(path), pageTexts, text: pageTexts.join("\n") });
  }
} finally {
  await browser.close();
  await new Promise((done, reject) => server.close((error) => error ? reject(error) : done()));
}

const json = `${JSON.stringify(results, null, 2)}\n`;
if (outputPath) {
  await writeFile(outputPath, json, "utf8");
}
process.stdout.write(json);
