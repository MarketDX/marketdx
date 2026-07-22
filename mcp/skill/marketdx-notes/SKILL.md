---
name: marketdx-notes
description: >-
  Use whenever the user ASKS a substantive investment or finance question whose ANSWER is worth keeping —
  a concept or mechanism question (what is a P/E ratio, what is EBITDA, how does a chip foundry work, how
  is lithium produced), an analysis, a thesis, a comparison — as well as any explicit save request (save
  this / จดไว้ / เก็บโน้ต) or a request to recall past notes (what did I note about X, my thesis on Y).
  Judge save-worthiness FROM THE QUESTION up front: if answering it will produce substantive INVESTMENT /
  ECONOMIC / financial knowledge, AUTO-SAVE that answer to their notes (do not ask first). Screen OUT
  anything not investment/economic. Applies even with NO live-data lookup — a pure explanation is still
  save-worthy.
---

# Investment notes — capture & recall the user's knowledge base

The user keeps a personal investment KNOWLEDGE BASE through the mdx notes tools (`write_note`,
`query_notes`, `get_note`). Its purpose: fight fragmented knowledge — capture substantive investment
knowledge, organized + entity-linked + retrievable later, and fuse it with live reads. This behavior is
NOT gated on fetching data: even a pure concept explanation (no tool call) is worth offering to keep.

## When to SAVE  — AUTO-SAVE (do NOT ask first)
The user has OPTED IN to auto-capture: when a turn produces save-worthy investment content, just SAVE it
with `write_note` as the final step — do NOT ask "เก็บเข้าโน้ตไหม?". They can prune later. But SCREEN hard
so only investment/economic knowledge lands.

- 🔴 **Judge from the QUESTION, before you answer.** When the user asks a substantive investment/finance
  knowledge or concept question (what is a P/E ratio, what is EBITDA, how does a foundry work), or asks for
  analysis / a thesis / a comparison, recognize UP FRONT that the answer is reference knowledge worth
  keeping — answer it, then as the FINAL step SAVE it (don't just answer and move on; don't ask). Applies
  even when you answered from your own knowledge with NO tool call.
  ✅ **KNOWLEDGE COUNTS** — a reference explanation IS save-worthy (the user's research corpus);
  "regenerable" is not a reason to skip.
- **Explicit "save this / จดไว้ / เก็บโน้ต" → always save** (even if off-topic → plain note).
- 🔴 **SCREEN — save ONLY investment / economic / financial / market / company content.** If the turn is
  NOT about that — chit-chat / thanks, off-topic (movies, travel, cooking, sports, general tech unrelated
  to markets), or a TRIVIAL one-fact lookup (a ticker symbol, "what does NVDA stand for") — do NOT save,
  discard it. When unsure whether it's investment-relevant, lean toward NOT saving.
- Don't save the same thing twice in one conversation.

## How to SAVE  (`write_note`)
- 🔴 **ONE note per COHERENT topic — never cram.** A multi-topic "save everything" → call `write_note`
  once PER topic (a lithium / semiconductor / gold chat → THREE notes), because a crammed note gets tagged
  with only one topic's entities and the rest become unretrievable. A genuine comparison ("NVDA vs AMD") is
  ONE note with both as subjects.
### 🔴 RESOLVE-THEN-WRITE — a REQUIRED procedure, not a suggestion
`write_note` is the LAST step. BEFORE it, classify what the note is fundamentally about and RESOLVE its
entities — the note is findable later only by what you link now. Run these checks IN ORDER; a note may hit
more than one (link all that apply). The resolvers return CANDIDATES → **YOU pick the right one(s)** (e.g.
"bank" → Regional Banks vs Investment Banking — decide from the note's meaning); never guess a number.

1. **Specific companies?** (a read/thesis on named firms, "NVDA vs AMD") → you already resolved the
   tickers via `find_stock` while answering → pass `stocks` (subjects) / `mentioned_stocks` (referenced).
2. **An emerging TREND / technology / mechanism?** (HBM, robotaxi, lithium, rare earths, solid-state
   batteries, "how a foundry works") → call **`find_megatrend([terms])`** (send the trend words straight
   from your answer — you don't need to know the taxonomy), PICK the id(s) → `megatrend_ids`.
3. **An established INDUSTRY / SECTOR?** (retail, airlines, banking, pharma, utilities, insurance) → call
   **`find_gics([terms])`**, PICK the code(s) → `gics`. (Sectors are NOT megatrends — retail/airlines have
   no megatrend node; this is their lane.)
4. **Both a trend AND a sector?** ("AI in banking", "EVs and the auto industry") → resolve BOTH.
5. **A general concept with no specific home?** (what is P/E, EBITDA, how bonds work) → link NOTHING; put
   the keywords in `tags` + body. `find_megatrend`/`find_gics` returning `[]` CONFIRMS this — don't force a
   match. It's still found later by semantic search + tags.

Then call `write_note` with everything you resolved, plus `note_type` (thesis | reference | snapshot |
decision | watchlist) + `summary` + `tags`. Do the resolve calls FIRST; the server canonicalizes tickers→
ids, derives GICS from any stocks, and stamps provenance automatically.

🔴 **A note whose subject is a trend or a sector, saved with an EMPTY `megatrend_ids`/`gics`, is a BUG —**
it means you skipped step 2/3. The only correct empties are: a single-stock note (stocks only) or a
general concept (step 5).

## RECALL  (`query_notes` / `get_note`)
- "what did I note about X / my notes on NVDA / my thesis on foundry" → `query_notes` (semantic `q` +
  filters: `stock`, `theme`, `tag`, `note_type`, `since`). Use `get_note(id)` for the full body.
- 🔴 **FUSE personal + live:** pair a recalled note with a fresh read — "your NVDA thesis from last week
  said …; here's the live `asset_pulse` now" — that personal-knowledge + live-graph combination is the point.

## Voice
Facts and observations, not advice.
