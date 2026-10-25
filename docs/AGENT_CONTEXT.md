# Humanoid Lift Lab — shared agent handoff

Reviewed 2026-10-25 against code commit `a67ea88` and the current saved artifacts. This file is a handoff, not a claim
that every binary asset or third-party dependency was audited. Recheck current code, logs and Git state before action.
`docs/context-manifest.json` fingerprints the first-party source/evidence files used for this handoff.

## User intent and scope

Build and explain a hackathon prototype in which Gemini Argon adapts humanoid lifting programs using simulation
feedback. Current framing: lift-and-shift work for small businesses, workshops and households without an on-site
controls engineer. Implemented physical task is **in-place lifting only**: no walking, carrying, placing or hardware.
The model is a G1-geometry humanoid with scaled actuators and assistance, not a stock G1 payload demonstration.

The user requested repo synchronization and cross-agent context. Commit/push owned changes with explicit paths.
The user explicitly said **do not submit; share prepared materials**. No assistant submission receipt exists.
Do not contact others or publish to new services on the user's behalf just because a submission packet exists.

## System map

| Area | Role and key contracts |
| --- | --- |
| `sim/humanoid_api.py` | Human-written motion/state API over MuJoCo. Generated file defines `run(robot)`. Payload mass is provided, not inferred visually. Includes posture interpolation, leg geometry, arm IK, squeeze, phase tags and coordinate transforms. |
| `sim/trial.py` | Runs a controller in a subprocess, saves `traj.npz`, `child.json`, `result.json`, computes deterministic scores. Programmatic runner accepts controller/mass/seed/output/assistance. |
| `sim/render.py` | Replays recorded qpos with `mj_forward`; no physics stepping during rendering. Hero/side/hands cameras, HUD, verified temporary MP4 writes. |
| `sim/reference_controller.py` | Engineer-written working reference used as adaptation seed. `baseline_controller.py` is the weak stoop-lift comparison. |
| `loop/argon.py` | `gemini-4-argon`, Interactions background calls, Files API video upload, code extraction/compile/run-entrypoint checks, usage logs. The checks are not a security sandbox. |
| `loop/prompts.py` | Task, API docs derived from plan/docstrings, diagnosis/change/code prompt. Gives substantial physics hints; it is not vision-only motor learning. |
| `loop/telemetry.py` | Summarizes trajectories into timestamped signals and phase histories. |
| `loop/run_loop.py` | Batch mass sweeps and rewrite loop; `--arm video` vs `text`; optional `--keep-best` selects a prior controller using pass count plus partial lift progress. |
| `demo/` | Local interactive payload request, trial/critic loop, native trajectory viewer and web progress UI. |
| `voice/` | Separate read-only native-audio questions about saved evidence; Argon answers and Gemini TTS speaks. |
| `evals/` | Saved-run audit/collection, prospective development validation and separate memory pilot. |
| `loop/skill_memory.py` | Optional explicit admission/retrieval of guidance associated with verified development evidence. Not automatically used by the normal batch/live loops. |
| `viz/` | Static results page/data/media, built from selected runs by `viz/build_site.py`. Render publishes this directory only. |
| `submission/` | Final form copy, final controller snapshots, recorded results, narrated MP4, manifest, and pitch. |

## Physics and scoring facts

- G1-like link masses remain at `MASS_SCALE=1.0` (about 35 kg), with increased joint torque limits. Do not describe
  the robot as a validated Apollo/Atlas equivalent or a stock G1 lifting 40 kg.
- Current timestep is **0.001 s**, recording **30 fps**, simulation cap **30 s**. An old module docstring says 500 Hz;
  the runtime timestep wins. Current integrator is `implicit`, with elliptic friction cone and 10 noslip iterations.
- Grip helper adds a **3 cm inward IK offset** and applies paired palm forces, capped at **450 N per palm**. These
  are supplied actuation approximations. Noslip/assumed friction do not establish real contact fidelity.
