# Memory-assisted development pilot

Started on 2026-10-25 in `runs/memory_text`; progress log is `runs/memory_text.log`.
This is a separate text-feedback condition with additional expert reference guidance. It does not alter the
existing `runs/video` or `runs/text` conditions, source files, or output directories.

Before starting, the hand-written reference controller was freshly executed on 10 kg seed 0 and 25 kg seed 1.
Prospective provenance is in `runs/memory_validation/dev_001/config.json`. Both trials passed; independent
trajectory rescoring emitted `validation.json`:

| Development case | Rise | Hold | Mean assistance |
| --- | --- | --- | --- |
| 10 kg, seed 0 | 0.5541 m | 4.1 s | 19.67 N |
| 25 kg, seed 1 | 0.5103 m | 3.8 s | 38.69 N |

One skill was explicitly admitted from that evidence: `9b4747b4186f04a3ab098eb1`. Its guidance includes the
reference program, observed development outcomes, applicability limits, and API reminders. Success does not
prove all guidance sentences are causally correct, nor that other masses will pass.

## Pilot settings

- Initial controller copied from `runs/video/round_0/controller.py`, the same baseline as the paired existing runs.
- Telemetry feedback only; 5, 10, 15, 20, 25, 30, 35, 40 kg; base seed 0 with existing loop's mass-index offset.
- Two Argon critique/rewrite calls, rounds 0..2 evaluated; at most two simulator workers.
- Frozen memory snapshot in `skills.frozen.json`; exact retrieved text, retrieval query, memory SHA256,
  initial-controller SHA256, and environment SHA256 in `memory-context.json`.
- Actual base task, augmented task, and API prompt snapshots retained alongside results.
- No rendering: text-feedback conditions do not consume videos. This changes wall time, not text observations.
- Completion writes `environment-check.json`. An environment mismatch invalidates cross-round physical comparisons.
- Existing environment/scorer retained; no thresholds or actuator strengths tuned for this pilot.

This run makes real paid Argon API calls. API usage/cost appears in `calls.jsonl`; recorded round results appear
in `summary.json`. No success for Argon's revisions is claimed until results are saved and inspected.

## Interpretation

This tests whether supplying a known working reference strategy helps the current task. It does not isolate
persistent-memory architecture from expert demonstrations, establish held-out generalization, or demonstrate
video benefit. Existing live runs and this pilot use development conditions. Do not call them final held-out scores.

Run owner: this evaluation workstream. Main video/text run owner can continue independently. After completion,
compare saved development outcomes, retain failures, and use the prospective evidence tool to validate any proposed
new skill. The pilot does not automatically admit its own generated controllers or update its frozen memory.

Implementation: `evals/run_memory_pilot.py` uses process-local prompt and video-selection overrides. It does not
modify shared `loop` modules on disk. A new pilot requires a fresh output directory; no silent resume/overwrite.

Tests: 28 tests passed before launch, including stale-environment, held-out-evidence, and empty-retrieval rejection.
