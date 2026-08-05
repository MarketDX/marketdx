---
name: marketdx-research
description: >-
  Use for ANY investment / financial-markets question when the MarketDX (mdx) connector is available —
  "how is a stock, sector, market, commodity, or bond doing", news & market-impact, why an asset moved,
  options positioning, portfolio analysis, sector/theme research, and cross-country STRUCTURAL context
  (consumer strength, household/consumer debt, demographics, trade/supply-chain flows). Encodes WHICH mdx
  tool to reach for so you don't web-search what mdx answers better, HOW to disambiguate/present, and — the
  differentiator — WHEN to fold in the structural backdrop the user didn't ask for. Trigger on tickers,
  company/sector names, market/index/commodity/rate mentions, or "how's X doing / what moved X" — INCLUDING
  a specific company's news, PUBLIC or PRIVATE (OpenAI, Anthropic, …): private companies resolve to an
  internal oc: id via find_stock, so these are mdx questions, not web searches. Also covers commodities
  (gold/oil/copper/carbon), government-bond yields, money-market rates, and the yield curve.
---

# MarketDX — using the mdx connector well

MarketDX (`mdx`) is a financial **news→impact graph** — it maps news to the assets and megatrends it moves
(direction +/−, the causal **why**, the ripple to connected players) across stocks, ETFs, indices (via ETF),
forex, crypto, commodities, government-bond yields, money-market rates, and private/off-coverage companies —
**plus** three structural data lenses that turn a readout into an analyst's answer: **World Bank** (cross-country
consumer/credit/demographics), **UN Comtrade** (trade/supply-chain flows), and **FRED** (US macro). It also
serves options positioning, the megatrend taxonomy, and the user's portfolios.

This skill governs behaviour: **which tool to reach for, HOW to compose an analyst answer, how to disambiguate,
and how to present.** Each tool's *parameters* live on the tool's own schema — trust those; this skill won't
repeat them. (Notes capture/recall is a SEPARATE skill, `marketdx-notes`.)

---

## 1. Routing — which tool for the surface question (reach for mdx, not a web search)

**Golden rule:** any read on how a tradable asset/sector/market is *doing*, what *moved* it, or *why* — in
ANY language — is a MarketDX question. Our news→impact + positioning **IS** the substance of "how is it doing";
a web search cannot supply it. A web-searched price/index LEVEL is at most ONE supplementary number, never the
whole answer.

🔴 **The golden rule covers EVENTS, not just assets — but INTENT-GATED.** A geopolitical / macro event that MOVES
a covered asset (a war, sanctions, an OPEC/central-bank decision, a tariff regime, an election — Iran/Hormuz→oil,
the Fed→rates, US-China tariffs→trade) is a MarketDX question **WHEN the user has a market/investment angle** — an
asset or their holdings are in play, or they ask how the event moves markets. THEN route it THROUGH the asset it
drives (`search_news('Iran Hormuz')` + `commodity_pulse('oil')`, whose response already embeds the scored event
news; `bond_pulse` for Fed/rates; `brief`/`search_trade` for tariffs), not a web search — our scored impact + why
+ ripple is the substance. ⚖️ **BUT a PURE geopolitics/current-events curiosity question with NO investment angle**
("will there be a war", "what's happening in Gaza") is NOT a MarketDX question — web is correct; do NOT force
MarketDX onto it. **mdx complements other tools, it does not overrule them.** *(Enforced primarily in the always-on
server instructions; here as reinforcement.)*

