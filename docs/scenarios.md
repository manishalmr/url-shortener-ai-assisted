# Three Scenarios: Greenfield, Brownfield, Ambiguous

Per the assignment's required deliverable, this document walks through one scenario of each
type end-to-end: requirement → decomposition → AI-assisted execution → validation.

---

## Scenario 1 (Greenfield): Build the URL shortener core from scratch

### Requirement
Build a URL shortener from the ground up covering core APIs, click analytics, and reliability
features (see `requirements-and-scope.md` §1 for the full framing).

### Task decomposition

| # | Task | Depends on |
|---|---|---|
| 1 | Define data model (`Url`, `ClickEvent`) and DB session lifecycle | - |
| 2 | Short code generation strategy (collision-safe, non-enumerable) | 1 |
| 3 | Input validation & abuse prevention (`security.py`) | - |
| 4 | Create/Get/List/Delete API (`routers/urls.py`) | 1, 2, 3 |
| 5 | Redirect endpoint with click tracking (`routers/redirect.py`) | 1, 4 |
| 6 | Analytics aggregation endpoint (`routers/analytics.py`) | 1, 5 |
| 7 | Reliability layer: cache, rate limiting, structured errors, logging | 4, 5 |
| 8 | Test suite covering all of the above | 1-7 |

Tasks 1-3 are independent and were built in parallel conceptually (no shared state), then wired
together in 4-7 sequentially since each depends on the data layer.

### AI-assisted execution
- Each task above was given to the AI as a scoped prompt with: the target file(s), the
  acceptance criteria (e.g. "atomic click increment, no lost updates under concurrency"), and
  constraints (e.g. "SQLAlchemy 2.0 style, config via `Settings`, no hard-coded DB URL").
- The engineer reviewed each generated module against its acceptance criteria before moving to
  the next task (see [`ai-usage-log.md`](./ai-usage-log.md) for the per-task AI-contribution
  breakdown, including one AI-suggested approach that was rejected).
- Iterative refinement example: the first draft of `crud.record_click` used a plain Python
  `+= 1` increment; on review this was identified as a race condition risk and the AI was asked
  to redo it as an atomic SQL `UPDATE`, which is what shipped (see `crud.py` docstring).

### Validation
- 32 automated tests covering creation, redirects, analytics, validation, and rate limiting.
- `ruff check` (lint) and `bandit -r app` (SAST) both clean.
- Manual end-to-end smoke test: created a short URL, redirected through it, confirmed the
  analytics endpoint reflected the click, confirmed `/health` reports DB connectivity.

---

## Scenario 2 (Brownfield): Harden the redirect path for production traffic

### Requirement (as it would arrive in a real sprint)
"The redirect endpoint is our highest-traffic path and currently hits the database on every
click with no abuse protection. Before we launch, add caching and rate limiting, and review the
click-counting logic for correctness under load."

### Codebase reasoning
Impacted modules identified before writing code:
- `app/routers/redirect.py` - the hot path; needs a cache-first lookup.
- `app/crud.py::record_click` - originally implemented as `url_row.click_count += 1` followed
  by `db.commit()`. This is a **read-modify-write race**: under concurrent requests for the same
  code, two workers can both read `click_count = N`, both compute `N + 1`, and the second
  `commit()` overwrites the first - silently losing a click. This is a real correctness bug,
  not just a style issue.
- `app/main.py` - needs new middleware for consistent response headers/logging across the
  (now-cached) hot path.
- No API contract changes required - this is a pure non-functional enhancement + bug fix.

### Task decomposition

| # | Task | Depends on |
|---|---|---|
| 1 | Add `TTLLRUCache` (`app/cache.py`), wire into the redirect lookup with invalidation on delete | Existing `crud.get_by_code` |
| 2 | Add `FixedWindowRateLimiter` (`app/rate_limiter.py`), apply to redirect + create endpoints | - |
| 3 | Fix the click-count race by switching to an atomic SQL `UPDATE` | Existing `record_click` |
| 4 | Regression tests for cache correctness, rate-limit enforcement, and concurrent-click correctness | 1, 2, 3 |
| 5 | Fix a second concurrency bug found via live testing: duplicate custom-alias creation raced to a raw 500 instead of a clean 409 | Existing `create_url` |

### Addendum: a second race condition found via live probing (post-launch review)

While demonstrating this project, `create_url`'s custom-alias path was checked more closely:
it follows a **check-then-act** pattern (`code_exists()` check, then `INSERT`). Two concurrent
requests for the *same* custom alias can both pass the check before either commits, so both
attempt to insert the same `code`. The database's `UNIQUE` constraint on `Url.code`
(`models.py`) correctly stops the second insert - but nothing caught that specific
`IntegrityError`, so it surfaced as a raw, unhandled `500 Internal Server Error` instead of the
clean `409 alias_unavailable` a sequential duplicate request gets.

