---
name: marketdx-research
description: >-
  Use for ANY investment / financial-markets question when the MarketDX (mdx) connector is available —
  "how is a stock, sector, market, commodity, or bond doing", news & market-impact, why an asset moved,
  options positioning, portfolio analysis, sector/theme research. Encodes WHICH mdx tool to reach for so
  you don't web-search what mdx answers better, and HOW to disambiguate/present. Trigger on tickers,
  company/sector names, market/index/commodity/rate mentions, or "how's X doing / what moved X" — INCLUDING
  a specific company's news, PUBLIC or PRIVATE (OpenAI, Anthropic, …): private companies resolve to an
  internal oc: id via find_stock, so these are mdx questions, not web searches. Also covers commodities
  (gold/oil/copper/carbon), government-bond yields, money-market rates, and the yield curve.
---

# MarketDX — using the mdx connector well

MarketDX (`mdx`) is a financial **news→impact graph**: it maps news to the assets and megatrends it moves —
direction (+/−), the causal **why**, and the ripple to connected players — across stocks, ETFs, indices
(via ETF), forex, crypto, commodities, government-bond yields, money-market rates, and private/off-coverage
companies. It also serves options positioning, the megatrend taxonomy, and the user's portfolios.

This skill governs behaviour: **which tool to reach for, how to disambiguate, and how to present.** Each
tool's *parameters* are documented on the tool itself (its schema) — trust those; this skill won't repeat
them. (Notes capture/recall is a SEPARATE skill, `marketdx-notes` — not covered here.)

---

## 1. Routing — reach for mdx, not a web search

**Golden rule:** any read on how a tradable asset/sector/market is *doing*, what *moved* it, or *why* — in
ANY language — is a MarketDX question. Our news→impact + positioning **IS** the substance of "how is it
doing"; a web search cannot supply it. Never answer these with only a web search. A web-searched price/index
LEVEL is at most ONE supplementary number, never the whole answer.

