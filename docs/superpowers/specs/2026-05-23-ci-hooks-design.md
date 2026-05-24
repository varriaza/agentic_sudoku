# Design: Automated Test Enforcement via Git Hook and GitHub Actions

**Date:** 2026-05-23  
**Status:** Approved

## Goal

Tests run automatically and block progress on failure in two places:
1. **Locally** — before any commit is accepted (hard enforcement)
2. **CI** — on every push and pull request via GitHub Actions

## Approach

Option A: committed shell script for the local hook, no new dependencies.

---

## Components

### `hooks/pre-commit`

A shell script committed at `hooks/pre-commit` (not `.git/hooks/`, so it travels with the repo).

```sh
#!/bin/sh
SKIP_PAYMENT=true pytest tests/ -q
```

- Uses whatever Python environment is active (`.venv`, conda, system)
- `-q` suppresses noise; full output shown only on failure
- Exits non-zero on any test failure, blocking the commit

**One-time developer setup:**
```
git config core.hooksPath hooks
```

This is documented in README and CLAUDE.md. New contributors must run it once after cloning.

### `.github/workflows/test.yml`

Triggers:
- `push` to any branch
- `pull_request` targeting `main`

Steps:
1. Checkout code
2. Set up Python 3.12
3. Restore pip cache (keyed on `requirements.txt` hash)
4. `pip install -r requirements.txt`
5. `SKIP_PAYMENT=true pytest tests/ -v`

Uses `-v` in CI for full output in the Actions log.

### `README.md` update

Add a **Development Setup** section with the `git config core.hooksPath hooks` command and a brief explanation.

### `CLAUDE.md` update

Update the test/run section to mention the hook setup command alongside the existing test run line.

---

## What is not in scope

- Linting, formatting, or type-checking hooks (not requested)
- Multi-Python-version matrix in CI (project targets 3.12 only)
- `pre-commit` framework (adds a dependency for no benefit here)
- Caching the `.venv` directory in CI (pip cache is sufficient)
