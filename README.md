# factful

**Agentic, fact-grounded Substack article generator** — Python.

Every factual sentence in a factful article traces back to a verified, sourced claim. An ensemble of specialized agents runs a deterministic pipeline with a bounded convergence loop: the claim database is the single source of truth, nothing is fabricated, and nothing unverified is ever auto-published.

[![CI](https://github.com/HananKavitz/factful/actions/workflows/ci.yml/badge.svg)](https://github.com/HananKavitz/factful/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/HananKavitz/factful/branch/main/graph/badge.svg)](https://codecov.io/gh/HananKavitz/factful)
[![Python](https://img.shields.io/badge/python-3.11-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/packaging-uv-7c3aed)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-strict-2b6db2)](http://mypy-lang.org/)

## Features

- **Fact-grounded generation** — a gather agent expands a topic into sub-queries, searches the web, and mines atomic, verifiable claims with provenance.
- **Claim-as-source-of-truth** — the writer drafts with inline `[[claim_id]]` tags; every claim must pass a retrieval-grounded fact-check before publishing.
- **Style engine** — a writing style profile (voice, sentence length, hooks, structure, CTA) is extracted from sample articles and drives the writer.
- **Verification engine** — hybrid BM25 + embeddings passage retrieval, a closed-book attribution judge, and deterministic numeric/date sanity gates.
- **Convergence QA loop** — writer, fact-checker, and critic iterate up to 3 passes with quality gates; unresolved claims are surfaced, never silently dropped.
- **Substack export** — pushes a rendered Markdown draft to Substack's internal drafts API, with a local `.md` fallback when credentials are absent.

## How it works

```
gather → write(mode: full) → factcheck → critique → [converge?]
                        ▲                                    │
              patch / reset (write(node) → factcheck → critique again) ──► publish
```

Four specialized agents, each a pure task function with a structured output schema:

| Agent | Role |
| --- | --- |
| **Gather** | Expand topic into 4–6 sub-queries, search (Tavily, `search_depth=high`), dedupe by canonical URL, fetch sources, and mine atomic claims (`Citation`). |
| **Write** | Generate the Markdown draft from the source bundle + style profile; every factual sentence carries an inline `[[claim_id]]`. |
| **Fact-check** | Verify every claim against its source (`FactVerdict`), returning suggested revisions for fixable issues. |
| **Critique** | Reader-engagement review (`CritiqueReport`) scoring hooks, readability, argument structure, and calls-to-action. |

The convergence loop `write → factcheck → critique` runs **up to 3 passes**. Pass 1 is a full generation; passes 2–N apply incremental patches (critic revisions + fact-checker `suggested_revision`s) rather than rewrites. A full regenerate is reserved for critical verdicts.

## Verification engine

Claims rarely match their source verbatim after synthesis, so fact-checking is retrieval-grounded:

1. **Source fetch (hallucination guard)** — re-fetch the `source_url`; a 404 or irrelevant page → `unsupported`.
2. **Passage retrieval** — locate the sentence in the source that evidences the claim.
3. **Attribution judge** — a medium model compares the claim's specific number against the retrieved passage only (closed-book, no confabulation).
4. **Corroboration** — two or more independent sources corroborating → `verified`; disagreeing sources → `contradicted` (surfaced, never silently resolved).

Passage retrieval is hybrid: **BM25 (70%)** for exact rare-token and number matches plus **cheap embeddings (30%)** for paraphrase. A pure-Python gate layer sanity-checks dates and numbers (percentages ≤ 100, unit consistency, percent-point vs. percent-change).

## Quality gates

The `converge` router decides the loop's lifetime and always terminates:

- **Hard gate** — publish when `score ≥ 85` **and** no `contradicted`/`unsupported` claims.
- **Diminishing returns** — stop when improvement drops below a threshold; further passes won't reach the target.
- **Oscillation guard** — stop if the score regresses or alternates, preventing A→B→A→B chasing.
- **Hard cap** — never more than `max_passes` (default 3).

If the loop ends with unresolved critical claims, the article still publishes, but every one is emitted inline as `[UNVERIFIED: claim_id]` with its provenance and verdict attached — surfaced for human review.

## Style engine

`extractor` ingests sample articles and emits a style profile (one YAML per voice) capturing:

- Voice & tone
- Average sentence and paragraph length
- Hook patterns and opener types
- Section skeleton / story beats
- Transitions and rhetorical devices
- CTA and sign-off style

The writer receives the profile as a system prompt plus a short few-shot excerpt.

## Engines & tools

| Layer | Engine | Role |
| --- | --- | --- |
| Search | Tavily (`search_depth=high`) | Source discovery & corroboration |
| Fetch / extract | `httpx` + readability | Clean article text |
| Retrieval | `rank_bm25` + cheap embeddings (hybrid 70/30) | Locate evidence passages |
| Attribution judge | medium LLM, structured output | Verify claim ↔ passage & source |
| Numeric / date gate | pure Python | deterministic sanity checks |
| Models | OpenRouter (unified API, pinned per agent) | Route cheap → top tiers per agent |

## Configuration

Two sources: **environment variables** for secrets and credentials (never committed) and **`settings.yaml`** for behavior (`pipeline.*` loop limits and thresholds, `corroboration.min_sources`, `retrieval.*` weights, `llm` model routing). Env always overrides the YAML.

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEY` | OpenRouter key (all chat agents) |
| `TAVILY_API_KEY` | Tavily search |
| `EMBEDDINGS_API_KEY` | Embedding model key if separate from OpenRouter |
| `SUBSTACK_SESSION_COOKIE` | Substack session cookie for draft push |
| `LOG_LEVEL` | `debug` / `info` / `warning` |

## Installation

```sh
uv sync
```

## Usage

```sh
uv run factful generate "topic"            # generate an article
uv run factful style samples/*.md --name kevich   # build a style profile
```

Set the keys in your `.env` (see `.env.example`); without Substack credentials the exporter falls back to a local Markdown draft.

## Development

```sh
uv sync                                   # install deps
uv run pytest                             # run tests with coverage
uv run ruff check .                       # lint
uv run ruff format --check .              # format check
uv run mypy -p factful                    # type check
```