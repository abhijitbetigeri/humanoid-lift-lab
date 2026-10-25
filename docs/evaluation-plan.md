# Lift Lab evaluation plan

Status: proposed protocol, 2026-10-25. No benchmark claims yet.

## Questions and scope

Primary: does video plus numerical telemetry improve Argon's controller revision over identical telemetry alone?
Secondary: do validated development skills improve performance on unseen lift conditions?
Model-specific superiority requires a separate matched-model comparison; the first experiment cannot establish it.

Scope is task-level controller synthesis using the supplied Humanoid motion primitives in a modified G1 simulation.
Joint limits are scaled, body masses remain G1-like, grip includes applied palm forces, and pelvis assistance is enabled.
Results do not establish stock G1 payload capability, unassisted control, hardware safety, or superiority to RL.

## Current evidence and readiness gate

- `runs/w3_video` and `runs/w3_text` are stub runs. Exclude their scores and videos from physics results.
- `runs/w3_integ/config.json` specifies the real backend, a reference seed controller, masses 10 and 30 kg,
  and zero revision rounds. Its summary has zero passes and no rendered videos. These are development failures,
  not an Argon improvement experiment.
- At 10 kg the saved integration result reports box rise 0.2575 m and a dropped box. At 30 kg the robot falls.
  These are historical integration results. A later `runs/w1_reference_v2` sweep records passes at 10, 15, 25,
  and 30 kg; reference solvability is therefore demonstrated in saved development artifacts. Bind these results
  to the exact evaluated environment/controller versions and verify rendering before using them in a comparison.
  Do not lower thresholds to make a final run pass.

Gate A: real-backend baseline and reference trials complete, trajectories rescore consistently, and one reference
controller passes at least one development case. Failed gates remain in the report. Simulator repairs are allowed
in development, followed by a new environment fingerprint and experiment version.
Gate B: render a real trial, attach it to an actual critique call, validate returned code, rerun physics, and retain
the complete provenance chain. A stub smoke test does not satisfy this gate.
Gate C: freeze environment, scorer, prompts, camera/HUD, budget, development cases, and evaluation cases before comparison.

## Experiment matrix

| ID | Condition | Revision feedback | Skill memory |
| --- | --- | --- | --- |
| B0 | Handwritten baseline | None | Off |
| B1 | Argon initial controller | None | Off |
| T | Argon revision loop | Telemetry only | Off |
| V | Argon revision loop | Same telemetry + scene video without numeric HUD | Off |
| VM | Argon revision loop | Same as V | Frozen validated development library |

T versus V is primary; V versus VM is secondary. The current HUD-video setting may be an additional exploratory
condition, labelled separately. Numeric HUD removal requires a verified renderer mode; do not assume it exists.
Human physics hints in the current task prompt must remain identical across arms and be published.

For each independent replicate generate ONE Argon initial controller, then copy exactly the same bytes to T, V,
and VM. B1 evaluates those bytes unchanged. Use three revision calls (rounds 0..3), the same development trial cases,
and the same feedback history policy. Select the candidate by development pass rate, breaking ties by lower mean
assist then earlier round. Report final-round results too, so candidate selection cannot hide regressions.
Separate interaction histories and run directories for each arm; randomize arm execution order within replicate.
Match output/thinking settings and call counts; video has additional input cost, which must be reported.

## Splits and trial counts

Pilot proposal (freeze only after readiness gates):

- Development masses: 5, 15, 25, 35 kg; placement seeds 0 and 1 (8 cases per round).
- Evaluation masses: 10, 20, 30, 40 kg; placement seeds 100..109 (40 cases per selected controller).
- Five independent initial-controller generations. Initial generations and resulting arms form paired replicates.
- VM memory is collected on separate development episodes before these five replicates, then frozen.
  T and V receive no retrieved library. VM never writes new skills during the comparison.
- Five conditions × five replicates × 40 evaluation cases = 1,000 evaluation trials, including repeated B0 trials
  which may be cached by exact controller/environment/case hash. Development and memory-building costs are additional.

