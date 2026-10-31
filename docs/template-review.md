# Eye/hood template review

The strict pack currently has only three eye templates. The relaxed extractor
finds many more candidates, but automatic expansion produced low-quality
iris-only eyes, so candidates now require human review.

```bash
# train-only candidates + contact sheet
.venv/bin/python scripts/build_template_gallery.py

# inspect out/production_benchmark/template_gallery.png
.venv/bin/python scripts/review_templates.py list
.venv/bin/python scripts/review_templates.py approve eyes <id> --notes "..."
.venv/bin/python scripts/review_templates.py reject hood_up <id> --notes "..."
```

- Candidates are extracted **only from the train split**.
- Approval is recorded in `out/production_benchmark/template_approvals.json`.
- No candidate enters the shipped pack until a human approves it.
- The gallery currently contains 19 eye candidates; most are stylized/iris-only.
  Review for sclera/iris readability and symmetry before approval.

`extract_eye_candidate()` is intentionally permissive and is **not** the
production extractor. The production pack remains the strict, quality-gated
three-template pack until approvals are available.
