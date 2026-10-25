# Prospective evidence for skill memory

`evals/development_validation.py` adds provenance and independent rescoring around the existing `sim.trial.run_trial`.
It does not edit the simulator, Argon loop, or existing runs, and never calls a model or launches simulation itself.
Prepare BEFORE a new development trial; old results cannot be relabelled with today's environment hash.

From the project root, prepare a fresh evidence directory (choose an unused path):

```bash
.venv/bin/python -m evals.development_validation prepare \
  --controller sim/reference_controller.py --case 10:0 \
  --out runs/memory_validation/dev_001
```

Preparation copies the controller, declares real/development/assisted execution, records cases and dependency/runtime
versions, and fingerprints simulator source/assets plus the validation and memory code. It assigns case directories
by index, exact mass, and seed, preventing seed/mass path collisions. It does not execute any cases.

The trial owner then runs the prepared controller for exactly those cases, using the existing API:

```python
import json
from pathlib import Path
from sim.trial import run_trial

root = Path('runs/memory_validation/dev_001').resolve()
config = json.loads((root / 'config.json').read_text())
for case in config['cases']:
    run_trial(str(root / 'controller.py'), case['mass_kg'], case['seed'],
              str(root / case['directory']), use_assist=True)
```

Then finalize:

```bash
.venv/bin/python -m evals.development_validation finalize --out runs/memory_validation/dev_001
```

Finalization checks unchanged controller/environment/runtime, declared placement seed and mass, finite trajectories,
and strictly increasing timestamps. It independently recomputes scores from trajectories and checks saved outcomes.
Only if every prepared case passes does it create `validation.json` in the format consumed by `SkillMemory.admit`.
It refuses to overwrite an existing validation manifest. Failed evidence remains in place and is never promoted.
Use the paths in `config.json` as the `environment_files` argument for admission (see `skill-memory.md`).

Do not run this tool against actively changing simulator assets; changed fingerprints reject finalization and require
a fresh preparation/run. Preserve the complete evidence directory and original environment files for retrieval.
Runtime versions are checked on finalization; frozen comparison manifests must also record runtime versions.

This is a trusted host tool, not protection from forged host records or arbitrary generated Python. Environment
hashes before/after detect normal concurrent edits, not an edit deliberately reverted between checks. The simulator
must actually be run with the copied controller and declared assistance setting; its current trajectories do not
encode every launch option. The independent scorer is the existing scorer, not a second physics implementation.
Successful evidence associates guidance with a working controller; it does not prove the guidance's causal effect.

Tests use synthetic trajectories to verify rejection and admission behavior. They are not robotics results:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_development_validation.py' -v
```
