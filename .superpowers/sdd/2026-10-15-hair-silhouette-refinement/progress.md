# SDD ledger — plan: docs/superpowers/plans/2026-10-15-hair-silhouette-refinement.md

Ruling: execute on current `master` rather than worktree — repository handover norm explicitly requires direct commits on master; cost if wrong: reduced isolation from unrelated work.
Spec: user-approved chat design (2026-10-15), A = head sides/back + body back/sides to observed length, short shoulder strands on front.
Pre-flight: Task 1 produces `HairStencil` per-column face profiles; Task 2 consumes the same type and adds body extent. Keep Task 1's legacy rule output and golden hashes, Task 2 body painting gated on `hair_source=mask` stencil evidence.
Initial HEAD: `8973626`.
Task 1: Ruling: side face profile width is 8, not 4 — `get_layout()` shows head is 8×8×8 and all head side faces are 8 columns; cost if wrong: half the legacy side fill disappears (the golden test caught this).
Task 1: Ruling: derive side/back profiles from post-arch, post-symmetry coverage before the front eye clamp — the clamp is a front-only face-template policy and must not shorten inferred side/back geometry; cost if wrong: longer side locks/back coverage get clipped to the eyes' safety boundary.
