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

**An API key is required.** Create a free one at **https://marketdx.lab.ai** (sign in → *API keys*), then
pass it to the client (keep it out of source control — read it from an env var / secret in real apps):

```python
from marketdx import MarketDX

mdx = MarketDX(api_key="avn_live_…")                     # your key from https://marketdx.lab.ai
for s in mdx.news(megatrend="ai-power", impact="indirect"):
    print(s.title, [(e.name, e.impact.net_direction) for e in s.entities])
```

That's the whole graph: every news event, every affected entity, labeled with **direction**,
**relevance**, the causal **aspect** (the *why*), and whether it's the **epicenter** or a **ripple** —
across five asset classes, **including private companies** ticker feeds can't see.

> **No key yet?** Explore everything with zero signup in the [playground](https://marketdx.lab.ai/playground),
> then grab a free key at **[https://marketdx.lab.ai](https://marketdx.lab.ai)**. Every request is
> authenticated with your key (`Authorization: Bearer <key>`) and metered in credits.

## Why the SDK (not just `requests`)

- **Typed graph** — `signal.entities[0].impact.aspects[0].direction` with autocomplete, not raw dicts.
- **Auto-pagination** — `for s in mdx.news(...)` pages for you. `limit=` caps how many you get
  (default 50; `limit=None` walks the whole match set); `page.total` is the full count.
- **Names, not ids** — `megatrend="ai-power"` or `"AI Power & Cooling"` or `10040000` all work.
- **`.to_df()`** — the whole result as a pandas DataFrame, one row per *(event × entity × aspect)*.
- **Typed errors** — `AuthError`, `QuotaError`, `RateLimitError`, `BadRequestError`, `NotFoundError`.

## The graph, a few ways

```python
# 1. Ripple: a themed event that also touches NON-thematic entities (our differentiator)
for s in mdx.news(megatrend="semiconductors", impact="indirect", limit=50):
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

# 5. Semantic search — match news by MEANING, not keywords (each hit is explainable)
for s in mdx.news_search("chip export controls to China", limit=5):
    print(round(s.similarity, 2), s.scored, s.title)   # how-strongly-matched + does-it-move-an-entity

# 6. Brief in ONE call — pulse timeseries + top stories + winners/losers + heatmap + assets.
#    Scope by theme, market, news-type, impact-channel, or any mix (>=1 scope).
brief = mdx.theme("ai-power").summary(window="qtd")            # theme brief (== brief(megatrend="ai-power"))
brief = mdx.brief(news_type="commodity_supply", country="JP", window="90d")  # "commodity news, in Japan"
print(brief["pulse"]["story_count"], brief["pulse"]["net_direction"])
print([w["ticker"] for w in brief["winners"]], "vs", [l["ticker"] for l in brief["losers"]])
print([a["name"] for a in brief["top_assets"]])          # commodity / forex / crypto the theme moves
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

**What to expect in `entities` (not bugs):**
- **Mostly mention-only.** An article's `entities` mix two kinds: *mentioned* (`e.direct is True`,
  `e.impact is None`) — every ticker the article names — and *scored* (`e.impact is not None`) — the ones
  the model judged materially moved. Mentions usually **outnumber** scored (a story names many tickers but
  moves a few). Want just the movers? `only_scored=True` or filter `e.impact`.
- **`entities` can be empty.** `include=entities` attaches entities *if the article maps to any*; a macro /
  policy / commodity story that names no covered company (e.g. "China bans helium exports") legitimately
  returns `entities == []`. It means *no entity resolved*, not a dropped/failed enrich.

**Provenance.** A scored `impact` ships its evidence, not just a label: `aspect`+`direction`+`relevance`
(the judgment), `reason` (why), `Entity.direct` (named vs affected-only), and `impact.label_version` — the
labeling-scheme version (currently `"1.0"`), a per-label stamp that bumps when the model/prompt/taxonomy
changes so you can detect and re-evaluate shifts. Audit or gate on it: `e.impact.label_version`.

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

Each collapsed signal also carries its cluster metadata — group a dashboard by `story_id` and see reach +
lifespan without double-counting:

```python
for s in mdx.news(megatrend="ai-power", limit=5):
    print(s.story_id, s.dup_count, s.first_seen, s.latest_seen)   # cluster id · outlets · broke · last echo
```

## The brief — the whole picture in one call

`mdx.theme(id).summary(...)` (a theme = a megatrend node; also `mdx.megatrends(id).summary(...)`) returns
a pre-composed **analyst brief** so you don't stitch 5+ requests together. It's a fixed composite `dict`,
not a paginated list:

```python
brief = mdx.theme("ai-power").summary(window="30d")     # 7d/30d/90d/180d/1y or mtd/qtd/ytd (or from_/to)
brief["pulse"]          # story_count, net_direction, pos/neg share + a `series` (volume+sentiment/bucket)
brief["top_stories"]    # epicenter, deduped; market-wraps & no-member-named stories deprioritized
brief["ripple"]         # indirect (ripple-in) stories, each with `via`
brief["winners"], brief["losers"]   # member stocks by net direction
brief["aspect_heatmap"] # which channels the theme is playing out through
brief["top_entities"]   # operating companies most in the news
brief["top_assets"]     # commodity / forex / crypto the theme moves (split out from companies)
```

Every count is **story-deduped** (20 outlets on one story = 1). The `pulse.series` is the momentum signal —
there's no single momentum scalar (the latest bucket is the current, partial period). Cost: 15 credits.

**Any scope, not just a theme.** `mdx.brief(...)` composes the *same* object over any AND-combination of
**megatrend / news_type / country / aspect** (≥1 required) — a theme, a market, a news category, an
impact channel, or a mix:

```python
mdx.brief(country="JP")                                   # how is Japan doing right now?
mdx.brief(news_type="commodity_supply", country="JP")     # commodity news, in Japan
mdx.brief(aspect="tariff", window="90d")                  # everything moving via tariffs
mdx.brief(megatrend="semiconductors", country="US")       # a theme, narrowed to one market
```

`applied_scope` echoes what you filtered. `node` + `ripple` appear **only when a single `megatrend`**
anchors the brief (without a theme there's no ripple). Under a megatrend scope `winners`/`losers` are the
theme's members; otherwise they're the top +/- companies in the scope. `theme(id).summary(...)` ==
`brief(megatrend=id, ...)`. `megatrend`/`news_type`/`country`/`aspect` each take one value or a list.

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
