# MEMO — MCP time-range support (news tools)

**To:** whoever is iterating the MarketDX MCP server (`mcp/server.py`)
**From:** API/backend side
**Status:** analysis + recommendation. Not yet implemented — your call to build.

## The problem (real user session)

Via MCP, a user asked an LLM:
> "ทองช่วงนี้มีข่าวอะไรบ้าง" → works.
> "แล้วช่วงต้นปีที่แล้วล่ะ เหมือนผันผวนหนัก… เทียบข่าว Q4 แต่ละปีย้อนหลัง 3-4 ปีหน่อย"

The LLM can't do the second one. Two independent reasons — one easy, one hard.

---

## Layer 1 — news-api: time support is GOOD (no change needed)

- `/v1/news`, `/v1/news/search`, `/v1/news/by-tickers` → accept **`from` + `to`** (ISO ts).
- `/v1/brief`, `/v1/themes/{id}/summary` → accept **`window`** (`7d/30d/90d/180d/1y/mtd/qtd/ytd`) **or** explicit **`from`+`to`**.

## Layer 2 — Python SDK: also supports it (no change needed)

Verified in `python/src/marketdx/client.py`:
- `news_search(q, *, …, from_, to, …)` ✅
- `MegatrendRef.news(*, …, from_, to, …)` ✅
- top-level `news(…)` and `news_by_tickers(…)` mirror the API — **confirm the exact kwarg names** (`from_` / `to`) when wiring.
- `theme(id).summary(window=…)` and `brief(window=…)` ✅

## Layer 3 — MCP: THIS is the gap (easy fix — do this)

The MCP tools DON'T pass a time param through, even though SDK+API support it:

| MCP tool (`mcp/server.py`) | today | add |
|---|---|---|
| `theme_summary` (206), `suggest_cta` (342) | has `window` ✅ | (optional) explicit `from_`/`to` too |
| **`news_feed` (234)** | ❌ none | **`from_` + `to`** → pass to `mdx().news(from_=…, to=…)` |
| **`search_news` (215)** | ❌ none | **`from_` + `to`** → `news_search(from_=…, to=…)` |
| **`stock_impact` (249)** | ❌ none | **`from_` + `to`** → maps to `news_by_tickers(from_=…, to=…)` |

**Design notes for the tool params:**
- Accept ISO dates (`from_="2026-04-01"`, `to="2026-06-30"`). Consider ALSO accepting a relative/calendar `window` string on `news_feed`/`search_news` for LLM convenience (`"90d"`, `"qtd"`, `"2026-Q2"`) and resolving it to from/to server-side — the LLM finds `window="qtd"` easier than computing dates.
- Update each tool's docstring so the LLM KNOWS it can pass a range (the LLM only uses params it can see described).

This alone unlocks "gold news in Q4 2026", "news in March 2026", "compare Apr vs Jun 2026" — **within the data we have.**

---

## Layer 4 — DATA COVERAGE: the hard wall (NOT an MCP fix)

⚠️ **News data exists only for `2026-01-01 → present`** (~6.5 months; backfill floor = 2026-01-01, still walking backward). There is **NO news before 2026.**

So the user's actual ask — "early LAST year (2025)", "Q4 across 3-4 years" — **returns empty no matter how good the time params are.** This needs a multi-year historical news backfill (separate, expensive decision: depends on EODHD news depth + ~thousands of $ + storage). Out of MCP scope.

**What the MCP SHOULD do about it (important — cheap, do this):**
1. Make the LLM AWARE of the boundary so it doesn't hallucinate or return empty silently. The `describe`/coverage tool (server.py ~366, already reports a "news window") should surface the **earliest available news date**; the server instructions should tell the LLM: *"news coverage starts YYYY-MM-DD; for older periods, say so — do not fabricate."*
2. Ideally, when a requested range is fully/partly before coverage, the tool returns a clear note (`"requested range predates news coverage (starts 2026-01-01)"`) rather than an empty list.

## The price-vs-news asymmetry (worth telling the LLM)

The user said *"เหมือนผันผวนหนักตอนนั้น"* = **price/volatility**, not news.
- **Price/EOD data goes back decades** (GOLD.COMM, stocks, indices → 1990s). Historical volatility IS answerable.
- **News is 2026+ only.**

So a good MCP answer to "why was gold volatile in 2023 and what was the news": give the PRICE history (available) + state that NEWS only covers 2026+ (so no news for 2023). If a price/quote tool isn't exposed via this MCP yet, that's a candidate addition for these "what happened historically" questions.

---

## TL;DR
1. **DO:** add `from_`/`to` (and ideally a `window` convenience) to `news_feed`, `search_news`, `stock_impact` + update docstrings. Pass through to SDK (already supports it). Unlocks time-scoped queries within 2026.
2. **DO:** surface the news-coverage start date to the LLM (describe tool + server instructions) so it stops silently returning empty / hallucinating for pre-2026 asks.
3. **DECIDE separately:** multi-year historical news backfill (expensive; verify EODHD depth first) — the only thing that makes "compare Q4 for 3-4 years" actually work.

---

## ✅ IMPLEMENTED (MCP side) 2026-07-17

Layer 3 + 4.1 done in `mcp/server.py`:
- `news_feed`, `search_news`, `stock_impact` now accept **`from_`/`to`** (ISO) + a **`window`** convenience
  (`90d`/`1y`/`mtd`/`qtd`/`ytd`, resolved client-side by `_win()` to a `from_` date). Passed through to the
  SDK (`news`/`news_search`/`StockRef.news` — all already had `from_`/`to`). Docstrings updated + tell the
  LLM to compare periods by calling once-per-window.
- Coverage boundary surfaced: server `instructions` state news starts `2026-01-01` (+ price/volatility
  goes back decades); `search_news` also returns a `_coverage_note()` when a range predates coverage.
- Layer 4.2 (per-call note on the list-returning tools) partial: search_news carries it; news_feed/
  stock_impact rely on instructions + docstrings (list shape kept). Layer 4 backfill = still a separate
  $$ decision. Price/quote tool = candidate future addition for "what happened historically".
