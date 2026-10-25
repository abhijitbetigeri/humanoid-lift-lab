# Memory-assisted Argon development pilot

Completed 2026-10-25. Two paid Argon revisions, with explicit user approval. Logged API cost estimate: **$0.0846**.

| Controller | Passes | Passing payloads | Mean assistance across cases |
| --- | --- | --- | --- |
| Round 0: shared baseline | 0/8 | None | 129.2 N |
| Round 1: reference-informed Argon rewrite | 6/8 | 10, 15, 20, 25, 30, 35 kg | 32.6 N |
| Round 2: further Argon revision | 1/8 | 5 kg | 86.4 N |

Round 1 is preserved as `runs/memory_text/best_controller.py`, with selection rule and SHA256 in `selection.json`.
Selection uses development pass rate, then lower assistance, then earlier round. All round outcomes are retained;
the best-round result must not be presented as the final-round result.

## What this establishes

Supplying an executable expert reference and validated development guidance helped this Argon run replace a
failing baseline with a controller that succeeds on six tested payloads. The round-1 `run(robot)` function is
AST-identical to the supplied hand-written reference function. This is successful reference reuse, not an
independently discovered lifting strategy or proof of a novel memory architecture.

The second revision changed grasp targets, clamped grip force, altered hip offsets, and revised the lift schedule.
It fixed 5 kg but lost all six previous successes. These simultaneous changes do not isolate a root cause.
The result demonstrates the need to retain the best validated candidate and reject regressions.

## Verification

- Identical initial controller bytes to the existing video and text runs.
- Same 5..40 kg masses and base-seed-plus-mass-index placement schedule; existing assistance and scorer thresholds.
- All 24 saved trial outcomes independently rescored identically from their trajectories.
- All 24 saved placement jitters matched their declared execution seeds.
- Original environment fingerprint unchanged before/after; generated UI videos are excluded from simulator inputs.
- Frozen memory, exact injected text, task/API snapshots, API responses, controllers, failures and costs retained.
- This condition used telemetry plus reference guidance; no videos were sent to Argon.

Detailed verification is in `runs/memory_text/verification.json`; results are in `summary.json` and per-case
`result.json` files. The initial network failure remains in `calls.jsonl`, separate from the two completed responses.
No further model calls were launched after the approved two revisions.

## Limits and next use

These are assisted, modified-G1 simulation development cases. There is no held-out generalization result,
independent model comparison, hardware validation, or isolated estimate of persistent-memory benefit.
The memory contains a hand-written expert demonstration validated on two development cases, so any comparison
with unguided runs must disclose that additional prior information.

Use round 1 as a working development candidate and a regression reference. Any later repair should preserve its
10..35 kg successes while addressing 5/40 kg, then face a separately frozen held-out protocol. The pilot itself
does not automatically admit generated controllers into memory or authorize additional paid revisions.
