# marketdx-mcp — MCP server

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives your AI agent the
[MarketDX](https://marketdx.lab.ai) financial **impact graph** as tools — ask *"which private AI
companies did this week's news move, and why?"* and the agent queries the graph directly (stocks,
commodities, FX, crypto, **and private companies**).

> Status: **early / in assembly** — simple tools + resources wired to the `marketdx` SDK; composite
> tools (`resolve_themes`, `suggest_cta`) are being finished. Design + rationale live in the Ava repo
> `docs/product/mcp-server-design.md`. Explore the shape now via the
> [sample dataset](../datasets/) and the [live playground](https://marketdx.lab.ai/playground).

## Install & run
```bash
pip install marketdx-mcp            # or: uvx marketdx-mcp
export MARKETDX_API_KEY=avn_live_…    # https://marketdx.lab.ai  (metered — your key, your credits)
export DEEPSEEK_API_KEY=…             # only for the composite tools (server-side LLM)
marketdx-mcp                           # stdio server
```
Claude Desktop / Cursor: point your MCP config at the `marketdx-mcp` command with those env vars.

## Tools
**Simple** (thin SDK wrappers — your client's LLM orchestrates):
`theme_summary` · `search_news` · `stock_impact` · `theme_players` · `private_movers` ·
`relationships` · `list_themes`.

**Composite** (whole multi-step pipeline runs server-side, one call):
`resolve_themes(terms)` — map trend-language ("HBM","foundry","cancer drug") to the right taxonomy
node(s). · `suggest_cta(theme)` — data-backed "explore further" hooks into the graph's moat.

## Resources
`marketdx://policy` — the gate/framing policy (skill.md) the client LLM should follow (honest scope,
5 response stances, no fudge). · `marketdx://capabilities` — live coverage/enums so the client scopes
correctly (expand "Asia" → the covered set; never request uncovered markets as if we had them).

## Architecture (why some tools are server-side)
The client's LLM (Claude / GPT / Gemini — the user's choice, we don't control it) handles single-pass
reasoning (which tool, final wording) guided by `marketdx://policy`. Correctness (coverage / dedup /
resolution) is deterministic in the API. Multi-step pipelines that would otherwise be many client↔server
roundtrips (`resolve_themes`, `suggest_cta`) are encapsulated as **one** composite tool running our own
cheap LLM (deepseek-v4-flash). Full split in the design doc.

⭐ **Star / watch** to hear when it ships.
