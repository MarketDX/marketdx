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

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from marketdx import MarketDX, NotFoundError

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
    "price even though there's no 2023 news. Any read on how a tradable asset (a stock, ETF, or index) is "
    "DOING — whatever the phrasing or language — is a MarketDX question: our news→impact + options-"
    "positioning read IS the substance of 'how is it doing' (the WHY it's moving + the market's stance), "
    "which a web search cannot supply. Reach for `asset_pulse(<ticker>)` on these. 🔴 This INCLUDES a "
    "MARKET / INDEX asked in a 'right now / ตอนนี้ / current' phrasing (S&P, Nasdaq, Dow, 'the market'): "
    "map it to its ETF (S&P→SPY · Nasdaq→QQQ · Dow→DIA — WE DO COVER their options + news) and call "
    "`asset_pulse` for the news-impact + positioning that IS 'how it's doing'. A web-searched index LEVEL "
    "is at most ONE supplementary number — NEVER answer a market/index question with only a web level, and "
    "never skip the MarketDX read (the level alone is not 'how is it doing'). asset_pulse = ONE call returning "
    "BOTH lenses, so the read is never half-informed. 🔵 But if the subject is a SECTOR / INDUSTRY / THEME "
    "CONCEPT rather than one ticker (semiconductors, tech, energy, banks, AI, clean energy, gold, …) → use "
    "`theme_pulse(<concept>)` instead: it resolves the concept across the THREE independent taxonomies and "
    "returns every angle that applies, each SEPARATE — the MarketDX megatrend cohort, the GICS-sector "
    "cohort (a different membership), and the tradable ETF's options positioning (it does the concept→ETF "
    "mapping for you; full 58-ETF set in marketdx://policy). So: a specific TICKER/company → `asset_pulse`; "
    "a sector/theme CONCEPT → `theme_pulse`. ⚠️ For a NON-US company or when unsure of the exact ticker "
    "(esp. Asian/European names — we use our OWN suffixes, Korea=.KO not .KS, so a guess 404s), resolve it "
    "FIRST with `find_stock(<name>)` and use the returned `ticker`. Also resolves commodities/crypto/"
    "private (gold→GOLD, openai→oc:52). "
    "Prefer these composites over calling stock_impact / "
    "options_sentiment one at a time; use those only to DRILL deeper afterwards. Synthesize where news and "
    "positioning AGREE or DIVERGE; if the user HOLDS the name, tie the read back to their position. "
    "To SUMMARIZE a whole scope — a news CATEGORY (e.g. "
    "'สรุปข่าว commodity' → news_type='commodity_supply'), a country/market, an impact channel (aspect), "
    "a GICS sector, a megatrend, or any AND-mix — use `brief` (the composed 'how is <X> doing right now?' "
    "picture), NOT search_news/news_feed (those return a raw article LIST, not a summary). Resolve a "
    "trend term via resolve_themes; follow marketdx://policy for voice, scope, and the response stance. "
    "NOTES — the user keeps a personal INVESTMENT KNOWLEDGE BASE via `write_note` (their notes join this "
    "same graph and are retrievable by entity later — the point is to fight scattered knowledge). Act as a "
    "proactive librarian: after a SUBSTANTIVE investment answer — a sector/mechanism explainer, a dated "
    "market read (with its 'why'), a thesis, a comparison, a decision — briefly OFFER to keep it "
    "('เก็บเข้าโน้ตไหม?'), and save right away on any explicit 'save this / จดไว้'. When you save, pass the "
    "tickers + megatrend ids you already used this turn so the note links to the graph. Do NOT offer on "
    "chit-chat, trivia lookups (e.g. 'what's NVDA's ticker'), or off-topic / non-investment turns; don't "
    "nag more than once, and never save pure filler."
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
# WRITE tools persist user data → readOnlyHint=False so a client can prompt/confirm before running.
# additive (a new note), not an update/delete → not destructive, not idempotent.
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)

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

def _to_nodes(spec: str) -> Optional[str]:
    """Resolve a csv of trend TERMS and/or node IDs → csv of node ids, in ONE resolve pass (so
    'foundry,hbm' becomes '56020000,56030000' without two round-trips). Numeric parts pass through as
    ids; term parts are batch-resolved via resolve_themes and take the top candidate each. Order-preserved,
    de-duped. Returns None if nothing resolves."""
    parts = [p.strip() for p in str(spec).split(",") if p.strip()]
    ids, terms = [], []
    for p in parts:
        (ids if p.isdigit() else terms).append(p)
    if terms:
        try:
            res = resolve_themes(terms)
            for t in terms:
                cand = res.get(t) or []
                if cand:
                    ids.append(str(cand[0]["id"]))
        except Exception:
            pass
    return ",".join(dict.fromkeys(ids)) or None

# ── SIMPLE tools (thin SDK wrappers — client LLM orchestrates) ────────────────
# The valid news_type names (GET /v1/news/types) — used to sanitize a hallucinated value before it
# hard-errors the API. Keep in sync with the API's list.
_NEWS_TYPES = {"product_tech", "ma_partnership", "industry_thematic", "earnings_results",
               "corporate_action", "management_governance", "analyst_rating", "macro_economic",
               "geopolitics", "commodity_supply", "regulatory_legal", "cybersecurity_digital_trust",
               "digital_finance_tokenization", "price_action_technical", "noise_other", "short_news",
               "crypto_related", "forex_related", "analyst_forecast"}

# The 58 opana-covered ETFs → concept label (from ava_listings.asset_type='ETF'). Doubles as the asset-
# angle resolver vocabulary for theme_pulse and the authoritative "which ETF is covered" set.
_COVERED_ETFS = {
    "SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Russell 2000", "DIA": "Dow 30", "MDY": "S&P Midcap 400",
    "XLK": "Technology sector", "XLF": "Financials sector", "XLE": "Energy sector", "XLV": "Healthcare sector",
    "XLY": "Consumer Discretionary", "XLP": "Consumer Staples", "XLI": "Industrials", "XLU": "Utilities",
    "XLB": "Materials", "XLRE": "Real Estate", "XLC": "Communication Services",
    "SMH": "Semiconductors", "SOXX": "Semiconductors", "XBI": "Biotech", "IBB": "Biotech",
    "KRE": "Regional Banks", "OIH": "Oil Services", "XOP": "Oil & Gas E&P", "XRT": "Retail",
    "JETS": "Airlines", "TAN": "Solar", "GLD": "Gold", "SLV": "Silver", "USO": "Crude Oil",
    "UNG": "Natural Gas", "GDX": "Gold Miners", "GDXJ": "Junior Gold Miners", "TLT": "20y+ Treasuries",
    "IEF": "7-10y Treasuries", "AGG": "US Aggregate Bonds", "LQD": "Investment-Grade Corp",
    "HYG": "High-Yield Corp", "TIP": "TIPS", "EMB": "EM Bonds", "EEM": "Emerging Markets",
    "EFA": "Developed ex-US", "FXI": "China Large-Cap", "KWEB": "China Internet", "EWJ": "Japan",
    "EWY": "South Korea", "EWZ": "Brazil", "INDA": "India", "VXX": "VIX Volatility", "UVXY": "VIX 2x",
    "IBIT": "Bitcoin", "ETHA": "Ethereum", "SPXL": "S&P 3x Bull", "SPXU": "S&P 3x Bear",
    "TQQQ": "Nasdaq 3x Bull", "SQQQ": "Nasdaq 3x Bear", "SOXL": "Semis 3x Bull", "TZA": "Small-Cap 3x Bear",
}

