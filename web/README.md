# Lead Engine — Modern RTL Dashboard

Modern control panel for the **Lead Engine** quota-aware multi-provider lead generation backend.

## Tech stack
- **React 19** + **Vite 6** + **TypeScript**
- **Tailwind CSS v4** (dark/light mode, glass morphism, RTL native)
- **Radix UI** primitives + **Lucide** icons
- **TanStack Query** for server state
- **Zustand** for UI/chat persistence
- **Wouter** for routing
- **Sonner** for toasts
- **React Markdown** + **remark-gfm** for chat

## Pages
| Page | Path | Description |
|---|---|---|
| Overview | `/` | Live metrics, provider health, recent jobs, cache, system info |
| Chat | `/chat` | AI assistant with tool calling, multi-session, markdown |
| Keys | `/keys` | API key management (multi-key, grouped by provider) |
| Providers | `/providers` | Live status, enable/disable, reset quota, filter/search |
| Jobs | `/jobs` | Run pipeline, resume paused, sync Supabase, view reports |
| Leads | `/leads` | Filterable table with stage/job filters, CSV export |
| Verify | `/verify` | 5-state email check (DELIVERABLE/RISKY/CATCH_ALL/INVALID/UNKNOWN) |
| Config | `/config` | YAML editor with syntax check, backup, revert |

## Local development

```bash
cd web
pnpm install
pnpm dev          # starts on http://localhost:5173
```

The Vite dev server proxies all `/api/*`, `/providers`, `/jobs`, etc. to the FastAPI backend
on `http://127.0.0.1:8000` by default. Override with the `VITE_BACKEND_URL` env var:

```bash
VITE_BACKEND_URL="https://lead-engine-gamma-silk.vercel.app" pnpm dev
```

## Production build

```bash
pnpm build
```

Output goes to `dist/`. The build is a static SPA — deploy to any static host (Vercel, Netlify, etc.).

## Deploying to Vercel

The `web/` directory has its own `vercel.json` so it can be deployed as a standalone Vercel project:

1. Push to GitHub (already done)
2. In Vercel, click "New Project" → import `7ari9aff-crypto/lead-engine`
3. Set **Root Directory** to `web`
4. Vercel auto-detects Vite framework
5. Set environment variable `VITE_BACKEND_URL` to your FastAPI deployment URL
6. Deploy

The dashboard will talk to the FastAPI backend via that URL with CORS handled.

## File structure

```
web/
├── public/              # Static assets
├── src/
│   ├── components/
│   │   ├── layout/      # Sidebar, Topbar
│   │   └── ui/          # Button, Card, Input, Switch, Dialog, Badge, EmptyState
│   ├── hooks/           # useTheme (Zustand), useLiveData
│   ├── lib/             # api (typed client), utils (formatters)
│   ├── pages/           # 8 main pages
│   ├── styles/
│   │   └── globals.css  # Tailwind v4 + theme tokens
│   ├── App.tsx          # Router + layout
│   └── main.tsx         # Entry + providers
├── index.html
├── vite.config.ts
└── package.json
```

## Theme

Dark mode is the default. Toggle in the topbar. Theme preference is persisted to `localStorage`
under `lead-engine-ui` key.
