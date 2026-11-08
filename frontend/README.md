# SketchLogic frontend (Next.js)

Next.js 16 (App Router, Turbopack), React 19, Tailwind CSS 4, Vitest + Testing Library.

```bash
npm install
cp .env.example .env.local     # Windows: Copy-Item .env.example .env.local
npm run dev                    # http://localhost:3000 (expects API on :8000)
```

| Script                            | Purpose                            |
| --------------------------------- | ---------------------------------- |
| `npm run dev` / `build` / `start` | Next.js                            |
| `npm test`                        | Vitest (jsdom)                     |
| `npm run typecheck`               | `tsc --noEmit`                     |
| `npm run lint`                    | ESLint (next/core-web-vitals + TS) |
| `npm run format` / `format:check` | Prettier                           |

Layout: `src/app/` routes · `src/components/` client UI · `src/lib/api.ts` typed API client ·
`src/lib/graph-schema.ts` TS mirror of graph schema v1 (checked against
`../shared/schemas/graph.v1.json` by tests).

> Next.js 16 differs from older versions. Check `node_modules/next/dist/docs/` before using
> unfamiliar APIs (see `AGENTS.md`).
