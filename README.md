# URL Shortener - AI-Assisted Software Engineering Assignment

A working URL shortener service (FastAPI + SQLAlchemy) with core APIs, click analytics, and
reliability features, built as the **AI-Assisted Software Engineer** interview assignment.

> This repo intentionally builds the "AI-assisted" variant of the assignment (engineer-led
> execution, AI as an accelerator within tasks) rather than the "Agentic" variant (autonomous
> orchestration engine). See [`docs/final-summary.md`](docs/final-summary.md) for why.

## Documentation index
| Doc | Contents |
|---|---|
| [`docs/requirements-and-scope.md`](docs/requirements-and-scope.md) | Requirement interpretation, functional/non-functional requirements, explicit scope decisions |
| [`docs/architecture.md`](docs/architecture.md) | Component diagram, execution approach, control flow, key decisions & rationale |
| [`docs/scenarios.md`](docs/scenarios.md) | Greenfield / brownfield / ambiguous-requirement walkthroughs (decomposition → execution → validation) |
| [`docs/ai-usage-log.md`](docs/ai-usage-log.md) | Traceability: what AI generated/edited/rejected, and why |
| [`docs/testing-and-limitations.md`](docs/testing-and-limitations.md) | Testing approach, known limitations, trade-offs |
| [`docs/final-summary.md`](docs/final-summary.md) | Plan, artifacts, risks, assumptions, limitations |

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.

### Run with Docker Compose (app + Postgres)
```bash
docker compose up --build
```

### Run the tests
```bash
pip install -r requirements-dev.txt
pytest                 # tests + coverage report
ruff check app tests   # lint
bandit -r app          # security scan
```

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/urls` | Create a short URL (optional `custom_alias`, `expires_in_days`) |
| `GET` | `/api/v1/urls` | List short URLs (paginated: `limit`, `offset`, `active_only`) |
| `GET` | `/api/v1/urls/{code}` | Get metadata for a short URL |
| `DELETE` | `/api/v1/urls/{code}` | Soft-delete a short URL |
| `GET` | `/api/v1/urls/{code}/analytics` | Click analytics: total, last 24h, daily series, top referrers |
| `GET` | `/api/v1/urls/{code}/qrcode` | PNG QR code encoding the short URL |
| `GET` | `/{code}` | Redirect to the original URL (307), records a click |
| `GET` | `/health` | Liveness/readiness check (verifies DB connectivity) |

### Example

```bash
curl -X POST http://localhost:8000/api/v1/urls \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com/some/very/long/path"}'
# => {"code":"aZ3kQmP","short_url":"http://localhost:8000/aZ3kQmP", ...}

curl -i http://localhost:8000/aZ3kQmP
# => HTTP/1.1 307 Temporary Redirect
#    location: https://example.com/some/very/long/path

curl http://localhost:8000/api/v1/urls/aZ3kQmP/analytics
```

## Project structure

```
app/
  main.py            # FastAPI app, middleware, exception handlers, router wiring
  config.py          # Environment-driven settings
  database.py        # SQLAlchemy engine/session
  models.py          # Url, ClickEvent ORM models
  schemas.py         # Pydantic request/response contracts
  crud.py            # DB access layer (atomic click counting, dedup, soft delete)
  shortener.py       # Base62 short-code generation
  security.py        # URL/alias validation, SSRF-style guardrails, domain blocklist
  cache.py           # In-process TTL/LRU cache for the redirect hot path
  rate_limiter.py    # In-process fixed-window rate limiter
  qrcode_service.py  # QR code generation (ambiguous-requirement scenario)
  middleware.py      # Request logging + security headers
  exceptions.py       # Domain errors -> consistent JSON error responses
  routers/
    urls.py, redirect.py, analytics.py, health.py
tests/               # 32 tests, 96% coverage on app/
docs/                # Assignment deliverables (see index above)
config/blocklist.txt # Example domain blocklist
```

## Configuration
All configuration is environment-driven (see [`.env.example`](.env.example)); copy it to `.env`
to override defaults. Key variables: `DATABASE_URL`, `BASE_URL`, `RATE_LIMIT_*`,
`CACHE_TTL_SECONDS`, `DEDUP_EXISTING_URLS`.