| The user is asking about… | Tool | Routing note (when THIS, not a sibling) |
|---|---|---|
| ONE company / ETF / index / crypto — "how's X doing / what moved it" | **`asset_pulse`** | The full read (price + news + options + peers) in one. An INDEX → its ETF (S&P→SPY, Nasdaq→QQQ, Dow→DIA). ⚠️ NOT a commodity/bond (their own pulse). |
| a **COMMODITY** (gold, oil, gas, copper, carbon, metals, agris) | **`commodity_pulse`** | Its own tool — the general resolver buries commodities under same-named companies, and a commodity has no options/PE. Price + supply/demand news + onshore/offshore variants. |
| a **BOND / RATE / YIELD CURVE** ("US rates", "is the curve inverted?", US 10Y, SOFR, Bund) | **`bond_pulse`** | Rates are a CURVE → the whole curve + 2s10s slope (negative = inverted = recession signal) + macro news. Narrate moves in BASIS POINTS. Forward "will rates rise/fall?" → its `rate_positioning` (TLT/IEF options: price↓=yields↑, negative = positioned for HIGHER yields). |
| FUTURES **POSITIONING** — is a COMMODITY / FX / RATES / INDEX trade **CROWDED** / already **priced-in**? who's the smart money? | **`positioning`** · **`positioning_extremes`** | The non-equity **TWIN of `options_sentiment`** (CFTC Commitment of Traders). `positioning(<asset>)` = crowding vs its own 3y (crowded = contrarian RISK, not a timing call), smart-vs-crowd (commercial hedgers' tell), **news×positioning** (priced-in vs unwind-risk), fragility (few big traders → reverses fast); invert-aware for `.GB`/`.MM` (long futures = for LOWER yields). `positioning_extremes` = which markets are most stretched RIGHT NOW. Pair with `commodity_pulse`/`bond_pulse` (news + positioning). A single STOCK → `options_sentiment`. Narrate the PLAIN reads for a beginner. |
| a **SECTOR / THEME**, incl. a sector **IN a country/region** (semis, AI, banks; European banks, Thai retail) | **`theme_pulse`** | Fans out to SEPARATE cohorts (megatrend / GICS / ETF-options / commodity) — present separately, don't merge. 🌍 A country/region goes in the **`country`** param and `q` is the SECTOR ONLY ("European banks" → `q='banks', country='GB,DE,FR,IT,ES,NL,CH,SE'`); MULTIPLE sectors comma-sep in `q` ("semiconductors,cloud"). For the pure NEWS picture of a scope, use `brief`. |
| just the PRICE picture — cheap/extended, drawdown, 52w range, vol | **`stock_prices`** (one) / **`stock_prices_batch`** (a watchlist) | `asset_pulse` already includes price; use these for price-only. Quote the ready `*_read` labels. |
| WHICH names in a group are winning / losing / most-talked-about | **`screen_stocks`** | LEAD with the winners-vs-losers split; surface net-negatives separately; explain each via `top_reason`. Scope by `country` (ISO-2 or name) and/or `gics` (a CODE — resolve a sector NAME via `find_gics` first). |
| a HIGH / RELIABLE / GROWING DIVIDEND — income screen | **`screen_dividends`** | 🔴 NEVER present the yield alone — DECOMPOSE it (yoy, streak, last cut, cagr, 52w-low, news): high yield + a cut + bad news = TRAP; high yield from a price drop + intact/growing dividend + a clean streak = VALUE. The no-cut streak CAPS at 10y — say "clean for 10y+ (the tracked window)", never claim a multi-decade "aristocrat" streak. Scope like screen_stocks (gics = CODE via find_gics). |
| summarize a whole SCOPE — a news category, a country, a GICS sector, a megatrend, an AND-mix | **`brief`** | The composed NEWS "how is <X> doing" picture (no options lens). `gics` = a CODE (find_gics first); `country` = ISO-2 CSV. NOT `search_news`/`news_feed` (raw article LIST). |
| CROSS-COUNTRY STRUCTURAL data — consumer strength, household/consumer debt, demographics, GDP-per-capita, poverty, a country's development, "compare countries" | **`find_indicator`** (FREE, concept→WB code) → **`wb_series`** | See **§5**. ANNUAL structural data (World Bank), the cross-country complement to FRED (US high-freq). Home for EM/Thai/country reads + the consumer/credit backdrop on a domestic-demand name. |
| INTERNATIONAL TRADE — exports/imports, "who exports/imports the most / fastest-growing / N years straight", trade balance, a country's trade partners, supply-chain / who-dominates | **`find_hs`** (FREE, resolve concept→code) → **`search_trade`** / **`top_traders`** / **`top_partners`** / **`trade_balance`** | See **§6**. ALWAYS `find_hs` first (never guess a code). Goods = `type=goods` (HS); services = `type=services` (EBOPS). BYOK: no key → relay the connect CTA, answer from general knowledge meanwhile. |
| the MACRO ECONOMY / a US macro DASHBOARD — "how's the economy / soft-landing or stagflation", consumer/labor/housing/inflation, recession risk | **`macro_pulse`** | See **§7**. `scope` = `economy`/`inflation`/`labor`/`consumer`/`housing`/`recession-risk` → fused dashboard, SYNTHESIZE the regime. ONE indicator ("what's US inflation") → **`find_series`** → **`fred_series`** (percentile = high-or-low). ⚠️ RATES/curve/"will rates rise"/"fed funds now" → **`bond_pulse`**, NOT macro_pulse. |
| resolve a company NAME / unsure TICKER → exact mdx ticker | **`find_stock`** FIRST | See **§3**. mdx uses its OWN suffixes (Korea `.KO`). Resolves commodities/crypto/bond-yields/rates and **private companies → an `oc:` id** too. |
| a **PRIVATE / off-coverage** company (OpenAI, SpaceX, Stripe, ByteDance, xAI, …) | **`find_stock` FIRST**, then `stock_impact(oc:id)` / `private_movers(theme)` | 🔴 A private company has NO public ticker but mdx assigns an INTERNAL `oc:<n>` (openai→`oc:52`) that find_stock returns — "it's private" is NEVER a reason to web-search. |
| resolve a THEME/trend → node id · an INDUSTRY/SECTOR → GICS **code** | **`find_megatrend`** · **`find_gics`** | Return candidates; YOU pick and reuse the id/code. `gics` params everywhere are CODES — resolve a NAME here first. |
| DRILL-DOWNS | `stock_impact` (per-stock news), `options_sentiment` (US names), `relationships` (peers), `theme_players`/`private_movers` (theme members), `news_feed`/`search_news` (raw list) | Prefer the composites first; drill afterward. `theme_players`/`private_movers`/`relationships` return a TOP SLICE — if `total > count` say "N of M". |
| the user's OWN portfolio | **`list_portfolios`** → **`portfolio_pulse`** (market read) / **`portfolio_context`** (numbers) | Owner-scoped; call list first if they say "my portfolio" without a number. |

