# Read-only run audit

The audit inventories saved configs, controllers, round trial tables, and sweeps.
It never invokes Argon, runs simulation, or changes an existing run.

```bash
.venv/bin/python -m evals.audit_runs --runs runs \
  --json reports/current-run-audit.json --markdown reports/current-run-audit.md
```

Backend labels distinguish explicit `stub: true`, explicit `stub: false`
(`configured-real`), and unknown provenance. A config declaration is not proof
of real execution. Historical reference sweeps without configs remain unknown;
their saved outcomes are inventoried without inventing environment provenance.

Every video/text pair is a candidate for structural checks, not an assertion that
the runs were designed to be compared. Checks include initial controller bytes,
environment digest, split, trial masses/seed, revision budget, and assistance mode.
Missing metadata blocks the checks. Even matching metadata does not establish
equal prompts/model settings, held-out isolation, actual video delivery, or a
causal improvement. Follow `evaluation-plan.md` for those requirements.

The report is a timestamped snapshot; concurrently running agents may change files
while it is produced. Re-run after experiments finish. The tool does not rescore
trajectories, validate videos, or bind historical outcomes to current source.
Its CLI refuses report outputs inside the audited runs directory.

Run focused tests with:

```bash
.venv/bin/python -m unittest discover -s tests -p test_audit_runs.py -v
```
