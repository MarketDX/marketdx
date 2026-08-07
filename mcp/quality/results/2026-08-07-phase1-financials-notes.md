# 2026-08-07 — Phase 1: financials interface + self-improving resolver + notes

Batches run while BUILDING the financials overhaul + notes.data. Verified via ground-truth (MCP values) and the
DB (not agent self-reports). Live rev at close: news-api `00265-n5m`, marketdx-mcp `00120-86k`.

## Batches + outcomes
| batch | what | result |
|---|---|---|
| period/fields mechanics | 11 cases via mcpcli (default digest · single-year · range · list · 5q · all · income · period-gap 2015 · >5 companies · >20 fields · limits block) | **11/11 pass** (fiscal-map 2023→2023-09; limits messages fire) |
| self-improving resolver | 6-case matrix (normal hit · data_shape+rule · data_shape no-rule · vocab · dedup-by-canonical · per-company gating) | **6/6 pass**; dedup-by-canonical holds on real agent field-name variety |
| curate→answer loop | disable rule → ask → curate → ask (real MCP) | proxy answer returns w/ reason only after curation |
| 7-case blind (interface) | digest-first · range · quarterly · non-US proxy · >5 limit · period-gap · non-equity | **7/7 behaviorally correct**; FX verified period-date-correct |
| **buyback compare ×5+4** | "5y Toyota vs Apple buybacks, who more?" | **W1**: 5/5 headlined "27×" (gross vs net). `_reminder` → 4/5 downgraded to directional. Accepted at directional. |
| **notes save (no-skill)** | save a 3-metric compare, tool-desc only | body-table **3/5**, data **2/5** — DB ground truth ≠ agent reports (**M1**) |
| **notes save (+skill)** | same, skill injected | body-table **5/5**, data **5/5**; numbers MCP→data→body all consistent |
| notes desc improvement | reframe body desc + top rule, re-measure no-skill | floor **3/5→4/5** table, **2/5→3/5** data (ceiling below skill) |
| discovery routing | "which US companies buy back a lot" | **W3 open**: agent guesses tickers / world-knowledge + verify; no screener exists |

## Shipped fixes (see issues.md)
- W2 FX-transparency `fx` block — 🟢 fixed. W4 note table-preservation (desc+skill) — 🟢 fixed.
- W1 basis-mismatch `_reminder` — 🟡 accepted-directional. W5 history-depth — 🟡 accepted+communicated.
- W3 discovery routing — 🔴 open (gate proposed, not built).
- Client-JSON `data` dropped → markdown source + offline deepseek extraction (placeholder). Cost measured ~0.5–2.5 satang/note.

## Not yet tested (for Phase 2 — pull from question-bank.md)
Compound cross-source (F), concept auto-save (E), non-equity absences (H25–27), data-bug honesty (AIG, W-G22),
recall+fuse (I30), bank/insurer line-shapes (C10), trade/macro ripple (F19–20).
