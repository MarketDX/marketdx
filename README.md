<h1 align="center">MarketDX</h1>

<p align="center">
  <b>The financial impact graph.</b><br>
  A structured, <i>explained</i> map of what financial news is about and who it touches — the <i>why</i>
  (causal channel), the story's lean, and the <i>ripple</i> — across stocks, commodities, FX, crypto,
  <b>and private companies</b>. A research &amp; context layer, not a trading signal.
</p>

<p align="center">
  <a href="https://marketdx.lab.ai/playground"><b>▶ Live playground</b></a> ·
  <a href="https://marketdx.lab.ai"><b>Docs & pricing</b></a> ·
  <a href="datasets/"><b>Sample dataset ↓</b></a>
</p>

---

Most feeds give you a headline and a sentiment score. MarketDX labels **every affected entity on every
event, across many dimensions** — 10 causal channels (demand · supply · regulation · tariff · competition
· pricing · capital · technology · geopolitics · monetary), per-entity direction & relevance, epicenter
**and** ripple, across **five asset classes including non-listed companies** ticker feeds structurally
can't see. It's a layer for **understanding and structuring** the news flow — a research, screening and
feature input — **not** a predictive price signal (news is largely priced in by the time it's public).

## What a signal looks like

One headline → every entity it touches, each labeled with the **lean** (+/−) and the **why**. Take
*"AI-driven memory shortage forces Apple, Samsung, Microsoft… to raise device prices"*:

| entity | | lean | why (aspect) |
|--------|---|:---:|---|
| Apple | stock | **−** | pricing — chip costs squeeze margins |
| Microsoft | stock | **−** | pricing |
| Nintendo | stock | **−** | pricing |
| Samsung | stock | **+** | demand — it *makes* the memory |

Same event, opposite outcomes — because the **why** is labeled, not just a sentiment score. And it spans
**five asset classes including private companies** (OpenAI, Anthropic, …) that ticker feeds structurally
can't see, plus the **ripple** into non-obvious names.
<sub>↑ a real row from the free [sample dataset](datasets/) — no signup needed.</sub>

## What's here

| | | |
|---|---|---|
| 📊 [**`datasets/`**](datasets/) | **A free sample** of the impact graph — 4,000+ labeled signals, every angle the [playground](https://marketdx.lab.ai/playground) answers. Start here. | ✅ available |
| 🐍 [**`python/`**](python/) | The official Python SDK — the graph in three lines. **`pip install marketdx`** | ✅ available |
| 🔌 [**`mcp/`**](mcp/) | MCP server — give your AI agent the financial impact graph. | 🔜 soon |

New here? → **[browse the sample dataset](datasets/)** (no signup), then
**[try it live](https://marketdx.lab.ai/playground)**.

## Quickstart

**See the data** — no signup: [browse the sample dataset](datasets/) or the [live playground](https://marketdx.lab.ai/playground).

**Use it in code** — the official Python SDK:

```bash
pip install marketdx
```

```python
from marketdx import MarketDX

mdx = MarketDX(api_key="…")                 # free key at marketdx.lab.ai
for s in mdx.news(megatrend="ai-power", impact="indirect"):
    print(s.title, [(e.name, e.impact.net_direction) for e in s.entities])
```

Full SDK docs → [`python/`](python/).

**Free to explore** — the [sample dataset](datasets/) and [playground](https://marketdx.lab.ai/playground)
need no signup, and the API has a free tier. Paid plans unlock full & live coverage — see [pricing](https://marketdx.lab.ai).

## License

Sample data under [CC BY 4.0](datasets/LICENSE); code (SDK, MCP) under MIT. See each directory.
Built by **[MarketDX](https://marketdx.lab.ai)** — *democratizing financial data.*
