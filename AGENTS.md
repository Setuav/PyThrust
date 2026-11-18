# AGENTS.md

Operating instructions for coding agents. Keep this file short and concrete.

## Core Rules

1. **Think before coding.**
   - State assumptions out loud before editing.
   - For trivial, unambiguous tasks (typo, local rename, single obvious fix), state a 1-sentence plan and proceed.
   - For non-trivial, multi-file, or ambiguous tasks, **stop before editing** and present this 5-line plan, then wait for approval:
     - **Goal:** 1 sentence
     - **Assumptions / Questions:** explicit assumptions or blockers
     - **Non-Goals:** what will not be touched
     - **Steps:** 2–5 short steps
     - **Verification:** command or check proving done
   - Once approved, complete implementation and verification end-to-end without pausing unless blocked.

2. **Simplicity first.**
   - Write the minimum code that solves the stated problem.
   - No unrequested features, speculative abstractions, or "for future extensibility" hooks.

3. **Surgical changes.**
   - Every changed line must trace directly to the request.
   - Do not refactor, reformat, or "improve" adjacent code or comments you weren't asked to touch.
   - Clean up only unused code/imports created by your own changes.

4. **Goal-driven execution.**
   - Define verifiable success criteria before editing (test, repro script, or check).
   - Run the check and read the output before reporting done. Plausibility is not correctness.

## Communication & Honesty

- **No filler, no flattery.** Skip openers like "Great question" or "You're absolutely right." Start with the answer or action.
- **Disagree when wrong.** If a premise, design, or constraint is flawed, push back before implementing.
- **Never fabricate.** Do not guess file paths, APIs, symbols, or test results. Read the file, run the command, or say "I don't know."

## Project Context

- **Stack:** Python >= 3.10, NumPy, SciPy; optional OpenMDAO and matplotlib; pytest; MkDocs Material docs. Package `setuav-pythrust`, import name `pythrust`.
- **Commands:**
  - Install: `python -m venv .venv && source .venv/bin/activate && pip install -e .[plot,openmdao,dev,docs]`
  - Test (single): `pytest tests/test_solver.py::test_name`
  - Test (all): `pytest`
  - Lint / Typecheck: none configured
  - Docs: `mkdocs build --strict`
  - Examples: `PYTHONPATH=. python examples/<script>.py`
- **Layout:** Source: `pythrust/` | Tests: `tests/` | Docs: `docs/` | Examples: `examples/` | Tools: `scripts/`
- **Conventions:**
  - Conventional Commits: `feat(scope):`, `fix(scope):`, `refactor!:` with a `BREAKING CHANGE:` footer for API breaks.
  - Work on `feat/...` or `fix/...` branches and merge to `main` through a pull request; never commit to `main` directly.
  - Release: bump `__version__` in `pythrust/__init__.py` in a separate `chore(release): bump version to X.Y.Z` commit. Publishing a GitHub release uploads to PyPI.
  - SI units, with the unit as a field-name suffix (`resistance_ohm`, `diameter_m`, `kv_rpm_per_v`).
  - Solvers return an infeasible `OperatingPoint` with `infeasible_reason`; they do not raise for infeasible operating points.
  - Every behavior change comes with a test, and with a docs update when it touches the public API (`docs/api_reference.md`, `docs/theory.md`).

## Project Learnings

Append a concrete one-line rule when corrected (`Always/Never X for Y`). Prune rules that no longer prevent real mistakes. Keep the full file under 120 lines.

- (empty)
