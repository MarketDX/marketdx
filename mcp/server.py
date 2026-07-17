"""MarketDX MCP server — gives an AI agent the MarketDX financial-impact graph as tools.

Architecture (see docs/product/mcp-server-design.md in the Ava repo):
  • SIMPLE tools  → thin wrappers over the marketdx Python SDK (which calls the metered /v1 API).
                    The client's own LLM orchestrates these; correctness lives in the API/SDK.
  • COMPOSITE tools (resolve_themes, suggest_cta) → multi-step pipelines that would be N client↔server
                    roundtrips if offloaded, so they run WHOLLY server-side on our own cheap LLM
                    (deepseek-v4-flash, reasoning off) and return a finished result in ONE call.
  • RESOURCES     → the gate policy (skill.md) + a live capabilities/coverage map.

Run:  MARKETDX_API_KEY=avn_live_… DEEPSEEK_API_KEY=… uvx marketdx-mcp     (or `python server.py`)
Deps: mcp (FastMCP), marketdx, openai (deepseek is OpenAI-compatible).
"""
from __future__ import annotations
import os, json, pathlib, contextvars
from dataclasses import asdict, is_dataclass
from typing import Any, Optional, List

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from marketdx import MarketDX

# DNS-rebinding protection defaults to a localhost allow-list (it guards a *local* server from
# browser-driven Host spoofing). We're a hosted API behind Cloud Run TLS with our own per-request
# Bearer auth, and the Host varies (run.app + mcp.marketdx.lab.ai) — so disable the Host check here.
# Server instructions — the client LLM reads this at connect time. Its main job: stop the client from
# web-searching topics MarketDX actually covers (esp. COMMODITIES/metals, which agents forget we have).
_INSTRUCTIONS = (
    "MarketDX is a financial news→impact graph: it maps news to the assets and megatrends it actually "
    "moves — direction (+/−), the reason WHY, and the ripple to connected players — across STOCKS, "
    "FOREX, CRYPTO, COMMODITIES (metals like copper & gold, energy like oil & gas, and agris), and "
    "PRIVATE / off-coverage companies. For ANY question about news, market impact, or what moved an "
    "asset or theme — INCLUDING commodities and metals (copper, gold, oil, …) — use THESE tools, not a "
    "web search: MarketDX returns scored per-article impact + the causal 'why' + the ripple that a web "
    "search cannot. Commodities use a `SYMBOL.COMM` ticker (COPPER.COMM, GOLD.COMM) with stock_impact, "
    "or just search_news('copper'). News tools accept a time range (`from_`/`to` ISO or `window` like "
    "'90d'/'qtd'/'1y'); to compare periods, call the tool once per period and compare. "
    "⚠️ NEWS coverage starts 2026-01-01 — there is NO news before 2026; for an older period say so "
    "plainly, never fabricate or present an empty result as 'nothing happened'. PRICE / volatility "
    "history, by contrast, goes back decades — so 'why was gold volatile in 2023' is answerable from "
    "price even though there's no 2023 news. Resolve a trend term via resolve_themes; follow "
    "marketdx://policy for voice, scope, and the response stance."
)
mcp = FastMCP("marketdx", instructions=_INSTRUCTIONS, website_url="https://marketdx.lab.ai",
              transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
_HERE = pathlib.Path(__file__).parent
# Served at /favicon.ico so clients (Claude's connector card) show the MarketDX mark for this host —
# without it, a favicon resolver strips the subdomain and grabs the apex lab.ai icon.
_FAVICON = (_HERE / "favicon.ico").read_bytes() if (_HERE / "favicon.ico").exists() else b""
# Every tool here is READ-ONLY (queries the graph / runs our own LLM — never writes user data). The
# readOnlyHint lets a client auto-run without a confirm prompt, and it's a Connector-Directory gate.
# Convention: give EVERY new tool a `title=` + `annotations=_RO` (or a destructive hint if it ever writes).
_RO = ToolAnnotations(readOnlyHint=True)

def _lim(n: Optional[int], default: int = 20, ceiling: int = 50) -> int:
    """Bound a list tool's page size so the result stays context-friendly. Heavily-covered assets
    (GOLD, oil, mega-caps) have hundreds of impact articles — dumping them all overflows the client's
    context. `None` → default; the LLM may raise it up to `ceiling`, then should page/narrow instead."""
    if n is None:
        return default
    return max(1, min(int(n), ceiling))

# News exists only from here (backfill floor; still walking backward). There is NO news before this.
# Price/EOD history, by contrast, goes back decades — so historical volatility is answerable, news isn't.
_NEWS_COVERAGE_START = "2026-01-01"

def _win(window: Optional[str]) -> Optional[str]:
    """Resolve a relative/calendar `window` ('90d','1y','mtd','qtd','ytd') to a `from_` ISO date (to=now)
    — an LLM-friendlier alternative to computing dates by hand. Unknown/None → None (no lower bound).
    Explicit `from_`/`to` always take precedence over this."""
    if not window:
        return None
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    w = window.strip().lower()
    try:
        if w.endswith("d") and w[:-1].isdigit():
            return (now - _dt.timedelta(days=int(w[:-1]))).date().isoformat()
        if w.endswith("y") and w[:-1].isdigit():
            return (now - _dt.timedelta(days=365 * int(w[:-1]))).date().isoformat()
        if w == "mtd":
            return now.replace(day=1).date().isoformat()
        if w == "ytd":
            return now.replace(month=1, day=1).date().isoformat()
        if w == "qtd":
            return now.replace(month=3 * ((now.month - 1) // 3) + 1, day=1).date().isoformat()
    except Exception:
        return None
    return None

def _coverage_note(from_: Optional[str]) -> Optional[str]:
    """If a requested range starts before news coverage, a caller-facing warning so the LLM never reads
    an empty/short result as 'no news happened' (it's 'no coverage')."""
    if from_ and str(from_)[:10] < _NEWS_COVERAGE_START:
        return (f"Requested range starts before MarketDX news coverage (news begins {_NEWS_COVERAGE_START}; "
                "there is NO news before 2026). Results are limited to the covered window — do NOT present an "
                "empty/short result as 'nothing happened'. Price/volatility history DOES go back decades.")
    return None

def _ser(items: list) -> list:
    """SDK returns typed @dataclass models; MCP needs JSON — convert to plain dicts."""
    return [asdict(x) if is_dataclass(x) else x for x in items]

# ── per-request identity (hosted) + client cache ─────────────────────────────
# HTTP transport: each request carries its OWN caller's key (Authorization header → _req_key,
# set by the ASGI auth middleware in main()), so users are metered on THEIR account — never a
# shared server key. stdio/local: no header → fall back to MARKETDX_API_KEY env.
_req_key: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("marketdx_req_key", default=None)
_clients: dict[str, MarketDX] = {}   # key → client (reuse the httpx pool across a user's calls)

def mdx() -> MarketDX:
    key = _req_key.get() or os.environ.get("MARKETDX_API_KEY")
    if not key:
        raise RuntimeError("no MarketDX API key — send 'Authorization: Bearer <key>' (hosted) "
                           "or set MARKETDX_API_KEY (local). Get one at https://marketdx.lab.ai")
    cli = _clients.get(key)
    if cli is None:
        if len(_clients) > 512:   # coarse bound — MVP; swap for an LRU if it ever matters
            _clients.clear()
        cli = _clients[key] = MarketDX(api_key=key)
    return cli

def _deepseek(system: str, user: str, temperature: float) -> dict:
    """Our server-side LLM for the composite tools. deepseek reasoning OFF (fast/cheap)."""
    from openai import OpenAI
    cli = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com/v1")
    r = cli.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature, response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
    )
    return json.loads(r.choices[0].message.content)

# ── theme resolution (server-side): gazetteer FIRST, then deepseek 3-tier match + deterministic solve.
#    Ported from the validated prototype /tmp/mcp-gate/resolve_themes.js + mstep2.js. ────────────────
_ALIAS = {  # curated: colloquial/abbrev term → EXACT node name. Grows from LLM-fallback logs.
    # families (tier-1)
    "ai": "Artificial Intelligence", "a.i.": "Artificial Intelligence", "เอไอ": "Artificial Intelligence",
    "semicon": "Semiconductors", "semiconductor": "Semiconductors", "semiconductors": "Semiconductors",
    "ชิป": "Semiconductors", "หุ้นชิป": "Semiconductors", "ev": "Electrification & Mobility",
    # semiconductors sub-nodes
    "cowos": "Advanced Packaging & Test (OSAT)", "advanced packaging": "Advanced Packaging & Test (OSAT)",
    "osat": "Advanced Packaging & Test (OSAT)", "eda": "EDA & Semiconductor IP",
    "wfe": "Wafer-Fab Equipment & Lithography", "wafer fab equipment": "Wafer-Fab Equipment & Lithography",
    "semiconductor equipment": "Wafer-Fab Equipment & Lithography", "chip equipment": "Wafer-Fab Equipment & Lithography",
    "lithography": "Lithography Systems", "euv": "Lithography Systems", "duv": "Lithography Systems",
    "dram": "Memory — DRAM, NAND & HBM", "nand": "Memory — DRAM, NAND & HBM",
    "asic": "Custom Silicon / ASIC", "custom silicon": "Custom Silicon / ASIC",
    "mlcc": "Passive Components (MLCC, Capacitors, Inductors)", "pcb": "Printed Circuit Boards (PCB & HDI)",
    "analog": "Analog, Power & Discrete", "logic chip": "Logic, Compute & Connectivity Processors",
    # AI sub-nodes
    "llm": "Foundation Models & Research Labs", "foundation model": "Foundation Models & Research Labs",
    "foundation models": "Foundation Models & Research Labs", "frontier model": "Foundation Models & Research Labs",
    "agentic ai": "Agentic AI & Autonomous Workflows", "ai agent": "Agentic AI & Autonomous Workflows",
    "copilot": "AI Applications & Copilots", "gpu": "GPU & Merchant Accelerators",
    "neocloud": "AI Compute Cloud & Neoclouds", "mlops": "AI Tooling, Data & MLOps",
    "inference chip": "Inference-Optimized Silicon", "optical interconnect": "Optical Interconnect & DCI",
    "cpo": "Optical Interconnect & DCI",
    # digital finance sub-nodes
    "stablecoin": "Stablecoin Issuers & Distribution", "stablecoins": "Stablecoin Issuers & Distribution",
    "neobank": "Digital Banking & Neobanks", "digital bank": "Digital Banking & Neobanks",
    "payments": "Payments Modernization & Rails", "payment rails": "Payments Modernization & Rails",
    "rwa": "Real-World Asset Tokenization", "tokenization": "Real-World Asset Tokenization",
    "crypto exchange": "Crypto Exchanges, Custody & Digital-Asset Infrastructure",
    "bitcoin treasury": "Bitcoin / Crypto Treasury & Store-of-Value Proxies",
    "robo advisor": "Digital Wealth & Robo-Advisory",
    # biotech sub-nodes
    "cancer drug": "Oncology Therapeutics", "cancer": "Oncology Therapeutics", "มะเร็ง": "Oncology Therapeutics",
    "oncology": "Oncology Therapeutics", "car-t": "Cell Therapy (CAR-T & beyond)", "cart": "Cell Therapy (CAR-T & beyond)",
    "cell therapy": "Cell Therapy (CAR-T & beyond)", "adc": "Antibody-Drug Conjugates (ADC)",
    "mrna": "mRNA Platforms", "rnai": "RNAi / Antisense Oligonucleotides", "sirna": "RNAi / Antisense Oligonucleotides",
    "glp-1": "Metabolic, Diabetes & Obesity", "glp1": "Metabolic, Diabetes & Obesity",
    "obesity drug": "Metabolic, Diabetes & Obesity", "gene editing": "Gene & Cell Editing", "crispr": "Gene & Cell Editing",
    "cgm": "Diabetes Devices (CGM & Insulin Delivery)", "cdmo": "CDMO / Contract Manufacturing",
    "immuno-oncology": "Immuno-Oncology / Checkpoint", "vaccine": "Vaccines (Recombinant & Traditional)",
    "rare disease": "Rare Disease", "ai drug discovery": "AI Drug Discovery",
}
_TAX: Optional[dict] = None
def _taxonomy() -> dict:
    global _TAX
    if _TAX is None:
        nodes = _ser(mdx().megatrends().to_list())
        children: dict = {}
        for n in nodes:
            children.setdefault(n.get("parent_id"), []).append(n)
        _TAX = {"nodes": nodes, "by_id": {n["id"]: n for n in nodes},
                "by_name": {n["name"]: n for n in nodes}, "children": children}
    return _TAX

def _children(nid: int) -> list:
    return _taxonomy()["children"].get(nid, [])

def _gazetteer(term: str) -> list:
    tax = _taxonomy(); t = str(term).strip(); lc = t.lower()
    if t.isdigit() and int(t) in tax["by_id"]:       # already a node id → pass through, no LLM
        return [int(t)]
    if t in tax["by_name"]:                          # exact node name → that node
        return [tax["by_name"][t]["id"]]
    if lc in _ALIAS:
        n = tax["by_name"].get(_ALIAS[lc]); return [n["id"]] if n else []
    hits = [n["id"] for n in tax["nodes"] if lc in n["name"].lower()]  # name contains phrase (multi-node ok)
    return hits if 1 <= len(hits) <= 4 else []

def _match(term: str, cands: list) -> list:
    """deepseek: which candidate nodes does the concept belong under? (binary classification)."""
    if not cands:
        return []
    lines = "\n".join(f"{n['id']} | {n['name']}" for n in cands)
    out = _deepseek(
        "Which taxonomy nodes does the CONCEPT belong under? Match a node if the concept clearly falls "
        f'within it. Return matching ids only.\nCONCEPT: "{term}"\nNODES:\n{lines}\n'
        'Return JSON: {"match":[<id>,...]}', term, 0.1)
    s = {int(x) for x in (out.get("match") or [])}
    return [n["id"] for n in cands if n["id"] in s]

def _solve(nid: int, matched: dict) -> list:
    """all-or-none → this node; tier-1 with no matched child → drop (loose wave); subset → drill."""
    tax = _taxonomy(); kids = _children(nid)
    if not kids:
        return [nid]
    ns = matched.get(tax["by_id"][nid]["tier"] + 1, set())
    mk = [k for k in kids if k["id"] in ns]
    if not mk:
        return [] if tax["by_id"][nid]["tier"] == 1 else [nid]
    if len(mk) == len(kids):
        return [nid]
    res: list = []
    for k in mk:
        res += _solve(k["id"], matched)
    return res

def _node_out(nid: int) -> dict:
    n = _taxonomy()["by_id"][nid]
    return {"id": nid, "name": n["name"], "tier": n["tier"]}

def _to_node(theme: str):
    """Resolve a human theme term → node id (our resolver); fall back to the raw string (SDK slug)."""
    try:
        r = resolve_themes([theme]).get(theme) or []
        return r[0]["id"] if r else theme
    except Exception:
        return theme

# ── SIMPLE tools (thin SDK wrappers — client LLM orchestrates) ────────────────
@mcp.tool(title="Theme Summary", annotations=_RO)
def theme_summary(theme: str, window: str = "30d", country: Optional[str] = None) -> dict:
    """Pre-composed analyst brief for a megatrend theme: pulse, winners/losers, top entities, aspect
    heatmap, ripple. `theme` = a theme name or id/slug; `window` = 7d/30d/90d/1y/mtd/qtd/ytd."""
    return mdx().theme(_to_node(theme)).summary(window=window, country=country)

_SIM_STRONG = 0.68   # cosine ≥ this = a solid semantic match. ⚠️ CALIBRATE against real off-topic queries.
_SIM_WEAK = 0.58     # below this = essentially no match

@mcp.tool(title="Search News", annotations=_RO)
def search_news(q: str, entity_type: Optional[str] = None, collapse: Optional[bool] = None,
                limit: Optional[int] = None, from_: Optional[str] = None, to: Optional[str] = None,
                window: Optional[str] = None) -> dict:
    """SEMANTIC news search across ALL covered asset classes — stocks, FX, crypto, COMMODITIES (metals
    like copper/gold, energy like oil), and private companies. Articles matched by MEANING, impact-labeled
    (title, publisher, entities, direction, why). USE THIS for 'copper news', 'metals', 'gold', etc.
    instead of a web search. `entity_type` keeps only stock/forex/crypto/commodity/private hits. For a
    FILTERED feed by aspect/direction/country use `news_feed`. `limit` = how many (default 20, max 50).
    TIME-SCOPE with `from_`/`to` (ISO dates, e.g. '2026-04-01') or a `window` ('90d','qtd','ytd','1y').
    ⚠️ News coverage starts 2026-01-01 — older ranges return nothing (that's no COVERAGE, not 'no news').
    Returns {match_quality, top_similarity, note, results}. If match_quality is 'weak'/'none', the corpus
    has no strongly relevant news — do NOT present these results as evidence; say so and use another route."""
    frm = from_ or _win(window)
    results = _ser(mdx().news_search(q, entity_type=entity_type, collapse=collapse,
                                     from_=frm, to=to, limit=_lim(limit)).to_list())
    sims = [r.get("similarity") for r in results if isinstance(r.get("similarity"), (int, float))]
    top = max(sims) if sims else 0.0
    quality = "strong" if top >= _SIM_STRONG else ("weak" if top >= _SIM_WEAK else "none")
    note = _coverage_note(frm) or (None if quality == "strong" else (
        "Weak/no semantic match — MarketDX likely has no strongly relevant news for this query. Do NOT "
        "present these as evidence; tell the user, and use world knowledge / another tool instead."))
    return {"match_quality": quality, "top_similarity": round(top, 3), "note": note, "results": results}

@mcp.tool(title="News Feed", annotations=_RO)
def news_feed(megatrend: Optional[str] = None, country: Optional[str] = None,
              aspect: Optional[str] = None, direction: Optional[str] = None,
              news_type: Optional[str] = None, only_scored: Optional[bool] = None,
              min_relevance: Optional[float] = None, limit: Optional[int] = None,
              collapse: Optional[bool] = None, from_: Optional[str] = None,
              to: Optional[str] = None, window: Optional[str] = None) -> list:
    """The filtered impact feed — news by megatrend/country/aspect/direction/news_type, across stocks,
    FX, crypto, COMMODITIES (metals/energy) and private cos. Use for 'negative tariff news on
    Semiconductors', 'macro news moving European stocks', 'copper / metals news', etc. Near-duplicate
    stories are MERGED by default (+`dup_count`); `collapse=false` for the raw feed. `limit` = how many
    (default 20, max 50); narrow the filters rather than paging deep. TIME-SCOPE with `from_`/`to` (ISO)
    or a `window` ('90d','qtd','ytd','1y'). To COMPARE periods, call once per period and compare the
    results. ⚠️ News starts 2026-01-01 — older ranges return nothing (no coverage, not 'no news')."""
    return _ser(mdx().news(megatrend=megatrend, country=country, aspect=aspect, direction=direction,
                          news_type=news_type, only_scored=only_scored, min_relevance=min_relevance,
                          collapse=collapse, from_=from_ or _win(window), to=to, limit=_lim(limit)).to_list())

@mcp.tool(title="Stock Impact", annotations=_RO)
def stock_impact(ticker: str, direction: Optional[str] = None, limit: Optional[int] = None,
                 collapse: Optional[bool] = None, from_: Optional[str] = None,
                 to: Optional[str] = None, window: Optional[str] = None) -> list:
    """How news moved a specific company/asset (incl commodities like GOLD.COMM) — per-article impact
    (direction + aspect + why), most recent first. Near-duplicate stories are MERGED by default (each row
    = one story + `dup_count`); `collapse=false` for the raw feed. `limit` = how many (default 20, max 50)
    — heavily-covered assets have HUNDREDS, so keep it small + narrow. TIME-SCOPE with `from_`/`to` (ISO)
    or `window` ('90d','qtd','1y'); to COMPARE periods, call once per period. ⚠️ News starts 2026-01-01 —
    older ranges return nothing (no coverage, not 'no news'; price/volatility history goes back decades)."""
    return _ser(mdx().stock(ticker).news(direction=direction, collapse=collapse,
                                         from_=from_ or _win(window), to=to, limit=_lim(limit)).to_list())

@mcp.tool(title="Theme Players", annotations=_RO)
def theme_players(theme: str, country: str, exposure: Optional[str] = None,
                  limit: Optional[int] = None) -> list:
    """Investable MEMBER companies of a theme (curated membership) in a country. Different from
    top_entities (which are news-derived). `limit` = how many (default 20, max 50; big themes have many)."""
    return _ser(mdx().theme(_to_node(theme)).stocks(country=country, exposure=exposure,
                                                    max_items=_lim(limit)).to_list())

@mcp.tool(title="Private Movers", annotations=_RO)
def private_movers(theme: str, country: Optional[str] = None, limit: Optional[int] = None) -> list:
    """Off-coverage / private companies the news moved within a theme — the 'beyond tickers' surface.
    `limit` = how many (default 20, max 50)."""
    return _ser(mdx().theme(_to_node(theme)).off_coverage(country=country, max_items=_lim(limit)).to_list())

@mcp.tool(title="Company Relationships", annotations=_RO)
def relationships(ticker: str, limit: Optional[int] = None) -> dict:
    """Competitors + peers of a company (news-derived relationship graph). `limit` caps EACH list
    (default 15, max 50)."""
    ref = mdx().stock(ticker)
    n = _lim(limit, default=15)
    return {"competitors": _ser(ref.competitors(limit=n).to_list()), "peers": _ser(ref.peers(limit=n).to_list())}

@mcp.tool(title="List Megatrends", annotations=_RO)
def list_themes(query: Optional[str] = None) -> list:
    """Browse / discover the megatrend taxonomy (25 tier-1 families + sub-nodes) — resolve a theme id."""
    return _ser(mdx().megatrends().to_list())

@mcp.tool(title="List Portfolios", annotations=_RO)
def list_portfolios() -> dict:
    """List the user's OWN portfolios (id, name, base_currency, account_type, nav, total_return_pct,
    unrealized_pnl, position_count, …) so you can pick one to analyze. Call this FIRST whenever the user
    says 'my portfolio' without a number — show the names, then pass the chosen `id` to
    `portfolio_context`. Owner-scoped: only ever the user's own portfolios.
    If `count` is 0 (they own none), the response carries a `note` with a create link — relay THAT
    (invite them to create a portfolio) instead of saying an empty 'you have no portfolios'."""
    return mdx().portfolios()

@mcp.tool(title="Portfolio Context", annotations=_RO)
def portfolio_context(portfolio_id: int) -> dict:
    """An LLM-ready snapshot of ONE of the user's OWN portfolios (owner-scoped) — analyze it directly.
    Returns: `meta` (stated goal/thesis/horizon/risk-reaction) · `summary` (NAV, P&L, exposure, cash) ·
    `lifetime` and `recent`(~12mo) blocks, EACH with `performance` (return/cagr/sharpe/sortino/calmar/
    drawdown/vol/win_rate) + `attribution` · `positions` (live holdings + megatrend path + value_trend) ·
    `closed_positions` (sold / margin-called, with realized_pnl) · `allocation` · `concentration` (HHI) ·
    `inferred_behavior` (revealed archetype) · `flags`. Needs the numeric `portfolio_id`
    (use `list_portfolios`); 404 if not the user's.

    HOW TO ANALYZE (research-analyst framing — see marketdx://policy):
    • Lead with the sharpest thing: a non-empty `flag`, or the biggest concentration / drawdown / tilt.
      One insight-first sentence, then support with the numbers.
    • "What drove the return / the drawdown / strengths & weaknesses" → use `attribution.contributors[]`
      (per-holding `pnl_contribution` + `pct_of_nav_change` + the `held` window; reconciles to `nav_change`
      to the cent and INCLUDES since-sold names). Use `recent` for 'this year', `lifetime` for the whole
      run. Do NOT estimate contribution yourself — read it from `attribution`.
    • ⚠️ Only TWO windows exist (lifetime + recent ~12mo). For a specific past window ('mid-2025', '2023
      vs now') you do NOT have exact data — say so; don't fabricate a per-period breakdown.
    • Make it NEWS-AWARE: FUSE with `stock_impact` on the notable holdings + `news_feed`/`search_news` on
      their `theme` paths for the WHY (⚠️ news only covers 2026+; portfolio history goes back further).
    • Facts, not advice. Observe; do NOT tell them to buy/sell/rebalance/time — hand the judgment back."""
    return mdx().portfolio_context(portfolio_id)

# ── COMPOSITE tools (whole multi-step pipeline server-side, ONE call) ─────────
@mcp.tool(title="Resolve Themes", annotations=_RO)
def resolve_themes(terms: List[str]) -> dict:
    """Map trend-language ('HBM', 'foundry', 'cancer drug', 'robotaxi') to the specific taxonomy
    node(s) at the right level (may be tier-1, -2, or -3; may be several for a polysemous term).
    Gazetteer first (deterministic, free), deepseek 3-tier match + deterministic solve for the rest.
    Returns {term: [{id,name,tier},...]}. Call this before theme queries; don't flatten/guess yourself."""
    tier1 = [n for n in _taxonomy()["nodes"] if n["tier"] == 1]
    result: dict = {}
    for term in terms:
        g = _gazetteer(term)
        if g:
            result[term] = [_node_out(i) for i in g]
            continue
        m1 = _match(term, tier1)
        c2 = [k for t in m1 for k in _children(t)]
        m2 = set(_match(term, c2))
        c3 = [k for t in m2 for k in _children(t)]
        m3 = set(_match(term, c3)) if c3 else set()
        nodes: list = []
        for t in m1:
            nodes += _solve(t, {2: m2, 3: m3})
        result[term] = [_node_out(i) for i in dict.fromkeys(nodes)]
    return result

@mcp.tool(title="Suggest Explorations", annotations=_RO)
def suggest_cta(theme: str, window: str = "30d") -> dict:
    """After answering, propose 1-2 data-backed 'explore further' hooks that pull the user into the
    graph's moat (ripple/relations/commodity/off-coverage). Server-side: theme_summary(has ripple/
    entities/aspects) + a semantic news search, then deepseek curates ONLY data-backed hooks.
    Validated in /tmp/mcp-gate/cta_tool.js (there via direct probes; here via the summary composite)."""
    brief = mdx().theme(_to_node(theme)).summary(window=window)  # already carries winners/losers/top_entities/aspect_heatmap/ripple
    signals = {k: brief.get(k) for k in ("winners", "losers", "top_entities", "top_assets",
                                         "aspect_heatmap", "ripple", "pulse")}
    curate = ("Given a theme brief's REAL signals, write 1-2 CTAs inviting deeper exploration. "
              "STRICT: use ONLY item names/numbers present in the signals; never invent. Prefer the "
              "highest-moat, most-active thread (ripple/relations over generic). Cite the number. "
              'Return JSON: {"ctas":[{"door":"...","hook":"<one line>"}]}')
    return _deepseek(curate, json.dumps(signals, ensure_ascii=False), temperature=0.4)

# ── RESOURCES (injected into the client LLM's context) ───────────────────────
@mcp.resource("marketdx://policy")
def gate_policy() -> str:
    """The gate & framing policy (skill.md) the client LLM should follow — scope resolution, the 5
    response stances, honest fidelity, no-fudge. Kept alongside the server."""
    p = _HERE / "policy.md"
    return p.read_text() if p.exists() else "policy.md not found"

@mcp.resource("marketdx://capabilities")
def capabilities() -> str:
    """Live coverage/capabilities map: covered markets + depth, asset classes, news window, tier-1
    themes — so the client scopes correctly (expand 'Asia'→covered set; don't request uncovered)."""
    try:
        return json.dumps({"enums": mdx().enums(), "account": mdx().account()}, ensure_ascii=False)
    except Exception as e:  # keep the resource readable even if the API hiccups
        return json.dumps({"error": str(e)})

# ── OAuth (WorkOS AuthKit) — MCP Authorization ────────────────────────────────
# When WORKOS_ISSUER is set the server advertises itself as an OAuth 2.0 Protected Resource (RFC 9728):
# an unauthenticated MCP request gets 401 + WWW-Authenticate pointing at the metadata document.
#
# We act as an **authorization-server-metadata proxy**: `authorization_servers` names US, and we serve
# BOTH RFC 8414 (`oauth-authorization-server`) and OIDC (`openid-configuration`) discovery docs from our
# own origin, built from WorkOS's RFC 8414 doc with `issuer` rewritten to us. Why: WorkOS advertises
# `registration_endpoint` + `client_id_metadata_document_supported` ONLY in its RFC 8414 doc, NOT in its
# openid-configuration — so a client that reads the OIDC doc (as Claude did → "automatic client
# registration isn't supported") sees no DCR/CIMD. Proxying both docs guarantees the client finds them
# either way and can use CIMD (no registration) or DCR. The OAuth endpoints still point at WorkOS, which
# authenticates the user (via our External Sign-in URI) and mints the JWT; we just forward the Bearer.
# Unset → no OAuth advertised; only the Bearer-key path works.
_WORKOS_ISSUER = os.environ.get("WORKOS_ISSUER", "").rstrip("/") or None
_RESOURCE_WK = "/.well-known/oauth-protected-resource"
_AS_WK = ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration")
_AS_CACHE: dict = {}   # WorkOS RFC 8414 metadata, fetched once

def _origin(scope) -> str:
    hdrs = dict(scope.get("headers") or {})
    host = hdrs.get(b"host", b"").decode() or "mcp.marketdx.lab.ai"
    proto = hdrs.get(b"x-forwarded-proto", b"https").decode().split(",")[0].strip() or "https"
    return f"{proto}://{host}"

def _resource_metadata(scope) -> dict:
    origin = _origin(scope)
    # `resource` must equal the token audience the client requests — our MCP endpoint URL. Derived
    # from the request host so both mcp.marketdx.lab.ai and the run.app URL self-describe correctly.
    return {
        "resource": os.environ.get("MCP_RESOURCE_URL") or f"{origin}/mcp",
        "authorization_servers": [origin],   # we proxy the AS metadata (see block comment)
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "email", "profile"],
    }

async def _as_metadata(scope) -> dict:
    """WorkOS RFC 8414 metadata with `issuer` rewritten to our origin (RFC 8414 §3.3 self-consistency).
    Endpoints still point at WorkOS. Fetched once and cached; falls back to a minimal doc on failure."""
    import asyncio, urllib.request
    if not _AS_CACHE:
        def _fetch():
            url = f"{_WORKOS_ISSUER}/.well-known/oauth-authorization-server"
            with urllib.request.urlopen(url, timeout=10) as r:
                return json.loads(r.read())
        try:
            _AS_CACHE.update(await asyncio.to_thread(_fetch))
        except Exception:  # WorkOS unreachable → minimal doc from known endpoints
            _AS_CACHE.update({
                "authorization_endpoint": f"{_WORKOS_ISSUER}/oauth2/authorize",
                "token_endpoint": f"{_WORKOS_ISSUER}/oauth2/token",
                "registration_endpoint": f"{_WORKOS_ISSUER}/oauth2/register",
                "jwks_uri": f"{_WORKOS_ISSUER}/oauth2/jwks",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
                "client_id_metadata_document_supported": True,
            })
    meta = dict(_AS_CACHE)
    meta["issuer"] = _origin(scope)   # served from our origin → issuer must be us
    return meta

async def _send_json(send, status: int, obj: dict, extra_headers: list | None = None):
    body = json.dumps(obj).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    headers += extra_headers or []
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})

