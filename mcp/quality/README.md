# MarketDX MCP — quality testing

Durable home for MCP quality testing: the method, a diverse question bank, dated result logs, and a
weaknesses tracker. Goal: probe the MCP the way real investors use it, find weaknesses, fix them at the
RIGHT layer, and prove the fix with re-measurement — without re-learning the same lessons every time.

## Folder layout
- `README.md` — this: method + how to run.
- `question-bank.md` — the diversity matrix + concrete questions tagged by axis + expected behavior.
- `issues.md` — weaknesses tracker (open / fixed / accepted), each with root-cause + which layer fixed it.
- `results/` — one dated file per test batch (`YYYY-MM-DD-<batch>.md`): what was asked, ground-truth check, grade.
- `harness/mcpcli.py` — minimal real MCP client (fresh initialize per call). `set MDX_TEST_BEARER=<test key>`.

## Method — the rules (hard-won; don't skip)
1. **Fresh agent = real MCP client.** Each test: a new agent runs `mcpcli list` (tools/list) → gets a NATURAL
   question → decides the tool(s)+args ITSELF. No coaching, no naming the tool. (Canonical: `docs/how-to-run-mcp-test.md`.)
2. **Grade PROCESS + OUTPUT.** Process = right tool, efficient (# calls), no brute-force/guessing. Output =
   correct, honest, well-caveated, no fabrication.
3. **Verify against GROUND TRUTH, not the agent's self-report.** Agents mis-report what they did (measured:
   note self-reports said "saved a table + data" but the DB showed 2/5 didn't). Check the actual payload / DB row.
4. **≥5 runs per scenario → measure a distribution, not one run.** A 1-in-5 failure = a 20% error rate. Single
   runs hide it (the FX-confusion + gross-vs-net error only showed up across repeats).
5. **Keep prompts NATURAL and hold them CONSTANT when A/B-ing.** Don't prime the very thing you measure (we once
   told the agent to "state a ratio" and then measured ratios — contaminated). Change ONE variable at a time.
6. **Test both arms: tool-desc-only (floor) vs +skill (reliability).** Field/tool descriptions are best-effort
   (~60–80%); the skill is the layer that reaches ~100%. Measure both so you know which lever moved.

## Fix loop (test → root-cause → right layer → re-measure)
1. On failure, classify the ROOT CAUSE: `tool-framing` (server asserts too much) · `client-analysis` (LLM
   judgment) · `data-bug` · `routing-gap` · `capability-gap`.
2. Fix at the RIGHT layer, most-robust first:
   `server-deterministic` > `API-response note` (ships with the data, unavoidable) > `tool-desc` > `skill` > `accept-limit`.
3. **Generalize, don't overfit** — one rule per failure CLASS, not a caveat per example (thousands of them).
4. Re-measure the SAME scenario (≥5 runs) → confirm the error rate dropped AND nothing regressed.
5. Update `issues.md` (status + the layer that fixed it) and drop a `results/` entry.

## How to run one test
```bash
export MDX_TEST_BEARER=<test-account key>      # e.g. the fin-mcp-test account
# spawn a fresh agent (Claude sub-agent) told ONLY: the mcpcli usage + the natural question, no tool hints.
# then verify: numbers vs `mcpcli call financials …` ground truth; notes/writes vs the DB row.
```
`fin-mcp-test` account (uid `XhnjPSM9…`) is disposable — safe to write test notes/trades there and prune.