@mcp.tool(title="Theme Summary", annotations=_RO)
def theme_summary(theme: str, window: str = "30d", country: Optional[str] = None) -> dict:
    """Pre-composed analyst brief for a megatrend theme: pulse, winners/losers, top entities, aspect
    heatmap, ripple. `theme` = a theme name or id/slug; `window` = 7d/30d/90d/1y/mtd/qtd/ytd."""
    return mdx().theme(_to_node(theme)).summary(window=window, country=country)

@mcp.tool(title="Brief", annotations=_RO)
def brief(news_type: Optional[str] = None, country: Optional[str] = None,
          aspect: Optional[str] = None, gics: Optional[str] = None,
          megatrend: Optional[str] = None, window: str = "30d",
          from_: Optional[str] = None, to: Optional[str] = None,
          interval: Optional[str] = None, lang: Optional[str] = None) -> dict:
    """The generalized ANALYST BRIEF — one composed "how is <scope> doing right now?" picture (pulse +
    net direction, top_stories, winners/losers, aspect_heatmap, top_entities, top_assets) for ANY
    AND-combination of scopes. ⭐ Use this to SUMMARIZE a SCOPE — a THEME, a news CATEGORY, a COUNTRY, a
    SECTOR, or an aspect (NOT a raw article list → that's search_news/news_feed). ⛔ NOT for a single
    COMPANY or a market INDEX/ticker: "how is the S&P / Nasdaq / AAPL doing?" → `options_sentiment`
    (+ `stock_impact`/`news_feed`), because an index maps to an ETF asset (S&P→SPY), not a brief scope.
    Scope by ≥1 of (each takes a CSV for multiple values):
      • `news_type` — a news CATEGORY. Use ONLY these EXACT names (never invent one): product_tech,
        ma_partnership, industry_thematic, earnings_results, corporate_action, management_governance,
        analyst_rating, macro_economic, geopolitics, commodity_supply, regulatory_legal,
        cybersecurity_digital_trust, digital_finance_tokenization, price_action_technical, crypto_related,
        forex_related, analyst_forecast. ("สรุปข่าว commodity" → commodity_supply; central-bank/rates →
        macro_economic — there is NO 'monetary_policy').
      • `country` — an ISO-2 market. country='JP' → "how is Japan doing right now?".
      • `aspect` — an impact CHANNEL. aspect='tariff' → "everything moving via tariffs".
      • `gics` — a GICS code prefix (sector 25 / industry-group 2550 / industry 255010), often × country.
      • `megatrend` — a theme node id/slug. For a NAMED theme use `theme_summary` (it resolves free text);
        use `megatrend` here only when you already have the id or want to AND it with another scope.
    Combine (AND): news_type='commodity_supply'+country='JP' = commodity news in Japan; gics='2550'+
    country='GB,DE,FR,IT,ES,NL' = a European retail pulse. `window` = 7d/30d/90d/180d/1y/mtd/qtd/ytd (or
    pass from_/to as ISO dates). ≥1 scope is REQUIRED (it never scans everything). ⚠️ News coverage starts
    2026-01-01. `node`+`ripple` appear only when a SINGLE megatrend anchors the brief."""
    # Runtime-sanitize news_type: the client can hallucinate a name (e.g. 'monetary_policy') → the API
    # hard-errors. Drop unknowns so the valid scope still returns; flag what we dropped.
    dropped = []
    if news_type:
        req = [t.strip() for t in str(news_type).split(",") if t.strip()]
        news_type = ",".join(t for t in req if t in _NEWS_TYPES) or None
        dropped = [t for t in req if t not in _NEWS_TYPES]
    res = mdx().brief(megatrend=megatrend, news_type=news_type, country=country, aspect=aspect,
                      gics=gics, window=window, from_=from_, to=to, interval=interval, lang=lang)
    if dropped and isinstance(res, dict):
        res["_warning"] = (f"Ignored invalid news_type(s) {dropped} — not real categories. Valid names: "
                           f"{sorted(_NEWS_TYPES)}. (There is no 'monetary_policy'; use 'macro_economic'.)")
    return res

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

@mcp.tool(title="Options Sentiment", annotations=_RO)
def options_sentiment(ticker: str, style: str = "plain") -> dict:
    """What the US OPTIONS MARKET is saying about `ticker` — the POSITIONING lens (~547 popular US
    optionable names, stocks + ETFs). Pairs with the news→impact read: for "how is <X> doing?" fetch
    THIS *and* `stock_impact`/`news_feed` and fuse them (news = what's happening + WHY; options = how the
    market is positioned — direction lean via put/call, fear/greed via skew, IV level, dealer-gamma
    stability, max-pain pinning, notable expiries). For a name the user HOLDS it shows how the market is
    hedging that position. Broad-INDEX question → pass the liquid ETF proxy: S&P 500→`SPY`, Nasdaq 100→
    `QQQ`, Dow→`DIA`, Russell 2000→`IWM`, 20y Treasuries→`TLT`, Gold→`GLD`. `ticker` = bare US symbol or
    `SYMBOL.US` (`NVDA`/`NVDA.US`); US-only. `style` = `plain` (everyday language, default) | `technical`.
    ⚠️ Narrate from the payload's `sentiment._guide`: read straight off each signal's `read` + `because`,
    DON'T recompute, DON'T compare raw O/S or IV across assets, `baseline_pending`/`level` ≠ "unusual"
    (only a `_percentile`/`_rank` read flags unusual), and the VERDICT is YOURS (opana stops at
    interpretation). Not covered → `{covered:false, note}`: say options data isn't available for it and
    use the news/impact read instead — never fabricate an options view."""
    try:
        return mdx()._get(f"/v1/options/{ticker}/sentiment", {"style": style}).data
    except NotFoundError as e:
        return {"covered": False, "symbol": ticker, "note": str(e) or (
            f"No options-sentiment for '{ticker}' — opana covers ~547 US-listed optionable names. Don't "
            "fabricate an options view; use news/impact for the read, and (if relevant) note options "
            "coverage isn't available for this name.")}

