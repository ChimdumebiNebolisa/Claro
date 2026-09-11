import { spawn, spawnSync, type ChildProcessByStdio } from "node:child_process";
import { createServer } from "node:net";
import { delimiter, join } from "node:path";
import type { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../../../", import.meta.url));
const launcherPath = join(
  repositoryRoot,
  "tests",
  "e2e-gate3",
  "support",
  "fastapi_server.py",
);
const defaultPythonPath =
  process.platform === "win32"
    ? join(repositoryRoot, ".venv", "Scripts", "python.exe")
    : join(repositoryRoot, ".venv", "bin", "python");

const delay = (milliseconds: number) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

export type Gate3FastApiServer = {
  origin: string;
  logs: () => string;
  stop: () => Promise<void>;
};

export async function reserveLoopbackPort(): Promise<number> {
  const listener = createServer();
  await new Promise<void>((resolve, reject) => {
    listener.once("error", reject);
    listener.listen(0, "127.0.0.1", resolve);
  });
  const address = listener.address();
  if (!address || typeof address === "string") {
    listener.close();
    throw new Error("Could not reserve a loopback port for the Gate 3 server");
  }
  await new Promise<void>((resolve, reject) => {
    listener.close((error) => (error ? reject(error) : resolve()));
  });
  return address.port;
}

export async function startGate3FastApiServer(options: {
  port: number;
  storagePath: string;
}): Promise<Gate3FastApiServer> {
  const pythonPath = process.env.CLAROS_GATE3_PYTHON ?? defaultPythonPath;
  const child = spawn(pythonPath, [launcherPath], {
    cwd: repositoryRoot,
    env: {
      ...process.env,
      CLAROS_GATE3_PORT: String(options.port),
      CLAROS_GATE3_STORAGE_PATH: options.storagePath,
      PYTHONPATH: [repositoryRoot, process.env.PYTHONPATH]
        .filter(Boolean)
        .join(delimiter),
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  let output = "";
  const appendOutput = (chunk: Buffer) => {
    output = `${output}${chunk.toString("utf8")}`.slice(-24_000);
  };
  child.stdout.on("data", appendOutput);
  child.stderr.on("data", appendOutput);

  const origin = `http://localhost:${options.port}`;
  const healthOrigin = `http://127.0.0.1:${options.port}`;
  const startupDeadline = Date.now() + 45_000;
  while (Date.now() < startupDeadline) {
    if (child.exitCode !== null) {
      throw new Error(
        `Gate 3 FastAPI server exited with ${child.exitCode} during startup.\n${output}`,
      );
    }
    try {
      const response = await fetch(`${healthOrigin}/health`);
      if (response.ok) {
        return {
          origin,
          logs: () => output,
          stop: () => stopChildProcess(child),
        };
      }
    } catch {
      // The socket is expected to refuse connections until Uvicorn is ready.
    }
    await delay(150);
  }

  await stopChildProcess(child);
  throw new Error(`Gate 3 FastAPI server did not become ready.\n${output}`);
}

async function stopChildProcess(
  child: ChildProcessByStdio<null, Readable, Readable>,
): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;

  const exited = new Promise<boolean>((resolve) => {
    child.once("exit", () => resolve(true));
  });
  child.kill("SIGTERM");
  if (await Promise.race([exited, delay(5_000).then(() => false)])) return;

  if (process.platform === "win32" && child.pid !== undefined) {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
  } else {
    child.kill("SIGKILL");
  }
  await Promise.race([exited, delay(5_000)]);
}

export function inspectPdf(pdfPath: string): {
  pageCount: number;
  warnings: string[];
} {
  const pythonPath = process.env.CLAROS_GATE3_PYTHON ?? defaultPythonPath;
  const verifierPath = join(
    repositoryRoot,
    "tests",
    "e2e-gate3",
    "support",
    "verify_pdf.py",
  );
  const result = spawnSync(pythonPath, [verifierPath, pdfPath], {
    cwd: repositoryRoot,
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) {
    throw new Error(
      `Downloaded PDF did not reopen cleanly.\n${result.stderr || result.stdout}`,
    );
  }
  return JSON.parse(result.stdout) as {
    pageCount: number;
    warnings: string[];
  };
}
