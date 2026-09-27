# Architecture Overview

## 1. Components

```
                          ┌───────────────────────────────────┐
                          │              FastAPI app           │
                          │            (app/main.py)           │
                          │                                     │
  HTTP  ─────────────────▶│  SecurityHeadersMiddleware          │
                          │  RequestLoggingMiddleware (req id)  │
                          │                                     │
                          │  ┌───────────────────────────────┐ │
                          │  │ Routers (app/routers/)         │ │
                          │  │  health.py    -> GET /health   │ │
                          │  │  urls.py      -> /api/v1/urls* │ │
                          │  │  analytics.py -> /analytics    │ │
                          │  │  redirect.py  -> GET /{code}   │ │
                          │  └───────────┬─────────────────┬─┘ │
                          │              │                 │   │
                          │   ┌──────────▼───────┐  ┌──────▼─┐ │
                          │   │ security.py       │  │ cache  │ │
                          │   │ rate_limiter.py   │  │ (TTL/  │ │
                          │   │ qrcode_service.py │  │  LRU)  │ │
                          │   └──────────┬────────┘  └────┬───┘ │
                          │              │                │     │
                          │        ┌─────▼────────────────▼──┐  │
                          │        │        crud.py            │  │
                          │        │  (DB access, atomic ops)  │  │
                          │        └─────────────┬────────────┘  │
                          │                      │                │
                          │              ┌───────▼────────┐       │
                          │              │  models.py /    │       │
                          │              │  database.py    │       │
                          │              │  (SQLAlchemy)   │       │
                          │              └───────┬────────┘       │
                          └──────────────────────┼────────────────┘
                                                  │
                                        ┌─────────▼─────────┐
                                        │ SQLite (dev) /     │
                                        │ Postgres (prod)    │
                                        └────────────────────┘
```

## 2. Execution approach: AI as an in-task accelerator

This project follows the **AI-assisted** model (not autonomous agentic orchestration - see the
sibling assignment for that variant). Concretely:

- **Tooling**: Cursor (Claude) was used as a pair-programmer inside the IDE/CLI.
- **Task framing**: each unit of work was scoped as an explicit task with intent, constraints,
  and acceptance criteria *before* generating code (see [`ai-usage-log.md`](./ai-usage-log.md)
  for the per-task breakdown and [`scenarios.md`](./scenarios.md) for the three required
  end-to-end walkthroughs).
- **Iteration loop**: generate → review diff → run tests/lint → accept, edit, or reject → commit.
  Nothing was accepted unread; every AI-authored module was reviewed against the acceptance
  criteria for that task before being kept.
- **Human ownership**: the engineer (not the AI) owns correctness of the merged code, decides
  what's in/out of scope (`requirements-and-scope.md` §5), and signs off on each scenario.

## 3. Control flow: request lifecycle

1. Request hits `SecurityHeadersMiddleware` → `RequestLoggingMiddleware` (assigns `X-Request-ID`,
   logs method/path/status/duration on the way out).
2. FastAPI dependency injection provides a request-scoped DB session (`get_db`).
3. Router-level rate limiter checks the caller's key (client IP) against a fixed 60s window
   before touching the DB - cheap rejection of abusive traffic.
4. **Create path** (`POST /api/v1/urls`): validate URL (scheme, host, blocklist) → dedup check →
   generate collision-free code (or validate custom alias) → persist → respond.
5. **Redirect path** (`GET /{code}`): check in-process TTL/LRU cache first; on miss, hit the DB
   and populate the cache → check active/expiry → atomically increment `click_count` + insert a
   `ClickEvent` row → 307 redirect.
6. Domain errors (`URLShortenerError` subclasses) are translated to consistent JSON error bodies
   by a single exception handler in `main.py`, each carrying the request id for traceability.
7. **Route registration order matters**: the catch-all `GET /{code}` redirect route is registered
   *after* `/api/v1/*` and `/health`, so those never get shadowed by the single-segment wildcard.

## 4. Key decisions & rationale

| Decision | Alternative considered | Why this was chosen |
|---|---|---|
| Random Base62 codes (`secrets.choice`) | Base62-encode an auto-increment id | Sequential ids are enumerable (`/abc1`, `/abc2`, ...), leaking creation order and letting anyone scrape every link in the system. Random codes close that hole at negligible cost (collision retry loop, max 5 attempts). |
| Denormalized `click_count` + atomic `UPDATE ... = click_count + 1` | Always `COUNT(*)` over `click_events` | O(1) reads for the hot metadata/analytics path vs. O(n) table scans; atomic SQL update avoids the read-modify-write race a naive `+= 1` in Python would hit under concurrency (see `crud.py` docstring and the brownfield scenario). |
| Soft delete (`is_active` flag) | Hard `DELETE` row | Preserves click history/audit trail; matches how most real link-shortener products behave. |
| In-process TTL/LRU cache for redirects | No cache / external cache (Redis) | Meaningfully cuts DB load on the hottest path with zero extra infra, appropriate for this exercise's scope; documented as a single-instance limitation with a clear upgrade path. |
| In-process fixed-window rate limiter | Token bucket / external limiter | Simple to reason about and test within the time-box; same caveat and upgrade path as the cache. |
| SQLAlchemy + `DATABASE_URL` env var | Hard-code SQLite or Postgres | One-line config change moves from local dev (SQLite) to a real deployment (Postgres), no code changes - see `docker-compose.yml`. |
| IP hashing (SHA-256) instead of storing raw IPs in `ClickEvent` | Store raw IP for richer analytics | Keeps enough signal for abuse/dedup analysis without retaining PII we don't need - a proportionate privacy/security default. |
| 307 redirect (not 301/302) | 301 permanent redirect | Avoids aggressive client/CDN caching of a mapping that can later expire or be deleted; still allows browsers to cache appropriately for the request lifetime. |

## 5. Reliability features summary

- Atomic click counting (no lost updates under concurrency).
- In-process cache + rate limiting to protect the DB under load/abuse.
- Soft delete + expiry checked at read time (no destructive background job required).
- Consistent structured error responses with request-id correlation for support/debugging.
- `/health` endpoint verifies actual DB connectivity, not just process liveness.
- Config-driven persistence (SQLite dev → Postgres prod) with no code changes.