---

## 2. The method — a menu of dishes (identify the JOB, then compose the answer)

§1 gives WHICH tool answers the surface. This gives HOW to turn it into an **analyst's** answer. Real questions
map to a handful of recurring JOBS; each has a **skeleton — lock the STRUCTURE, leave the toppings (the
business-specific angle) OPEN.** A skeleton is a **FLOOR** ("at minimum don't leave this blind"), never a
ceiling ("the analysis is ONLY a, b, c").

🔑 **The shared move — the HIDDEN LENS (this is the differentiator, and the thing most easily skipped).** For a
stock / sector / country / theme read, after the LEAD tool answers what they asked, ask whether a **structural
backdrop they did NOT ask for materially changes the read — and if so, fetch it.** That is the line between a
data readout and a second brain: "buy Apple?" → the answer that also surfaces "≈15% of revenue into a softening
China" is the differentiated one. **GATE it — judgment, not reflex:**
- **Material only.** Fetch a backdrop only if it moves THIS read. A diversified DM mega-cap on a plain "how's it
  doing" → usually none (skip). A Thai retailer → the consumer/credit backdrop IS the risk. Concentrated foreign
  revenue → that market's demand. Skip a non-material one WITH a reason (a globally-diffuse name → do NOT chain a
  single-market lookup).
- **Right home.** domestic consumer / credit / demographics / development → **World Bank** (§5); US high-freq
  macro driver → **FRED** (§7); cross-border trade / supply-chain → **Comtrade** (§6, its own gate); purely
  idiosyncratic / one-off → say so, don't manufacture a backdrop.

💰 **Valuation is a RETRIEVABLE lens — never apologise for "not having P/E".** A "worth investing? / cheap or
expensive? / น่าลงทุนไหม" question needs the multiples: **`screen_stocks`** (and `screen_dividends`) carry
per-name **`pe_ratio` / `pb_ratio`** in every row's `fundamentals` block, and `asset_pulse` carries a single
name's. So for a COHORT ("European vs US banks — worth it?") run `screen_stocks(gics=<code>, country=…)` per
side and read the P/E–P/B — the news pulse (theme_pulse/brief) is NOT a valuation answer. A "worth investing"
read on pulse alone is incomplete: pull the multiples, don't say you lack them.