@mcp.tool(title="Find Stock / Resolve Ticker", annotations=_RO)
def find_stock(q: str, country: Optional[str] = None, limit: Optional[int] = None) -> list:
    """Resolve ANY free-text — a company NAME, a ticker (full or prefix), an alias, a phrase, or a
    non-English name — to the EXACT MarketDX `ticker`. 🔴 Use this BEFORE asset_pulse / stock_impact
    whenever you're not 100% sure of the exact ticker — ESPECIALLY for NON-US companies: MarketDX uses
    its OWN exchange suffixes (Korea = `.KO` NOT Yahoo's `.KS`; Taiwan = `.TW`; etc.) so GUESSING a
    foreign ticker usually 404s. Also resolves commodities (gold→`GOLD`), crypto (`BTC`), and off-coverage
    PRIVATE companies (openai→`oc:52`). Matching = lexical first (symbol/prefix/alias/name), then a
    SEMANTIC fallback so a phrase ('chip maker') or another language still resolves. Returns matches with
    a ready-to-use `ticker` (paste straight into asset_pulse/stock_impact), `type` (stock/etf/commodity/
    crypto/forex/private), `name`, `country`, `market_cap_usd`, `similarity`. `country` restricts to a
    market. Take the top match; for a US mega-cap you already know the ticker (AAPL) you can skip this."""
    rows = mdx()._get("/v1/stocks", {"q": q, "country": country,
                                     "limit": _lim(limit, default=8, ceiling=25)}).data.get("matches", [])
    keep = ("ticker", "symbol", "name", "type", "country", "exchange", "market_cap_usd", "similarity",
            "match_type", "mode")
    return [{k: m[k] for k in keep if k in m} for m in rows]

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
def portfolio_context(portfolio_id: int, from_: Optional[str] = None, to: Optional[str] = None,
                      window: Optional[str] = None, snapshots: Optional[str] = None) -> dict:
    """An LLM-ready snapshot of ONE of the user's OWN portfolios (owner-scoped) — analyze it directly.
    NO window → default: `meta` · `summary` · a `lifetime`(all-time) + `recent`(~12mo) block, EACH with
    `performance` (return/cagr/sharpe/sortino/calmar/drawdown/vol/win_rate) + `attribution` · `positions`
    · `closed_positions` (realized_pnl) · `composition` (point-in-time holdings) · `allocation` ·
    `concentration` (HHI) · `inferred_behavior` · `flags`. `portfolio_id` from `list_portfolios`; 404 if
    not the user's.

    TIME WINDOW — `from_`/`to` (ISO) or `window` (`7d|30d|90d|180d|1y|mtd|qtd|ytd`): REPLACES lifetime+
    recent with ONE `window` block (that span's `performance` + `attribution` + `nav_trend`) and scopes
    `composition` to match. So ANY period's return + drivers is answerable. `snapshots` = composition
    granularity only (`year|quarter|month|week|day|off`).
    🔴 MANDATORY for period questions: the default / `lifetime` / `recent` blocks DO NOT contain the
    performance or attribution of an arbitrary period (e.g. Q1-2025, "H1 2024"). To answer ANY specific
    period — or to COMPARE periods (Q1/25 vs Q1/26, 2023 vs 2025) — you MUST call this tool AGAIN with
    `from_`/`to` (or `window`) for EACH period, then compare the returned `window` blocks. NEVER derive a
    period's return/sharpe/drawdown/attribution from the default view — those numbers aren't in it; making
    them up is a hard error. If you haven't fetched a period's window, say you need to fetch it, don't guess.

    HOW TO ANALYZE (research-analyst framing — see marketdx://policy):
    • Lead with the sharpest thing: a non-empty `flag`, or the biggest concentration / drawdown / tilt.
    • "What drove the return / drawdown / strengths & weaknesses" (for the default OR a window) → read
      `attribution.contributors[]` (per-holding `pnl_contribution` + `pct_of_nav_change` + `held` window;
      reconciles to `nav_change` to the cent, INCLUDES since-sold names). Don't estimate it yourself.
    • "What did I hold on date X / how did the book evolve" → `composition` (set `snapshots` + a window).
    • ⚠️ TRUST THE EDGE NOTES, never fabricate: a window before the portfolio's `inception_date` returns
      `window.empty=true` + a note (or clamped) — say "the portfolio didn't exist then". If
      `composition.coarsened` is true, the step was widened to stay bounded — for finer, narrow the window.
    • NEWS-AWARE: fuse `stock_impact` / `news_feed`/`search_news` on the holdings' `theme` paths for the
      WHY (⚠️ news only covers 2026+; portfolio history goes back to inception, further than news).
    • Facts, not advice. Observe; do NOT tell them to buy/sell/rebalance/time — hand the judgment back."""
    return mdx().portfolio_context(portfolio_id, from_=from_, to=to, window=window, snapshots=snapshots)

# WHICH surface authored a note — read from the MCP `clientInfo` handshake, NEVER a model argument (an
# LLM must not be trusted to self-report provenance). Known clients → a stable token; unknown → a safe slug.
_AGENT_ALIASES = (("claude", "claude"), ("chatgpt", "chatgpt"), ("openai", "chatgpt"),
                  ("cursor", "cursor"), ("marketdx", "marketdx-web"))

def _client_agent(ctx: Optional[Context]) -> Optional[str]:
    try:
        raw = (ctx.session.client_params.clientInfo.name or "").strip().lower()
    except Exception:
        return None
    if not raw:
        return None
    for needle, token in _AGENT_ALIASES:
        if needle in raw:
            return token
    slug = "".join(c if (c.isalnum() or c in "._-") else "-" for c in raw)[:40].strip("-")
    return slug or None