**How it was confirmed (not just theorized):** a two-thread probe script fired two identical
`POST /api/v1/urls` requests (same `custom_alias`) at the exact same instant against a running
instance. Result before the fix: one `201`, one raw `500`. After the fix, repeated over 15+
trials with fresh aliases each time: always one `201` + one clean `409`, zero `500`s.

**Fix**: wrap the `db.commit()` in `create_url` in `try/except IntegrityError`, roll back, and
raise the existing `AliasUnavailableError` - so the race produces the exact same response a
human would expect from a sequential duplicate request. See the docstring in `crud.py` for the
full explanation kept alongside the fix.

**Regression test**: `tests/test_create_url.py::test_concurrent_duplicate_alias_creation_handled_gracefully`
simulates the race deterministically (by forcing `code_exists` to report "not taken" for both
calls) rather than depending on real thread timing, which is flaky in CI.

### AI-assisted execution
- Asked the AI to first **explain** the concurrency risk in the existing `record_click` before
  writing any fix, to confirm shared understanding of the bug (traceability: this explanation is
  captured in `ai-usage-log.md`).
- AI proposed two fix options: (a) atomic SQL `UPDATE ... SET click_count = click_count + 1`, or
  (b) drop the denormalized counter entirely and always `COUNT(*)` over `click_events`. The
  engineer chose (a) - it preserves O(1) reads on the hot analytics/metadata path, which (b)
  would sacrifice for correctness we can get more cheaply.
- Cache invalidation was **not** initially generated correctly by the AI (it cached before
  checking `is_active`/expiry, which could serve a soft-deleted URL from cache after deletion for
  up to the TTL window). Engineer caught this in review and had the AI move deletion to also call
  `redirect_cache.invalidate(code)` explicitly in the `DELETE` handler - see `routers/urls.py`.

### Validation
- `tests/test_redirect.py::test_redirect_deleted_url_returns_410` and
  `test_redirect_expired_url_returns_410` specifically guard the cache-invalidation/expiry-check
  ordering bug described above.
- `tests/test_rate_limiting.py` verifies both the standalone limiter logic and its enforcement at
  the endpoint level (429 + consistent error body).
- Re-ran the full suite + lint + bandit after the change; no regressions.

---

## Scenario 3 (Ambiguous requirement): "Add QR code support for short links"

### Requirement as given
"Add QR code support for short links." - no format, no endpoint shape, no persistence
expectations specified.

### Ambiguity identification
Before writing code, the following unknowns were flagged and had to be resolved by engineering
judgment rather than by guessing silently:

| Ambiguity | Options considered | Assumption made & why |
|---|---|---|
| Delivery format | Base64 JSON field vs. binary image endpoint vs. SVG | Binary PNG via a dedicated `GET .../qrcode` endpoint - directly usable as `<img src>`, cacheable by HTTP infra, no client-side decoding needed |
| Persisted or generated on demand? | Store QR image in DB/blob storage vs. generate per-request | Generate on demand - QR generation is cheap (single-digit ms) and avoids storage/staleness if the underlying short URL changes state (deleted/expired) |
| What data is encoded in the QR? | The short URL vs. the original long URL | The **short URL** - so scanning it still benefits from click tracking/analytics, consistent with the product's purpose |
| Configurability | Expose size/error-correction/margin as query params | Kept fixed sensible defaults (`box_size=8, border=2`) to keep the API surface small for this iteration; documented as a follow-up if product needs vary |

### Task decomposition

| # | Task | Depends on |
|---|---|---|
| 1 | Resolve ambiguities above and document assumptions (this section) | - |
| 2 | Implement `qrcode_service.generate_qr_png` | 1 |
| 3 | Add `GET /api/v1/urls/{code}/qrcode` endpoint, 404 for unknown codes | 2, existing `crud.get_by_code` |
| 4 | Tests: valid PNG returned for existing code, 404 for unknown code | 3 |

### AI-assisted execution
- Framed the task to the AI explicitly as "the requirement is ambiguous; list the ambiguities
  and propose defaults before generating code" rather than letting it silently pick an
  implementation - this produced the assumption table above, which the engineer then confirmed
  before any code was written.
- Implementation itself was low-risk boilerplate (the `qrcode` library) and was accepted with
  only minor review (docstring clarifying the assumptions, matching existing error-handling
  conventions via `URLNotFoundError`).

### Validation
- `tests/test_qrcode_ambiguous_feature.py` asserts a real PNG is returned (magic-byte check) and
  that unknown codes 404 consistently with the rest of the API.
- Manually verified the PNG renders as a scannable QR code (see chat walkthrough / README).
