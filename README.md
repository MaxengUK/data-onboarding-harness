# data-onboarding-harness

MAXENG Data Onboarding Harness — a client-agnostic execution kernel plus a layered
library of rules, deployed inside the client boundary.

**`CLAUDE.md` is the specification and takes precedence over this file.** Read §0
before making any code change. This page is only the set of commands you need to
work in the repo.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows;  source .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"
pre-commit install          # installs the synthetic-fixture guard as a commit hook
```

## Regenerating the JSON Schemas

The Pydantic models under `schemas/` are the source of truth; `schemas/json/*.json`
is generated from them. After changing any model, regenerate and commit the result:

```bash
python -m schemas.export_json_schema
```

`python schemas/export_json_schema.py` works too. Output is deterministic — fixed
indent, LF endings, trailing newline — so the same models produce the same bytes on
Windows and on Linux CI (P2, §12).

`tests/test_schema_sync.py` fails if the committed schemas drift from the models, so
forgetting this step breaks the build rather than going unnoticed.

## Tests and checks

```bash
pytest -q                        # full suite
ruff check .                     # lint
python -m kernel.gates.guard     # synthetic-fixture guard (§5, §8.2)
```

The guard scans the whole tree for values that are checksum- or range-*authentic*
rather than merely PII-shaped, and exits non-zero on a hit. It runs in CI and as a
pre-commit hook. Fixture conventions — which invalid ranges to use, and the known
limits of detection — are in [`tests/fixtures/README.md`](tests/fixtures/README.md).
