"""Prompts for the Argon controller-writing loop (W3).

api_md() is generated from PLAN.md's Humanoid API section, plus the public method docstrings of
sim/humanoid_api.py when that file exists, so the docs track W1's real API at integration.
"""
from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

TASK_MD = """\
# Task: a whole-body lift controller for a Unitree G1 humanoid

## Why this matters
Humanoids are being piloted in warehouses and car plants (Agility Digit, Apptronik Apollo, Figure, Unitree) to move
totes and parts in spaces built for people. Tote weights change by the hour. A lift tuned for 8 kg tips the robot
forward or drops the load at 30 kg. You are the robotics engineer: write ONE controller that lifts any tote from
5 kg to 40 kg, reading `robot.box_mass_kg` and adapting to it. The same file is run for every mass.

## Scene
The G1 (about 35 kg, 1.3 m, 29 body DoF plus hands, real joint torque limits) stands in front of a tote on the floor.
The tote is a rigid box (`robot.box_size`, pose from `robot.box_pose()`), mass 5-40 kg depending on the trial.
A weak PD "balance assist" on the pelvis keeps the robot from falling over, but every newton it applies is recorded
and counted against you.

## Success (judged by physics, not by you)
- the box rises at least 0.45 m above its start height and is held there for at least 3 s,
- the robot does not fall (pelvis height stays above 0.45 m) and does not drop the box,
- mean balance-assist force stays within the budget (lower is better; it is reported per trial),
- all of it inside a 30 s sim-time cap.

## Physics to reason about
- **Centre of mass over the support polygon.** The combined CoM of robot + load must stay inside the feet
  (`robot.com()`, `robot.support_polygon()`). A heavy box held in front shifts the combined CoM forward by roughly
  m_box * d_box / (m_robot + m_box): at 40 kg held 0.4 m in front of the ankles that is ~0.2 m, past the toes.
  Counter it: hips back, box close to the body, feet/stance choice, lean that is planned rather than accidental.
- **Squat vs. stoop.** Stooping (bending at the waist with straight knees) puts the load's moment on the waist/back
  and hip pitch joints with a long lever arm. Squatting (knees and hips flex, torso near upright) shares the load
  across knees and hips and keeps the box near the CoM. Use knee flexion; keep torso pitch modest.
- **Joint torque vs. limits.** tau ≈ m * g * horizontal lever arm. Check `robot.limits()` and `robot.joint_torques()`.
  A joint at tau_frac ≈ 1.0 is saturated: it cannot track and the posture collapses. Peak load is at lift-off and at
  the deepest point of the squat; spread effort across joints and use slower motion where torque is high.
- **Grip friction.** With two palms squeezing with normal force N each and friction coefficient μ, the box is held
  if 2 μ N ≥ m (g + a), with a the upward acceleration. Add a safety factor (1.5-2x). Squeeze BEFORE lifting and
  ramp the force with mass; too much squeeze can saturate the arms/wrists. Watch `robot.hand_box_slip()`.
- **Acceleration.** Faster lifts raise a and the required grip, and add inertial torque. A minimum-jerk profile over a
  longer duration lowers peak acceleration. Heavy loads deserve slower, staged motion.
- **Keep the load close.** Every centimetre between the box and the body is lever arm on the back, hips and
  shoulders and shifts the CoM forward. Bring the box toward the torso as it rises.
- **The cost of balance assist.** If the controller relies on the pelvis assist to stay upright, it is not a real
  solution. Treat a large assist force as a sign that the CoM or posture is wrong.

## Rules
- Generalize across masses: scale grip, timing, posture and stance with `robot.box_mass_kg` through physical
  formulas or smooth schedules. Do not special-case a single test mass.
- Use only the `Humanoid` API below. You may `import math` (and numpy as np). No other imports, no file or network
  access, no access to simulator internals.
- Tag phases with `robot.phase("...")` so the video HUD and telemetry show where you are.
"""

OUTPUT_RULES = """\
## Output format
Return the COMPLETE controller file in a single fenced block:

```python
import math

def run(robot):
    ...
```

The file must define `def run(robot):` at top level, compile on Python 3.11, and use only the API above.
Put helper functions in the same file. No placeholders and no "rest unchanged".
"""

