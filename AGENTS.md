# AGENTS.md

Guidance for AI coding agents working in this repository. This file is the source of
truth for project-wide conventions and commands. Update it when conventions change.

## Project

`factful` — a Substack articles generator.

- **Python core** — pure domain logic and a FastAPI app that exposes it over JSON.
- **Frontend** — a React/Redux SPA that consumes the API. Lives in `frontend/`.
- TDD is a first-class project value: tests drive development, not the other way round.

## Repo layout

- `src/factful/` — Python package (core logic + FastAPI API).
- `frontend/` — React/Redux SPA (Vite + TypeScript + Tailwind).
- `tests/` — mirrors the `src/` layout, with fixtures in `conftest.py`.
- `config/` — `substack.toml` and `.env*` (never committed).
- `docs/` — project documentation (git ignored).

## Tooling

Source of truth for the Python environment and dependencies is **uv**.
Source of truth for the frontend is **npm**.

- `uv` — Python env + dependency management.
- `pytest` — Python tests.
- `ruff` — Python lint + format.
- `mypy` — Python static type checking.
- `npm` — frontend dependency management + scripts.
- `vitest` — frontend tests.
- `tsc` — frontend type check.
- `alembic` — database schema migrations (applies on app boot for real DBs).

## Commands (canonical dev loop)

```sh
uv sync                                   # install Python deps
uv run pytest                             # run Python tests
uv run ruff check .                       # lint Python
uv run ruff format --check .              # format check Python
uv run mypy -p factful                    # type check Python

cd frontend && npm install                # install frontend deps
npm run test                              # run frontend tests
npm run build                             # type-check + build the SPA
npm run typecheck                         # tsc only

uv run uvicorn factful.api:app --reload   # backend API (port 8000)
cd frontend && npm run dev                # frontend dev server (proxies /api -> 8000)
```

### Database migrations (Alembic)

Schema is managed with Alembic (`migrations/`, `alembic.ini`). `init_db` runs
`alembic upgrade head` automatically at app boot for every real database (local
file SQLite and Turso/libsql alike); in-memory engines used by tests are created
with `create_all` instead.

- Fresh local DB: nothing to do — the first boot creates the full schema.
- Existing pre-migration local `factful.db` (has tables, no version): stamp once,
  then boot applies newer migrations.
  ```sh
  uv run alembic stamp 0001_baseline
  uv run alembic upgrade head
  ```
- Turso cloud: the empty DB is created in the Turso dashboard; the first deployed
  boot creates the full schema and later deploys apply new migrations. Use the
  same `DATABASE_URL` / `TURSO_AUTH_TOKEN` env as the app, and `migrations/env.py`
  resolves them with the app's own engine logic.
- Author a new migration with `uv run alembic revision --autogenerate -m "..."`,
  then review `migrations/versions/` before committing.

The verification gate for the web app additionally runs `npm run test`, `npm run
build`, and `npm run typecheck` in `frontend/`. In production the FastAPI app also
serves the built SPA (`frontend/dist`) via `src/factful/static.py`.

## Development workflow (TDD)

Follow the RED → GREEN → REFACTOR loop. Write a failing test first, make it pass,
then clean up. A change is not done until the full verification gate (below) passes.

## Principles

### Hard constraints (non-negotiable — never break these)

- **TDD** — write the failing test before the implementation; no red-driven-after code.
- **Verification gate** — a change is only "done" when `pytest`, `ruff check`,
  `ruff format --check`, and `mypy` all pass, plus the frontend gate
  (`npm run test`, `npm run build`, `npm run typecheck` in `frontend/`).
- **Never commit secrets** — `.env`, `.env.*`, and `config/substack.toml` stay out of git.
- **No network calls in unit tests** — mock the Substack/client I/O layer; tests stay fast, deterministic, and hermetic.
- **No speculative code** — YAGNI. Build only what the tests and current scope require. No unused abstractions, dead paths, or guessed features.
- **No silent failure** — fail fast. Raise and validate explicitly; never swallow errors with bare `pass` or empty exception handlers.

### Guidance (strongly preferred — follow unless a good reason not to)

- **DRY** — Don't Repeat Yourself. Factor duplicated logic into a single, tested home.
- **KISS** — prefer the simplest solution that satisfies the tests; avoid cleverness.
- **Single Responsibility (SRP)** — one module/function does one thing; keep it easy to test.
- **Separation of Concerns** — keep pure domain logic separate from I/O adapters (Substack, network, HTTP) so the pure core is trivially testable without mocks.
- **Composition over inheritance** — prefer small collaborating objects/functions to deep inheritance chains.
- **Thin, stable contracts** — keep the public API minimal and stable; it will become the REST/JSON boundary for the React app. Don't leak internals.
- **Convention over configuration** — follow ruff defaults (`E,F,I,N` + `UP,S,B,ASYNC`) and the framework's idiomatic patterns. Don't invent bespoke setups.
- **Type everything public** — annotate all public signatures; keep `mypy` clean.
- **Tests document intent** — name tests by the behavior they assert; tests are the executable spec of the module.

## Code conventions

- PEP 8 via ruff. Run `ruff format` so style is enforced, not argued.
- No code comments unless they add real value; the code and tests should be self-explanatory.
- Config comes from `config/substack.toml` and `.env`; wire through a config layer rather than hardcoding values.
- Keep pure domain logic independent of I/O so it stays unit-testable (see Separation of Concerns).

## Frontend (React/Redux)

Vitest + React Testing Library for component/unit tests, Redux Toolkit + RTK Query
for state and data fetching. Vite dev server proxies `/api` to `http://localhost:8000`.
Tests mock RTK Query hooks and never hit the network. State lives in
`src/features/*/` with `*Api.ts` (RTK Query) and `*Slice.ts` (Redux) per feature.