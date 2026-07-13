# Schema / data dictionary

Every CSV is **story-first** (the human columns come first) and **lean** (one job per column). The
`.jsonl` files carry the same data **plus** the full nested structure and extra fields — use them when you
want everything.

## `impact-signals.csv` · `private-impact.csv` — one row per **event × entity × aspect**

| column | meaning |
|---|---|
| `published_at` | when the article was published (UTC, ISO-8601) |
| `title` | the news headline |
| `brief_text` | a neutral 1-paragraph summary of the article (right after the title, so the row is self-contained without opening the URL) |
| `entity_name` | the affected company / asset (e.g. *NVIDIA Corporation*, *Gold Futures*, *OpenAI*) |
| `entity_ticker` | its symbol — `NVDA.US`, `BTC`, `NATGAS`, `USDJPY.FOREX`; **empty for private companies** (they have no ticker) |
| `entity_type` | `stock` · `commodity` · `forex` · `crypto` · `private` · `public_off_coverage` |
| `direction` | how this news moves the entity: `pos` (helps) · `neg` (hurts) · `ambiguous` |
| `aspect` | **the *why*** — the single channel the news acts through: `demand` · `supply` · `pricing` · `capital` · `competition` · `technology` · `regulation` · `tariff` · `geopolitics` · `monetary` (empty = judged directional but channel unclear) |
| `reason` | one-line explanation of the impact (the model's rationale) |
| `relevance` | 0–1 — how central this entity is to the article (1 = the article is about it) |
| `impact` | `direct` = the entity is the article's **epicenter**; `indirect` = it's a **ripple** (affected but not the subject); **empty** = the row came from an asset-class feed (commodity/forex/crypto) that has no epicenter/ripple framing |
| `impact_score` | 1–5 — how big the news *event* is, market-wide |
| `theme` | which pull the row came from (`ai-power`, `semiconductors`, `commodities`, `forex`, `crypto`, `ai`, `digital-finance`) |
| `node_name` | the megatrend node the article's epicenter maps to |
| `entity_country` | ISO-2 country of the entity |
| `publisher` | the real **de-aggregated** outlet (Reuters, Business Wire, The Motley Fool …) — *not* the host it was republished on (finance.yahoo.com) |
| `url` | the article link |

> **Grain / primary key** = one row per `(event × entity × aspect)` **per lens**, where a lens =
> `(theme, impact)`. The same article legitimately recurs across lenses (epicenter of one trend, ripple of
> another; re-surfaced by an asset feed) — so `url` repeats. The composite key is
> **`(url, entity_ticker, entity_name, aspect, theme, impact)`**. To collapse to one lens, filter to a
> single `theme`. The `.jsonl` nests aspects under one entity with an aggregate `net_direction`.

## `screener.csv` — curated "who's winning / losing on X"

`pattern_label` (the screen in words) · `rank` · `symbol` · `name` · `country` · `net_direction` ·
`news_count` (how many articles) · `aspects` · `top_reason` · `pos`/`neg` (article counts) ·
`top_relevance` · `market_cap_usd` · `pattern` (machine key).

## `discover.csv` — semantic search (ask in plain English)

`question` (the plain-English query) · `search_query` (the exact text embedded) · `rank` · `similarity`
(cosine, 1 = identical) · `title` · `entity_name` · `entity_ticker` · `entity_type` · `direction` ·
`aspect` · `reason` · `published_at` · `url` · `brief_text` (article summary).

> ⚠️ discover rows are **retrieval hits** — the semantic match is always present, but `direction` /
> `aspect` / `reason` are **empty on ~45%** of rows (the matched article mentions the entity but the
> impact layer didn't score it). Downstream code should treat impact fields as optional here.

## `relationships.csv` — news-derived company graph

`source` (ticker) · `relation` (`competitor` | `peer`) · `target_symbol` · `target_name` ·
`target_country` · `weight` (competitor = shared competition-flavoured articles; peer = shared trend nodes).

## `private-roster.csv` — the private / off-coverage universe

`company` · `type` (`private` | `public_off_coverage`) · `country` · `theme` · `megatrend_node` ·
`exposure` (`core` | `secondary`).

## `megatrends.csv` — the trend taxonomy (join on `node_name` / `node_id`)

`node_id` · `name` · `tier` (1–3) · `parent_id` · `family_id` · `layer` (value-chain layer).
