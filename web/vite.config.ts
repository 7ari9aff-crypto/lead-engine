import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const BACKEND = env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

  return {
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
        "/api": { target: BACKEND, changeOrigin: true },
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
  };
});
