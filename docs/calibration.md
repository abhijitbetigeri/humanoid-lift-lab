# Calibration (W1): strength, friction, grip formula, assist budget

All values are applied at runtime in `sim/humanoid_api.py`. `sim/g1/g1_with_hands.xml` is not edited.

## Reference robots

| Robot | Mass | Payload | Joint torques | Source |
|---|---|---|---|---|
| Apptronik Apollo | 72.6 kg, 1.73 m | 25 kg | not published (custom linear actuators) | https://qviro.com/product/apptronik/apollo/specifications, https://spectrum.ieee.org/humanoid-robot |
| Boston Dynamics Atlas (electric, 2026) | 90 kg, 1.9 m | 30 kg sustained, 50 kg brief, 20 kg one hand | not published | https://bostondynamics.com/atlas, https://bostondynamics.com/wp-content/uploads/2026/01/atlas-spec-sheet.pdf |
| Agility Digit | 45–65 kg (sources disagree) | 16 kg | — | https://robotsguide.com/robots/digit |
| Figure 02 | ~70 kg | 20–25 kg (aggregators) | — | https://qviro.com/product/figure/figure-02/specifications |
| Unitree H1 / H1-2 | 47 / 70 kg | H1-2 arm 7 kg rated, 21 kg peak | H1: knee 360, hip 220, arm 75 N·m; H1-2 shoulder/elbow 120 N·m | https://www.unitree.com/h1 |
| Unitree G1 (sim model) | 34.4 kg | ~2–3 kg per arm | knee/hip-roll 139, hip-pitch 88, ankle/waist 50, arm 25, wrist 5 N·m | https://www.unitree.com/g1, https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1 |

## Strength scaling we use (`STRENGTH` table)

We bring the G1 up to the torque class of the H1-2 and Atlas, so that a well-planned lift of about 25–30 kg is possible
and 40 kg is at the edge.

| Joint | G1 (N·m) | Ours (N·m) | kp (N·m/rad) |
|---|---|---|---|
| hip pitch / roll / yaw | 88 / 139 / 88 | 320 / 300 / 200 | 2500 / 2000 / 1500 |
| knee | 139 | 400 (H1 360) | 3000 |
| ankle pitch / roll | 50 / 50 | 200 / 150 | 2000 / 1500 |
| waist yaw / roll / pitch | 88 / 50 / 50 | 200 / 250 / 250 | 2000–2500 |
| shoulder (3) / elbow | 25 / 25 | 150 / 120 (H1-2 120) | 1200 / 1000 |
| wrist roll / pitch+yaw | 25 / 5 | 60 / 40 (H1-2 ~30) | 400 / 300 |

Damping is scaled by sqrt(kp_new/kp_old) to keep the actuators near critical damping. Fingers are unchanged.
Link masses stay at the G1 values (`MASS_SCALE = 1.0`): doubling them to Apollo mass was tried and made balance worse
for the same assist gains, so we kept the lighter body.

## Friction

No published static value for rubber or silicone on polypropylene/HDPE was found. Nearby values from the Engineering
ToolBox (https://www.engineeringtoolbox.com/friction-coefficients-d_778.html): rubber on cardboard 0.5–0.8, rubber on
dry concrete 0.6–0.85, polyethylene on polyethylene 0.2. Silicone pads span about 0.2 to above 1.0, depending on hardness
(US patent 12043530). We use tote μ = 0.8, palm/finger μ = 0.85–1.0 (MuJoCo takes the larger value of the pair), with an
elliptic friction cone (`impratio = 5`). Treat it as an assumption, the upper end of rubber on plastic.

## Grip sizing formula

F = m (g + a) · S / (μ · n)

- m is the tote mass, a the lift acceleration, S the safety factor (2 is standard), μ the friction coefficient and n the number of jaws (2 palms).
- Sources:
  - Bystronic: F = m(g+a)·2/μ, https://bystronic-mediacenter.picturepark.com/v/eEZo3g4C
  - Schunk catalog: assumes μ = 0.1 and S = 2, https://schunk.com/kr/ko/geuliping-siseutem/hoejeon-geuliping-modyul/c/PUB_8297
  - SMC: 2μF > mg, with a ×4 margin, https://ca01.smcworld.com/catalog/Electric-en/mpv/Electric-LEH-ABS_en/data/Electric-LEH-ABS_en.pdf
- `squeeze(F)` is capped at `GRIP_MAX_N = 450` N per palm. At μ = 0.8 and S = 2, that covers about 36 kg.
- The squeeze is an equal and opposite inward force pair on the two palms, so the net external force is zero, as with an
  internal actuator. The arm IK targets also move 3 cm inward. The box is held only by contact friction.

## Balance assist and budget

- The assist is a PD force on the pelvis, driven by the capture point of the combined CoM (robot plus tote once the
  tote leaves the floor). The capture point is the CoM plus v/ω, with ω = sqrt(g/z).
- It acts only on the part of the capture point that lies outside the foot rectangle shrunk by 2 cm. The gains are
  3000 N/m and 300 N·s/m, capped at 600 N.
- It also applies roll/pitch damping of 30 N·m·s, a roll spring of 150 N·m/rad, and anti-collapse vertical support
  below a pelvis height of 0.50 m.
- Logged magnitude = |F| + |τ|/0.5 m.
- `ASSIST_BUDGET = 60 N` mean over the trial. At 40 N, the reference failed at 25 kg by about 1 N, so we raised it to 60 N.
  The reference uses 20–47 N between 10 and 30 kg.

## Other scene choices

- The tote is 0.24 × 0.34 × 0.44 m, centred at x = 0.42 m in front of the pelvis.
- Tote inertia is recomputed from the runtime mass (solid box, I = m/3·(b²+c²) with half-extents), so it scales with mass.
- `noslip_iterations = 10` (`NOSLIP_ITERS`). MuJoCo's soft contacts let friction creep under a sustained load, so a
  held tote slowly slid between the palms. The noslip pass enforces the friction cone as hard as Coulomb friction does,
  so the grip is decided by μ and the squeeze, not by solver softness. In tests it turned 35 kg from a fall/blow-up into a pass.
- `condim = 4` (torsional friction) on the tote was tried. It fixed 25 kg but broke 20 kg, so it was not kept.
- Ejection as a named failure: at 35–40 kg the tote catches on the knees and hip links while the robot stands up. It
  then gets wedged between the palms, the legs and the floor and shoots out (box pitch rate above 50 rad/s). When the
  speed check trips while the tote is touching knee/hip/pelvis links and the accelerations are still finite, the
  sim raises `BoxEjected`. The trial then reports "dropped the box: tote jammed against the legs (...)" instead of
  "contact explosion". "physics: simulation became unstable" is left for real solver blow-ups only.
- The physics timestep is 1 ms. The sim stops with "physics: simulation became unstable" if the root or the tote exceeds
  50 m/s or rad/s.
