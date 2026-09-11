import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const writeMode = process.argv.includes("--write");
const pythonCandidates = [
  process.env.CLAROS_PYTHON,
  process.platform === "win32"
    ? join(repositoryRoot, ".venv", "Scripts", "python.exe")
    : join(repositoryRoot, ".venv", "bin", "python"),
  process.platform === "win32" ? "python" : "python3",
].filter(Boolean);

function selectPython() {
  for (const candidate of pythonCandidates) {
    if (candidate.includes("\\") || candidate.includes("/")) {
      if (existsSync(candidate)) return candidate;
      continue;
    }
    const probe = spawnSync(candidate, ["--version"], { stdio: "ignore" });
    if (probe.status === 0) return candidate;
  }
  throw new Error("Python 3.11 environment not found.");
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: repositoryRoot,
    encoding: "utf8",
    stdio: "pipe",
  });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.status !== 0) process.exit(result.status ?? 1);
}

const python = selectPython();
const schemaPath = join(repositoryRoot, "backend", "openapi.json");
const generatedPath = join(repositoryRoot, "src", "v2", "api", "generated.ts");
const openapiCli = join(
  repositoryRoot,
  "node_modules",
  "openapi-typescript",
  "bin",
  "cli.js",
);
const prettierCli = join(
  repositoryRoot,
  "node_modules",
  "prettier",
  "bin",
  "prettier.cjs",
);

run(python, ["scripts/generate-openapi.py", writeMode ? "--write" : "--check"]);

if (writeMode) {
  run(process.execPath, [openapiCli, schemaPath, "--output", generatedPath]);
  run(process.execPath, [prettierCli, "--write", generatedPath]);
  console.log("Wrote src/v2/api/generated.ts");
} else {
  const temporaryDirectory = mkdtempSync(join(tmpdir(), "claros-openapi-"));
  const temporaryTypes = join(temporaryDirectory, "generated.ts");
  try {
    run(process.execPath, [openapiCli, schemaPath, "--output", temporaryTypes]);
    run(process.execPath, [prettierCli, "--write", temporaryTypes]);
    if (
      !existsSync(generatedPath) ||
      readFileSync(generatedPath, "utf8") !==
        readFileSync(temporaryTypes, "utf8")
    ) {
      throw new Error(
        "Generated TypeScript API drift detected. Run `npm run generate:api`.",
      );
    }
  } finally {
    rmSync(temporaryDirectory, { recursive: true, force: true });
  }
  console.log("Generated TypeScript API is current.");
}
