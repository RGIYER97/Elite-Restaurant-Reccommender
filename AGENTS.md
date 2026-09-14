# Repository guidance

## Project

- This is a Python 3.10+ Streamlit application. The entry point is `app.py`;
  reusable API, domain, and presentation code lives under `restaurant_finder/`.
- Google credentials and runtime settings belong in local `.env` files or the
  deployment platform's secret store. Never commit `.env`, API keys, or tokens.
- `PLACES_API_MAX_PAGES` controls pagination per area/category query: `3` is
  the normal full 60-result Text Search window, while `0` follows all tokens.
  Changes to pagination should include cost/coverage documentation and tests.

## Validation

Run the full test suite before committing:

```bash
.venv/bin/python -m pytest -q
```

Also run `git diff --check` and compile changed Python modules when practical.
Tests use fake HTTP sessions and must not make live Google requests.

## Changes

- Keep search, filtering, and API behavior in their respective package modules;
  keep Streamlit orchestration in `app.py` and shared styles in `ui.py`.
- Update `README.md` when configuration, API usage, deployment, or user-facing
  behavior changes.
- Preserve existing user changes in a dirty worktree and inspect `git status`
  before staging. Do not use destructive reset or checkout commands without
  explicit approval.
