## What / why

<!-- one paragraph; link the issue if there is one -->

## Verification

<!-- paste commands and results, e.g.:
- .venv/bin/python -m pytest -q → 505 passed
- cd frontend && npm run lint && npm run build → green
-->

## Risk / rollback

<!-- what could break; how to revert -->

## Checklist

- [ ] Tests pass locally (unpiped, exit code checked)
- [ ] `npm run lint` / `npm run build` (frontend changes)
- [ ] No generated files, `.env`, models, or secrets committed
- [ ] `docs/handover.md` updated if the session changed state
- [ ] Policy/constant changes include an A/B baseline
