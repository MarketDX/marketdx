#!/usr/bin/env python3
"""
Load the MarketDX sample and walk every angle from the README — then go live.

    python3 examples/loader.py                              # analyze locally (no key)
    MARKETDX_KEY=avn_live_... python3 examples/loader.py    # + one live API call at the end

Pure stdlib. The sample is a TASTE — the last step shows the same shape, live, from the API.
"""
import csv, json, os, collections, urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
def load(name): return list(csv.DictReader(open(ROOT / "data" / name)))
def _group(rows, key):
    g = collections.OrderedDict()
    for r in rows:
        g.setdefault(r[key], []).append(r)
    return g

core = load("impact-signals.csv")
print(f"loaded {len(core):,} signal rows  ·  "
      f"{len({r['title'] for r in core}):,} events  ·  "
      f"{len({r['entity_ticker'] for r in core if r['entity_ticker']})} listed entities\n")

# 🛢️ Asset-class focus — same table, filtered by entity_type
print("ASSET-CLASS FOCUS (slices of the one core table)")
for t in ("commodity", "forex", "crypto"):
    s = [r for r in core if r["entity_type"] == t]
    top = collections.Counter(r["entity_ticker"] for r in s).most_common(5)
    print(f"  {t:10} {len(s):4} signals  top: {', '.join(k for k,_ in top)}")

# 🌍 Macro / cross-asset — one event touching 3+ asset classes
by_evt = collections.defaultdict(set)
for r in core:
    if r["entity_type"] in ("stock", "commodity", "forex", "crypto"):
        by_evt[r["title"]].add(r["entity_type"])
xasset = [t for t, a in by_evt.items() if len(a) >= 3]
macro = [r for r in core if r["aspect"] in ("monetary", "tariff", "geopolitics")]
print(f"\nMACRO / CROSS-ASSET: {len(macro)} macro-aspect signals · "
      f"{len(xasset)} events touch 3+ asset classes")
for t in xasset[:3]:
    print(f"     {sorted(by_evt[t])}  ← {t[:56]}")

# 📈 Screener — curated winner/loser screens
print("\nSCREENER (curated 'who's winning on X')")
for pat, rows in _group(load("screener.csv"), "pattern").items():
    top = rows[0]
    print(f"  {pat:28} → {top['symbol']} ({top['news_count']} news, {top['net_direction']})  "
          f"[{rows[0]['pattern_label'][:34]}]")

# 🕸️ Relationships — news-derived rivalry graph
rel = load("relationships.csv")
comp = [r for r in rel if r["relation"] == "competitor"]
heavy = sorted(comp, key=lambda r: -int(r["weight"] or 0))[:5]
print(f"\nRELATIONSHIPS: {len(rel)} edges "
      f"({sum(r['relation']=='competitor' for r in rel)} competitor / {sum(r['relation']=='peer' for r in rel)} peer)")
for r in heavy:
    print(f"     {r['source']:9} ↔ {r['target_symbol']:8} (weight {r['weight']})")

# 🕵️ Beyond tickers — private companies
priv = load("private-impact.csv")
top = collections.Counter(r["entity_name"] for r in priv)
ripple = sum(1 for r in priv if r["impact"] == "indirect")
print(f"\nBEYOND TICKERS: {len(priv)} signals on private/off-coverage firms ({ripple} via ripple)")
for name, c in top.most_common(6):
    print(f"     {name:32} {c:3} signals")

# 🔎 Discover — semantic search: plain-English question → impact hits (incl private)
disc = load("discover.csv")
print(f"\nDISCOVER (semantic search): {len(disc)} hits across "
      f"{len({r['question'] for r in disc})} plain-English questions")
for lab, rows in _group(disc, "question").items():
    types = collections.Counter(r["entity_type"] for r in rows if r["entity_type"])
    mix = ", ".join(f"{k} {v}" for k, v in types.most_common(3))
    print(f"     {lab:26} → {mix}")

# ---- now do it LIVE ----
print("\n" + "=" * 64)
print("This was a fixed sample. The SAME shape, live, from the API:")
key = os.environ.get("MARKETDX_KEY")
url = ("https://api.marketdx.lab.ai"
       "/v1/news?megatrend=10040000&include=entities,impact&impact=indirect&limit=3")
if not key:
    print("  (set MARKETDX_KEY to run it — free tier at https://marketdx.lab.ai)")
    print(f"  curl -H 'Authorization: Bearer $MARKETDX_KEY' \\\n    '{url}'")
else:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    print(f"  live AI-Power ripple, {len(d.get('results', []))} fresh events:")
    for e in d.get("results", []):
        ents = ", ".join(x.get("ticker") or x.get("name") for x in e.get("entities", [])[:4])
        print(f"    · {e['title'][:58]}  [{ents}]")
    print("\n  → full docs & higher limits: https://marketdx.lab.ai")
