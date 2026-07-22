---
name: marketdx-research
description: >-
  Use for ANY investment / financial-markets question when the MarketDX (mdx) connector is available —
  "how is a stock, sector, or market doing", news & market-impact, why an asset moved, options
  positioning, portfolio analysis, sector/theme research. Encodes which mdx tool to reach for so you
  don't web-search what mdx answers better. Trigger on tickers, company/sector names, market/index
  mentions, or "how's X doing / what moved X" — INCLUDING a specific company's news, PUBLIC or PRIVATE
  (OpenAI, Anthropic, SpaceX, …): private companies resolve to an internal oc: id via find_stock and mdx
  tracks their news→impact, so these are mdx questions, not web searches.
---

# MarketDX — using the mdx connector well

MarketDX (`mdx`) is a financial **news→impact graph**: it maps news to the assets and megatrends it
actually moves — direction (+/−), the causal **why**, and the ripple to connected players — across
stocks, ETFs, indices (via ETF), forex, crypto, commodities, and private/off-coverage companies. It also
serves options positioning, the megatrend taxonomy, the user's portfolios, and a personal notes layer.

This skill governs ONE job: **route to the right mdx tool** (don't web-search what mdx answers better).
Capturing and recalling the user's notes is a SEPARATE concern, owned entirely by the **`marketdx-notes`**
skill — this skill says nothing about it.

---

## 1. Tool routing — reach for mdx, not web search

**Golden rule:** any read on how a tradable asset/sector/market is *doing*, what *moved* it, or *why* — in
ANY language/phrasing — is a MarketDX question. Our news→impact + options positioning **IS** the substance
of "how is it doing" (the why it's moving + the market's stance) — a web search cannot supply it. Never
answer these with only a web search.

| The user is asking… | Use | Notes |
|---|---|---|
| How is ONE company/ticker/ETF doing? what moved it? why? | **`asset_pulse(ticker)`** | ONE call = PRICE (level/drawdown/vol) + news-impact + options. This is the full read. |
| Is a ticker CHEAP / EXTENDED / how has its PRICE moved / drawdown / 52w range / vol? (just the price picture) | **`stock_prices(ticker)`** | Digested price features (adjusted) — windowed changes, drawdown-from-peak, realized-vol percentile, volume conviction; `*_read` labels ready to quote. `asset_pulse` includes this; use `stock_prices` for price-only. |
| A WATCHLIST/cohort price snapshot (which names most extended / deepest drawdown) | **`stock_prices_batch([…])`** | up to 50 tickers in one call. |
| How is a SECTOR / INDUSTRY / THEME doing? (semiconductors, AI, energy, banks, gold, robotics…) | **`theme_pulse(concept)`** | Fans out to 3 independent cohorts (megatrend / GICS / tradable-ETF options) — present them SEPARATELY, don't merge. |
| Which STOCKS in a group are INTERESTING / winning / losing / most-talked-about? (rank the NAMES inside semis / a GICS sector / a country) | **`screen_stocks(megatrend?, gics?, country?)`** | News-impact screener. ≥1 scope required (name or id — resolved for you). LEAD with the winners-vs-losers split (`direction_split`), surface net-NEGATIVE standouts separately, explain each via `top_reason`. `direction=pos/neg`, `order_by=news_count/relevance/market_cap`. Different from `theme_pulse` (the sector's overall pulse) — this ranks the members. |
| Which stocks pay a HIGH / RELIABLE / GROWING DIVIDEND? income / yield / "กินปันผล" | **`screen_dividends(country?, gics?, sector?)`** | Income screener over ALL payers (not just news-covered). ≥1 scope. `order_by=yield`(default)`/streak/cagr`, `min_yield`/`max_yield` (%), `min_streak_years` (≤10). 🔴 NEVER present the yield alone — each row DECOMPOSES it (`ttm_div_yoy_pct`, `no_cut_streak_yrs`, `last_cut_year`, `cagr_5y_pct`, `week52_low`, `news`): high yield + recent cut + bad news = TRAP; high yield from a price drop + intact/growing dividend + a clean 10y streak = VALUE. ⚠️ `no_cut_streak_yrs` is a bounded RELIABILITY signal — no-cut years within a 10-YEAR window, **caps at 10** (10 = clean through the whole decade incl. 2020 & 2022 stress). It is NOT the dividend's full age: do NOT report a multi-decade "aristocrat / dividend-king" streak — not from this tool and not from your own knowledge; say "clean for 10y+ (the full tracked window)". A pure "which has the LONGEST-EVER streak / oldest dividend king" trivia question is outside this tool's 10y window — say so rather than web-guessing a number. Follow the payload `_guide`. |
| The MARKET / an INDEX "right now" (S&P, Nasdaq, Dow, "the market") | **`asset_pulse`** on its ETF: S&P→SPY, Nasdaq→QQQ, Dow→DIA | We DO cover their options + news. A web-searched index *level* is at most ONE supplementary number — never the whole answer, never skip the mdx read. |
| Summarize a whole SCOPE — a news category ("commodity news"), a country/market, a GICS sector, a megatrend, or an AND-mix | **`brief(...)`** | The composed "how is <X> doing" picture. NOT `search_news`/`news_feed` (those return a raw list, not a summary). |
| Resolve a company NAME or an unsure/foreign TICKER → exact mdx ticker | **`find_stock(name)`** FIRST | ⚠️ mdx uses its OWN suffixes (Korea `.KO` not `.KS`, Taiwan `.TW`, …) — guessing a non-US ticker 404s. Also resolves commodities (gold→`GOLD`), crypto (`BTC`), private (openai→`oc:52`). Take the top match's `ticker`. |
| A **PRIVATE / off-coverage** company (OpenAI, Anthropic, SpaceX, Stripe, ByteDance, xAI, Databricks, …) — its status or news | **ALWAYS `find_stock(name)` FIRST**, then `stock_impact(<the oc: id>)` / `news_feed`; or `private_movers(theme)` | 🔴 CRITICAL mental-model fix: a private company has **NO public ticker — but MarketDX assigns it an INTERNAL id `oc:<n>`** that `find_stock` returns (openai→`oc:52`). So "it's private / has no ticker" does **NOT** mean "no data" and is **NEVER** a reason to web-search. Do NOT skip `find_stock` because you think there's no ticker — run it on the NAME, take the `oc:` id, and query mdx with it (mdx tracks their news→impact; OpenAI alone has 200+ scored articles). Web only to SUPPLEMENT, clearly labeled. |
| Resolve a THEME/trend term → megatrend node id | **`find_megatrend(terms)`** | The megatrend counterpart of find_stock — returns `{id,name,tier}` candidates; YOU pick, then reuse the id. |
| Resolve an INDUSTRY/SECTOR term → GICS code | **`find_gics(terms)`** | The sector counterpart (retail, airlines, banks, pharma have GICS but no megatrend node); returns `{code,name,level}` candidates; YOU pick. |
| A raw LIST of news articles on a ticker/scope | **`news_feed`** / **`search_news`** | Use `brief` instead if they want a *summary*, not a list. |
| Options positioning / dealer-gamma / fear-greed on a name | **`options_sentiment(ticker)`** | US underlyings only. `covered=false` → skip options for that name. |
| Per-stock news impact timeline | **`stock_impact(ticker)`** | Drill-down; prefer `asset_pulse` first. |
| Competitors / peers of a company | **`relationships(ticker)`** | News-derived graph. |
| Investable member companies of a theme | **`theme_players(theme, country)`** | Curated membership. Returns `{stocks, count, total, note}` — if `total` > `count` you're seeing a TOP SLICE (big themes have 100+): tell the user "N of M" and offer to widen (`limit`) or narrow the scope, don't imply it's the full roster. Same for `private_movers` / `relationships`. |
| Off-coverage / private companies a theme moved | **`private_movers(theme)`** | The "beyond tickers" surface. |
| Browse the megatrend taxonomy | **`list_themes()`** (shown as "List Megatrends") | |
| The user's OWN portfolio(s) | **`list_portfolios()`** → **`portfolio_context(id)`** (numbers) or **`portfolio_pulse(id)`** (numbers + market read on top holdings) | Owner-scoped. Call list first if they say "my portfolio" without a number. |

**Prefer the composites** (`asset_pulse`, `theme_pulse`, `portfolio_pulse`) over calling
`stock_impact`/`options_sentiment` one at a time; use the singles only to drill deeper afterward.

**Coverage guardrails:**
- News coverage starts **2026-01-01** — for anything older, say so plainly; never fabricate or present an
  empty result as "nothing happened". (Price/volatility history goes back decades — so "why was gold
  volatile in 2023" is answerable from price even without 2023 news.)
- For a NON-US or uncertain ticker, `find_stock` FIRST, then use the returned `ticker`.
- A bare current-price LEVEL is the only thing a web lookup may supplement — and even then, the mdx read is
  the substance ("the level alone is not 'how is it doing'").

---

## 2. Gotchas we hit (so you don't)

- **The connector caches its tool list + instructions at connect-time.** If tools/behavior seem stale
  after an update, the user must DISCONNECT and reconnect the mdx connector (a new chat is not enough).
- **Non-US tickers:** always `find_stock` first (our suffixes differ from Yahoo/others).
- **theme_pulse returns THREE separate cohorts** (megatrend / GICS / ETF) — a concept can span GICS
  sectors, so their winners/losers genuinely differ. Present them separately; don't blend into one list.

---

## Voice
Research-analyst framing: facts and observations, not advice. Explain the *why* (news + positioning);
where news and positioning agree or diverge, say so. If the user holds the name, tie the read to their
position. Don't tell them to buy/sell/time — hand the judgment back.