- `box_pose()['pos']` is world-frame. `hands_to` uses pelvis-frame targets and returns IK residuals. Use
  `world_to_pelvis_frame` for world coordinates. Motion calls execute sequentially and advance simulation.
- Pass: tote rise **>=0.45 m**, contiguous hold **>=3 s**, no fall/drop/error, mean assistance **<=60 N**. Fall
  threshold is pelvis z <0.45 m. Slip/drop logic and post-fall error precedence are in `sim/trial.py`.
- Assistance includes pelvis forces and torque-equivalent magnitude; it is not zero or a hardware safety bound.
  Whole-episode mean can vary with controller duration. Scoring is independent of the model's opinion, not an
  independent validation of real-world physics or protection against malicious generated Python.
- Seeds currently jitter box XY by +/-2 cm, not friction, dimensions or actuator limits.

## Results — keep experiments separate

| Experiment | Controller/setup | Recorded outcome |
| --- | --- | --- |
| `video_adapt` | Reference seed, current setup, video+telemetry, keep-best | Pass counts by rounds 0..4: **7, 0, 3, 6, 8** out of 8. Logged model cost estimate $0.2557. |
| `text_adapt` | Same reference, telemetry-only, keep-best | Pass counts: **7, 0, 0, 6, 8**. Logged estimate $0.1766. |
| `memory_text` | Earlier setup, weak baseline + full expert-reference guidance, text-only | Counts **0, 6, 1**. Best round 1 (10..35 kg), final round 2 (5 kg only). Estimate $0.0846. Round-1 `run` AST matched the reference. |
| `video_final` | Weak stoop baseline, revised setup, keep-best | All saved rounds 0..8 have 0/8 passes. Do not hide this limitation. |
| `text_final` | Weak baseline, revised setup, keep-best | Saved rounds 0..6 have 0/8 at review time; running files may change. |
| `w3_video`, `w3_text`, `w3_test/dry` | Explicit stub configurations | Harness evidence only; not physics results even if an actual Argon API call occurred. |

Latest adaptation sweeps use 5,10,15,20,25,30,35,40 kg (about 11..88 lb), one trial per mass/round, base seed 0 plus
mass index. Four revisions = five evaluated versions. Final video 5 kg result: rise 0.6867 m, hold 4.966 s,
mean assist 12.61 N; recorded reference 5 kg case dropped with rise 0.2889 m and slip 0.7146 m.

Both adaptation arms reached 8/8: **no demonstrated video-superiority claim**. These are development cases seen
during adaptation, not held-out generalization. Those configs lack explicit historical environment hashes/splits;
do not retrofit current hashes. `submission/results.json` preserves selected final facts, hashes and both controllers.
The earlier memory pilot belongs to a different physics snapshot; do not join its curve to the current results.

## Live demo behavior and reliability

- `python -m demo.app --no-viewer`: port **8790**. Optional native viewer uses macOS `mjpython`.
- Browser speech recognition transcribes commands; a regex parser interprets mass/rounds. Bare numbers mean pounds,
  lb converts to kg rounded to nearest 0.5 kg, accepted range 5..40 kg, default revision budget 3, explicit rounds 1..4.
  The phrase "rated for" in parser messages describes a simulation task range, not a manufacturer hardware rating.
- Default controller is the engineer reference. Judge mass is tested alongside two loads chosen from 15,30,20 kg,
  excluding near-duplicates. A target pass is insufficient if a regression check fails.
- Each critic call can see all attempts' available videos. The UI exposes evidence labels, timestamped diagnosis,
  exact code diff, checks and elapsed time. The native viewer replays completed trajectories, not real-time hardware.
- Keep-best can restore the strongest attempt for another rewrite; it does not guarantee that the final attempt
  passes. A last-iteration failure can still be the displayed final result.
- At review time `runs/live/state.json` referred to **162353_m5**, completed with a fall after four attempts;
  anchor checks were 15 and 30 kg. This separate live trial is not the 8/8 batch result. Recheck state before a demo.
  For a dependable pitch, use the recorded successful batch footage rather than promise an arbitrary live repair.

