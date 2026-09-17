import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Dedicated test config (kept apart from vite.config.ts so the production build
 * never loads jsdom/testing-library). The alias mirrors the app config so tests
 * import exactly what the app imports.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
    restoreMocks: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.{test,spec}.{ts,tsx}", "src/test/**", "src/**/*.d.ts"],
      // Smoke-level floor: the suite guards the shared primitives and the
      // highest-traffic pages. Raise it as page-level tests land.
      thresholds: { lines: 15, functions: 15, statements: 15, branches: 10 },
    },
  },
});
