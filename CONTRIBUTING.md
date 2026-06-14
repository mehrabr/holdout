# Contributing

## Set up

```bash
git clone https://github.com/mehrabr/holdout.git
cd holdout
uv pip install -e ".[dev]"   # or: pip install -e ".[dev]"
```

Requires Python 3.11+.

## Run the gate

All four must pass before a PR is ready:

```bash
ruff check src tests          # lint
ruff format --check src tests # formatting
mypy --strict src             # types (strict; src only)
pytest                        # tests (live tests excluded by default)
```

Run them together:

```bash
ruff check src tests && ruff format --check src tests && mypy --strict src && pytest
```

Live tests hit a real provider endpoint and need an API key. They are opt-in and never
gate ordinary work:

```bash
pytest -m live
```

## Before opening a PR

- Keep commits small and focused on one module or concern.
- Any change that touches synthesis prevention or blind commitment should be obviously
  visible in the diff — reviewers look for this.
- If a change seems to require loosening a validator in `types.py`, fix the change, not
  the contract.
- If a change seems to require merging agent positions or passing peer output between
  agents, read `CLAUDE.md` — the two invariants explain why those paths are closed.

## Project structure

The repo map and build order are in `CLAUDE.md`. The two design invariants (no synthesis,
blind commitment) are described there too; they are encoded in the types and call graph,
not just in docs.