class _AuthASGI:
    """Pure-ASGI middleware (NOT BaseHTTPMiddleware — that runs the route in a separate task where a
    contextvar set here wouldn't propagate). Reads `Authorization: Bearer <key>` and stashes it in
    _req_key for the duration of the request, so mdx() picks up THIS caller's key. Also implements the
    OAuth protected-resource discovery (RFC 9728) when WORKOS_ISSUER is configured."""
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        auth = dict(scope.get("headers") or {}).get(b"authorization", b"").decode()
        key = auth[7:].strip() if auth[:7].lower() == "bearer " else None

        # Public branding asset (no auth) — the connector's icon.
        if path == "/favicon.ico":
            hdrs = [(b"content-type", b"image/x-icon"), (b"content-length", str(len(_FAVICON)).encode()),
                    (b"cache-control", b"public, max-age=86400")]
            await send({"type": "http.response.start", "status": 200 if _FAVICON else 404, "headers": hdrs})
            await send({"type": "http.response.body", "body": _FAVICON})
            return

        if _WORKOS_ISSUER:
            # Public discovery documents (RFC 9728 + RFC 8414/OIDC proxy) — no auth.
            if path.startswith(_RESOURCE_WK):
                return await _send_json(send, 200, _resource_metadata(scope))
            if path.startswith(_AS_WK):
                return await _send_json(send, 200, await _as_metadata(scope))
            # Unauthenticated MCP call → challenge so the client starts the OAuth flow. (Bearer present
            # → fall through; the token, key or JWT, is validated downstream by the API.)
            if key is None:
                challenge = f'Bearer resource_metadata="{_origin(scope)}{_RESOURCE_WK}"'
                return await _send_json(send, 401, {"error": "unauthorized"},
                                        [(b"www-authenticate", challenge.encode())])

        tok = _req_key.set(key)
        try:
            await self.app(scope, receive, send)
        finally:
            _req_key.reset(tok)

def main() -> None:
    """Console entry point (`marketdx-mcp`). MCP_TRANSPORT=http → hosted Streamable HTTP (per-request
    Bearer auth); else stdio (local, MARKETDX_API_KEY env)."""
    if os.environ.get("MCP_TRANSPORT", "stdio").replace("-", "") in ("http", "streamablehttp"):
        import uvicorn
        app = _AuthASGI(mcp.streamable_http_app())
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
    else:
        mcp.run()   # stdio

if __name__ == "__main__":
    main()
