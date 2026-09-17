import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // BACKEND_URL is server-side only (not exposed to the browser).
  // VITE_BACKEND_URL is kept as a fallback for local dev workflows.
  const BACKEND = env.BACKEND_URL || env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

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
      chunkSizeWarningLimit: 700,
      rollupOptions: {
        output: {
          // Split heavy libraries into their own long-lived chunks so the entry
          // stays small and the browser can fetch them in parallel. Everything
          // here is a top-level dependency of a lazy route, so it is only
          // requested once that route is opened (except the react/ui pair).
          manualChunks(id) {
            if (id.includes("node_modules")) {
              if (/[\\/]node_modules[\\/](react|react-dom|scheduler|wouter)[\\/]/.test(id)) {
                return "vendor-react";
              }
              if (/[\\/]node_modules[\\/]recharts[\\/]/.test(id) || /[\\/]node_modules[\\/]d3-/.test(id)) {
                return "vendor-charts";
              }
              if (/[\\/]node_modules[\\/](framer-motion|motion-dom|motion-utils)[\\/]/.test(id)) {
                return "vendor-motion";
              }
              if (/[\\/]node_modules[\\/](react-markdown|remark-|rehype-|micromark|mdast-|hast-|unified|unist-|vfile|property-information|space-separated-tokens|comma-separated-tokens|decode-named-character-reference|character-entities|trim-lines|devlop|bail|trough|is-plain-obj|html-url-attributes|zwitch|longest-streak|markdown-table|ccount|escape-string-regexp|parse-entities|character-reference-invalid|is-alphanumerical|is-decimal|is-hexadecimal|stringify-entities)[\\/]/.test(id)) {
                return "vendor-markdown";
              }
              if (/[\\/]node_modules[\\/](@supabase|@aws-sdk|iceberg-js)[\\/]/.test(id)) {
                return "vendor-supabase";
              }
              if (/[\\/]node_modules[\\/](@tanstack|zustand)[\\/]/.test(id)) {
                return "vendor-data";
              }
              if (/[\\/]node_modules[\\/](@radix-ui|class-variance-authority|clsx|tailwind-merge|sonner|lucide-react)[\\/]/.test(id)) {
                return "vendor-ui";
              }
            }
            return undefined;
          },
        },
      },
    },
  };
});
