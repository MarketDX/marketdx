<h1 align="center">marketdx</h1>

<p align="center">
  <b>The financial impact graph, in Python.</b><br>
  News → who it <i>touches</i> and <i>why</i> — the causal channel, the story's <i>lean</i>, and the
  <i>ripple</i> — across stocks, commodities, FX, crypto, <b>and private companies</b>.<br>
  A research, screening &amp; feature layer — direction is the news's content lean, not a price forecast.
</p>

<p align="center">
  <a href="https://marketdx.lab.ai/playground"><b>▶ Live playground</b></a> ·
  <a href="https://marketdx.lab.ai">Docs & pricing</a> ·
  <a href="https://github.com/MarketDX/marketdx/tree/main/datasets">Sample dataset</a>
</p>

---

```bash
pip install marketdx          # add [pandas] for .to_df():  pip install "marketdx[pandas]"
```

```python
from marketdx import MarketDX

mdx = MarketDX(api_key="avn_live_…")                     # get a key at marketdx.lab.ai
for s in mdx.news(megatrend="ai-power", impact="indirect"):
    print(s.title, [(e.name, e.impact.net_direction) for e in s.entities])
```

That's the whole graph: every news event, every affected entity, labeled with **direction**,
**relevance**, the causal **aspect** (the *why*), and whether it's the **epicenter** or a **ripple** —
across five asset classes, **including private companies** ticker feeds can't see.

