# Humanoid Lift Lab — build plan (deadline 16:30 PDT, submit by 16:15)

**Pitch:** Argon acts as the robotics engineer. It writes a whole-body lift controller for a Unitree G1 humanoid
(MuJoCo), then watches simulation video of its own attempts lifting totes of **5–40 kg** from the floor. It diagnoses
the physics (centre of mass leaving the feet, bending at the waist instead of squatting, hip/knee/back torque
saturation, hands slipping) and rewrites the controller. **Physics scores every round**; the critic never scores itself.

Prior art (for the form): RMA (Kumar et al. RSS 2021), Tan et al. 2018 and Walk These Ways (2022) handle varying
payload by mass randomization plus RL over millions of steps. Argon instead gets there in about 10 rounds of
watch → diagnose → rewrite, and produces a controller a person can read.

**Headline chart:** success rate vs. tote mass (5–40 kg), round 0 → round N, and the heaviest lift with low balance assist.
**Baselines:** (1) a textbook controller: stoop lift with grip from the friction formula F = m(g+a)·S/(μ·n);
(2) the same Argon loop with text telemetry only (no video).

## Use case

Humanoids are being piloted in warehouses and car plants (Agility Digit, Apptronik Apollo, Figure, Unitree) to move
totes and parts in spaces built for people. Tote and part weights change by the hour. A lift tuned for 8 kg tips the
robot forward or drops the load at 30 kg. Today an engineer re-tunes it by hand. Argon does that re-tuning in sim,
explains the failure in plain language, and ships a safer controller before it touches the real robot.

## Files and owners (agents edit only their own files)

| Path | Owner | Contract |
|---|---|---|
| `sim/g1/g1_with_hands.xml` + meshes | nobody (read-only) | Unitree G1, 29 DoF body + hands, real torque limits |
| `sim/g1/scene_lift.xml` | W1 = PHYSICS SECTION, W2 = VISUAL SECTION | scene; body `box` (freejoint `box`, geom `box`) |
| `sim/humanoid_api.py` | W1 | `Humanoid` class the generated controllers call |
| `sim/trial.py` | W1 | `run_trial(controller_path, mass_kg, seed, out_dir, use_assist=True) -> dict`; writes `out_dir/traj.npz` + `out_dir/result.json` |
| `sim/baseline_controller.py`, `sim/reference_controller.py` | W1 | textbook baseline; hand-written proof that heavy lifts are solvable |
| `docs/calibration.md` | W1 | sources for the strength scaling, friction and the grip formula |
| `sim/render.py` | W2 | `render_traj(traj_npz, out_mp4, camera="hero", hud=True, size=(1280,720), fps=30)`; replay only |
| `loop/argon.py`, `loop/prompts.py` | W3 | `write_controller(...)`, `critique_and_fix(...)` |
| `loop/run_loop.py` | W3 | rounds → `runs/<arm>/round_<k>/{controller.py, trials.json, critique.md, videos/*.mp4}` |
| `viz/` | W4 (later) | results page + demo video from `runs/` only |

### `traj.npz` schema (W1 writes, W2 reads)
- `qpos[T, nq]` at 30 fps, `time[T]`
- `box_mass` (scalar), `assist_force[T]` (N on the pelvis)
- `tau_frac[T, nu]` = |actuator force| / limit
- `com_margin[T]` (m; centre-of-mass distance inside the support polygon, negative = outside)
- `box_slip[T]` (m; box movement relative to the hands)
- `phase[T]` (str label from `robot.phase(...)`)

### `result.json` (hidden scorer)
`{success, mass_kg, box_rise_m, held_s, max_assist_n, mean_assist_n, peak_tau_frac, max_slip_m, fell, dropped, fail_reason}`
- **Success:** the box rises ≥ 0.45 m and is held ≥ 3 s, without the robot falling (pelvis z > 0.45) or dropping the box,
  and with mean balance assist ≤ ASSIST_BUDGET.

### `Humanoid` API (all a generated controller may use)
- Reads: `robot.box_mass_kg`, `robot.box_pose()`, `robot.box_size`, `robot.limits()`, `robot.com()`,
  `robot.support_polygon()`, `robot.joint_names()`, `robot.q()`, `robot.joint_torques()`, `robot.hand_box_slip()`, `robot.time()`
- Motion: `robot.set_posture(dict joint→rad, duration_s, profile="minjerk")` (whole-body joint targets, smooth interpolation),
  `robot.squat(depth_m, duration_s)`, `robot.hands_to(left_xyz, right_xyz, duration_s)` (arm IK in the pelvis frame),
  `robot.squeeze(force_n)` (palms press inward on the box), `robot.release()`
- Control: `robot.wait(s)`, `robot.phase(label)` (tags the video/HUD), `robot.abort(reason)`
- Controller file: `def run(robot): ...`, run in a subprocess with a 30 s sim-time cap.

## Workstreams

| ID | Work | Est. |
|---|---|---|
| **W1 Physics + API + scoring** | Humanoid API, arm IK, balance assist (PD on the pelvis that records force), strength scaling to Apptronik Apollo / Atlas class (about 25 kg rated, about 40 kg peak) with sources, trial runner, hidden scorer, textbook baseline, reference controller. Calibrate so the baseline fails above about 15 kg and the reference reaches about 35 kg. | 75 min |
| **W2 Visual quality** | Warehouse-cell look (floor, shelving, lighting, soft shadows, safety marks, tote styling by mass), 3 cameras (hero 3/4, side profile for posture, close-up on the hands), HUD (mass, phase, balance margin, torque bars, assist force, PASS/FAIL), mp4 at 30 fps. Builds against a fake trajectory until W1 lands. | 60 min |
| **W3 Argon loop** | Prompts, Files API video upload, Interactions background calls, code extraction and validation, video vs. text-only arms, round bookkeeping; built against a stub `run_trial`. | 60 min |
| **W4 Results + demo** | Results page, charts, side-by-side videos, 60 s demo cut, README. | 45 min, from 13:30 |
| **Main session** | Contracts, integration, real runs, submission text. | — |

## Timeline

| Time | Milestone |
|---|---|
| 12:35–13:45 | W1, W2, W3 build in parallel |
| 13:45–14:00 | Integration; the reference controller passes; round 0 runs end to end |
| 14:00–15:15 | Real runs: video arm + text-only arm |
| 15:15–15:45 | Results page, demo cut |
| 15:45–16:15 | Voice-over, YouTube upload, public repo (user OK), form |
