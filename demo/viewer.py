"""Native MuJoCo viewer for the live demo. Run with mjpython (required for the viewer on macOS):

  .venv/bin/mjpython -m demo.viewer

It watches runs/live/state.json and plays the newest scored attempt in the interactive MuJoCo window, at real time,
looping until the next attempt lands. The motion is the exact qpos the physics trial recorded (sim/trial.py), so
what you see is what the scorer judged; drag to orbit, scroll to zoom.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import mujoco
import mujoco.viewer
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim.render import Scene, load_traj  # noqa: E402

STATE = ROOT / "runs" / "live" / "state.json"


def newest_traj():
    """(traj path, label) of the newest attempt whose trial finished, or (None, None)."""
    try:
        s = json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        return None, None
    for att in reversed(s.get("attempts", [])):
        p = ROOT / "runs" / "live" / s["run"] / f"round_{att['round']}" / "trial" / "traj.npz"
        if p.exists() and att.get("verdict"):
            return p, f"Attempt {att['round'] + 1} at {s['mass_kg']:g} kg: {att['verdict']}"
    return None, None


def main():
    sc = Scene(64, 64)  # only its model/data and replay helpers are used here
    with mujoco.viewer.launch_passive(sc.m, sc.d) as v:
        v.cam.azimuth, v.cam.elevation, v.cam.distance = 135, -15, 3.2
        v.cam.lookat[:] = (0.25, 0.0, 0.6)
        cur, tr, label, t0 = None, None, "waiting for a run...", time.time()
        while v.is_running():
            p, lab = newest_traj()
            if p is not None and p != cur:
                try:
                    tr = load_traj(str(p))
                    cur, label, t0 = p, lab, time.time()
                    sc.tint_tote(tr["box_mass"])
                except Exception:  # noqa: BLE001  (file mid-write: try again next tick)
                    pass
            if tr is not None:
                tt = tr["time"]
                span = float(tt[-1]) + 1.5  # hold the last pose 1.5 s before looping
                i = int(np.searchsorted(tt, min((time.time() - t0) % span, float(tt[-1]))))
                sc.set_qpos(tr["qpos"][min(i, len(tt) - 1)])
            if hasattr(v, "set_texts"):
                try:
                    v.set_texts((mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT,
                                 "Humanoid Lift Lab", label))
                except Exception:  # noqa: BLE001
                    pass
            v.sync()
            time.sleep(1 / 30)  # 30 fps is smooth enough and leaves CPU for the physics trials


if __name__ == "__main__":
    main()