> **No key yet?** Explore everything with zero signup in the [playground](https://marketdx.lab.ai/playground),
> then grab a free key at [marketdx.lab.ai](https://marketdx.lab.ai).

## Why the SDK (not just `requests`)

- **Typed graph** — `signal.entities[0].impact.aspects[0].direction` with autocomplete, not raw dicts.
- **Auto-pagination** — `for s in mdx.news(...)` walks every page for you. Nothing to manage.
- **Names, not ids** — `megatrend="ai-power"` or `"AI Power & Cooling"` or `10040000` all work.
- **`.to_df()`** — the whole result as a pandas DataFrame, one row per *(event × entity × aspect)*.
- **Typed errors** — `AuthError`, `QuotaError`, `RateLimitError`, `BadRequestError`, `NotFoundError`.

## The graph, a few ways

```python
# 1. Ripple: a themed event that also touches NON-thematic entities (our differentiator)
for s in mdx.news(megatrend="semiconductors", impact="indirect", max_items=50):
    ...

# 2. Beyond tickers: private companies in a trend (OpenAI, Anthropic, Ampere, ChangXin…)
for c in mdx.megatrends("semiconductors").off_coverage():
    print(c.name, c.type, "→", c.megatrend["node_name"])

# 2b. …or just the NEWS that moves private companies — one server-side filter on the feed
for s in mdx.news(entity_type="private", only_scored=True):   # also: crypto / commodity / forex / stock
    print(s.title, [e.name for e in s.entities if e.type == "private"])

# 3. Per-stock impact timeline + its news-derived rivals
tl    = mdx.stock("NVDA.US").news(aspect="competition")
peers = mdx.stock("NVDA.US").competitors()

# 4. News-driven screen — where the news leans positive on a theme (the model's read, for research)
positive_lean = mdx.stocks(megatrend="ai-power", direction="pos", country="US", order_by="news_count")

# 5. Semantic search — match news by MEANING, not keywords
hits = mdx.news_search("chip export controls to China")
```

## Straight to pandas

`.to_df()` returns the **same columns as the [sample dataset](https://github.com/MarketDX/marketdx/tree/main/datasets)** (`impact-signals.csv`) — so
anything you prototyped on the free CSV runs unchanged on the live graph:

```python
df = mdx.news(megatrend="ai-power", impact="indirect").to_df()
# published_at · title · brief_text · entity_name · entity_ticker · entity_type · direction ·
# aspect · reason · relevance · impact · impact_score · node_name · entity_country · publisher · url

df.groupby(["entity_type", "direction"]).size()      # who the news lands on, +/− by asset class (the model's read)
df[df.aspect == "tariff"].entity_name.value_counts()  # who the tariff channel touches
```

## Filtering — read this before you filter

**Feed filters are EVENT-level, not row-level.** `news(direction=…, aspect=…, news_type=…, country=…)`
selects **articles** that contain *at least one* matching impact and returns the **whole** article with
**all** its entities and aspects. So `direction="pos"` can return an article that also moves something `neg`,
and `aspect="supply"` can return one whose other entities are hit via `monetary`. For exact per-row
filtering, **post-filter the entities**:

```python
for s in mdx.news(news_type="commodity_supply", direction="pos"):
    for e in s.entities:
        for a in (e.impact.aspects if e.impact else []):
            if e.type == "commodity" and a.direction == "pos" and a.aspect == "supply":
                ...   # exact row you asked for
```

**Two different "direct" axes** (don't conflate):
- `Signal.impact_type` (`direct`|`indirect`) = the **article's** relation to the **queried node** —
  epicenter (`direct`) vs ripple (`indirect`). Set by `news(megatrend=…, impact="indirect")`.
- `Entity.direct` (`True`|`False`) = whether that **entity** is **factually mentioned** in the article
  (`True`) vs **impact-only / not named** (`False`).

**Narrow the feed by entity — server-side.** `news()` (and `news_search()`) filter by
`entity_type` / `only_scored` / `min_relevance` in the API, so `page.total` stays the exact filtered
count (no wasted paging). These keep the *whole* article — for an exact per-row cut, still post-filter
the entities as above.

```python
mdx.news(entity_type="commodity")                      # feed → only stories that move a commodity
mdx.news(entity_type="private")                        # only stories moving a private co (OpenAI, SpaceX)
mdx.news(only_scored=True)                              # drop mention-only articles (keep judged impact)
mdx.news(min_relevance=0.8)                             # only a strongly-relevant scored entity
mdx.news(megatrend="ai-power", entity_type="crypto")   # entity filters compose with megatrend scope
mdx.news_search("oil supply shock", entity_type="commodity")  # search supports entity_type too
mdx.news_by_tickers("NVDA.US")                          # a covered STOCK's news (direct + indirect)
mdx.megatrends("ai-power").off_coverage()              # private / off-coverage roster
```

> Entity filters do **not** apply to `impact="indirect"` (the ripple feed) — the API returns 400 if you
> combine them. On `news_by_tickers`, the ticker set already scopes the entities.

**Only entities with a *scored* impact** (many are mentioned-only) — `only_scored=True` narrows to such
articles server-side; then read the scored entities off each signal:

```python
scored = [e for s in mdx.news(megatrend="ai-power", only_scored=True)
          for e in s.entities if e.impact and e.impact.aspects]
```

**`stock(t).news()` is a stock-centric timeline** — a `StockNews` (the stock's own `impact` /`trend`/
`relevance`), **not** an entity graph (no `entities[]`). For the full graph of an article, use `news()`.

**Story-collapse (on by default).** The same story is often republished / rewritten across outlets.
`news()`, `news_search()` and `news_by_tickers()` merge those near-duplicates into a single signal by
default (cosine-similarity grouping, server-side) so a feed reads one-story-one-row. Pass
`collapse=False` when you want the raw, un-deduped stream — e.g. to measure coverage volume:

```python
merged = mdx.news(megatrend="ai-power").to_list()                 # deduped (default)
raw    = mdx.news(megatrend="ai-power", collapse=False).to_list() # every republication
```

## Metering & errors

Every call carries `X-Credits-Charged` / `X-RateLimit-*`; check your balance any time (free, unmetered):

```python
mdx.account()   # {'plan': …, 'credits': {'balance', 'daily_quota', 'resets_at', 'unlimited'}, 'rate_limit': …}
```

```python
from marketdx.errors import QuotaError, RateLimitError

try:
    signals = mdx.news(megatrend="ai-power").to_list()
except RateLimitError as e:
    time.sleep(e.retry_after or 1)
except QuotaError:
    ...   # daily quota spent — resets 00:00 UTC
```

Enum values (`aspect`, `direction`, `entity_type`, …) are **type hints** for your editor — the API is the
source of truth, so new values work without upgrading the SDK. The live list: `mdx.enums()`.

## Reference

`news` · `news_search` · `news_types` · `megatrends` (`.stocks` / `.off_coverage`) · `gics` (`.stocks`) ·
`stocks` (search + screener) · `stock` (`.news` / `.competitors` / `.peers`) · `enums` · `account`.
Full API docs: [marketdx.lab.ai](https://marketdx.lab.ai).

## License

MIT. Built by [MarketDX](https://marketdx.lab.ai) — *democratizing financial data.*
