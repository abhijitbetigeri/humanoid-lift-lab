# Lift Lab reference context for Argon

Collected 2026-10-25. This is development reference guidance, not validated skill memory or evaluation evidence.
Use the exact same pack across compared arms, log its hash, and never append held-out outcomes to it.
Machine-readable source metadata and local source hashes are in `sources.json`.

## Actual local task and model

This project uses a **modified humanoid simulation based on G1 geometry**, not a stock G1 carrying 40 kg.
The local `sim/humanoid_api.py`, `sim/trial.py`, and MJCF files define the experiment. Manufacturer specifications
and upstream model defaults do not override local runtime settings. These files are actively changing; this
collection is a dated snapshot and does not certify any historical run's environment.

Observed installed MuJoCo package: **3.17.0** (package metadata, no simulation launched). The online references below
use live `stable` documentation; version-specific 3.17.0 documentation URLs could not be retrieved, so exact
documentation/runtime version correspondence is unverified.

Local settings inspected:

| Setting | Local value or definition |
| --- | --- |
| Physics timestep / recording / cap | 0.001 s / 30 fps / 30 simulated seconds |
| Body mass scaling | `MASS_SCALE = 1.0`; G1-like body masses retained |
| Hip pitch/roll/yaw torque limits | 320 / 300 / 200 N·m |
| Knee / ankle pitch/roll limits | 400 / 200 / 150 N·m |
| Waist yaw/roll/pitch limits | 200 / 250 / 250 N·m |
| Shoulder / elbow / wrist limits | 150 / 120 / 60 or 40 N·m, depending on joint |
| Grip helper | Up to 450 N per palm; 0.03 m inward IK offset plus equal/opposite applied palm forces |
| Contact options | Elliptic friction cone, `impratio = 5`, `noslip_iterations = 10` |
| Tote | Full size 0.24 × 0.34 × 0.44 m; initial centre (0.42, 0, 0.22) m before jitter |
| Placement sampling | Seeded uniform XY offsets within ±0.02 m |
| Tote inertia | Recomputed for runtime mass using solid-box inertia |
| Assistance | Pelvis capture-point PD plus angular/vertical assistance; counted in the score |
| Pass requirements | Rise ≥0.45 m, hold ≥3 s, no fall/drop/error, mean assist ≤60 N |
| Fall / drop thresholds | Pelvis below 0.45 m; slip threshold 0.25 m plus post-liftoff return-near-floor check |

The source docstring mentions 500 Hz, but the runtime constant is 1 ms (1000 Hz); use actual runtime settings.
The current task prompt says “real joint torque limits”; that conflicts with `STRENGTH`. Do not repeat that claim.
The calibration document's comparison to Apollo/Atlas is a design motivation, not a validated equivalent robot.

## Controller API and frames

Controller entrypoint: `def run(robot): ...`. Ask `robot.limits()` and `robot.joint_names()` for actual limits/names.

- State: `box_mass_kg`, `box_size` (full extents), `box_pose()` (world position and wxyz quaternion), `q()`,
  `joint_torques()`, `time()`, `hand_box_slip()`, `pelvis_height()`.
- Balance: `com()` includes the tote when considered lifted; `support_polygon()` returns an **axis-aligned rectangle**
  from foot collision geometry, not a general contact-support polygon. `com_margin()` is margin to that rectangle.
- `hands_to(left_xyz, right_xyz, duration_s=1)` uses **pelvis-frame** targets: x forward, y left, z up. It returns
  left/right IK residual errors. `box_pose()` is world-frame; convert with `world_to_pelvis_frame` before combining them.
- `set_posture(targets, duration_s=1, profile="minjerk")` interpolates joint targets. `squat(depth_m, duration_s=1.5,
  torso_pitch=0, hip_back=0)` sets leg targets; positive torso pitch is forward, hip-back is metres.
- `squeeze(force_n)` caps force and adjusts hand targets; `release()`, `wait(s)`, `phase(label)`, `abort(reason)`.
  Motion calls advance simulation time and run sequentially; they are not simultaneous commands.

These are supplied motion primitives. Argon revises task-level programs over this API; it is not learning raw motor
control from video alone. Read current method docstrings when generating a controller.

## Physics guidance and its limits

For an ideal symmetric two-contact pinch, a useful first estimate is `2 μ N ≥ m(g+a)`, with `N` per palm and an
explicit margin. This is an analytic approximation, not a measured guarantee: contact alignment, arm saturation,
acceleration, collision geometry, and the simulator's contact solver affect outcomes.

The tote's MJCF sliding coefficient is 0.8; the hand collision class includes 0.85. These are **simulation assumptions**,
not measured coefficients for the real materials. Inspect active contact pairs and priority/mixing rules before
treating either number as the effective grasp coefficient.

MuJoCo models contact compliance; numerical slip does not uniquely establish a bad grasp. Solver changes can change
outcomes, so keep them fixed across arms. [Contact computation](https://mujoco.readthedocs.io/en/stable/computation/)

`noslip_iterations` enables an additional pass that suppresses drift in friction dimensions. It does not certify
perfect Coulomb contact or transfer to hardware. `condim`, friction, priority and solver settings belong in the
environment fingerprint. [XML reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html)

## External context

The Menagerie G1 is a simplified MJCF derived from Unitree's public description. Its README notes added position
actuators need tuning. Its MJX model is a separate configuration; do not transfer that model's validation claims to
our modified lifting scene. [Upstream G1 README](https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main/unitree_g1/README.md)

Unitree's current page lists approximately 35 kg body weight, approximately 2 kg G1 / 3 kg G1 EDU arm loading, and
states loading depends on arm extension. This is context for the difference between hardware and our simulation,
not a direct bimanual tote-lift rating. [Manufacturer G1 specifications](https://www.unitree.com/g1/)

ASPIRE provides relevant prior art: code-policy repair from execution traces, validation by re-execution, reusable
skills, and separate debug/evaluation seeds. Borrow trace structure and split discipline; ASPIRE's results are not
Lift Lab results. [ASPIRE method](https://research.nvidia.com/labs/gear/aspire/)

## Use and attribution

This pack contains short original notes and links, not copied manuals or external datasets. The upstream G1 model
declares BSD-3-Clause; retain the model's notices when redistributing relevant assets. Other code/assets retain
their own terms. Reference links do not grant permission to redistribute whole documentation sites or videos.
[G1 license](https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main/unitree_g1/LICENSE)

No external video was downloaded, no external skill was admitted, and no held-out performance was inspected for
this reference pack. All reference guidance remains separate from episode observations and validated memory.
