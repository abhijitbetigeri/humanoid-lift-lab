# Parallel evaluation work: integration handoff

These additions leave `sim/`, `loop/run_loop.py`, `loop/argon.py`, prompts, and saved run artifacts unchanged.
They do not start competing physics, rendering, or model jobs.

## For the trial/Argon-loop owner

1. Continue real video/text loop integration. The added tools do not replace that work.
2. Use one identical starting controller for the paired conditions and separate output directories.
3. Before a development trial intended as skill evidence, prepare a prospective provenance record using
   `evals.development_validation`. Run the copied controller on its declared cases, then finalize to rescore it.
   Follow `development-validation.md`; the tool must precede the trial, not retroactively certify old artifacts.
4. Admit reviewed guidance through `SkillMemory.admit` using the finalized evidence. Freeze the memory store and
   referenced evidence before comparisons. Do not admit held-out outcomes.
5. Existing loop still needs explicit off/frozen-memory retrieval, split/environment provenance, retrieved IDs,
   actual injected prompt logging, and matching test cases. This handoff does not claim those are integrated.

## For results/submission work

Regenerate the saved-artifact audit independently of running experiments:

```bash
.venv/bin/python -m evals.audit_runs --runs runs \
  --json reports/current-run-audit.json --markdown reports/current-run-audit.md
```

Audit reports are inventories of saved artifacts, not live agent/process status or certificates of comparability.
Historical sweep passes remain useful development evidence, but lack immutable environment fingerprints.
Never use the old stub scores as physical performance. A real configuration alone does not prove a model saw video.

## Completed here

- Read-only artifact audit and reports.
- Development-only prospective validation bridge compatible with the existing memory admission API.
- Eighteen tests across audit, validation, and memory; all passed on 2026-10-25.
- No paid model calls, no simulation launches, no new performance claims.