@mcp.tool(title="Save Note", annotations=_WRITE)
def write_note(subject: str, body: str, summary: Optional[str] = None,
               note_type: Optional[str] = None, category: Optional[str] = None,
               tags: Optional[List[str]] = None,
               stocks: Optional[List[str]] = None,
               mentioned_stocks: Optional[List[str]] = None,
               megatrend_ids: Optional[List[int]] = None,
               gics: Optional[List[str]] = None,
               portfolio_id: Optional[int] = None,
               ctx: Context = None) -> dict:
    """🔴 WRITE — save a NOTE to the user's account (this PERSISTS data; it is NOT a read/lookup). Typical
    flow: FIRST give the user your complete answer as usual, THEN — as the final step of the turn — call
    `write_note` once to keep it.

    CONTENT:
      • `subject` — a short title you compose (≤200 chars).
      • `body` — the substance to keep: your full answer, or a clean self-contained distillation (you are
        RE-WRITING it here, so it need not be byte-identical to what you showed — make it stand alone).
      • `summary` — a 1–2 sentence gist for scanning later.
      • `note_type` — one of `thesis` / `reference` / `snapshot` / `decision` / `watchlist`.
      • `category` — a free bucket, e.g. `research` / `portfolio` / `idea`.
      • `tags` — a few keywords for retrieval.

    ENTITY LINKS — this is what makes the note findable later by interest and joinable to the graph, so
    fill them whenever the note is about specific things. Pass what you ALREADY resolved this turn; the
    server canonicalizes and links them (and tells you what linked in the response):
      Pass the identifiers you ALREADY picked this turn (same ones you used to answer) — do NOT re-resolve:
      • `stocks` — the MarketDX ticker(s) this note is ABOUT (its subjects) — the one you PICKED from
        `find_stock` (e.g. `005930.KO`); a bare US symbol (`AAPL`) also works.
      • `mentioned_stocks` — tickers merely referenced, not the focus.
      • `megatrend_ids` — the megatrend node id(s) you settled on: from `find_megatrend` (returns
        {id,name,tier} candidates — YOU pick) or a theme tool's output (`theme_pulse` returns the resolved
        `megatrend.id`). Reuse that id — never guess a number.
      • `gics` — 6-digit GICS sector code(s), reused from a theme tool's output (`theme_pulse` → `gics_code`).
      • `portfolio_id` — if the note is about one of the user's portfolios (from `list_portfolios`).
      If you're unsure of an entity, leave it out or just name it in `tags`/`body` — anything unresolved is
      preserved verbatim, nothing is lost.

    WHEN TO SAVE — this is the investor's knowledge base; CAPTURE substantive investment content generously
    (reference/understanding, a dated market-read WITH its 'why', a thesis/decision, curated research). Value
    is realized on RETRIEVAL, so lean toward keeping. SKIP only the noise floor: chit-chat/thanks, trivial
    lookups ("what's the ticker?"), or off-topic non-investment content (save that only if explicitly asked).
    An explicit "save this / จดไว้" → always save. Otherwise, if the content is note-worthy, briefly OFFER to
    keep it — don't nag on every turn, and don't save pure filler. Owner-scoped. Returns `{id, created_at,
    linked}` where `linked` confirms what was tied to the graph (resolved ids + any `unresolved` names)."""
    payload = {k: v for k, v in {"subject": subject, "body": body, "summary": summary,
                                 "type": note_type, "category": category, "tags": tags,
                                 "stocks": stocks, "mentioned_stocks": mentioned_stocks,
                                 "megatrend_ids": megatrend_ids, "gics_codes": gics,
                                 "portfolio_id": portfolio_id,
                                 "agent": _client_agent(ctx)}.items() if v is not None}
    r = mdx()._http._client.post("/v1/notes", json=payload)
    if r.is_success:
        return r.json()
    try:
        j = r.json(); msg = j.get("error") or r.text; note = j.get("note")
    except Exception:
        msg = r.text or f"HTTP {r.status_code}"; note = None
    raise ValueError(f"save failed: {msg}{' — ' + note if note else ''}")

@mcp.tool(title="My Notes", annotations=_RO)
def query_notes(q: Optional[str] = None, stock: Optional[str] = None, theme: Optional[str] = None,
                gics: Optional[str] = None, tag: Optional[str] = None, note_type: Optional[str] = None,
                since: Optional[str] = None, limit: Optional[int] = None) -> dict:
    """Recall the USER'S OWN saved notes — their personal investment knowledge base (owner-scoped, only
    ever their notes). Two combinable ways:
      • SEMANTIC recall via `q` — natural language ("what did I say about foundry manufacturing?"); results
        are ranked by MEANING with a `similarity` score (cross-language OK).
      • Structured filters: `stock` (a ticker → their notes about it), `theme` (a sector/trend NAME →
        resolved to the megatrend, subtree included), `gics` (6-digit code), `tag`, `note_type`
        (thesis/reference/snapshot/decision/watchlist), `since` (e.g. '30d').
    Returns note SUMMARIES + linked entities + `similarity` — NOT the full body (call `get_note(id)` for
    that). `limit` default 10 (max 50).
    🔴 FUSE personal + live: when the user asks about something they've likely noted, pair this with the
    live read — e.g. `asset_pulse(NVDA)` AND "your NVDA thesis from last week said …". That personal-
    knowledge + live-graph combination is the whole point of the notes layer."""
    params: dict = {}
    if q:
        params["q"] = q
    if stock:
        params["stock"] = stock
    if theme:
        try:
            hits = resolve_themes([theme]).get(theme) or []
            if hits:
                params["megatrend"] = hits[0]["id"]
        except Exception:
            pass
    if gics:
        params["gics"] = gics
    if tag:
        params["tag"] = tag
    if note_type:
        params["type"] = note_type
    if since:
        params["since"] = since
    params["limit"] = _lim(limit, default=10, ceiling=50)
    return mdx()._get("/v1/notes", params).data

@mcp.tool(title="Read Note", annotations=_RO)
def get_note(note_id: int) -> dict:
    """The FULL saved note (including its `body`) by id — owner-scoped. Use after `query_notes` when you
    need the complete content, not just the summary."""
    return mdx()._get(f"/v1/notes/{note_id}", {}).data

# NB: portfolio_card / portfolio_nav IMAGE tools (rendered PNG via /v1/portfolios/:id/{card,nav}) were
# built + removed 2026-07-17 — Claude custom connectors DON'T render inline tool-result images (same gate
# as MCP Apps UI), so a 120KB PNG just burned context without displaying. The API endpoints stay; re-add
# these tools if a client gains connector-image rendering or via a Connector Directory listing.

# ── COMPOSITE tools (whole multi-step pipeline server-side, ONE call) ─────────
# Composites bundle several endpoints → keep each row APPROPRIATELY light so the bundle stays
# context-friendly (the raw impact row carries a huge `raw` blob; options a big per_bucket audit).
_ART_KEEP = ("title", "brief_text", "url", "publisher", "published_at", "impact", "news_types",
             "impact_score", "dup_count")
def _slim_articles(rows, n=6):
    """Keep only the narratable fields of an impact-article row (drop the big `raw` blob + ids) + cap N."""
    return [{k: a[k] for k in _ART_KEEP if k in a} for a in (rows or [])[:n]]

_REL_KEEP = ("name", "symbol", "exchange", "country", "gic_code")
def _slim_relations(rows, n=5):
    """Keep just enough of a competitor/peer to judge sector-overlap (name/symbol/exchange/country)."""
    return [{k: c[k] for k in _REL_KEEP if c.get(k) is not None} for c in (rows or [])[:n]]

