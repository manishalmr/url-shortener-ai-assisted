# AI Usage & Traceability Log

Per the "AI-Assisted Execution (Critical Differentiator)" requirement, this log records how AI
was used across the project: what was generated, what the engineer edited or rejected, and why.
Tool used: Cursor with Claude (Sonnet) as the in-IDE pair-programmer.

Legend: **Generated** = accepted largely as produced · **Edited** = accepted with engineer
changes · **Rejected** = AI proposal not used, alternative chosen instead.

| Task | AI Contribution | Engineer Review / Edits | Outcome | Rationale |
|---|---|---|---|---|
| Data model (`models.py`) | Generated `Url`/`ClickEvent` SQLAlchemy 2.0 models | Edited: switched `DateTime(timezone=True)` to naive-UTC (`timezone=False`) throughout | Edited | SQLite silently drops tzinfo on read, which raised `TypeError: can't compare offset-naive and offset-aware datetimes` the first time expiry logic ran against it in a test. Standardized on naive-UTC everywhere instead of patching call sites individually. |
| Short code generation (`shortener.py`) | Proposed Base62-encoding of the DB auto-increment id | Rejected | Rejected | Sequential ids are enumerable (`GET /api/v1/urls/1`, `/2`, ...), allowing anyone to scrape every short URL in the system. Asked for random `secrets.choice`-based codes with a collision-retry loop instead. |
| Input validation (`security.py`) | Generated scheme allow-list + private-IP blocking via `ipaddress` | Edited: added explicit `localhost` hostname check | Edited | A test (`test_invalid_or_unsafe_urls_rejected[http://localhost/internal]`) failed because `ipaddress.ip_address("localhost")` raises `ValueError` and is treated as "not an IP literal, therefore allowed." The AI's IP-literal check didn't cover bare hostnames. Fixed by adding a small denylist for known local hostnames alongside the IP-literal check. |
| Click counting (`crud.record_click`) | First draft: `url_row.click_count += 1; db.commit()` | Rejected, redone as atomic SQL `UPDATE` | Edited | Engineer flagged the read-modify-write race under concurrent redirects before it shipped (see `docs/scenarios.md` Brownfield case study). Asked the AI to explain the race first, then implement the atomic-update fix. |
| Custom-alias creation (`crud.create_url`) | Original draft only checked `code_exists()` then inserted, with no handling for a concurrent duplicate | Edited: wrapped `db.commit()` in `try/except IntegrityError`, translating it into the existing `AliasUnavailableError` | Edited | Found live, not by inspection: a two-thread probe firing simultaneous requests with the same custom alias produced one `201` and one raw `500` (unhandled `IntegrityError` from the DB's `UNIQUE` constraint). Verified the fix by re-running the same probe 15+ times post-fix - consistently one `201` + one clean `409`, zero `500`s. See `docs/scenarios.md` Scenario 2 addendum. |
| Redirect caching (`cache.py`, `routers/redirect.py`) | Generated `TTLLRUCache` + cache-first lookup in the redirect handler | Edited: added explicit `redirect_cache.invalidate(code)` on delete | Edited | Initial version cached the row before checking `is_active`, meaning a soft-deleted URL could keep 307-redirecting for up to `CACHE_TTL_SECONDS` after deletion. Caught in review, not by a failing test initially - a regression test was then added (`test_redirect_deleted_url_returns_410`) to lock in the fix. |
| Rate limiting (`rate_limiter.py`) | Generated a fixed-window in-process limiter | Generated (accepted as-is) | Generated | Simple, testable, sufficient for the assignment's single-instance scope; documented the multi-instance limitation rather than over-engineering a distributed limiter (see `testing-and-limitations.md`). |
| QR code feature (`qrcode_service.py`, ambiguous scenario) | Asked to first enumerate ambiguities in "add QR code support" before writing code | Generated (assumptions confirmed by engineer, then implementation accepted as-is) | Generated | See `scenarios.md` Scenario 3 for the full ambiguity/assumption table produced by this prompt. |
| Analytics aggregation (`routers/analytics.py`) | Generated referrer counting + daily bucketing using `collections.Counter`/`defaultdict` | Generated (accepted as-is) | Generated | Straightforward, matched acceptance criteria (total/24h/daily/top-5-referrers) on first pass; verified via `test_analytics.py`. |
| Test suite (`tests/*`) | Generated the bulk of test cases per module from stated acceptance criteria | Edited: added the two race-condition/cache-invalidation regression tests manually as a direct response to the bugs found above | Edited | Ensures the two real bugs found during development can never silently regress. |
| Lint/security gates | N/A (tooling, not AI-generated code) | Ran `ruff check --fix`, manually wrapped remaining long lines, ran `bandit -r app` | N/A | Quality gate required by the assignment; both are clean on the final codebase (0 lint errors, 0 bandit findings). |

## Prompting discipline used throughout
1. **State intent + constraints + acceptance criteria** before asking for code (e.g. "atomic
   increment, no lost updates under concurrency" rather than "fix the click counter").
2. **Ask the AI to explain before fixing** for anything touching correctness/concurrency, so the
   engineer can confirm the diagnosis before accepting a fix.
3. **Run tests + lint + bandit after every task**, not just at the end - two of the three bugs in
   this log were caught this way rather than in a final pass.
4. **Explicit engineer sign-off** on every accepted module against its stated acceptance
   criteria - nothing was merged unread.

## Secure AI usage notes
- No secrets, credentials, or proprietary data were included in any prompt or file sent to the
  AI tool.
- Generated code was scanned with `bandit` (SAST) before being considered final; zero findings.
- Dependency versions are pinned in `requirements.txt`/`requirements-dev.txt` rather than
  left floating, so AI-suggested library choices are reproducible and auditable.
