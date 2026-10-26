# Test fixtures

Small images used by the contract tests. They are committed so a fresh clone
and GitHub Actions run the whole suite instead of silently skipping it.

| File | Used by | Source |
|---|---|---|
| `messi5.jpg` | backend, quality | OpenCV sample image |
| `lena.jpg` | quality | Classic public image-processing test image |
| `7f18cb16d51f6228b635d23c18772c05.jpg` | backend hair-bbox, eval | Stock portrait from the earlier evaluation pool |
| `ex6(half).png` | backend upper-body/jeans | Half-body crop from the earlier fitting set |

These are **test fixtures only**. They are not part of the tuning or held-out
evaluation sets anymore; do not reuse them for policy tuning or accuracy claims.
