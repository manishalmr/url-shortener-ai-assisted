# Testing Approach, Limitations & Trade-offs

## 1. Testing approach

| Layer | Tool | What it covers |
|---|---|---|
| Unit/integration | `pytest` + `httpx`/`TestClient` | All API endpoints, validation rules, rate limiting logic, atomic click counting, cache behavior, error responses |
| Coverage | `pytest-cov` | 96% line coverage on `app/` (see `pyproject.toml` for config) |
| Lint/static analysis | `ruff` | Style, unused imports, common bug patterns (`E`, `F`, `I`, `UP`, `B` rule sets) |
| Security (SAST) | `bandit` | Scans `app/` for common Python security anti-patterns; currently 0 findings |
| Manual E2E smoke test | `curl` against a running `uvicorn` instance | Full create → redirect → analytics → QR code flow, confirming behavior matches automated tests against a real running process |

Each test uses an isolated in-memory SQLite database (`tests/conftest.py`) so tests never share
state and can run in any order or in parallel.

### Running the tests yourself
```bash
pip install -r requirements-dev.txt
pytest                 # runs the full suite with coverage
ruff check app tests   # lint
bandit -r app          # security scan
```

## 2. Known limitations

| Limitation | Why it exists | Production upgrade path |
|---|---|---|
| Rate limiter and redirect cache are **in-process** | Kept the implementation simple and dependency-free for a 2-3 day exercise | Swap `TTLLRUCache`/`FixedWindowRateLimiter` for Redis-backed equivalents behind the same interface; no call-site changes needed since both are already accessed through small, focused classes |
| SQLite is the default datastore | Zero-setup local development | `DATABASE_URL` is the only thing that needs to change to point at Postgres (see `docker-compose.yml`); SQLAlchemy abstracts the rest |
| No authentication / multi-tenancy | Out of scope per `requirements-and-scope.md` | Add an auth dependency (e.g. JWT bearer) and an `owner_id` column + filter on `Url`; the layered architecture (routers → crud) makes this a contained change |
| Analytics are computed synchronously on read, from raw `click_events` rows | Simplicity; acceptable at the data volumes implied by this exercise | For high click volumes, pre-aggregate into hourly/daily rollup tables via a background job, keeping `click_events` as the raw source of truth |
| No captcha/bot-detection beyond rate limiting | Rate limiting is a proportionate first line of defense for this scope | Add a pluggable abuse-scoring hook in the create/redirect path if bot traffic becomes a real problem |
| Click analytics do not resolve geography/device from user-agent | Avoids adding a UA-parsing dependency for a "nice to have" that wasn't explicitly requested | Add `user-agents` (or similar) parsing in `crud.record_click`/`get_analytics_raw` if needed |
| QR code endpoint has fixed size/margin (no query params) | Kept the API surface small per the ambiguity write-up in `scenarios.md` | Add optional query params (`size`, `format=svg|png`) if product requirements clarify |

## 3. Trade-offs made explicitly

- **Denormalized `click_count` vs. always `COUNT(*)`**: chose the denormalized counter (updated
  atomically) for O(1) reads on the hot metadata/analytics path, accepting the small added
  complexity of keeping it in sync (mitigated by doing the increment and the `ClickEvent` insert
  in the same transaction).
- **Soft delete vs. hard delete**: chose soft delete to preserve click history, accepting that
  the `urls` table will grow indefinitely without a separate archival/purge job (not built, since
  it wasn't part of the core ask).
- **Synchronous click recording vs. async/queued**: chose synchronous (in the request path) for
  simplicity and to avoid introducing a message broker for this exercise; documented as the
  first thing to revisit if redirect latency under real load becomes a concern.
