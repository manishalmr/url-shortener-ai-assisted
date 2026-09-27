# Requirement Understanding & Scope

## 1. Requirement as given

The brief asked for a URL shortener built from scratch - covering core APIs, click analytics,
and reliability - to be completed and iterated on over a short, time-boxed window with the help
of AI coding assistants, while the engineer demonstrates sound judgment throughout (see the
top-level `README.md` for the assignment framing this project responds to).

This is a **well-defined outcome with an ambiguous implementation surface**: the deliverable
("URL shortener with core APIs, analytics, reliability") is clear, but the exact API shape,
persistence choice, abuse-prevention strategy, and analytics depth are left to engineering
judgment. Normalizing this into a concrete engineering problem required making explicit
decisions (documented below and in [`architecture.md`](./architecture.md)) rather than treating
ambiguity as a blocker.

## 2. Normalized engineering problem

Build a stateless HTTP service that:

1. Accepts a long URL and returns a short, unique code (optionally a caller-supplied alias).
2. Redirects visitors from `/{code}` to the original URL with minimal latency.
3. Records per-click analytics (volume over time, referrers) without storing unnecessary PII.
4. Is resilient to abuse (unsafe URLs, excessive request rates) and partial failure (expired/
   deleted links, DB unavailability) without crashing or corrupting state.
5. Is portable across a local SQLite dev setup and a Postgres-backed deployment with zero code
   changes (config-only).

## 3. Functional requirements

| # | Requirement | Where implemented |
|---|---|---|
| F1 | Create short URL, optional custom alias, optional expiry | `POST /api/v1/urls` |
| F2 | Redirect short code to original URL | `GET /{code}` |
| F3 | Retrieve short URL metadata | `GET /api/v1/urls/{code}` |
| F4 | List short URLs (paginated) | `GET /api/v1/urls` |
| F5 | Delete (soft) a short URL | `DELETE /api/v1/urls/{code}` |
| F6 | Per-link analytics: total clicks, last 24h, clicks/day, top referrers | `GET /api/v1/urls/{code}/analytics` |
| F7 | QR code for a short link (ambiguous scenario, see `scenarios.md`) | `GET /api/v1/urls/{code}/qrcode` |
| F8 | Liveness/readiness check | `GET /health` |

## 4. Non-functional requirements

- **Reliability**: no lost clicks under concurrent redirects (atomic counters), graceful
  degradation on cache miss, bounded request rates to protect the DB.
- **Security**: scheme allow-list, private/loopback IP blocking, domain blocklist, no raw client
  IP retention (hashed), reserved-alias protection, security response headers.
- **Observability**: structured request logs with correlation IDs (`X-Request-ID`).
- **Maintainability**: layered architecture (routers → crud → models), typed schemas, ≥85% test
  coverage on `app/`.
- **Portability**: single `DATABASE_URL` env var switches SQLite ↔ Postgres.

## 5. Explicitly out of scope (and why)

Given the 2-3 day time-box, the following were deliberately deferred rather than half-built:

| Deferred item | Rationale |
|---|---|
| User accounts / auth / multi-tenancy | Not requested; would roughly double the surface area (auth, ownership checks, per-user quotas) without adding signal on the core assignment criteria. |
| Distributed rate limiting / cache (Redis) | The in-process implementations are documented as single-instance-only; swapping in Redis is a config/adapter change, not a redesign (see `testing-and-limitations.md`). |
| Custom domains / link branding | Product feature, orthogonal to the core shortening/analytics/reliability ask. |
| Async event pipeline for click analytics (Kafka/queue) | Click volume expected in this exercise doesn't justify the operational complexity; synchronous atomic-update approach is documented as the trade-off. |
| CAPTCHA / bot filtering | Basic rate limiting is a proportionate first line of defense for this exercise's scope. |

## 6. Ambiguities identified and resolved

| Ambiguity | Resolution | Rationale |
|---|---|---|
| What counts as "analytics"? | Total clicks, 24h clicks, daily time series (14 days), top-5 referrers | Matches the most common real-world shortener analytics (Bitly-style) without over-engineering (no geo/device parsing, which would need a UA-parsing dependency) |
| Should short URLs ever truly disappear? | Soft delete (`is_active=False`) instead of hard delete | Preserves analytics history and audit trail; a real product almost never wants to lose click history on delete |
| Should duplicate long URLs get duplicate short codes? | De-duplicate by default (return existing code), configurable via `DEDUP_EXISTING_URLS` | Avoids unbounded table growth from repeated submissions of the same link; documented as an assumption since the brief didn't specify |
| Redirect status code (301 vs 302 vs 307)? | 307 Temporary Redirect | Preserves HTTP method/body on redirect and avoids browsers/CDNs permanently caching a mapping that can later be deleted or expire (301 is cached indefinitely by some clients) |