## Voice, memory, evidence, deployment

- `python -m voice.app`: port **8791**, read-only questions about saved results. Short recording or typed question
  -> Argon native audio/text understanding -> grounded answer -> `gemini-3.8-flash-tts`, voice Kore, WAV playback.
  Argon itself has no native speech output/Live API in this implementation.
- Keys remain server-side. One active answer, local host/origin/token checks, 3 MB audio cap, 20-second browser
  recording cap, ephemeral jobs. TTS failure preserves text. No automatic model call on page load or evidence refresh.
- Local evidence takes precedence; fresh clones fall back to explicitly labelled `data/voice-evidence/`, which
  contains the **earlier memory pilot**, not the 8/8 adaptation run. No silent fallback over local stubs/held-out data.
- Memory is ASPIRE-inspired, not an imported ASPIRE dependency or benchmark reproduction. It needs host validation,
  explicit real/development config, controller/environment/result/trajectory hashes and successful outcomes.
  Admission is provenance checking, not proof that a verbal rule caused success. Retrieval is deterministic lexical
  ranking, bounded and opt-in. It is not a production memory database or adversarial trust boundary.
- `evals/development_validation.py`: prepare before running, then independently rescore and finalize; never certify
  old trajectories using today's environment. `run_memory_pilot.py` supplied frozen guidance in a separate condition.
- `evals/collect_data.py` outputs episode/repair/failure/API indices plus hashed small snapshots. Initial collection
  indexed 112 episodes, including stubs/unknown provenance; these are not 112 verified independent experiments.
- `docs/evaluation-plan.md` is a proposed repeated/held-out protocol, not a completed benchmark. Frozen holdouts,
  repeated model generations, varied layouts/friction, and hardware transfer remain future work.

Public repository: https://github.com/abhijitbetigeri/humanoid-lift-lab

Render results/demo: https://humanoid-lift-lab.onrender.com/#demo

Direct video: https://humanoid-lift-lab.onrender.com/assets/humanoid-lift-lab-60s.mp4

Render is static (`render.yaml`, directory `viz`, build `true`), so neither Python service runs there.
The video is 60.0 s, 1280x720/24 fps H.264/AAC, with Gemini TTS narration and summary captions. It combines actual app
captures and recorded trial replay, not a continuous live session. The form's example is YouTube; no YouTube upload
or form acceptance should be claimed. The user will submit materials themselves.

## Source precedence and checks

1. Current code/constants and specific saved artifacts determine implemented behavior.
2. `submission/results.json`, controller snapshots and manifests support submitted numerical claims.
3. Current `submission/SUBMISSION.md`/`form-fields.json` include manually refined framing from `a67ea88`.
   **Do not rerun `prepare_packet.py` blindly:** its embedded prose predates those manual edits.
4. `PLAN.md`, `PREP.md`, old audit/diagnosis/reference documents are historical; they contain outdated 10-round
   aspirations, stock-torque/500 Hz wording, early failures and unverified equivalent-robot comparisons. Do not quote
   them as the latest implementation. Some reports correctly describe only their own dated experiment.
5. Installed/tested top-level dependencies are pinned in `requirements.txt`; Python 3.14 on the development Mac.
   `GEMINI_API_KEY` loads from env/untracked `.env`. Never display or commit credentials.

At review time all **46 unit tests passed**. They cover evidence/memory/collection/voice utilities, not proof of
robot-controller robustness. Browser checks use mocked paid routes; a separate synthetic native audio round trip
really exercised Google TTS -> Argon audio -> TTS. No need to repeat paid calls merely to explain these features.

Useful checks: `python -m unittest discover -s tests -q`, `node --check voice/client.js`, and compare the manifest
hashes to current files. Graphics may require unsandboxed macOS access. Render workers are capped to avoid loading
the laptop excessively; even one replay render took about 270 s. Preserve other agents' running tasks.