def _brief_slim(b):
    """Keep a brief's breadth SUBSTANCE (pulse summary + winners/losers + top_stories) for a multi-angle
    bundle; drop the heavy chart-series + aspect_heatmap + top_entities/top_assets (get the full brief via
    `brief`/`theme_summary`)."""
    if not isinstance(b, dict):
        return b
    out = {k: b[k] for k in ("applied_scope", "window", "winners", "losers", "top_stories") if k in b}
    p = b.get("pulse") or {}
    out["pulse"] = {k: p[k] for k in ("story_count", "net_direction", "pos_share") if k in p}
    return out

def _slim_context(ctx: dict) -> dict:
    """Drop CHART-only / redundant bulk from a portfolio_context for the pulse bundle — the analytical
    substance (summary, performance, attribution, positions, allocation, concentration, flags, meta,
    closed_positions) stays; only the raw nav sparklines, per-position value_trend, and point-in-time
    `composition` snapshots go (call `portfolio_context` if you need those)."""
    c = dict(ctx)
    c.pop("composition", None)
    for blk in ("lifetime", "recent", "window"):
        if isinstance(c.get(blk), dict):
            c[blk] = {k: v for k, v in c[blk].items() if k not in ("nav", "nav_trend")}
    if isinstance(c.get("positions"), list):
        c["positions"] = [{k: v for k, v in p.items() if k != "value_trend"} for p in c["positions"]]
    return c

@mcp.tool(title="Asset Pulse", annotations=_RO)
def asset_pulse(ticker: str, window: Optional[str] = None, limit: Optional[int] = None,
                style: str = "plain") -> dict:
    """⭐ THE tool for "how is <ticker> doing right now?" — gathers EVERY lens in ONE call so the answer
    is never half-informed (the whole point: you decide ONCE, the server guarantees completeness). Fans
    out server-side, in parallel, to:
      • `price` — the LEVEL + how it's moving: windowed changes (1w→1y), 52-week range, drawdown from the
        peak, realized-vol percentile (is today's vol high vs its OWN year), volume conviction — digested
        with plain-language `*_read` labels (split/div-adjusted). The number that makes news+options actionable.
      • `impact` — the ticker's news→impact feed (what moved it + direction + aspect + WHY; == stock_impact)
      • `options` — the US options market's positioning (fear/greed via skew, put/call lean, dealer-gamma
        stability, max-pain pinning, notable expiries; == options_sentiment)
      • `relationships` — competitors + peers (== relationships) → tells you if a move is SECTOR-WIDE
        (rivals/peers moving too) or IDIOSYNCRATIC (this name only)
    PREFER THIS over calling stock_impact / options_sentiment separately for any "how is X doing / what's
    up with X / X update" ask — it guarantees BOTH lenses are present; use the individual tools only to
    DRILL into one afterwards. `ticker` = a company (`AAPL` / `NVDA.US`) or a market INDEX via its liquid
    ETF proxy (S&P 500→`SPY`, Nasdaq 100→`QQQ`, Dow→`DIA`, Russell 2000→`IWM`, 20y UST→`TLT`, Gold→`GLD`).
    `window` = 7d/30d/90d/180d/1y/mtd/qtd/ytd — scopes the news recency. Then SYNTHESIZE a multi-lens read:
    the sharpest insight is often where NEWS and OPTIONS POSITIONING **diverge** (e.g. calm news but
    options paying up for downside). Narrate `options` from ITS `_guide` (read+because, no recompute, no
    cross-asset O/S·IV compare, verdict is yours). `options.covered=false` (non-US / not in the ~547) →
    answer from `impact` and say options isn't available; never fabricate positioning. If the user HOLDS
    the ticker, tie the read to their position (facts, not advice)."""
    cli = mdx()  # bind the caller's client in THIS thread — the contextvar key isn't set inside workers
    frm = _win(window)
    def _impact():
        try:
            rows = _ser(cli.stock(ticker).news(collapse=True, from_=frm, limit=_lim(limit, default=6)).to_list())
            return {"articles": _slim_articles(rows, 6)}
        except Exception as e:  # unknown ticker / no impact rows — degrade, don't kill the bundle
            return {"error": str(e), "articles": []}
    def _options():
        try:  # single asset → return options FULL (it's only ~10KB; keeps _guide.audience so the plain-
            return cli._get(f"/v1/options/{ticker}/sentiment", {"style": style}).data  # language mandate survives
        except NotFoundError as e:
            return {"covered": False, "note": str(e)}
        except Exception as e:
            return {"covered": False, "note": f"options lookup failed: {e}"}
    def _relations():
        try:
            ref = cli.stock(ticker)
            return {"competitors": _slim_relations(_ser(ref.competitors(limit=5).to_list())),
                    "peers": _slim_relations(_ser(ref.peers(limit=5).to_list()))}
        except Exception as e:
            return {"error": str(e), "competitors": [], "peers": []}
    def _price():
        try:  # the LEVEL lens — digested, already-narrated price features (1w→1y changes, 52w range,
            return cli._get(f"/v1/stocks/{ticker}/prices", {}).data  # drawdown, realized-vol percentile, volume conviction; *_read labels)
        except NotFoundError as e:
            return {"note": f"no price history: {e}"}
        except Exception as e:  # endpoint not shipped yet / lookup failed → degrade, don't kill the bundle
            return {"note": f"price unavailable: {e}"}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        fi, fo, fr, fp = ex.submit(_impact), ex.submit(_options), ex.submit(_relations), ex.submit(_price)
        impact, options, relations, price = fi.result(), fo.result(), fr.result(), fp.result()
    return {
        "ticker": ticker, "window": window or "recent",
        "price": price, "impact": impact, "options": options, "relationships": relations,
        "_guide": ("Synthesize a MULTI-LENS read — do NOT answer from one lens. `price` = the LEVEL + how "
                   "it's moving (windowed changes, how far below the 52w peak = `drawdown_from_52w_high_pct`, "
                   "is today's vol high vs its OWN year = `realized_vol_percentile_1y`, accumulation vs "
                   "distribution = `up_down_volume_ratio_1mo`); `impact` = what the news did (+ why); "
                   "`options` = how the options market is positioned; `relationships` = is the move "
                   "SECTOR-WIDE (peers/rivals moving too) or IDIOSYNCRATIC? Lead with where the lenses AGREE "
                   "or DIVERGE (divergence is the insight — e.g. strong news but price −14% from the peak). "
                   "QUOTE price `*_read` labels directly (pre-computed, don't re-derive). 🔴 EXPLAIN "
                   "`options` FOR A NON-EXPERT (follow the options payload's own `_guide.audience`) — "
                   "translate EVERY options term (put/call, IV, gamma, skew, max-pain, O/S) into plain "
                   "everyday words, keep a number only if it helps a layperson; do NOT dump jargon. If "
                   "`options.covered` is false, answer from `impact`+`price`; `price.note` present → say "
                   "price isn't available; never fabricate."),
    }