WRITER_INSTRUCTIONS = """\
You are a senior humanoid-robotics controls engineer. Write the first version of the lift controller.
Before the code, write a short plan (at most 12 bullets): the phases, how each quantity (squat depth, hand targets,
squeeze force, durations, torso pitch) scales with mass, and the physics that sets each number
(grip formula, CoM shift, torque estimate).
"""

CRITIC_INSTRUCTIONS = """\
You are a senior humanoid-robotics controls engineer reviewing your controller's last round of trials.
The physics simulator scored every trial; those scores are ground truth. Your job is diagnosis and a better controller.

## Write the critique first (markdown, headed `## Diagnosis`)
For each failing mass (and the heaviest pass, if it is marginal):
- Cite **timestamps** (m:ss, sim time) from the video{video_note} and the telemetry, e.g.
  "at 0:06 the centre of mass moves past the toes (com_margin -0.03 m) while the torso pitches ~40°, so the assist
  saturates at 180 N".
- Name the **physical cause**: CoM outside the support polygon, stoop instead of squat, which joint group saturates
  (tau_frac ≈ 1) and why (lever arm, speed), grip below m(g+a)/(2μ), slip at a high-acceleration moment,
  box too far from the body, reliance on balance assist.
- Point to the **line or parameter in the code** responsible.
Then `## Changes`: a numbered list of targeted changes, each tied to a diagnosis item and stated as a rule that
generalizes across masses (a formula or a schedule in `robot.box_mass_kg`), never a special case for one test mass.
Do not break lifts that already pass: keep what works for light masses.
If earlier rounds are listed, do not repeat a change that was already tried and failed.

## Then the code
"""


def _plan_api_section() -> str:
    plan = (ROOT / "PLAN.md").read_text()
    m = re.search(r"### `Humanoid` API.*?\n(.*?)(?=\n## |\n### |\Z)", plan, re.S)
    return m.group(1).strip() if m else ""


def _humanoid_docstrings() -> str:
    path = ROOT / "sim" / "humanoid_api.py"
    if not path.exists():
        return ""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return ""
    lines = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Humanoid":
            doc = ast.get_docstring(node)
            if doc:
                lines.append(doc.strip())
            for fn in node.body:
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and not fn.name.startswith("_"):
                    args = ast.unparse(fn.args).replace("self, ", "").replace("self", "")
                    is_prop = any(ast.unparse(d) == "property" for d in fn.decorator_list)
                    sig = f"robot.{fn.name}" if is_prop else f"robot.{fn.name}({args})"
                    d = ast.get_docstring(fn) or ""
                    lines.append(f"- `{sig}`" + (f": {d.strip()}" if d else ""))
    return "\n".join(lines)


def api_md() -> str:
    out = ["# `Humanoid` API (the only interface a controller may use)", "", _plan_api_section()]
    extra = _humanoid_docstrings()
    if extra:
        out += ["", "## Method reference (from sim/humanoid_api.py)", "", extra]
    out += ["", "Units: metres, radians, seconds, newtons, kilograms. Positions for `hands_to` are in the pelvis frame "
            "(x forward, y left, z up). Motion calls block until the motion completes (sim time advances)."]
    return "\n".join(out)


def writer_prompt(task_md: str, api: str) -> str:
    return "\n\n".join([WRITER_INSTRUCTIONS, task_md, api, OUTPUT_RULES])


def critic_prompt(task_md: str, api: str, code: str, trials_md: str, history_md: str, use_video: bool,
                  video_index_md: str) -> str:
    video_note = (" (the attached videos: hero 3/4 view on the left, side profile on the right; HUD shows mass, "
                  "phase, balance margin, torques, assist)" if use_video else "")
    parts = [
        CRITIC_INSTRUCTIONS.format(video_note=video_note),
        task_md,
        api,
        "# Current controller\n\n```python\n" + code.rstrip() + "\n```",
        "# Trial results (physics-scored) and telemetry\n\n" + trials_md,
    ]
    if use_video and video_index_md:
        parts.append("# Attached videos (in order)\n\n" + video_index_md)
    if history_md:
        parts.append("# Earlier rounds\n\n" + history_md)
    parts.append(OUTPUT_RULES)
    return "\n\n".join(parts)


def fix_prompt(error: str) -> str:
    return ("Your last reply did not contain a valid controller: " + error +
            "\nReply again with ONLY the complete controller file in one ```python fenced block, "
            "defining `def run(robot):` at top level.")