| The user is asking about… | Tool | Routing note (when THIS, not a sibling) |
|---|---|---|
| ONE company / ETF / index / crypto — "how's X doing / what moved it" | **`asset_pulse`** | The full read (price + news + options + peers) in one. An INDEX → its ETF (S&P→SPY, Nasdaq→QQQ, Dow→DIA). ⚠️ NOT a commodity/bond (they have their own pulse). |
| a **COMMODITY** (gold, oil, gas, copper, carbon, metals, agris) | **`commodity_pulse`** | Its own tool because the general resolver buries commodities under same-named companies, and a commodity has no options/PE. Returns price + supply/demand news + onshore/offshore variants. |
| a **BOND / RATE / YIELD CURVE** ("US rates", "is the curve inverted?", US 10Y, SOFR, Bund) | **`bond_pulse`** | Rates are a CURVE, not a point → the whole curve + 2s10s slope (negative = inverted = recession signal) + macro news. Narrate moves in BASIS POINTS. For a forward "will rates rise/fall?" it also returns `rate_positioning` (US Treasury-ETF options TLT/IEF: ETF price↓=yields↑, negative score = positioned for HIGHER yields) — use it, don't reach for TLT options yourself. |
| a **SECTOR / THEME**, or a **COUNTRY / REGION market** (semis, AI, banks; Chinese stocks, the Thai market) | **`theme_pulse`** | Fans out to up-to-three SEPARATE cohorts (megatrend / GICS / tradable-ETF options) — present them separately, don't merge. A country/region resolves only the ETF-options cohort (China→MCHI, HK→EWH, TW→EWT, TH→THD, JP→EWJ); pair with `brief` for the news picture. |
| just the PRICE picture — cheap/extended, drawdown, 52w range, vol | **`stock_prices`** (one) / **`stock_prices_batch`** (a watchlist) | `asset_pulse` already includes price; use these for price-only. Quote the ready `*_read` labels. |
| WHICH names in a group are winning / losing / most-talked-about | **`screen_stocks`** | LEAD with the winners-vs-losers split; surface net-negatives separately; explain each via `top_reason`. (Ranks the members — different from `theme_pulse`, the group's overall pulse.) |
| a HIGH / RELIABLE / GROWING DIVIDEND — income screen | **`screen_dividends`** | 🔴 NEVER present the yield alone — DECOMPOSE it (yoy, streak, last cut, cagr, 52w-low, news): high yield + a cut + bad news = TRAP; high yield from a price drop + intact/growing dividend + a clean streak = VALUE. The no-cut streak CAPS at 10y — say "clean for 10y+ (the tracked window)", never claim a multi-decade "aristocrat" streak (not from this tool nor your own memory). |
| summarize a whole SCOPE — a news category, a country, a GICS sector, a megatrend, an AND-mix | **`brief`** | The composed NEWS "how is <X> doing" picture (no options lens). NOT `search_news`/`news_feed` (those are a raw article LIST). |
| resolve a company NAME / unsure TICKER → exact mdx ticker | **`find_stock`** FIRST | See **§2** for disambiguation. mdx uses its OWN suffixes (Korea `.KO` not `.KS`). Resolves commodities/crypto/bond-yields/rates and **private companies → an `oc:` id** too. |
| a **PRIVATE / off-coverage** company (OpenAI, SpaceX, Stripe, ByteDance, xAI, …) | **`find_stock` FIRST**, then `stock_impact(oc:id)` / `private_movers(theme)` | 🔴 A private company has NO public ticker but mdx assigns an INTERNAL `oc:<n>` (openai→`oc:52`) that find_stock returns — so "it's private" is NEVER a reason to web-search. Run find_stock on the NAME, take the `oc:` id, query with it (OpenAI alone has 200+ scored articles). |
| resolve a THEME/trend → node id · an INDUSTRY/SECTOR → GICS code | **`find_megatrend`** · **`find_gics`** | Return candidates; YOU pick and reuse the id/code. |
| DRILL-DOWNS | `stock_impact` (per-stock news), `options_sentiment` (US names), `relationships` (peers), `theme_players`/`private_movers` (theme members), `news_feed`/`search_news` (raw list) | Prefer the composites (`asset_pulse`/`theme_pulse`/`commodity_pulse`/`bond_pulse`) first; use singles to drill afterward. `theme_players`/`private_movers`/`relationships` return a TOP SLICE — if `total > count` say "N of M", don't imply the full roster. |
| the user's OWN portfolio | **`list_portfolios`** → **`portfolio_pulse`** (market read) / **`portfolio_context`** (numbers) | Owner-scoped; call list first if they say "my portfolio" without a number. |
| INTERNATIONAL TRADE — exports/imports, "who exports/imports the most / fastest-growing / N years straight", trade balance, a country's trade partners | **`find_hs`** (FREE, resolve concept→code) → **`search_trade`** / **`top_traders`** / **`top_partners`** / **`trade_balance`** | See **§4**. ALWAYS `find_hs` first (never guess a code). Merchandise = `type=goods` (HS); services (travel/IT/financial) = `type=services` (EBOPS). BYOK: no key → relay the connect CTA, answer from general knowledge meanwhile. |

---

## 2. Resolving a name — DISAMBIGUATE, don't blind-pick (find_stock)

🌐 **Answer in the user's language, but for a generic ASSET-CLASS concept (a commodity/sector/index) resolve
in ENGLISH** (ทองคำ/黄金→"gold", 天然ガス→"natural gas", 半導体→"semiconductors"). A COMPANY proper name passes
as-is (the DB has native names: 茅台→Kweichow Moutai, トヨタ→Toyota). *(Better still, a commodity → skip
find_stock and go straight to `commodity_pulse`.)*

🔴 **When a name maps to 2+ genuinely DIFFERENT entities and the user's wording doesn't pin one, ASK — don't
silently pick #1.** The two collision types:
- **asset TYPE** — a company vs a same-named commodity: Apple Inc `AAPL.US` vs the Fuji-apple commodity
  `APPLE.COMM`; "coke" = Coca-Cola vs coke (the fuel).
- **COUNTRY** — the same name is two REAL companies in different markets: "KBANK" = Kasikornbank `KBANK.BK`
  🇹🇭 vs the Korean `Kbank` `279570.KO` 🇰🇷.

🔴🔴 An exact ticker-SYMBOL match does **NOT** settle it — symbol-match only orders the display; the user may
still mean the foreign namesake. Don't rationalise "KBANK is the exact Thai ticker so they must mean Thai."

✅ **But don't OVER-ask — the query itself often settles it, then just ANSWER:** an asset-TYPE word
("หุ้น"/"stock" excludes the commodity; "commodity"/"futures" picks it), a COUNTRY word ("ของไทย"), or a
more-specific name ("กสิกร"=Kasikorn, "iPhone maker"=Apple) mapping to ONE candidate. Also skip the ask when
the other hits clearly aren't the same kind of thing (an ETF that merely tracks it, a tiny unrelated firm).
Ask ONLY when the wording is bare/generic and 2+ real different-entity candidates remain (bare "แอปเปิ้ล",
bare "KBANK").

🧵 **CONVERSATIONAL context is a real prior — apply it SYMMETRICALLY, even AGAINST the exact-symbol default.**
After discussing KOREAN names (SK Hynix, Samsung), a bare "KBANK" more likely means the Korean Kbank than the
Thai `KBANK.BK` — so ASK, surfacing the Korean one FIRST. It works both ways: after Thai names (PTT/CPALL),
"KBANK" is unambiguously the Thai bank → just answer. The failure to avoid: using context only when it agrees
with the symbol match and ignoring it when it disagrees.

*(Tool choice IS part of the disambiguation: "หุ้น apple"→`asset_pulse`, "apple futures"→`commodity_pulse`,
bare ambiguous "apple"→ask.)*

---

## 3. Coverage, voice, gotchas

**Coverage:** mdx NEWS starts **2026-01-01** — for anything older say so plainly; never present an empty
result as "nothing happened". PRICE/volatility history goes back DECADES, so "why was gold volatile in 2023"
IS answerable from price (not news) — reach for the price lens, don't conflate "no news" with "no data".

**Voice:** research-analyst — facts + the *why* (where news and positioning agree or diverge), NOT advice.
Never say buy/sell/time; never predict a future price. If the user holds the name, tie the read to their
position. Hand the judgment back. A pure DEFINITION/concept question ("what is a P/E ratio") is general
knowledge — answer it directly, don't force a tool or a web search.

**Gotcha:** the connector caches its tool list + descriptions at connect-time — after an mdx update the user
must DISCONNECT and reconnect (a new chat is not enough).

---

## 4. Trade lens (UN Comtrade) — physical import/export flows

The trade tools add the one substrate news+price+options lack: **how much of a good/service actually flows
between which countries, over time** — decomposed (value/volume/price), ranked, trended. Two uses:

**(a) A DIRECT trade question** ("who exports the most soybeans", "coffee imports down 3y straight", "Thai
vs Vietnamese rice exports", "is Thailand a net exporter to China") → the tools in the §1 row.
`find_hs` (FREE) FIRST → pick the code from its evidence (`score` ~0.7+ = clean; `excludes` name the
siblings; ambiguous *different* concepts like pet-food 230910 vs livestock-feed 230990 → **ask** which) →
`search_trade` (a flow over time, read its `analysis` block) / `top_traders` (rank countries — value /
growth / **streak**) / `top_partners` (a country's buyers/sellers) / `trade_balance`. Pass the **specific
tradable form** ("hot-rolled steel coil", not "steel" → which drifts to finished articles). "#2 exporter" =
the rank:2 row; "both X and Y up 5y" = call per commodity and intersect yourself; an empty list is a real
answer — relay it.

**(b) A HIDDEN lens** on a stock / commodity / theme / tariff-news question — reach for it only after the
**gate**, in order:
1. 🔴 **Cross-border?** Comtrade sees ONLY goods/services crossing borders — we have EXIM, **no domestic
   consumption/sales data**. A domestic-demand business (CPALL/7-Eleven, domestic utilities/telecom/retail
   banks) → **ABSTAIN**: say "trade data can't speak to this (cross-border only)", don't force a weak angle.
   The signal: `price.revenue_by_region` foreign share (home-only → domestic). The border test is subtle for
   services — *does a flow cross the border / serve foreign demand?*, not goods-vs-services: a hotel serving
   FOREIGN tourists = travel-services **export** ✅; a domestic convenience chain ❌.
2. **Goods or services** → set `type`.
3. **Materiality** → for the input/output COMMODITY angle, TRUST `price.related_assets` (materiality-
   weighted; `channel` = the analytical angle: `output_price` = its product, `input_cost` = a cost driver,
   `demand` = a demand backdrop — all valid). NOT listed = not material — don't free-associate a supply
   chain (a GPU's copper is immaterial; a battery's lithium is not).

**Deriving the keyword (your world knowledge does this — read what's in the payload, don't guess codes):**
`price.description` + `gics` say what the firm makes/does → **enumerate ALL material lines** (a conglomerate
like MINT = hotels **and** restaurants; don't stop at the gics headline — verify/web-search if unsure), then
`find_hs` per line. `price.revenue_by_region` = the WHERE (which reporter/partner). Enumerate broadly (find_hs
is FREE), pull metered trade data only on the material lines.

**Signature uses:** a MINER (BHP → output = iron ore/copper; is demand in its destination markets rising or
FALLING? the divergence is the insight) · a policy-exposed name (NVDA → China revenue + tariff/export-control
news → chip HS 8542 US↔China flow, NOT a materials chain) · **tariff / trade-war news** (US-China → pull the
actual `trade_balance` to quantify what the sentiment only gestures at).

**Voice/limits:** quote the `analysis`/`reason` (sourced); surface `_license_note`; data goes back to 1962
(older than news); a gap in old years = an HS-revision break, not zero trade. Same research-analyst voice.
