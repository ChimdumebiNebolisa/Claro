import { defineConfig } from "vitest/config";
import { resolve } from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "./src"),
    },
  },
  test: {
    globals: true,
    include: [
      "tests/**/*.test.ts",
      "tests/**/*.test.tsx",
      "src/v2/**/*.test.ts",
      "src/v2/**/*.test.tsx",
    ],
    exclude: ["output/**", "node_modules/**"],
    pool: "threads",
    maxWorkers: 1,
    testTimeout: 30_000,
  },
});
