# Lift Lab data collection

First collection: `data/collections/2026-10-25-v1/`. This is an artifact inventory, not a benchmark release.
Read its `summary.json` and `README.md` before consuming JSONL records.

## Collected outputs

| File | Contents |
| --- | --- |
| `episodes.jsonl` | One record per saved `result.json`, with outcome, mass, available seed/jitter, controller, trajectory, video, critique, and API-log links |
| `repairs.jsonl` | Consecutive controller versions linked to the critique and a unified code diff; before/after episode IDs |
| `failures.jsonl` | Recorded failures with conservative outcome tags; no model diagnosis promoted to a ground-truth cause |
| `artifacts.jsonl` | Project-relative source paths, byte counts, SHA256 values, read-stability flags, and available snapshot paths |
| `api_calls.jsonl` | Saved run-level call records and source line numbers, including any recorded cost/token/latency data |
| `excluded_from_prompt_data.jsonl` | Records that cannot be treated as development prompt candidates and reasons for exclusion |
| `objects/` | Content-addressed copies of small JSON, controller, critique, model-reply, and log artifacts, plus controller diffs |

Videos and trajectories are hashed references to the source files, not duplicate binary copies. A filename ending in
`.mp4` does not certify decodability or actual model consumption; `.partial.mp4` files are explicitly flagged.
Unlinked videos and trajectories remain visible in the artifact inventory. Artifact counts are not episode counts.
No new simulator/model execution is performed. Source files and existing run directories are not modified.

## Provenance rules

- `backend=stub` means the saved config explicitly says `stub: true`.
- `backend=configured-real` means it says `stub: false`; this is a declaration, not proof of real execution.
- No config/backend declaration stays `unknown`, even for plausible historical reference sweeps.
- Path names containing `fake` generate a synthetic hint; absence of this hint does not establish real physics.
- Only explicit per-case seed metadata is indexed as the seed. A run's base seed is a separate setting. Folder names,
  jitter values, and today's loop implementation are not used to invent missing historical seeds.
- The environment fingerprint is taken only from saved metadata. Current simulator files are never used to
  retroactively fingerprint an old run. Current model/reference context lives separately in `data/references/`.
- Episode IDs depend on source-relative paths; source SHA256 values distinguish changing contents at those paths.
  Use both the ID and collection snapshot when comparing collections.

A `development-candidate` requires explicit real/development metadata, saved controller/trajectory, seed, mass,
and environment fingerprint. That label still requires review and independent validation; it is not memory admission.
Evaluation/held-out/test episodes are marked `evaluation-only`; stubs and missing-provenance records are `review-only`.
The first collection has zero eligible development candidates because existing artifacts lack explicit split metadata.

The collector indexes held-out outcome metadata for offline audit. Never send the complete collection to a model.
It creates no model-facing episode bundle and writes no skill memory. Use the prospective evidence workflow in
`development-validation.md` for new skills; do not relabel old artifacts merely to pass admission.

## Repair interpretation

A repair record means a critique sits between round K and K+1 controller artifacts. It does not prove the fix worked.
Critique text is a model claim. Before/after outcomes are matched only when mass and per-case seed are explicit and
unambiguous. Unknown seed cases remain linked as round-level observations, not a matched comparison.
The collector sets `validated_improvement=false` on every record; independent evaluation is needed to change a claim.
Stub repairs remain useful harness records, but cannot populate a library of physically validated fixes.

Run-level API log records are not automatically charged to individual episodes. Do not sum a shared run's cost once
per episode. Unlogged generation errors, missing calls, and unrecorded model settings cannot be reconstructed here.

## Refresh

Run from the project root and choose an unused destination:

```bash
.venv/bin/python -m evals.collect_data --out data/collections/2026-10-25-v2
```

The collector refuses an existing destination or one inside `runs/`. It snapshots small files and detects ordinary
in-read changes, but scanning an actively written directory is not an atomic experiment snapshot. Repeat after runs
settle and retain prior collections. No copying old metadata onto new outcomes.

Reference context is in `data/references/argon-reference-pack.md`, with official source links, current local settings,
and caveats. `docs/reference-collection.md` explains its separate role. Apply identical reference context across
compared conditions and record its hash. No external benchmark outcomes are claimed as our robot's evidence.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Collection tests cover held-out/stub exclusion, unknown seed handling, repair diffs, immutable source reads,
snapshot hashes, partial videos, output protection, and conservative failure labels. Synthetic fixtures test
collection behavior only, not simulated lifting success.
