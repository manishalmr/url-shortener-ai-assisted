# Final Engineering Summary

## Plan & rationale
The brief asked for a URL shortener with core APIs, analytics, and reliability features, built
using AI as an in-task accelerator with the engineer retaining ownership. The plan was to:
1. Normalize the ambiguous parts of the brief into explicit functional/non-functional
   requirements and documented assumptions (`requirements-and-scope.md`) before writing code.
2. Build the system in dependency order (data model → validation → core CRUD APIs → redirect →
   analytics → reliability hardening), using AI for each scoped task under explicit acceptance
   criteria, with the engineer reviewing every accepted module (`ai-usage-log.md`).
3. Demonstrate the three required scenario types (greenfield build, brownfield hardening/bug
   fix, ambiguous-requirement feature) as real, tested increments rather than hypothetical
   descriptions (`scenarios.md`).
4. Apply quality gates (tests, lint, SAST) continuously, not just at the end, so defects were
   caught while cheap to fix.

## Artifacts produced
- Working FastAPI service (`app/`) - runnable locally or via Docker/Compose.
- 32 automated tests, 96% line coverage, 0 lint errors (`ruff`), 0 SAST findings (`bandit`).
- Architecture documentation with component diagram, control flow, and key decisions
  (`architecture.md`).
- Requirements/scope write-up with explicit ambiguity resolutions and deferred-scope rationale
  (`requirements-and-scope.md`).
- Three end-to-end scenario walkthroughs (`scenarios.md`).
- Full AI-usage traceability log covering what was generated, edited, or rejected and why
  (`ai-usage-log.md`).
- Testing/limitations/trade-offs write-up (`testing-and-limitations.md`).
- Setup instructions and API reference (`README.md`).

## Risks, trade-offs, and how they were mitigated
| Risk | Mitigation |
|---|---|
| Lost clicks under concurrent redirects (found during development) | Fixed via atomic SQL `UPDATE` for the click counter; regression-tested |
| Stale cached redirects serving deleted/expired links | Explicit cache invalidation on delete + expiry checked on every read regardless of cache state; regression-tested |
| Abuse via unsafe redirect targets (localhost/private IPs, dangerous schemes) | Allow-listed schemes, blocked private/loopback/link-local targets and known local hostnames, domain blocklist hook; tested with a parametrized suite |
| Service overload from excessive requests | In-process rate limiting on create and redirect paths, documented as single-instance (Redis upgrade path noted) |
| Losing production readiness by chasing scope creep in a time-boxed exercise | Explicit deferred-scope table with rationale (`requirements-and-scope.md` §5) instead of half-building auth, distributed infra, etc. |

## Assumptions
- No authentication/authorization was requested, so the service is single-tenant with no user
  ownership model.
- Duplicate long-URL submissions should be de-duplicated by default (configurable).
- Short URLs should never truly disappear on delete (soft delete, preserves analytics history).
- QR code support (ambiguous ask) should encode the *short* URL, generated on demand, delivered
  as PNG via a dedicated endpoint - full rationale in `scenarios.md` Scenario 3.

## Limitations
See `testing-and-limitations.md` for the full table. Headline items: in-process cache/rate
limiter are single-instance only; no auth/multi-tenancy; synchronous (not queued) click
recording. Each has a stated, low-effort upgrade path that doesn't require re-architecting the
layered design (routers → crud → models).

## Engineering judgment demonstrated
- Identified and fixed a real concurrency bug (lost click updates) and a real cache-invalidation
  bug (stale redirects after delete) during development rather than shipping them - both are
  now regression-tested.
- Made deliberate, documented trade-offs (denormalized counters, soft delete, in-process
  cache/rate-limiting) rather than either over-engineering for scale that wasn't asked for, or
  under-engineering reliability that was explicitly requested.
- Treated AI output as a draft requiring review against explicit acceptance criteria in every
  case, with a clear paper trail of what was accepted, edited, or rejected and why.