@mcp.tool(title="Stock Prices", annotations=_RO)
def stock_prices(ticker: str, to: Optional[str] = None, from_: Optional[str] = None) -> dict:
    """Price context for a tradable ticker (stock / ETF / index-ETF / forex / crypto / commodity), split &
    dividend-ADJUSTED — a DIGESTED read, NOT a raw bar series: windowed changes (1w/1mo/3mo/ytd/1y), 52-week
    range + `drawdown_from_52w_high_pct` (how far below the peak), realized vol + `realized_vol_percentile_1y`
    (is today's vol high vs its OWN year), trend vs SMA50/200, volume conviction (`up_down_volume_ratio_1mo`,
    rvol). `*_read` fields are ready plain-language labels — quote them, don't re-derive. Reach for this on
    "is it cheap/extended / how has it moved / why is it dropping" — the LEVEL that makes a news+options read
    actionable (or use `asset_pulse` to get price + news + options in one). `to` = as-of date (point-in-time,
    YYYY-MM-DD, features as of that day); `from_` bounds history (narrowing below ~1y nulls the long windows).
    For a SECTOR/theme (not one ticker) use `theme_pulse`, not this."""
    return mdx()._get(f"/v1/stocks/{ticker}/prices", {"to": to, "from": from_}).data

@mcp.tool(title="Batch Stock Prices", annotations=_RO)
def stock_prices_batch(tickers: List[str], to: Optional[str] = None, from_: Optional[str] = None) -> dict:
    """The same digested price context for UP TO 50 tickers in ONE call — a watchlist / cohort snapshot
    ("which of these names are most extended, or deepest in drawdown"). Returns `results` (in input order)
    + `unresolved` (unknown / no-price-history tickers). `to`/`from_` as in `stock_prices`."""
    return mdx()._get("/v1/stocks/prices", {"tickers": ",".join(tickers), "to": to, "from": from_}).data

def _options_brief(o: Optional[dict]) -> dict:
    """Compact an options-sentiment payload for a bundle: keep positioning_score + flow + per-horizon
    metrics (IV/gex/pcr/skew/max_pain, ~0.7KB) + read/because + slim key_dates; DROP only the big
    `per_bucket` audit block (~4.6KB → get it from `options_sentiment`) + the redundant top-level `_guide`
    (the composite carries its own), so it stays context-light even across N holdings."""
    if not o or o.get("covered") is False:
        return {"covered": False, "note": (o or {}).get("note")}
    s = o.get("sentiment") or {}
    hz = {k: {"positioning_score": v.get("positioning_score"),
              "metrics": v.get("metrics"),   # the raw numbers (IV/gex/pcr/skew/max_pain) — only ~0.7KB
              "signals": [{"read": g.get("read"), "because": g.get("because")}
                          for g in (v.get("signals") or [])]}
          for k, v in (s.get("horizons") or {}).items()}
    return {"positioning_score": s.get("positioning_score"), "stale": o.get("stale"),
            # audience = the style=plain narration mandate ("explain for a non-expert, no jargon"). KEEP it
            # — dropping it (with the rest of _guide) is what made the LLM narrate options technically.
            "audience": (s.get("_guide") or {}).get("audience"),
            "flow": s.get("flow"), "horizons": hz,
            "key_dates": [{"expiry": d.get("expiry"), "dte": d.get("dte"), "read": d.get("read"),
                           "because": d.get("because")} for d in (s.get("key_dates") or [])]}

@mcp.tool(title="Portfolio Pulse", annotations=_RO)
def portfolio_pulse(portfolio_id: int, top_n: int = 3, window: Optional[str] = None) -> dict:
    """⭐ THE tool for "how is my portfolio doing?" / "how is my <holding> doing?" — the owner-scoped
    portfolio snapshot FUSED with the market lenses on its biggest positions, in ONE call. Returns
    `context` (holdings / performance / attribution / composition / flags — == portfolio_context) PLUS
    `holdings_pulse`: for the TOP-`top_n` positions by value, a COMPACT news→impact + options-positioning
    read, so you can explain WHAT is happening to the book, not just its numbers. Prefer this over
    `portfolio_context` alone whenever the user asks how the portfolio (or a position in it) is DOING;
    use `portfolio_context` for pure numbers/analytics (a period's sharpe, attribution, composition).
    Drill into any single holding with `asset_pulse(symbol)` for full detail. `top_n` default 3 (cap 5 —
    each holding adds credits + latency). `window` scopes the news recency. `portfolio_id` from
    `list_portfolios`; 404 if not the user's. Analyze as an analyst (marketdx://policy PORTFOLIO)."""
    cli = mdx()  # bind the caller's client in THIS thread (contextvar not set inside workers)
    frm = _win(window)
    ctx = cli.portfolio_context(portfolio_id)  # owner-scoped; surfaces 404 if not the user's
    nav = (ctx.get("summary") or {}).get("nav") or 0
    positions = [p for p in (ctx.get("positions") or []) if p.get("symbol")]
    top = sorted(positions, key=lambda p: abs(p.get("value") or 0), reverse=True)[:max(1, min(top_n, 5))]
    def _holding(p):
        sym = p["symbol"]
        try:
            imp = _slim_articles(_ser(cli.stock(sym).news(collapse=True, from_=frm, limit=3).to_list()), 3)
        except Exception as e:
            imp = {"error": str(e)}
        try:
            opt = _options_brief(cli._get(f"/v1/options/{sym}/sentiment", {"style": "plain"}).data)
        except NotFoundError:
            opt = {"covered": False}
        except Exception as e:
            opt = {"covered": False, "note": str(e)}
        w = round((p.get("value") or 0) / nav * 100, 1) if nav else None
        return {"symbol": sym, "name": p.get("name"), "weight_pct": w, "side": p.get("side"),
                "impact": imp, "options": opt}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(5, len(top) or 1)) as ex:
        holdings_pulse = list(ex.map(_holding, top))
    return {
        "context": _slim_context(ctx), "top_n": len(top), "holdings_pulse": holdings_pulse,
        "_guide": ("Analyze as a research analyst (marketdx://policy PORTFOLIO): LEAD with context.flags / "
                   "the dominant concentration / drawdown; explain the return from context…attribution; "
                   "THEN use holdings_pulse to say WHAT news + options positioning is driving the biggest "
                   "positions (tie each to its weight_pct). Narrate options from read/because; "
                   "covered=false → skip options for that name. Facts, not advice — hand the call back."),
    }

