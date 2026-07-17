# MEMO — Portfolio time-windows: one decision to close

**To:** API/backend team (portfolio)
**From:** MCP side
**Re:** How `from`/`to` windows scope the `/v1/portfolios/:id/context` blocks. One decision + 3 small clarifications.

## Design we already agreed (no change wanted)
**Arbitrary-window analysis = the LLM calls the tool ONCE PER WINDOW and compares the results itself.**
No `compare_to[]` param, no multi-window payload. "Compare 2023 vs 2025" → two calls. This is settled
and correct — composable, LLM-native. Nothing to build for the *comparison mechanic*.

## The one thing that's actually unclear
Today the snapshot params **only re-scope the `composition` block** (docs, verbatim: *"Query params — all
optional — they only tune the `composition` block"*). So per-window calls give:

| block | responds to a window? |
|---|---|
| `composition` (point-in-time holdings) | ✅ yes — `snapshots_from`/`snapshots_to` zoom any window |
| `performance` (return/sharpe/drawdown/…) | ❌ no — fixed at `lifetime` + `recent`(~12mo) |
| `attribution` (who drove the NAV change) | ❌ no — fixed at `lifetime` + `recent` |

**Consequence for the agreed per-window design:** a per-window call returns that window's *holdings*, but
NOT that window's *return / sharpe / drawdown / contributors*. So "compare the **performance & what drove
each** in 2023 vs 2025" is NOT a clean 2-call today — the LLM only ever gets lifetime + last-12-months
performance, no matter the window it asks for.

### DECISION NEEDED
**Should an explicit window (`from`/`to`) also re-scope `performance` + `attribution` (not just
`composition`)?**

- **Option A — YES (recommended).** When a window is passed, return that window's `performance` +
  `attribution` + `composition` (one window's worth). When NO window is passed, keep today's default:
  the `lifetime` + `recent` split (token-light for a 10-yr book). → This makes the agreed per-window
  design work for **everything**, and the LLM answers "2023 vs 2025 performance + drivers" in 2 calls.
- **Option B — NO.** Keep performance/attribution at the two fixed windows forever; only holdings are
  windowable. → Then the MCP framing must tell the LLM "you can compare HOLDINGS across any window, but
  performance/attribution only exist for lifetime + the last 12 months" — and the earlier real user ask
  ("compare 2023 vs this year, strengths/weaknesses") stays partially unanswerable.

Either is fine to implement on the MCP side — I just need to know which, so the tool params + the framing
tell the LLM the truth and it never fabricates a per-window number it can't actually get.

## 3 small clarifications (whichever option)
1. **Param naming.** If a window scopes more than composition (Option A), rename `snapshots_from`/
   `snapshots_to` → a plain **`from`/`to`** (+ keep `snapshots` as the *granularity* of the composition
   series only). Aligns with the news tools (`from_`/`to`/`window`) and stops implying "snapshots only".
2. **Bounding at fine granularity.** `snapshots=day` over a multi-year window — what's the guarantee? Cap
   at ~40 and auto-coarsen? Error? A note? The MCP must keep responses context-safe, so I need the
   deterministic rule (and ideally a `note` when a request got coarsened).
3. **Coverage edges.** (a) How far back does portfolio history go — inception only? (b) What comes back for
   a window *before inception*, or for a *liquidated* book? A clear empty/`note` (not a silent 0) lets the
   LLM say "before this portfolio existed" instead of inventing.

## TL;DR
1. Per-window-call design = agreed, done, no change.
2. **Decide:** does `from`/`to` re-scope `performance`+`attribution` too (Option A, recommended), or only
   `composition` (Option B)? That's the whole question.
3. If A: rename to `from`/`to`; confirm the day-granularity cap + coverage-edge behavior so the MCP framing
   is truthful.