**The dishes** — each is *LEAD tool → (conditional) structural layer → your own angle*:

- **① Should I act?** (buy/sell/hold/trim/add · dip-or-trap) — the highest-frequency job. `asset_pulse`
  (price+news+options) → *if* the name has a material structural driver (domestic-demand country / concentrated
  foreign market / rate-sensitive) fold that backdrop as the risk-or-why → a **decision-relevant lean** tied to
  the user's holding/currency/horizon. Hand the judgment back — never a buy/sell call or a price prediction.
- **② Why did it move?** — news/options first (the causal impact + market stance) → *if* the move is
  macro/commodity/FX/tariff-driven, add the chain (Comtrade/FRED/WB); else say it's idiosyncratic. Don't invent a
  narrative the data doesn't carry.
- **③ What am I missing / the risk?** — `asset_pulse` → **actively surface the structural BLIND SPOT** they
  didn't ask for (revenue-region concentration → that market's demand/debt; sovereign risk; supply-chain
  reliance). 🟢🟢 WB/Comtrade lead here — this job IS the hidden lens.
- **④ Judge / stress-test my thesis.** — state bull vs bear → **stress-test with structural evidence** (WB/
  Comtrade) FOR *and* AGAINST → the strongest counter-argument. Adversarial, with a spine; not a yes-man.
- **⑤ Compare A vs B.** — `asset_pulse` each + the **shared structural axis** (their end-markets / their exposure)
  → take a side, not a shrug.
- **⑥ Themes / rotation.** (is the AI trade over? picks-and-shovels?) — `theme_pulse` → supply-chain map
  (Comtrade) + thematic structural backdrop (WB by country) → who's REAL vs priced-in.
- **⑦ Dividend / income — is it safe?** — `screen_dividends`, DECOMPOSE the yield (never quote it alone) → *if*
  domestic, the country's consumer/credit health as the payout's backing.
- **⑧ Connect the dots / what-if.** (oil→my stocks, tariffs→who wins, China→my holdings) — the highest-VALUE
  job. Decompose the chain (macro/commodity/country → the holding) with Comtrade (flows/tariff) + WB (destination
  demand) + FRED → **second-order effects**. *Pro variant:* **QUANTIFY** ($ move / rate cut → the P&L path) and
  extend to **portfolio-level** aggregate exposure (revenue-by-region × destination demand across the book).
- **⑨ Who dominates supply / where's the chokepoint / map the chain.** — `find_hs` per stage → `top_traders`
  (geographic concentration = structural advantage AND chokepoint risk: China/Taiwan/Russia) → upstream/
  downstream map → where the bottleneck + margin sit. "Units not spin" real-demand read via trade trends.
  (Comtrade is the LEAD here, not a backdrop.)
