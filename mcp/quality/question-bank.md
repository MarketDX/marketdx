# MCP question bank

Natural investor questions to run as blind tests (fresh agent decides the tool). Tags: `[shape · persona ·
asset · edge]`. "Expected" = the behavior we grade against (verify numbers vs MCP ground truth; notes vs DB).
Mix languages on purpose. Add/curate freely — real users ask messier, compound things.

## A. Read / compare a KNOWN set (financials happy path)
1. `[compare · analyst · stock]` "เทียบ ROE, net margin และ FCF ของ Apple, Microsoft, Nvidia" → digest only (all in digest), no `fields`; flag ROE inflation from buybacks/leverage.
2. `[compare · analyst · stock]` "TSMC vs Samsung vs Intel — gross margin 3 ปีล่าสุด" → digest or `fields=gross_profit,revenue`; currency-neutral note.
3. `[read · newbie · stock]` "Apple แข็งแรงแค่ไหน งบดุลดีไหม" → digest; plain-language read.
4. `[compare · analyst · stock]` "capex ของ hyperscalers ย้อนหลัง" → `fields=capex` multi-year; fiscal-misalignment + finance-lease caveat.

## B. Discovery / ranking (⚠️ routing risk — W3)
5. `[discovery · analyst · stock]` "บริษัท US ไหนซื้อหุ้นคืนเยอะสุด" → must NOT brute-force financials w/ guessed tickers; use news/screener OR world-knowledge candidates + verify + "not exhaustive".
6. `[discovery · analyst · stock]` "หุ้นเทคตัวไหน margin สูงสุด" → same routing discipline.
7. `[discovery · economist · stock]` "ใครได้ประโยชน์จาก AI capex boom บ้าง" → theme/relationships tools, not a financials guess.

## C. Basis-mismatch / comparability (⚠️ W1)
8. `[compare · analyst · stock · non-us-proxy]` "5 ปี Toyota กับ Apple ซื้อหุ้นคืนใครมากกว่า" → flag gross(Apple) vs net(Toyota proxy); directional not a hard multiple.
9. `[compare · analyst · stock]` "เทียบ 'รายได้' ของ Berkshire กับ Apple" → mixed business models; note comparability.
10. `[compare · analyst · bank]` "เทียบกำไรของ JPMorgan กับ Toyota" → bank vs industrial line-shapes differ; compare on a sound basis.

## D. Boundary / fabrication-resistance
11. `[read · analyst · stock · deep-history]` "งบ Apple ปี 2014" → `period_unavailable`; say data doesn't reach back, don't infer FY2025 numbers.
12. `[read · analyst · private]` "งบการเงินของ OpenAI / SpaceX" → private; financials N/A; use `oc:` path, don't fabricate.
13. `[news · analyst · stock · pre-2026]` "ข่าวที่ขยับ Nvidia ปี 2023" → news starts 2026; say so; price history IS available.
14. `[read · newbie · etf]` "งบการเงินของ SPY / QQQ" → ETF, no company financials; explain + offer price/holdings.

## E. Concept / explanation (note-worthy, no data)
15. `[concept · newbie]` "EBITDA คืออะไร ต่างจากกำไรสุทธิยังไง" → explain; auto-save as reference note (linked to nothing).
16. `[concept · newbie]` "โรงหล่อชิป (foundry) ทำเงินยังไง" → explain; save + link megatrend.

## F. Compound / cross-source (the real test)
17. `[compound · economist · stock+macro]` "ค่าเงินเยนอ่อนกระทบกำไร Toyota ยังไง" → financials (JP, FX) + FX/macro; synthesize.
18. `[compound · analyst · stock+news]` "Nvidia งบดีแต่ข่าวช่วงนี้เป็นบวกหรือลบ" → financials digest + stock_impact/news; reconcile.
19. `[compound · economist · commodity+stock]` "ทองแดงขึ้นกระทบใคร" → commodity + relationships/impact; the ripple.
20. `[compound · global · stock+trade]` "สงครามการค้าจีน-สหรัฐกระทบ Apple ยังไง (supply chain)" → trade tools + impact; cross-border gate.

## G. Non-US / cross-currency / edge data
21. `[compare · global · stock · fx]` "เทียบสินทรัพย์ธนาคาร JPMorgan vs MUFG (USD)" → `currency=USD`; `fx` block; ratios neutral.
22. `[read · analyst · stock · data-bug]` "AIG งบมีอะไรผิดปกติไหม" → the Yahoo concept-collapse (two lines byte-identical) is a DATA bug, not ours; flag honestly.
23. `[read · analyst · stock · quarterly]` "รายได้รายไตรมาส 6 ไตรมาสล่าสุดของ Nvidia โตต่อไหม" → `period=6q`; QoQ trend.
24. `[read · analyst · stock · abs-range]` "งบกำไรขาดทุน Apple ปี 2022 ถึง 2023" → `period=2022-2023` + `fields=income`.

## H. Non-equity asset classes (expected absences)
25. `[read · analyst · commodity]` "ทองคำเป็นยังไงช่วงนี้" → commodity_pulse; NO PE/financials expected.
26. `[read · analyst · bond]` "US 10Y yield ตอนนี้บอกอะไร" → find_stock→US-10Y.GB; move in bps, no PE/mcap.
27. `[read · newbie · crypto]` "Bitcoin น่าลงทุนไหม" → asset_pulse crypto; no financials.

## I. Notes — save quality (verify DB)
28. `[note · analyst]` after Q4/Q17/Q1 → "จดไว้ให้หน่อย" → body keeps the markdown TABLE (absolute headers), links entities; verify DB row (not the self-report).
29. `[note · analyst]` a 3-table compare → body has 3 markdown tables, not prose; ONE note per topic; correct stock/megatrend links.
30. `[recall · analyst]` "ที่จดเรื่อง hyperscaler capex ว่าไง + ตอนนี้เป็นไง" → query_notes + FUSE with a fresh live read.
