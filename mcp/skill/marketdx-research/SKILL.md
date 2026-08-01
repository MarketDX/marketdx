---
name: marketdx-research
description: >-
  Use for ANY investment / financial-markets question when the MarketDX (mdx) connector is available —
  "how is a stock, sector, or market doing", news & market-impact, why an asset moved, options
  positioning, portfolio analysis, sector/theme research. Encodes which mdx tool to reach for so you
  don't web-search what mdx answers better. Trigger on tickers, company/sector names, market/index
  mentions, or "how's X doing / what moved X" — INCLUDING a specific company's news, PUBLIC or PRIVATE
  (OpenAI, Anthropic, SpaceX, …): private companies resolve to an internal oc: id via find_stock and mdx
  tracks their news→impact, so these are mdx questions, not web searches. Also covers COMMODITIES
  (`SYMBOL.COMM` — metals, energy, agris, carbon/EU-ETS, LME-vs-onshore-China variants), GOVERNMENT-BOND
  YIELDS (`<ISO2>-<TENOR>.GB`, e.g. US-10Y.GB) and MONEY-MARKET RATES (`<TOKEN>.MM`, e.g. SOFR.MM) — so
  "US 10-year treasury / SOFR / the yield curve / copper / carbon price" are mdx questions too.
---

# MarketDX — using the mdx connector well

