# REPLY — Portfolio time-windows: decision closed

**To:** MCP side
**From:** API/backend team (portfolio)
**Re:** Your `MEMO-portfolio-time-windows.md` — decided + shipped.

## Decision: **Option A — YES.**
An explicit window (`from`/`to`/`window`) now re-scopes **`performance` + `attribution` + `composition`
together**, not just composition. So the agreed per-window design works for *everything*: "compare 2023
vs 2025 performance **and** what drove each" = **2 calls**, each self-contained.

It was nearly free — the metric functions were already `[a,b]`-index-windowed internally; a windowed call
is the same math over different indices (no re-derivation). **Deployed to prod.**

## Exact contract (build your framing on this)

**No window** → unchanged default: `lifetime` (all-time) + `recent` (~12mo) blocks + `composition`
(quarter, whole history, ≤12 snapshots).

**With a window** (`from`/`to`, or relative `window`) → `lifetime`+`recent` are **replaced by one
`window` block**, and `composition` follows the same span:
```jsonc
"window": {
  "from": "2023-01-03", "to": "2023-12-29",   // clamped to actual trading days
  "label": "2023-01-01 → 2023-12-31",          // or the keyword, e.g. "ytd"
  "years": 1.0,
  "performance": { "return_pct": 20.58, "sharpe": 1.24, "max_drawdown_pct": -7.81, ... },
  "nav_trend": { "cadence": "coarse (~40 points over the window)", "unit": "JPY", "nav": [...] },
  "attribution": { "nav_change": 2201256, "contributors": [ { "symbol":"MC.BK","pct_of_nav_change":63.13, ... } ], ... }
}
```

### Clarification 1 — param naming (done)
- **`from` / `to`** (ISO) = the analysis window. Scopes perf+attr+composition.
- **`window`** = relative span, same keyword set as the news tools: `7d|30d|90d|180d|1y|mtd|qtd|ytd`
  (anchored on the LAST data date, not wall-clock). Alt to from/to.
- **`snapshots`** = composition **granularity only**: `year|quarter|month|week|day|off`.
- `snapshots_from`/`snapshots_to` still accepted as **back-compat aliases** for `from`/`to` (you can drop them).

### Clarification 2 — bounding at fine granularity (deterministic)
Never unbounded. Cap = **12** snapshots (no window) / **40** (windowed). If the requested `snapshots`
step would exceed the cap, it **auto-coarsens** (widens the stride) and tells you:
```jsonc
"composition": { "requested_step": "day", "effective_step": "~7 trading days", "coarsened": true,
                 "count": 40, "note": "Requested step 'day' was AUTO-COARSENED to ~7 trading days to keep ≤40 snapshots — narrow the window (from/to) for finer granularity." }
```
So `snapshots=day` over a multi-year window → coarsened to fit, flagged. To truly get daily, **narrow the
window** (e.g. one month) — then `day` fits under 40 and `coarsened:false`. Rule of thumb for context-safe
daily: window ≤ ~40 trading days.

### Clarification 3 — coverage edges (explicit, never silent 0)
- **History depth** = inception (the playlist's `created_at`); the nav series starts there. `meta.inception_date` is in every response.
- **`from` before inception** → clamped, with `window.note: "window start clamped to inception (YYYY-MM-DD)"`.
- **Window entirely before inception** → `window: { empty:true, note:"portfolio did not exist before YYYY-MM-DD — no data for this window", performance:{}, attribution:null }` and `composition` is empty with the same note. (Verified: `?from=2010-01-01&to=2010-12-31` → empty+note, not zeros.)
- **Window too small (<2 trading days)** → same `empty:true` + a note.
- **Liquidated book** → `summary.liquidated:true` + a `flags[]` entry; the windowed metrics reflect the
  post-liquidation reset (residual). If a window lands in a dead post-liq span it comes back empty+note.

## Verified on prod (portfolio 34)
- default → lifetime+recent ✓
- `?from=2023-01-01&to=2023-12-31&snapshots=month` → `window` block, 2023 perf (return 20.58% / sharpe 1.24), attribution (MC.BK 63% / GOLD 22%), monthly composition (14 snaps) ✓
- `?window=ytd` → 2026-01-02→last, label "ytd", return 12.08% ✓
- `?from=2010-01-01&to=2010-12-31` → empty + inception note ✓

## Docs updated (all live)
`docs/api/news-api-v1.md` · console `/console` (Portfolio → context: params + window/composition) ·
postman collection + downloadable zip. The comparison mechanic itself (call-once-per-window) is unchanged
— nothing for you to build there; just point the LLM at `from`/`to`/`window` and the edge notes so it
never fabricates a per-window number.
