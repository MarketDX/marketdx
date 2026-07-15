# MarketDX — Financial Impact Signals (sample)

> A structured, **explained** map of *what financial news is about and who it touches* — across stocks,
> commodities, FX, crypto, **AND private companies**. For every event: the causal channel (**why**), the
> story's direction, who's in the **ripple**, and a one-line reason.
>
> A **research, screening & feature layer — not a trading signal.** (`direction` is the model's read of who
> the news *helps or hurts*, not a price forecast — by the time news is public it is largely priced in.)

A **bounded historical sample** (~2 weeks of impact-ranked events) of the MarketDX **Financial Impact
Graph** — the downloadable twin of our [live playground](https://marketdx.lab.ai/playground). One slice,
**many angles**. (A curated demo, not a production feed — see *Data quality* & *Scope*.)

| file | what | rows |
|---|---|---|
| [`data/impact-signals.csv`](data/impact-signals.csv) / [`.jsonl`](data/impact-signals.jsonl) | **the core** — one row per `event × entity × aspect`; **all asset classes** | 3,841 |
| [`data/screener.csv`](data/screener.csv) | curated screens — 6 "who the news is helping / hurting on X" patterns (the model's read) | 98 |
| [`data/discover.csv`](data/discover.csv) | **semantic search** — 15 plain-English questions → impact-labeled hits (incl. private) | 377 |
| [`data/relationships.csv`](data/relationships.csv) | **news-derived** competitor + peer graph (edge list) | 401 |
| [`data/private-impact.csv`](data/private-impact.csv) / [`.jsonl`](data/private-impact.jsonl) | **beyond tickers** — impact on OpenAI, Anthropic, Stripe… | 602 |
| [`data/private-roster.csv`](data/private-roster.csv) | the private universe mapped to trends | 1,175 |
| [`data/megatrends.csv`](data/megatrends.csv) | the 335-node trend taxonomy (interpret `node_id`) | 335 |

```
1,794 events · 3,841 impact labels · themes: AI-Power · Semiconductors  (+ AI · Digital Finance for private)
asset classes: stock · commodity · forex · crypto · private   ·   2026-06-25 → 2026-07-06   ·   CC BY 4.0
```

### What it's for — and what it isn't

- ✅ **For:** *understanding and structuring* the news firehose — the **why** (10 causal channels),
  multi-asset in one frame, second-order **ripple**, and coverage of **private companies** ticker feeds
  can't see. A research, screening, exposure-mapping and **feature** layer.
- ❌ **Not:** a predictive price signal. The labels describe the *content* of the news (who it's about, the
  channel, the story's lean) — they **do not forecast returns** on their own; by the time news is public
  it's largely priced in. Use it to understand and structure the flow, then combine it with your own
  price / surprise / positioning data.

### Start where you are

| you're a… | start with | you'll get |
|---|---|---|
| 🔬 **Analyst / PM / asset manager** | [`impact-signals.csv`](data/impact-signals.csv) + [`screener.csv`](data/screener.csv) | who each event touches and **why** (the causal channel) — theme & exposure mapping |
| 🛠️ **Developer / builder** | [`examples/loader.py`](examples/loader.py) → [playground](https://marketdx.lab.ai/playground) | the shape, then 3 lines to the live graph |
| 🧠 **Quant / data scientist** | [`impact-signals.csv`](data/impact-signals.csv) as a **feature** | labeled channel + direction per entity — an *input* to combine with your own data, not a standalone signal |
| 📰 **Journalist / VC** | [`private-impact.csv`](data/private-impact.csv) + [`discover.csv`](data/discover.csv) | news on OpenAI/Anthropic/… — the part ticker feeds can't see |
| 🤖 **AI agent / tool** | [`datapackage.json`](datapackage.json) + [`llms.txt`](llms.txt) | machine schema (types, enums, joins) + an LLM-first map |

---

## The angles this one slice answers

Because every record is labeled on many axes, the **same table** answers very different questions — just filter it.

### 🎯 Impact signals — *why* the news bears on each entity
`(event, entity) → {aspect, direction, relevance, reason}`. 10 causal channels — demand · technology ·
capital · competition · regulation · supply · pricing · geopolitics · monetary · tariff. One entity can be
touched through several at once; one event can land **positively on some and negatively on others** (the
model's read of the story, not a price call).

### 🛢️ Asset-class focus — *the multi-asset frame ticker feeds don't have*
The core carries every asset class, so slice by `entity_type`:

| focus | signals | what shows up |
|---|--:|---|
| **Commodities** (`entity_type=commodity`) | 311 | Gold · Brent · WTI · Copper — OPEC+ output, Fed risk, tariff |
| **FX** (`entity_type=forex`) | 159 | USD/JPY · USD/CNY · GBP/USD — intervention, "AI boom reshapes FX flows", Fed/ECB |
| **Crypto** (`entity_type=crypto`) | 203 | BTC · ETH — FOMC positioning, ETH gov guidance, regulation |

### 🌍 Macro / cross-asset ripple — *one shock, many markets*
Filter `aspect ∈ {monetary, tariff, geopolitics}` (476 signals) — or find events that touch **3+ asset
classes at once**. Real example in the data: *"Tech stocks surge as Micron earnings ease AI fears, oil
falls"* → **stock + commodity + FX** on a single headline. That's second-order impact, priced.

### 📈 Screener — *who the news is landing on, + / −, on a theme* ([`screener.csv`](data/screener.csv))
Six curated screens (the model's read of who each theme's news helps / hurts) — each well-populated:

| pattern | criteria | top names (news_count) |
|---|---|---|
| 💰 AI-capex gold rush | AI · capital · positive | **MU (141)** · SK Hynix (85) · META · NVDA |
| ⚖️ Big Tech regulatory heat | AI · regulation · negative | MSFT · Alibaba · GOOGL · AAPL |
| ⚔️ Chip competitive crossfire | Semis · competition | **NVDA (43)** · MU · INTC · AVGO |
| 🔺 Memory supercycle pricing | Semis · pricing · positive | MU · TSMC · Samsung · SK Hynix |
| ⚡ Power-demand winners | Energy · demand · positive | **TSLA (31)** · GE Vernova · Constellation (nuclear) |
| 🇹🇼 Taiwan chip complex | Semis · positive · TW | ASE · UMC · the Taiwan supply chain |

### 🔎 Discover — *ask in plain English, no ticker required* ([`discover.csv`](data/discover.csv))
Semantic (vector) search: a natural-language question → the news it matches **by meaning**, with the
impacted entities. 15 curated questions here, and the results resolve to the right asset class on their
own — *"gold as a safe haven"* → commodities, *"dollar strength & intervention"* → FX, *"bitcoin & the
Fed"* → crypto. The killer: *"private AI mega-rounds"* → **Together AI's $800M round and its VCs** (Aramco
Ventures, General Catalyst, March Catalyst) — all entities with **no ticker**. You can't `WHERE ticker=`
your way to that; you have to search by meaning.

### 🕸️ Relationships — *the rivalry/peer graph, learned from news* ([`relationships.csv`](data/relationships.csv))
Not hand-curated — 351 edges *emergent* from 100k+ articles. Competitor edges are weighted by shared
competition-flavoured coverage (`NVDA↔AMD` is the heaviest); peer edges from shared trend membership.

### 🕵️ Beyond tickers — *private companies as first-class entities*
Two files. [`private-roster.csv`](data/private-roster.csv) maps **1,175 private / off-coverage firms**
(OpenAI, Anthropic, SpaceX, ByteDance, Stripe…) to the trends they belong to — the *coverage* no
ticker-keyed feed (Bloomberg / Polygon / Alpha Vantage) can offer at all.
[`private-impact.csv`](data/private-impact.csv) is the subset we scored per-entity impact on — **296
signals** (Ripple Labs · Anthropic · Binance · YMTC · EDF), same `direction · aspect · reason`, ripple
included. Honest caveat: private companies are **mentioned** far more than they're impact-*scored* (the
per-entity impact layer is thinner for non-listed names) — every mention is preserved in the `.jsonl`.

---

## Schema

Every CSV is **story-first & lean** — the human columns first, so a row reads like a sentence:

```
title                                     entity_name   type       direction  aspect   reason
"Natural gas set to overtake petroleum…"  Natural Gas   commodity  pos        demand   "…demand up 3.4%…"
```

Full column-by-column dictionary → **[`SCHEMA.md`](SCHEMA.md)**. The `.jsonl` files carry the same data
plus the nested structure (`entities[] → impact.aspects[]`) and the extra aggregate/meta fields.

**Machine-readable / AI-agent-ready:** [`datapackage.json`](datapackage.json) (Frictionless standard —
types, enums, and join keys, auto-loadable by pandas/frictionless) and [`llms.txt`](llms.txt) (an
LLM-first map for "study this folder"). An agent can learn the whole dataset from those two + the runnable
loader without guessing.

---

## 🚀 From sample to live

1. **See it, no signup** → real queries in the **[Playground](https://marketdx.lab.ai/playground)** (screener / newsfeed / impact / ripple / discover).
2. **Query it live** — same shape, every theme + asset class:
   ```bash
   curl -H "Authorization: Bearer $MARKETDX_KEY" \
     "https://api.marketdx.lab.ai/v1/news?megatrend=10040000&include=entities,impact&impact=indirect&limit=10"
   ```
3. **Pricing** → free tier to start → **[marketdx.lab.ai](https://marketdx.lab.ai)**.

Run [`examples/loader.py`](examples/loader.py) to reproduce every angle above, then hit the live API.

## How it was built

Generated by calling the **public MarketDX API like a customer would** (we dogfood our own product — this
*is* our regression test). The core pulls megatrend themes (AI-Power + Semiconductors) plus asset-exposure
feeds (commodity / FX / crypto) so it's multi-asset; the private companion adds AI + Digital Finance. No
internal database access; everything here is reproducible against the live API with a key.

## Data quality — what's in the flat tables

Impact labels are model-generated, so the CSVs are **curated, not raw**:
- **Every CSV row is a real signal** — an entity with a judged impact (`direction` + `relevance` +
  `reason`, aspect where classifiable). Entities that were merely *mentioned* (no impact) are **not** filler
  rows; they live in the `.jsonl` as nested context so nothing is hidden.
- **Entity resolution is cleaned** — a company's news no longer drags in its preferred shares, money-market
  funds, ETFs or index lines; ADRs collapse to the home listing (e.g. `HSBC.US → HSBA.LSE`).
- **Near-duplicate stories collapsed** — republished/rewritten versions of the same story are merged (cosine-clustered, one representative per group), so the feed is concise.
- **Real publisher, de-aggregated** — `publisher` is the actual outlet (Reuters, Business Wire, The Motley
  Fool …), resolved *through* the host it was republished on (finance.yahoo.com), not the host itself.
- **Source-vs-subject filtered** — when a research house issues a forecast (*"Goldman cuts its Brent
  target"*), it's the **source**, not an affected company, so it isn't scored as an impacted entity.
- **Grain** — one row per `(event × entity × aspect)` per `(theme, impact)` lens; `url` recurs across
  lenses by design (composite key in [`SCHEMA.md`](SCHEMA.md)). `discover.csv` rows are retrieval hits —
  ~45% have empty impact fields (matched but not scored).

## Scope & honesty

A **curated demo SAMPLE, not a production feed**: ~2 weeks (2026-06-25 → 07-06), a handful of themes,
impact-ranked (semiconductors is capped — there's more). It proves labeling quality on a slice; the live
graph is broader, fresher, complete. Labels are model-generated (not infallible), source-diverse but skewed
to what the window surfaced, and the private roster's long tail includes thinly-described small firms. To
go production-grade you'd add source dedup, provenance audit, label-agreement sampling and leakage checks —
this sample is for evaluation (RAG, screening, feature prototyping), not backtesting.

## License

[CC BY 4.0](LICENSE) — free to use, adapt, redistribute **with attribution** to *MarketDX — Financial
Impact Graph* ([marketdx.lab.ai](https://marketdx.lab.ai)).
