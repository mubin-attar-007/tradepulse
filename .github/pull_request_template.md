## What & why

<!-- One or two sentences: what changed and the reason. -->

## Checklist

- [ ] `just check` passes locally (ruff, mypy, import-linter, pytest)
- [ ] Frontend `npm run lint && npm run typecheck && npm run build` pass (if web changed)
- [ ] OpenAPI/TS contracts regenerated if the API changed (no drift)
- [ ] No secrets committed (gitleaks clean); `.env` untouched
- [ ] Docs/ADRs updated if behavior or architecture changed
- [ ] Did not enable real-money live trading or weaken a safety gate
