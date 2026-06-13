# MarketTrace Web

Next.js 15 (App Router) frontend for the MarketTrace market event analysis platform.

## Stack

- Next.js 15 + React 19 + TypeScript 5
- TanStack Query v5 for data fetching
- Tailwind CSS v3 for styling
- Recharts for charts (AbnormalReturnChart, ScoreBars)
- lightweight-charts installed (available for price series if needed)

## Getting Started

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | FastAPI backend base URL |

## Type Generation

Hand-written types live in `src/types/api.ts` and work without the backend running.

To regenerate from the live OpenAPI schema (requires backend running):

```bash
npm run gen:types
```

This writes `src/types/api.d.ts` from `http://localhost:8000/openapi.json` via `openapi-typescript`.

## Pages

| Route | Description |
|---|---|
| `/events` | Events list table |
| `/events/[id]` | Event detail with score bars and abnormal return chart |
| `/instruments/[id]` | Instrument event timeline |

## Build

```bash
npm run build   # production build
npx tsc --noEmit  # type-check only
```
