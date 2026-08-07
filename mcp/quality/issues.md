# MCP weaknesses tracker

Living log of weaknesses found by testing. Each: root-cause class + the layer that fixed it (or why accepted).
Status: 🔴 open · 🟡 mitigated/accepted · 🟢 fixed+verified · 📋 method note.

Root-cause classes: `tool-framing` (server asserts too much) · `client-analysis` (LLM judgment) · `data-bug` ·
`routing-gap` · `capability-gap` · `presentation` · `method`.
Fix layers (most-robust first): `server-deterministic` > `API-note` > `tool-desc` > `skill` > `accept-limit`.

---

## Found in Phase 1 (financials + notes), 2026-08-07

### 🟡 W1 — cross-company compare on MISMATCHED basis (gross vs net)
"5y Toyota vs Apple buybacks → who more?" → **5/5** headlined "Apple ~27×" comparing Apple's GROSS `buybacks`
to Toyota's NET `net_stock_issuance` proxy — not like-for-like; the multiple is invalid (direction is fine).
- root-cause: `client-analysis` (LLM compares two differently-named metrics anyway; it footnotes the caveat but
  still headlines the ratio). NOT tool-framing — verified: removing the proxy rule (arm A) gave the SAME result
  because the agent self-finds `net_stock_issuance` from `available_fields`. NOT a labeling gap — payload labels
  the fields distinctly + `resolved_via_rule` explains it.
- fix: `API-note` — an always-on `_reminder` ("before dividing figures, confirm same metric + same basis; a
  proxy is a different metric; don't headline a cross-company ratio on mismatched bases"). Measured: moved
  "hard 27× as fact" → "directional, not precise" in 4/5.
- status: **ACCEPTED at "directional + caveat"** (ran: รับได้). Did NOT chase "refuse-when-invalid" or a
  per-proxy caveat (overfit — thousands of cases). NOT reached: compare on common basis (net-vs-net) = 0/5.
- ⚠️ generalizes to: consolidated-vs-segment, trailing-vs-point-in-time, currency, fiscal-period mismatch.

### 🟢 W2 — FX magnitude looks "100× wrong"
1/5 agents saw a JPY→USD converted value (~150× smaller than native) and doubted it as a bug → wasted a re-fetch.
- root-cause: `presentation` (payload showed only the shrunk USD value; nothing to verify against).
- fix: `server-deterministic` — added an `fx` block (native currency + the exact per-period rate used) so the
  conversion is self-verifiable. Deployed. (FX math itself was correct — period-date rates.)
- status: **FIXED.**

### 🔴 W3 — discovery / ranking routed to the wrong tool
"Which US companies buy back a lot?" → agent brute-forced `financials` with GUESSED tickers (a discovery/rank
question, but `financials` only READS known tickers).
- root-cause: `routing-gap` + `capability-gap` — no buyback/metric screener exists (`screen_stocks` has no
  buyback dimension; `financials` can't rank a universe). Best agents used world-knowledge candidates + verified
  + flagged "not exhaustive"; worst brute-forced random tickers.
- fix (PROPOSED, not built): `tool-desc` + `skill` negative gate — "financials READS supplied tickers; it does
  NOT discover/rank a universe; never guess tickers. For 'which/top companies by X' → news (events) / screener,
  then financials to read the shortlist." (Real capability = a metric screener; bigger, data-dependent.)
- status: **OPEN.**

### 🟢 W4 — notes flattened a table into prose (+ dropped the machine copy)
Save a table answer → 2/5 (no-skill) saved the body as PROSE, losing the table.
- root-cause: `tool-framing` — the write_note docstring's "you are RE-WRITING it / distillation" invited prose.
- fix: reframed `body` desc ("distill = trim wording, NOT collapse a table"; use ABSOLUTE headers) + a top rule.
  Measured floor 3/5 → 4/5. `skill` (marketdx-notes format rule) → **5/5**.
- status: **FIXED** (desc = floor ~80%, skill = reliability). Client-supplied JSON `data` was DROPPED (unreliable
  ~3/5, fiddly); decision → keep markdown as source, extract `data` OUT-OF-BAND (deepseek, placeholder in
  `note.rs::extract_note_data`). `notes.data` jsonb column kept.

### 🟡 W5 — history depth ~4–5 years ("5 years" returns 4)
- root-cause: `capability-limit` (Yahoo standard-feed depth; EDGAR for more = custom-taxonomy trap, rejected).
- fix: `accept-limit` + communicate — top-level `limits.history` + `period_unavailable` note for an out-of-range
  absolute year. Verified: agents relay it, don't infer zero.
- status: **ACCEPTED + communicated.**

## Found in Phase 2 batch 1, 2026-08-07

### 🟢 W6 — `bond_pulse` free-text query resolves to the WRONG country (FIXED)
`bond_pulse({query:"US 10Y"})` → returns the **German (DE)** curve (`country: DE`), not the US curve. A client
that doesn't notice gets German yields for a US question = silent wrong answer. (The test agent caught it and
worked around via `find_stock → US-10Y.GB → asset_pulse`.)
- root-cause (FOUND): `find_stock('US 10Y')` top match = **`DE-US-10Y.SPREAD`** ("Germany–US 10Y Spread",
  domicile **DE**, score **1.0**) — its name contains the literal "US 10Y", so it out-scores `US-10Y.GB`
  ("United States Government Bond 10Y", 0.95, no literal "US"). bond_pulse (server.py ~L1812) then does
  `iso = (bond or ms[0]).domicile` → picks DE from that match → builds the German curve. Two layers:
  (1) SEARCH — a SPREAD instrument whose name embeds a country hijacks a country query; (2) bond_pulse country-
  pick doesn't filter `.SPREAD` or honor the query's country token, and reads `domicile` instead of the `.GB`
  ticker prefix.
- fix (PROPOSED, not built) — do the tractable bond_pulse-side guard: (a) EXCLUDE `.SPREAD` when picking the
  curve country; (b) derive ISO from the `.GB` ticker PREFIX (`US-10Y.GB`→`US`), not `domicile`; (c) if the
  query has a country token, prefer the `.GB` whose prefix matches. ⚠️ before finalizing, verify `US-10Y.GB` IS
  in the `asset_class=bond` candidate list (if the search drops it entirely, the search side needs a fix too).
- fix (SHIPPED, mcp rev 00121-4xj): `bond_pulse` curve-country now derives ISO by priority — (1) a country word
  in the query (`_COUNTRY_KW`: us/germany/jgb/gilt/…), (2) a clean `.GB`/`.MM` ticker's ISO PREFIX (skipping
  `.SPREAD`), (3) a non-spread match's domicile. Builds the curve from the ISO deterministically, so it works
  even if `US-10Y.GB` isn't in the match list. Didn't touch search ranking (the spread still scores 1.0, but
  it no longer drives the country).
- verified: US 10Y → US ✅ (was DE) · US yield curve → US · Germany 10Y → DE · JGB 2Y → JP · SOFR → rate (no regression).
- status: **🟢 FIXED + verified.**

## Method notes (baked into README)
- 📋 M1 — **agent self-reports are unreliable**; verify the DB row / actual payload (W4 was caught only this way).
- 📋 M2 — **harness contamination**: we once told the agent to "state a ratio" then measured ratios. Keep prompts
  natural; hold constant when A/B-ing; change one variable.
- 📋 M3 — **measure a distribution (≥5 runs)**; a 1/5 fail (W2) = 20% and single runs hide it.