@mcp.tool(title="Theme Pulse", annotations=_RO)
def theme_pulse(query: str, window: str = "30d") -> dict:
    """⭐ THE tool for "how is <a SECTOR / INDUSTRY / THEME> doing?" (semiconductors, tech, energy, banks,
    AI, clean energy, …) — a concept that spans MULTIPLE INDEPENDENT taxonomies. It resolves the concept
    and fans out, in ONE call, to EVERY angle that applies (skipping ones that don't), each a SEPARATE
    lens over a DIFFERENT dataset — present them separately, do NOT merge:
      • `theme` — the MarketDX MEGATREND cohort (our proprietary trend tree) → a brief (pulse / winners /
        losers / top stories). Membership = companies EXPOSED to the trend (can cross GICS sectors).
      • `gics` — the standard GICS SECTOR cohort → a brief. A DIFFERENT membership (strict sector
        classification) → genuinely different winners/losers than the megatrend.
      • `asset` — the tradable ETF's OPTIONS positioning (SMH/XLK/GLD/…) — fear-greed / dealer-gamma.
    Applicable angles VARY: 'semiconductors' → all 3; 'gold' → asset only (GLD, no GICS/megatrend for a
    commodity); 'AI' → theme (no single AI ETF covered). `skipped` lists the angles that didn't resolve.
    ⚠️ Use `asset_pulse(ticker)` for a SINGLE company/ETF; use `theme_pulse` for a sector/theme CONCEPT.
    `window` = 7d/30d/90d/1y/…"""
    cli = mdx()
    # ── resolve the concept into its (up to 3) angle keys — skip any that don't resolve ──
    mt = _to_node(query)
    megatrend = mt if isinstance(mt, int) else None
    gics = etf = None
    try:
        r = _deepseek(
            "Map a market concept to standard classifications. Return JSON "
            '{"gics": <best-matching GICS sector/industry code as a digit string, or null>, '
            '"etf": <the ONE best ticker from the provided covered list, or null>}. '
            "gics = the standard GICS code (e.g. semiconductors->'453010', energy->'10', banks->'4010', "
            "software->'451030'); null if the concept is NOT a GICS sector/industry (a single commodity "
            "like gold, a cross-sector trend like AI, a country). etf = the ticker whose theme matches the "
            "concept; null if none fits well.",
            f"Concept: {query}\nCovered ETFs: " + ", ".join(f"{k}={v}" for k, v in _COVERED_ETFS.items()),
            0.0)
        g = str(r.get("gics") or "").strip()
        gics = g if (g.isdigit() and 2 <= len(g) <= 8) else None
        etf = r.get("etf") if r.get("etf") in _COVERED_ETFS else None
    except Exception:
        pass

    def _theme():
        if megatrend is None:
            return None
        try:
            return {"megatrend": _node_out(megatrend), "brief": _brief_slim(cli.brief(megatrend=megatrend, window=window))}
        except Exception as e:
            return {"error": str(e)}
    def _gics():
        if not gics:
            return None
        try:
            return {"gics_code": gics, "brief": _brief_slim(cli.brief(gics=gics, window=window))}
        except Exception as e:
            return {"error": str(e), "gics_code": gics}
    def _asset():
        if not etf:
            return None
        try:
            return {"etf": etf, "concept": _COVERED_ETFS.get(etf),
                    "options": _options_brief(cli._get(f"/v1/options/{etf}/sentiment", {"style": "plain"}).data)}
        except NotFoundError:
            return {"etf": etf, "covered": False}
        except Exception as e:
            return {"error": str(e)}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:
        ft, fg, fa = ex.submit(_theme), ex.submit(_gics), ex.submit(_asset)
        angles = {k: v for k, v in {"theme": ft.result(), "gics": fg.result(), "asset": fa.result()}.items()
                  if v is not None}
    return {
        "query": query, "window": window, "angles": angles,
        "skipped": [k for k in ("theme", "gics", "asset") if k not in angles],
        "_guide": ("Present each angle SEPARATELY — they are DIFFERENT cohorts: `theme` = MarketDX "
                   "megatrend membership (trend-exposed, may cross sectors); `gics` = standard GICS sector "
                   "classification (different winners/losers); `asset` = the tradable ETF's options "
                   "positioning. Do NOT merge them. `skipped` angles don't apply to this concept. Lead "
                   "with the sharpest cross-angle read (e.g. where the megatrend and the GICS sector "
                   "diverge, or where options positioning contradicts the news breadth). Narrate options "
                   "from its read/because for a non-expert."),
    }