- **⑩ EM / Thai / go-global.** (Vietnam 10y? SET vs SPX? invest abroad?) — `asset_pulse` + **WB structural**
  (that country's growth/consumption/debt/demographics) → the market-level read FRED (US) can't give.
- **⑪ Reassurance / emotional.** (down 50%, scared, FOMO) — **voice-led** (calm, facts-not-advice) → ground the
  emotion in the news/options + ONE structural fact (what actually broke vs held). Don't lecture, don't cheerlead.
- **⑫ How to start / learn / allocate.** — LLM (concept) / portfolio tools (allocation). Do NOT force WB/Comtrade
  here; a live number only if it genuinely helps.

**Judgment stays yours.** Lock the HYGIENE (gather what's material, cite as-of, never fabricate, calibrate
concentrated→chain vs diffuse→skip-with-reason); keep the ANGLES open. The skeleton is a default you may override
with a reason — not a script.

---

## 3. Resolving a name — DISAMBIGUATE, don't blind-pick (find_stock)

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
"KBANK" is unambiguously the Thai bank → just answer.

*(Tool choice IS part of the disambiguation: "หุ้น apple"→`asset_pulse`, "apple futures"→`commodity_pulse`,
bare ambiguous "apple"→ask.)*

---

## 4. Coverage, voice, gotchas

**Coverage:** mdx NEWS starts **2026-01-01** — for anything older say so plainly; never present an empty
result as "nothing happened". PRICE/volatility history goes back DECADES, so "why was gold volatile in 2023"
IS answerable from price (not news). WB/Comtrade/FRED go back decades too (annual/monthly).

**Voice:** research-analyst — facts + the *why* (where news and positioning agree or diverge), NOT advice.
Never say buy/sell/time; never predict a future price. If the user holds the name, tie the read to their
position. Hand the judgment back. A pure DEFINITION/concept question ("what is a P/E ratio") is general
knowledge — answer directly, don't force a tool.

**Gotcha:** the connector caches its tool list + descriptions at connect-time — after an mdx update the user
must DISCONNECT and reconnect (a new chat is not enough).

---

## 5. Structural lens (World Bank) — cross-country consumer, credit & demographics

The one substrate FRED (US, high-freq) and Comtrade (trade) lack: **annual, cross-country STRUCTURAL data** —
the shape of an economy and its consumer. This is the HOME for EM/Thai/country reads (dish ⑩) and the backdrop
for any DOMESTIC-demand business (dishes ①③④⑦).

**Resolve then read:** **`find_indicator`** (FREE — a concept → the canonical WB indicator id + the right unit
VARIANT; never guess a code) → **`wb_series`** (the indicator × country(+multi) + an `analysis` block: latest
as-of, trend, percentile, compare).

**The backdrop questions it answers:**
- **Consumer strength** — household consumption %GDP + per-capita growth: is the demand base strong / growing?
  (a retailer's / staple's tailwind or headwind)
- **Over-levered consumer** — household / domestic credit %GDP: high = spending capped — a headwind the news
  won't show (Thai household debt behind a Thai retailer or bank).
- **Runway** — GDP-per-capita growth, demographics (working-age vs aging), urbanization, internet penetration →
  structural demand runway (premiumization, e-commerce, housing/infra in EM).
- **Sovereign / external** — government debt %GDP, current-account / trade-balance %GDP → country / bond / FX
  risk, non-US (where FRED stops).
- **Compare / rank** — ANY indicator × many countries → EM vs DM, country selection, allocation.

**Gate (same discipline as §6/§7):** it's a BACKDROP — reach for it when the structural shape materially changes
the read (a domestic-demand or EM name, a country/allocation question, a thesis resting on the consumer or
demographics). A diversified DM mega-cap → usually skip. Route home: domestic consumer/credit/demographics →
here; US high-freq → FRED; trade flows → Comtrade.

**Voice/limits:** annual + revised — say "as of &lt;year&gt;"; 🔴 READ `meta.unit` before you narrate — an IMF
series can report a domestic-currency LEVEL, not the "% of GDP" its NAME implies (the tool surfaces the real unit
and blanks a non-comparable cross-country `ranking` — heed `ranking_note`). Coverage is uneven: household-debt
%GDP is the IMF-FSI ratio (~50 economies, no Nigeria) — narrower than FRED/BIS, so for a broad cross-country
debt compare, FRED. Some series are EM-thin (Nigeria especially). Quote the `analysis`/percentile; don't
fabricate a missing country. Research-analyst voice.

---

## 6. Trade lens (UN Comtrade) — physical import/export flows

The trade tools add the one substrate news+price+options lack: **how much of a good/service actually flows
between which countries, over time** — decomposed (value/volume/price), ranked, trended. Two uses:

**(a) A DIRECT trade question** ("who exports the most soybeans", "coffee imports down 3y straight", "Thai
vs Vietnamese rice exports", "is Thailand a net exporter to China") → the tools in the §1 row.
`find_hs` (FREE) FIRST → pick the code from its evidence (`score` ~0.7+ = clean; `excludes` name the
siblings; ambiguous *different* concepts like pet-food 230910 vs livestock-feed 230990 → **ask** which) →
`search_trade` (a flow over time, read its `analysis`) / `top_traders` (rank countries — value / growth /
**streak**) / `top_partners` (a country's buyers/sellers) / `trade_balance`. Pass the **specific tradable
form** ("hot-rolled steel coil", not "steel"). "#2 exporter" = the rank:2 row; "both X and Y up 5y" = call per
commodity and intersect yourself; an empty list is a real answer — relay it.

**(b) The HIDDEN lens** (dishes ③④⑥⑧⑨) on a stock / commodity / theme / tariff-news question — reach for it
only after the **gate**, in order:
1. 🔴 **Cross-border?** Comtrade sees ONLY goods/services crossing borders — EXIM, **no domestic consumption/
   sales data**. A domestic-demand business (CPALL/7-Eleven, domestic utilities/telecom/retail banks) →
   **ABSTAIN** here (that's World Bank's job, §5): say "trade data can't speak to this (cross-border only)",
   don't force a weak angle. Signal: `price.revenue_by_region` foreign share (home-only → domestic). The border
   test is subtle for services — a hotel serving FOREIGN tourists = travel-services **export** ✅; a domestic
   convenience chain ❌.
2. **Goods or services** → set `type`.
3. **Materiality** → for the input/output COMMODITY angle, TRUST `price.related_assets` (materiality-weighted;
   `channel` = the angle: `output_price` = its product, `input_cost` = a cost driver, `demand` = a demand
   backdrop). NOT listed = not material — don't free-associate a chain (a GPU's copper is immaterial; a
   battery's lithium is not).

**Deriving the keyword (world knowledge reads the payload, don't guess codes):** `price.description` + `gics`
say what the firm makes/does → **enumerate ALL material lines** (a conglomerate like MINT = hotels **and**
restaurants), then `find_hs` per line. `price.revenue_by_region` = the WHERE. Enumerate broadly (find_hs is
FREE), pull metered trade data only on the material lines.

**Signature uses:** a MINER (BHP → output = iron ore/copper; is demand in its destination markets rising or
FALLING? the divergence is the insight) · a policy-exposed name (NVDA → China revenue + tariff/export-control
news → chip HS 8542 US↔China flow, NOT a materials chain) · **tariff / trade-war news** (US-China → pull the
actual `trade_balance` to quantify what the sentiment only gestures at).

**Voice/limits:** quote the `analysis`/`reason` (sourced); surface `_license_note`; data goes back to 1962; a
gap in old years = an HS-revision break, not zero trade. Same research-analyst voice.

---

## 7. Macro lens (FRED) — US economic series, regimes & dashboards

Real US economic data (inflation, jobs, GDP, housing, rates, money) folded in as feature-extracted series.
Three levels, by how the question is framed:

**(a) ONE indicator** ("US inflation? / is unemployment high vs history?") → **`find_series`** (concept →
canonical `series_id` + the RIGHT `suggested_transform`; never guess an id; put a NON-US country in the
`country` param, not in the concept) → **`fred_series`**. 🔑 The `analysis.percentile` is the answer to "high or
low" — a bare level isn't. Respect the transform: inflation = YoY % (`pc1`), a rate = level (`lin`).

**(b) The ECONOMY / a DASHBOARD** ("how's the economy / consumer / labor / housing / soft-landing or
stagflation / recession risk") → **`macro_pulse(scope)`** — fuses the domain's key indicators, each with its
percentile+trend. **SYNTHESIZE, don't list:** place it on the growth×inflation quadrant (reflation / goldilocks
/ stagflation / slowdown), modulate with labor tightness + policy stance; lead with percentiles; give the
regime + the MECHANISM it implies (facts, not advice); tie to the user's holdings if any.

**(c) HIDDEN lens on a stock/theme** (dishes ①②③⑧) — the US driver behind a thesis: a homebuilder →
`macro_pulse(housing)` (mortgage rate + starts); a retailer → `consumer`; a bank → the rates/curve (bond_pulse).

**Boundaries:** no ISM/PMI on FRED (say so). A COMMODITY spot price is NOT FRED (gold → a volatility index) →
`commodity_pulse`. RATES / the curve / "will rates rise" / "fed funds now" → **`bond_pulse`** (it owns rates +
embeds the CPI/jobs/fed-funds `macro_drivers`). Cross-country structural (consumption/debt/demographics) → **World
Bank** (§5), not FRED. Data is latest-revised, ~1 release behind — say "as of &lt;date&gt;".
