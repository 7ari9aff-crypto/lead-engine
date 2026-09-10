import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

const BACKEND = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      // All /api/* paths go through (no rewrite — backend uses /api/*)
      "/api": { target: BACKEND, changeOrigin: true },
      // Other backend paths
      "/providers": { target: BACKEND, changeOrigin: true },
      "/leads": { target: BACKEND, changeOrigin: true },
      "/jobs": { target: BACKEND, changeOrigin: true },
      "/benchmark": { target: BACKEND, changeOrigin: true },
      "/verify-email": { target: BACKEND, changeOrigin: true },
      "/report": { target: BACKEND, changeOrigin: true },
      "/sync-supabase": { target: BACKEND, changeOrigin: true },
      "/mcp": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
      "/docs": { target: BACKEND, changeOrigin: true },
      "/openapi.json": { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    target: "es2022",
  },
});
