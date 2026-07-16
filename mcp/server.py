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
from marketdx import MarketDX

# DNS-rebinding protection defaults to a localhost allow-list (it guards a *local* server from
# browser-driven Host spoofing). We're a hosted API behind Cloud Run TLS with our own per-request
# Bearer auth, and the Host varies (run.app + mcp.marketdx.lab.ai) — so disable the Host check here.
mcp = FastMCP("marketdx", transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
_HERE = pathlib.Path(__file__).parent

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
@mcp.tool()
def theme_summary(theme: str, window: str = "30d", country: Optional[str] = None) -> dict:
    """Pre-composed analyst brief for a megatrend theme: pulse, winners/losers, top entities, aspect
    heatmap, ripple. `theme` = a theme name or id/slug; `window` = 7d/30d/90d/1y/mtd/qtd/ytd."""
    return mdx().theme(_to_node(theme)).summary(window=window, country=country)

_SIM_STRONG = 0.68   # cosine ≥ this = a solid semantic match. ⚠️ CALIBRATE against real off-topic queries.
_SIM_WEAK = 0.58     # below this = essentially no match

@mcp.tool()
def search_news(q: str, entity_type: Optional[str] = None, collapse: Optional[bool] = None) -> dict:
    """SEMANTIC news search — articles matched by MEANING, impact-labeled (title, publisher, entities,
    direction, why). `entity_type` keeps only stock/forex/crypto/commodity/private hits. For a
    FILTERED feed by aspect/direction/country use `news_feed`.
    Returns {match_quality, top_similarity, note, results}. If match_quality is 'weak'/'none', the corpus
    has no strongly relevant news — do NOT present these results as evidence; say so and use another route."""
    results = _ser(mdx().news_search(q, entity_type=entity_type, collapse=collapse).to_list())
    sims = [r.get("similarity") for r in results if isinstance(r.get("similarity"), (int, float))]
    top = max(sims) if sims else 0.0
    quality = "strong" if top >= _SIM_STRONG else ("weak" if top >= _SIM_WEAK else "none")
    note = None if quality == "strong" else (
        "Weak/no semantic match — MarketDX likely has no strongly relevant news for this query. Do NOT "
        "present these as evidence; tell the user, and use world knowledge / another tool instead.")
    return {"match_quality": quality, "top_similarity": round(top, 3), "note": note, "results": results}

@mcp.tool()
def news_feed(megatrend: Optional[str] = None, country: Optional[str] = None,
              aspect: Optional[str] = None, direction: Optional[str] = None,
              news_type: Optional[str] = None, only_scored: Optional[bool] = None,
              min_relevance: Optional[float] = None) -> list:
    """The filtered impact feed — news by megatrend/country/aspect/direction/news_type. Use for
    'negative tariff news on Semiconductors', 'macro news moving European stocks', etc."""
    return _ser(mdx().news(megatrend=megatrend, country=country, aspect=aspect, direction=direction,
                          news_type=news_type, only_scored=only_scored, min_relevance=min_relevance).to_list())

@mcp.tool()
def stock_impact(ticker: str, direction: Optional[str] = None) -> list:
    """How recent news moved a specific company — per-article impact (direction + aspect + why)."""
    return _ser(mdx().stock(ticker).news(direction=direction).to_list())

@mcp.tool()
def theme_players(theme: str, country: str, exposure: Optional[str] = None) -> list:
    """Investable MEMBER companies of a theme (curated membership) in a country. Different from
    top_entities (which are news-derived)."""
    return _ser(mdx().theme(_to_node(theme)).stocks(country=country, exposure=exposure).to_list())

@mcp.tool()
def private_movers(theme: str, country: Optional[str] = None) -> list:
    """Off-coverage / private companies the news moved within a theme — the 'beyond tickers' surface."""
    return _ser(mdx().theme(_to_node(theme)).off_coverage(country=country).to_list())

@mcp.tool()
def relationships(ticker: str) -> dict:
    """Competitors + peers of a company (news-derived relationship graph)."""
    ref = mdx().stock(ticker)
    return {"competitors": _ser(ref.competitors().to_list()), "peers": _ser(ref.peers().to_list())}

@mcp.tool()
def list_themes(query: Optional[str] = None) -> list:
    """Browse / discover the megatrend taxonomy (25 tier-1 families + sub-nodes) — resolve a theme id."""
    return _ser(mdx().megatrends().to_list())

# ── COMPOSITE tools (whole multi-step pipeline server-side, ONE call) ─────────
@mcp.tool()
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

@mcp.tool()
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

class _AuthASGI:
    """Pure-ASGI middleware (NOT BaseHTTPMiddleware — that runs the route in a separate task where a
    contextvar set here wouldn't propagate). Reads `Authorization: Bearer <key>` and stashes it in
    _req_key for the duration of the request, so mdx() picks up THIS caller's key. Unauthed requests
    are allowed through (the tool raises a clear error) — discovery/health stay open."""
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        auth = dict(scope.get("headers") or {}).get(b"authorization", b"").decode()
        key = auth[7:].strip() if auth[:7].lower() == "bearer " else None
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