Begin with a two-mass, two-seed local readiness smoke before scheduling this matrix. Use a small development-only
timing sample to estimate CPU/render/API cost; full matrix launch depends on that estimate and available budget.
No paid experiment has been launched by writing this plan.

Current seeds jitter box XY placement by +/-2 cm. They do not randomize friction, dimensions, or actuator limits.
The same seed across masses pairs placement perturbations; this is intentional. Log actual jitter as well as seed.
All historical cases are development data. If reserved cases have been inspected or used to revise code, replace
them before freezing and record that change. Mass holdout tests interpolation plus the 40 kg boundary; report each.
Later robustness suite: friction, tote dimensions, reach distance, and reduced/no assistance. Each needs explicit
simulator support and a separately versioned protocol; do not advertise those evaluations as implemented.

## Scoring and statistics

Keep existing scorer thresholds fixed for v1: rise >=0.45 m, hold >=3 s, pelvis never below 0.45 m, no dropped box,
mean assist <=60 N, no controller/physics error. Audit scorer edge cases before freezing, including empty/nonfinite
trajectories, early termination, hold boundaries, and assist averaging over differing controller durations.
Report assistance over a common evaluation horizon or active lift/hold window as a secondary metric to expose dilution
by long low-assist waits. Record the existing full-trajectory definition for comparability.

Primary metric: held-out success fraction, equally weighted across cases. Primary effect: paired V minus T success
rate per independent generation. Secondary effect: VM minus V. Show every replicate, mean difference, and uncertainty;
five generations is a pilot with limited power. Use paired bootstrap over generations, retaining paired cases,
and clearly label unstable intervals. Do not treat all trials as independent controller-generation replicates.

Also report per-mass success, falls/drops, maximum contiguous mass range passed, rise/hold, peak and mean assist,
body torque saturation, slip, regression rate versus round 0, simulator failures, controller errors, wall time,
API tokens/cost, and number of attempts. Include failed generation/revision calls in cost and failure reporting.
Environment crashes are recorded separately; any rerun follows a predeclared infrastructure-retry rule and retains
both attempts. Controller exceptions and unstable commanded motion count as failures.

## Skill-memory integrity

Use `loop/skill_memory.py` and `docs/skill-memory.md` for the initial implementation. It is ASPIRE-inspired,
not an integration or reproduction of ASPIRE. Only real, independently scored development trials can validate a skill.
Store skill rationale, applicability, controller digest, environment digest, and evidence paths. A critique alone
is not evidence of a working skill. Admission validates evidence provenance; it cannot prove a verbal rule caused
the improvement. Test skill transfer separately. Reject stub and held-out records; filter retrieval by environment.
Freeze and hash the library before each comparison; record retrieved IDs and exact injected prompt text.

## Implementation sequence and exit criteria

1. Local protocol and provenance: this plan, immutable experiment manifest, content hashes, split/case IDs,
   explicit backend, controller ancestry, dependency versions, runtime platform, and recorded prompt/video settings.
2. Scorer audit and readiness runs: fix scoring defects with meaningful boundary tests; establish a successful
   real reference trial; validate actual video rendering and API consumption. Correct prompt's stock torque claim.
3. Evaluation runner: isolated per-case directories including seed AND exact mass; never reuse the current
   mass-only paths across seeds. Reject stale artifacts on fingerprint mismatch. Freeze candidate selection before test.
4. Feedback modes: identical telemetry across T/V, tested no-HUD scene video, separate histories, fixed revision budget.
5. Memory integration: explicit off/frozen retrieval settings, development-only validated admission, leakage tests.
6. Development-only timing and pilot, then frozen matrix and analysis. No held-out feedback goes back into prompts.
7. Release: protocol, manifests, dependency lock, prompts, controllers, memory snapshot, all outcomes/costs,
   analysis command, representative successes AND failures, and asset attribution. Exclude credentials.

Completion means another person can regenerate the cases, rescore trajectories, reproduce tables, distinguish
stubs from physics, and trace each generated controller to its exact inputs. Publish null/negative findings honestly.
Benchmark and technical report are realistic first outputs; broader research claims require additional tasks/models.
