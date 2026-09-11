import { access, readFile } from "node:fs/promises";

const packageJson = JSON.parse(
  await readFile(new URL("../package.json", import.meta.url), "utf8"),
);
const lock = JSON.parse(
  await readFile(new URL("../package-lock.json", import.meta.url), "utf8"),
);

const required = {
  "@embedpdf/core": ["2.15.0", "MIT"],
  "@embedpdf/engines": ["2.15.0", "MIT"],
  "@embedpdf/models": ["2.15.0", "MIT"],
  "@embedpdf/pdfium": ["2.15.0", "MIT"],
  "@embedpdf/plugin-document-manager": ["2.15.0", "MIT"],
  "@embedpdf/plugin-render": ["2.15.0", "MIT"],
  "@embedpdf/react-pdf-viewer": ["2.15.0", "MIT"],
  "@tanstack/react-query": ["5.102.8", "MIT"],
  "@untitledui/file-icons": ["0.0.9", "MIT"],
  "@untitledui/icons": ["0.0.22", "MIT"],
  motion: ["12.43.0", "MIT"],
  "openapi-fetch": ["0.17.0", "MIT"],
  "react-aria": ["3.52.0", "Apache-2.0"],
  "react-aria-components": ["1.21.0", "Apache-2.0"],
  msw: ["2.15.0", "MIT"],
  "msw-storybook-addon": ["3.0.0", "MIT"],
  "openapi-typescript": ["7.13.0", "MIT"],
};

const direct = { ...packageJson.dependencies, ...packageJson.devDependencies };
const problems = [];

if (packageJson.engines?.node !== ">=22.12 <23") {
  problems.push(
    `Node engine must be >=22.12 <23; found ${packageJson.engines?.node ?? "missing"}`,
  );
}

for (const [name, declared] of Object.entries(direct)) {
  if (/^[~^*]|\s|\|/.test(declared)) {
    problems.push(`${name} is not exactly pinned (${declared})`);
  }
}

for (const [name, [version, license]] of Object.entries(required)) {
  if (direct[name] !== version) {
    problems.push(
      `${name} must be declared at ${version}; found ${direct[name] ?? "missing"}`,
    );
  }
  const locked = lock.packages?.[`node_modules/${name}`];
  if (locked?.version !== version) {
    problems.push(
      `${name} lock must resolve ${version}; found ${locked?.version ?? "missing"}`,
    );
  }
  if (locked?.license !== license) {
    problems.push(
      `${name} license must be ${license}; found ${locked?.license ?? "missing"}`,
    );
  }
}

for (const legacy of [
  "radix-ui",
  "react-pdf",
  "react-dropzone",
  "react-resizable-panels",
  "lucide-react",
]) {
  if (!packageJson.dependencies[legacy]) {
    problems.push(`${legacy} must remain present until the Gate 6 cutover`);
  }
}

for (const component of [
  "application/file-upload/file-upload-base.tsx",
  "application/modals/modal.tsx",
  "application/loading-indicator/loading-indicator.tsx",
  "application/empty-state/empty-state.tsx",
  "base/textarea/textarea.tsx",
  "base/radio-buttons/radio-buttons.tsx",
  "base/badges/badges.tsx",
]) {
  try {
    await access(new URL(`../src/components/${component}`, import.meta.url));
  } catch {
    problems.push(`Approved Untitled component is missing: ${component}`);
  }
}

if (problems.length) {
  throw new Error(
    `Gate 1 dependency verification failed:\n- ${problems.join("\n- ")}`,
  );
}

console.log(
  `Verified ${Object.keys(required).length} exact Gate 1 versions/licenses, seven approved Untitled primitives, Node 22, and retained legacy dependencies.`,
);
