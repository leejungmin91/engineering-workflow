---
id: 2026-11-19-round-refunds-per-line-item
title: "Round refunds per line item"
task: "T1"
skills: "payments"
model: "sonnet"
commits: "a1b2c3d"
review: "codex: no findings"
concerns: "skill:payments"
decisions: "Ship behind a flag"
---

Refund totals were off by one unit when an order mixed tax rates. Rounding moved from the order total to each line.
Dropped: rounding in the display layer, because exports use the stored value.
