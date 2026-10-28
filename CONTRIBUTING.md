# Contribution Guide

Thanks for contributing to RoboAgent.

## The One Rule

**You must understand your code.** If you cannot explain what your changes do and how they interact with the rest of the system, your PR will be closed.

Using AI to write code is fine. Submitting AI-generated slop without understanding it is not.


## 1. Development Setup

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or .venv\Scripts\activate on Windows
pip install -e .
pip install -e ".[dev]"
```

## 2. Project Workflow

1. Create a feature branch from `main`.
2. Keep changes scoped to one task or fix.
3. Run formatting, linting, and tests locally before opening a PR.
4. Update docs when behavior or configuration changes.

## 3. Quality Checks

Run these commands before committing:

```bash
ruff check .
black .
pytest
```

## 4. Code Organization Rules

- Add new tools as plugin modules in `agent/plugin/` whenever possible.
- Add or update tests under `test/` for all behavior changes.
- Keep built-in tool changes in `agent/core/` focused and minimal.
- If you add or change tooling behavior, keep `README.md` in sync.

## 5. Pull Request Checklist

- [ ] Change is focused and minimal
- [ ] Tests added/updated where needed
- [ ] `ruff check .`, `black .`, and `pytest` pass
- [ ] Documentation updated (README/config/docs)
- [ ] PR description explains what changed and why