MarketDX (`mdx`) is a financial **news→impact graph**: it maps news to the assets and megatrends it
actually moves — direction (+/−), the causal **why**, and the ripple to connected players — across
stocks, ETFs, indices (via ETF), forex, crypto, commodities (`SYMBOL.COMM`), government-bond yields
(`.GB`), money-market rates (`.MM`), and private/off-coverage companies. It also serves options
positioning, the megatrend taxonomy, the user's portfolios, and a personal notes layer.

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
| How is a SECTOR / INDUSTRY / THEME doing? (semiconductors, AI, energy, banks, gold, robotics…) — OR a COUNTRY / REGION MARKET (Chinese stocks, the Thai market, Hong Kong, Taiwan, Japan) | **`theme_pulse(concept)`** | Fans out to the cohorts that apply (megatrend / GICS / tradable-ETF options) — present them SEPARATELY, don't merge. A country/region resolves to its covered country ETF for the **options/sentiment** lens (China→MCHI, Hong Kong→EWH, Taiwan→EWT, Thailand→THD, Japan→EWJ; theme/GICS auto-skip). This is how "how's the <country> market / sentiment doing" reaches options — `brief(country=…)` gives the news summary but NOT options, so for a SENTIMENT/positioning read use `theme_pulse` (or `asset_pulse` on the country ETF), and pair with `brief` for the news picture. |
| Which STOCKS in a group are INTERESTING / winning / losing / most-talked-about? (rank the NAMES inside semis / a GICS sector / a country) | **`screen_stocks(megatrend?, gics?, country?)`** | News-impact screener. ≥1 scope required (name or id — resolved for you). LEAD with the winners-vs-losers split (`direction_split`), surface net-NEGATIVE standouts separately, explain each via `top_reason`. `direction=pos/neg`, `order_by=news_count/relevance/market_cap`. Different from `theme_pulse` (the sector's overall pulse) — this ranks the members. |
| Which stocks pay a HIGH / RELIABLE / GROWING DIVIDEND? income / yield / "กินปันผล" | **`screen_dividends(country?, gics?, sector?)`** | Income screener over ALL payers (not just news-covered). ≥1 scope. `order_by=yield`(default)`/streak/cagr`, `min_yield`/`max_yield` (%), `min_streak_years` (≤10). 🔴 NEVER present the yield alone — each row DECOMPOSES it (`ttm_div_yoy_pct`, `no_cut_streak_yrs`, `last_cut_year`, `cagr_5y_pct`, `week52_low`, `news`): high yield + recent cut + bad news = TRAP; high yield from a price drop + intact/growing dividend + a clean 10y streak = VALUE. ⚠️ `no_cut_streak_yrs` is a bounded RELIABILITY signal — no-cut years within a 10-YEAR window, **caps at 10** (10 = clean through the whole decade incl. 2020 & 2022 stress). It is NOT the dividend's full age: do NOT report a multi-decade "aristocrat / dividend-king" streak — not from this tool and not from your own knowledge; say "clean for 10y+ (the full tracked window)". A pure "which has the LONGEST-EVER streak / oldest dividend king" trivia question is outside this tool's 10y window — say so rather than web-guessing a number. Follow the payload `_guide`. |
| The MARKET / an INDEX "right now" (S&P, Nasdaq, Dow, "the market") | **`asset_pulse`** on its ETF: S&P→SPY, Nasdaq→QQQ, Dow→DIA | We DO cover their options + news. A web-searched index *level* is at most ONE supplementary number — never the whole answer, never skip the mdx read. |
| A GOVERNMENT-BOND YIELD or a MONEY-MARKET RATE (US 10-year treasury, the yield curve, JGB, Bund, SOFR, EFFR, EURIBOR, Fed policy rate) | **`asset_pulse`/`stock_prices`** on `<ISO2>-<TENOR>.GB` (US-10Y.GB, JP-10Y.GB, DE-2Y.GB) or `<TOKEN>.MM` (SOFR.MM, EFFR.MM) — resolve via **`find_stock`** if unsure | 🔴 A yield is a LEVEL, not a price: the payload has `metric_kind="yield"` → narrate each window's **`change_bps` in BASIS POINTS**, NOT `change_pct` (a % of a yield is sign-inverted + wrong unit; "US-10Y +52 bps" not "+12%"). Bonds also give `price_proxy_pct` + `mod_duration` = an L1 bond-PRICE estimate (≈ −ModDur×Δy; label it an estimate, point to TLT/IEF for an exact bond return). **yield↑ ⇒ bond price↓.** No options/PE/market-cap and null volume on a yield = EXPECTED, not a gap. Macro news (Fed/BOJ/CPI) links here via `stock_impact`/`search_news`. |
| Summarize a whole SCOPE — a news category ("commodity news"), a country/market, a GICS sector, a megatrend, or an AND-mix | **`brief(...)`** | The composed NEWS "how is <X> doing" picture (no options lens). NOT `search_news`/`news_feed` (raw list). For a country/region *sentiment/positioning* read, add `theme_pulse` (its country-ETF options). |
| Resolve a company NAME or an unsure/foreign TICKER → exact mdx ticker | **`find_stock(name)`** FIRST | ⚠️ mdx uses its OWN suffixes (Korea `.KO` not `.KS`, Taiwan `.TW`, …) — guessing a non-US ticker 404s. Also resolves commodities (gold→`GOLD`, carbon→`CARBON_EU`, LME nickel→`NICKEL_LME`), crypto (`BTC`), private (openai→`oc:52`), bond yields (US 10-year treasury→`US-10Y.GB`), and rates (SOFR→`SOFR.MM`). 🔴 **DISAMBIGUATE, don't blind-pick the top match:** if 2+ candidates are BOTH strong (≈equal similarity) AND genuinely different entities — a different **asset type** (Apple Inc `AAPL.US` vs the Fuji-apple commodity `APPLE.COMM`; a company vs a same-named commodity) or a different **country** ("KBANK" = Kasikornbank `KBANK.BK` 🇹🇭 vs Korean `Kbank` `279570.KO` 🇰🇷 — two REAL banks that share the name) — and the user's wording doesn't pin one down, **ASK which they mean** ("Apple the company or apple the commodity?" / "the Thai or the Korean one?") before answering. Multiple equally-strong hits = that IS the ambiguity signal. 🔴🔴 An exact **ticker-SYMBOL** match does **NOT** count as "dominating" over a same-named real company in another country: symbol-match only breaks DISPLAY ordering, it does NOT resolve the human question — the user may still mean the foreign namesake, so **still ASK**. (Do not rationalise "KBANK is the exact Thai ticker so they must mean the Thai one" — a Korean bank is literally also named Kbank.) Only auto-pick when the other candidates are clearly NOT the same kind of thing (an ETF that merely tracks it, a tiny unrelated firm, a commodity when context is obviously equities) OR the context settles it. ✅ **The QUERY'S OWN wording often settles it — then just ANSWER, do NOT over-ask** (asking would be annoying): an asset-TYPE word (`หุ้น`/"stock"/"the stock" → excludes the commodity; "commodity"/"สินค้าโภคภัณฑ์"/"ฟิวเจอร์ส" → the commodity), a COUNTRY word (`ของไทย`/Thai vs Korean → picks that country's), or a more-SPECIFIC name (`กสิกร` = Kasikorn → the Thai bank; "iPhone maker" → Apple Inc) that maps to exactly ONE candidate. Ask ONLY when the wording is bare/generic and 2+ real different-entity candidates remain (bare "แอปเปิ้ล", bare "KBANK"). 🧵 **CONVERSATIONAL context is a real prior — apply it SYMMETRICALLY, even AGAINST the exact-symbol / bigger-cap default.** The country/sector the chat has been about carries into an ambiguous follow-up. If you've been discussing KOREAN names (SK Hynix, Samsung) and the user then says "แล้ว KBANK ล่ะ", do **NOT** silently default to the Thai `KBANK.BK` just because it's the exact-symbol / larger match — in a Korean conversation the Korean namesake (`Kbank` `279570.KO`) is now the *more likely* read. When context points AWAY from the symbol-match default, that IS ambiguity → **ASK, surfacing the context-implied one FIRST** ("เราคุยหุ้นเกาหลีกันอยู่ — หมายถึง Kbank เกาหลี (279570.KO) หรือกสิกรไทย (KBANK.BK) ครับ?"). The prior works both ways: after PTT/CPALL (Thai) → "KBANK" is unambiguously the Thai bank → just answer. The failure mode to avoid: using context only when it agrees with the symbol match, and ignoring it when it disagrees. |
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
- **theme_pulse returns UP TO three separate cohorts** (megatrend / GICS / ETF) — a concept can span GICS
  sectors, so their winners/losers genuinely differ. Present them separately; don't blend into one list.
  A country/region resolves only the ETF cohort (theme/GICS skip) — that's expected, see `skipped`.
- **Commodities have NO country** (they're global) — `find_stock` returns a `region` instead (currency-
  derived: CNY→onshore China, else Global). Some metals trade as BOTH an onshore-China (CNY) contract and
  an LME (USD) one — these are DIFFERENT prices (onshore vs offshore can diverge); palm oil has a USD
  (`PALMOIL`) vs Bursa-MYR (`PALMOIL_MY`) variant. Read the `region`/currency before comparing prices.
- **A bond yield / rate is a LEVEL** — always narrate its move in `change_bps` (basis points), never as a
  % of the yield. `yield↑ ⇒ bond price↓`. A yield having no options/PE/market-cap is EXPECTED.

---

## Voice
Research-analyst framing: facts and observations, not advice. Explain the *why* (news + positioning);
where news and positioning agree or diverge, say so. If the user holds the name, tie the read to their
position. Don't tell them to buy/sell/time — hand the judgment back.
