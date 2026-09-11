import { readFile, readdir } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const manifest = JSON.parse(
  await readFile(new URL("dist/.vite/manifest.json", root), "utf8"),
);
const entry = Object.values(manifest).find((item) => item.isEntry);

if (!entry) {
  throw new Error("Vite manifest has no entry chunk");
}

const staticFiles = new Set();
const visit = (item) => {
  if (!item || staticFiles.has(item.file)) return;
  staticFiles.add(item.file);
  for (const key of item.imports ?? []) visit(manifest[key]);
};
visit(entry);

const staticSource = (
  await Promise.all(
    [...staticFiles].map((file) =>
      readFile(new URL(`dist/${file}`, root), "utf8"),
    ),
  )
).join("\n");

if (/(?:@embedpdf|pdfium|realtime-adapter)/i.test(staticSource)) {
  throw new Error(
    "The marketing entry's static import closure contains PDF or Realtime implementation code",
  );
}

const keys = Object.keys(manifest);
for (const expected of [
  "src/v2/document/DocumentCrop.tsx",
  "src/v2/document/WorksheetDialog.tsx",
]) {
  if (!keys.some((key) => key.endsWith(expected))) {
    throw new Error(
      `Expected lazy chunk is absent from the Vite manifest: ${expected}`,
    );
  }
}

if (keys.some((key) => key.endsWith("src/v2/realtime/realtime-adapter.ts"))) {
  throw new Error("The Gate 2 fake Realtime adapter was emitted in production");
}

const assetNames = await readdir(new URL("dist/assets/", root));
const emittedJavaScript = (
  await Promise.all(
    assetNames
      .filter((name) => /\.(?:js|mjs)$/.test(name))
      .map((name) => readFile(new URL(`dist/assets/${name}`, root), "utf8")),
  )
).join("\n");

for (const fakeOnlyMarker of [
  "Plants need sunlight because light energy helps them make food.",
  "fixture-operation-",
]) {
  if (emittedJavaScript.includes(fakeOnlyMarker)) {
    throw new Error(
      `The production bundle contains Gate 2 fake Realtime fixture text: ${fakeOnlyMarker}`,
    );
  }
}

console.log(
  `Verified ${staticFiles.size} marketing entry chunks exclude PDF/Realtime, PDF lazy boundaries exist, and the Gate 2 fake Realtime adapter is absent from production.`,
);
