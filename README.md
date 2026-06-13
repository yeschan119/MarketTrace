# MarketTrace

A stock event-analysis system. It ingests official disclosures (SEC EDGAR, OpenDART),
extracts structured **events** from them with an LLM, and measures their market
impact via numerically-computed 1/5/20-day abnormal returns. The LLM only extracts;
all return math lives in dedicated numeric modules.

The full roadmap, architecture decisions, and acceptance criteria live in
[`.omc/plans/market-trace-roadmap.md`](.omc/plans/market-trace-roadmap.md).

## Monorepo layout

```text
MarketTrace/
├─ docker-compose.yml     # postgres:16 (backend/web services scaffolded for later)
├─ backend/               # Python 3.12+ backend
│  ├─ pyproject.toml
│  ├─ .env.example
│  ├─ alembic/            # DB migrations
│  ├─ src/markettrace/    # config, db, providers, storage, nlp, impact, api, pipeline
│  └─ tests/
└─ web/                   # Next.js frontend (added in a later phase)
```

## Running the backend

Requires Python 3.12+ (metadata target). A local PostgreSQL is provided via Docker,
but the test suite runs entirely on in-memory SQLite — no database, network, or API
key required.

```bash
# 1. Set up a virtualenv and install the backend (editable, with dev extras)
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure environment (copy and edit)
cp .env.example .env

# 3. Start PostgreSQL
docker compose -f ../docker-compose.yml up -d postgres

# 4. Apply migrations
alembic upgrade head

# 5. Run the tests (no postgres/network needed)
pytest -q

# 6. Seed instruments (idempotent; default watchlist, or a single --ticker)
markettrace-seed --help

# 7. Run the end-to-end vertical slice (later phase)
markettrace-slice --help
```

## Configuration

Settings are read from environment variables (or a `.env` file) via
`markettrace.config.Settings`. See `backend/.env.example` for the available keys:

- `LLM_PROVIDER` — event-extraction backend: `anthropic` (default) or `openai`
- `ANTHROPIC_API_KEY` — Claude API key (used when `LLM_PROVIDER=anthropic`)
- `OPENAI_API_KEY` — OpenAI API key (used when `LLM_PROVIDER=openai`)
- `EXTRACTION_MODEL` — optional model override; defaults per provider
  (`claude-sonnet-4-6` for anthropic, `gpt-4o` for openai)
- `DATABASE_URL` — SQLAlchemy URL (defaults to the local postgres compose service)
- `SEC_USER_AGENT` — required by SEC EDGAR; identify yourself
- `OBJECT_STORE_DIR` — local directory for raw disclosure storage
- `PRICE_PROVIDER` — US price data backend: `tiingo` (default) or `stooq`
- `TIINGO_API_KEY` — Tiingo API key (used when `PRICE_PROVIDER=tiingo`)