@mcp.tool(title="Screen Stocks", annotations=_RO)
def screen_stocks(megatrend: Optional[str] = None, gics: Optional[str] = None,
                  country: Optional[str] = None, direction: Optional[str] = None,
                  aspect: Optional[str] = None, order_by: Optional[str] = None,
                  min_impact: Optional[int] = None, min_relevance: Optional[float] = None,
                  min_market_cap_usd: Optional[float] = None, since: Optional[str] = None,
                  from_: Optional[str] = None, to: Optional[str] = None,
                  gate: Optional[str] = None, limit: Optional[int] = None) -> dict:
    """⭐ "Which stocks in <a group> are INTERESTING / winning / losing / most-talked-about?" — the
    news-driven impact SCREENER. Ranks the companies in a scope by how the news is hitting them, so you
    can lead with the WINNERS-vs-LOSERS split, not a flat list.
      • Scope (≥1 REQUIRED — it never scans the whole universe): `megatrend` (one OR SEVERAL trend
        names/ids as csv — resolved for you in one pass, same as theme_pulse: 'foundry', 'foundry,hbm',
        '56020000'), `gics` (csv GICS prefixes from your own knowledge: '453010' semis, '2550' retail,
        '201010' aerospace/defense, '352010' biotech), `country` (csv ISO-2; for a REGION pass every
        country — Asia='CN,JP,KR,TW,HK,IN,SG'). Combine freely — "China+Taiwan foundry & HBM names" = ONE
        call: country='CN,TW', megatrend='foundry,hbm'.
      • `order_by` = `news_count` (default — most attention) | `relevance` (most central to its news) |
        `market_cap` (biggest).
      • `direction` = `pos` → winners only · `neg` → losers/at-risk only · omit → all, each with its own
        net_direction. `aspect` = keep only a channel (demand/competition/capital/…).
      • Quality floors: `min_impact` (1–5 article-importance), `min_relevance` (0–1 centrality),
        `min_market_cap_usd`, `since` ('7d'). `gate` (megatrend scope only) = `both` (default, strict:
        member AND epicenter) | `membership` (looser, more leakage).
      • TIME WINDOW: `since='7d'` = trailing N days ("this week"=7d, "this month"=30d). For a SPECIFIC past
        window use `from`/`to` (YYYY-MM-DD): "last week"→the two dates, "as of <date>"→`to`. ⚠️ per-stock
        IMPACT scoring only exists from ~2026-07-03 onward, so any window BEFORE early-July-2026 (a Q1/March
        query) returns EMPTY — say so plainly ("no impact data that far back"); do NOT present empty as
        "nothing happened".
    Each row = `{symbol, name, country, gic_code, market_cap_usd, impact:{news_count, pos, neg, ambiguous,
    net_direction, top_relevance, aspects, top_reason}}` — each row carries `market_cap_usd`, so for a
    constraint we DON'T support (e.g. "SMALL-cap only", a max size) return the cohort and filter/annotate
    from that field + your own knowledge. `direction_split` pre-tallies the cohort's winners/losers so you
    can open with it. If a scope term isn't a MarketDX taxonomy node (a niche theme like 'protein
    engineering'), map it to the nearest `gics`/`country` you CAN pass and lean on your world knowledge for
    the rest. For ONE ticker use `asset_pulse`; for a sector's overall pulse use `theme_pulse`; use THIS to
    rank the NAMES inside a group. `limit` default 10 (max 50)."""
    mt = _to_nodes(megatrend) if megatrend else None
    if not (mt or gics or country):
        return {"error": "screen_stocks needs at least one scope: megatrend (node id from find_megatrend), gics, or country."}
    params = {"megatrend": mt, "gics": gics, "country": country, "direction": direction,
              "aspect": aspect, "order_by": order_by, "min_impact": min_impact,
              "min_relevance": min_relevance, "min_market_cap_usd": min_market_cap_usd,
              "since": since, "from": from_, "to": to,
              "gate": gate, "limit": _lim(limit, default=10, ceiling=50)}
    rows = mdx()._get("/v1/stocks", params).data.get("stocks", [])
    keep = ("stock_id", "symbol", "ticker", "name", "country", "gic_code", "market_cap_usd", "impact")
    stocks = [{k: r[k] for k in keep if k in r} for r in rows]
    def _nd(r):
        return ((r.get("impact") or {}).get("net_direction")) or "n/a"
    split = {"total": len(stocks),
             "net_positive": sum(1 for r in stocks if _nd(r) == "pos"),
             "net_negative": sum(1 for r in stocks if _nd(r) == "neg"),
             "ambiguous": sum(1 for r in stocks if _nd(r) == "ambiguous")}
    return {
        "scope": {k: v for k, v in {"megatrend": mt, "gics": gics, "country": country}.items() if v},
        "order_by": order_by or "news_count", "direction": direction,
        "direction_split": split, "stocks": stocks,
        "_guide": ("LEAD with the winners-vs-losers split (`direction_split` + each row's `impact."
                   "net_direction` with its pos/neg counts), NOT a flat ranked dump. Surface any "
                   "net-NEGATIVE standouts SEPARATELY — they're the contrarian / at-risk names. For each "
                   "name explain WHY it's interesting from its `impact.top_reason` + `aspects` (the "
                   "channels), not just that it ranks high. If a name has high news_count but a large neg "
                   "count too, call it CONTESTED. Research-analyst voice — observations, not advice."),
    }

@mcp.tool(title="Find Megatrend", annotations=_RO)
def resolve_themes(terms: List[str]) -> dict:
    """🔴 The MEGATREND counterpart of `find_stock`: map trend-language ('HBM', 'foundry', 'robotaxi',
    'robotics') to the specific taxonomy node(s) — returns CANDIDATES for YOU to pick from (exactly like
    `find_stock` returns candidate tickers). May be tier-1/-2/-3; may be several for a polysemous term.
    Gazetteer first (deterministic, free), deepseek 3-tier match for the rest. Returns
    {term: [{id,name,tier},...]}. Call this to get a megatrend `id`, then REUSE the id you pick downstream
    (theme queries, `write_note`) — don't flatten or guess the number yourself."""
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
        # offline_access is REQUIRED so the client asks WorkOS for a refresh token and can renew the
        # access token silently — without it a spec-compliant client (Claude) never requests refresh
        # and must reconnect every time the ~1h access token expires. WorkOS supports it.
        "scopes_supported": ["openid", "email", "profile", "offline_access"],
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
        except Exception:  # WorkOS unreachable → minimal doc from known endpoints. Return WITHOUT
            fallback = {   # caching so a transient boot-time egress hiccup doesn't poison the cache
                "authorization_endpoint": f"{_origin(scope)}/oauth2/authorize",  # our force-offline_access proxy
                "token_endpoint": f"{_WORKOS_ISSUER}/oauth2/token",
                "registration_endpoint": f"{_WORKOS_ISSUER}/oauth2/register",
                "jwks_uri": f"{_WORKOS_ISSUER}/oauth2/jwks",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "scopes_supported": ["openid", "email", "profile", "offline_access"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
                "client_id_metadata_document_supported": True,
                "issuer": _origin(scope),
            }
            return fallback
    meta = dict(_AS_CACHE)
    meta["issuer"] = _origin(scope)   # served from our origin → issuer must be us
    # Guarantee offline_access is advertised (don't depend on WorkOS's list) so the client requests a
    # refresh token → silent renewal instead of reconnect-on-expiry.
    meta["scopes_supported"] = sorted(set(meta.get("scopes_supported") or []) |
                                      {"openid", "email", "profile", "offline_access"})
    # Point authorize at OUR proxy (below) which force-injects offline_access before forwarding to
    # WorkOS — advertising the scope isn't enough (a client, e.g. Claude, may not copy scopes_supported
    # into its authorize request → WorkOS issues no refresh token → hourly reconnect). token/jwks/
    # register still point at WorkOS (unchanged).
    meta["authorization_endpoint"] = f"{_origin(scope)}/oauth2/authorize"
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
            # Authorize proxy — force-inject offline_access so WorkOS always mints a refresh token,
            # then 302 to WorkOS's real authorize. Advertising offline_access in scopes_supported is not
            # enough: a client (e.g. Claude, whose CIMD declares no scope) may not copy it into its
            # authorize request → no refresh token → the user must reconnect every ~1h. Injecting it here
            # is client-independent. PKCE (code_challenge) is passed through untouched; the token exchange
            # still hits WorkOS directly, so the verifier check is unaffected.
            if path == "/oauth2/authorize":
                from urllib.parse import parse_qsl, urlencode
                params = dict(parse_qsl(scope.get("query_string", b"").decode(), keep_blank_values=True))
                scopes = (params.get("scope") or "").split()
                for s in ("openid", "offline_access"):
                    if s not in scopes:
                        scopes.append(s)
                params["scope"] = " ".join(scopes)
                target = f"{_WORKOS_ISSUER}/oauth2/authorize?{urlencode(params)}"
                await send({"type": "http.response.start", "status": 302,
                            "headers": [(b"location", target.encode()), (b"content-length", b"0")]})
                await send({"type": "http.response.body", "body": b""})
                return
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
