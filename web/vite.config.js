import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vite'

// Backend URL for the dev proxy — same contract as the dashboard always had:
// the browser talks to :5173 only, and every API path is proxied same-origin
// so cookie auth works without CORS.
const BACKEND = process.env.BACKEND_URL || process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'

const proxy = Object.fromEntries(
  [
    '/api', '/v6/api', '/v6/healthz', '/providers', '/leads', '/jobs',
    '/benchmark', '/verify-email', '/report', '/sync-supabase', '/mcp',
    '/health', '/docs', '/openapi.json', '/redoc',
  ].map((p) => [p, { target: BACKEND, changeOrigin: true }]),
)

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5173,
    host: true,
    proxy,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
    chunkSizeWarningLimit: 900,
  },
})
