"""Trial runner + hidden scorer (W1).

    run_trial(controller_path, mass_kg, seed, out_dir, use_assist=True) -> dict
    .venv/bin/python -m sim.trial <controller.py> --masses 5,10,15,20,25,30,35,40 --out runs/x
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- hidden scorer constants -------------------------------------------------
ASSIST_BUDGET = 60.0      # N, mean balance-assist magnitude allowed for a pass
RISE_M = 0.45             # box must rise at least this much
HOLD_S = 3.0              # ... and stay up this long
FALL_Z = 0.45             # pelvis below this = fell
DROP_SLIP_M = 0.25        # box moved this far relative to the palms = dropped
WALL_TIMEOUT_S = 240


def _child(controller_path, mass_kg, seed, out_dir, use_assist):
    """Runs inside the subprocess: simulate the controller, write traj.npz + child.json."""
    sys.path.insert(0, ROOT)
    import importlib.util
    from sim.humanoid_api import Humanoid, AbortError, SimTimeout, PhysicsDiverged, BoxEjected

    rng = np.random.default_rng(seed)
    jitter = rng.uniform(-0.02, 0.02, size=2)
    robot = Humanoid(box_mass_kg=mass_kg, box_offset=jitter, use_assist=use_assist)
    err = None
    try:
        spec = importlib.util.spec_from_file_location("controller", controller_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "run"):
            raise RuntimeError("controller has no run(robot)")
        mod.run(robot)
    except SimTimeout:
        pass  # the cap is not a failure by itself; scoring decides
    except BoxEjected as e:
        err = f"dropped the box: {e}"
        robot.log = {k: v[:-3] if len(v) > 3 else v for k, v in robot.log.items()}
    except PhysicsDiverged as e:
        err = f"physics: {e}"
        # drop the exploded tail so renders stay sane
        robot.log = {k: v[:-3] if len(v) > 3 else v for k, v in robot.log.items()}
    except AbortError as e:
        err = f"aborted: {e}"
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc(limit=3)
        err = f"exception: {type(e).__name__}: {e} | {tb.splitlines()[-2].strip() if len(tb.splitlines()) > 1 else ''}"
    traj = robot.trajectory()
    traj["box_z0"] = np.float64(robot._box_z0)
    np.savez_compressed(os.path.join(out_dir, "traj.npz"), **traj)
    with open(os.path.join(out_dir, "child.json"), "w") as f:
        json.dump({"error": err, "jitter": jitter.tolist()}, f)


def score(traj, mass_kg, error=None):
    t = traj["time"]
    q = traj["qpos"]
    box_z = q[:, -5]           # box freejoint is the last joint: x y z qw qx qy qz
    z0 = float(traj["box_z0"]) if "box_z0" in traj else float(box_z[0])
    rise = box_z - z0
    pelvis_z = q[:, 2]
    assist = traj["assist_force"]
    slip = traj["box_slip"]
    fell_idx = np.where(pelvis_z < FALL_Z)[0]
    fell = bool(len(fell_idx))
    lifted_ever = rise > 0.10
    dropped = False
    if lifted_ever.any():
        after = np.arange(len(t)) > np.argmax(lifted_ever)
        dropped = bool(np.any(after & (rise < 0.03)) or np.max(slip) > DROP_SLIP_M)
    # longest contiguous hold above RISE_M (before any fall)
    up = rise >= RISE_M
    if fell:
        up[fell_idx[0]:] = False
    held, best, start = 0.0, 0.0, None
    dt = np.diff(t, prepend=t[0])
    for i, u in enumerate(up):
        if u:
            held += dt[i] if start is not None else 0.0
            start = i if start is None else start
            best = max(best, held)
        else:
            held, start = 0.0, None
    res = {
        "success": False,
        "mass_kg": float(mass_kg),
        "box_rise_m": round(float(rise.max()), 4),
        "held_s": round(float(best), 3),
        "max_assist_n": round(float(assist.max()), 2),
        "mean_assist_n": round(float(assist.mean()), 2),
        "peak_tau_frac": round(float(traj["tau_frac"].max()), 3),
        "max_slip_m": round(float(slip.max()), 4),
        "fell": fell,
        "dropped": dropped,
        "fail_reason": None,
    }
    # peak torque among body joints only (fingers saturate trivially)
    names = [str(n) for n in traj.get("joint_names", [])]
    if names:
        body = [i for i, n in enumerate(names) if "hand" not in n]
        res["peak_tau_frac"] = round(float(traj["tau_frac"][:, body].max()), 3)
    if fell and error and (error.startswith("physics") or error.startswith("dropped the box")):
        # the fall happened first; whatever the solver did afterwards does not change the outcome
        reason = f"fell (pelvis below {FALL_Z} m at t={t[fell_idx[0]]:.1f}s); sim stopped after the fall"
    elif error:
        reason = error
    elif fell:
        reason = f"fell (pelvis below {FALL_Z} m at t={t[fell_idx[0]]:.1f}s)"
    elif dropped:
        reason = "dropped the box (slipped out of the hands)"
    elif rise.max() < RISE_M:
        reason = f"box rose only {rise.max():.2f} m (< {RISE_M} m)"
    elif best < HOLD_S:
        reason = f"held only {best:.1f} s (< {HOLD_S} s)"
    elif res["mean_assist_n"] > ASSIST_BUDGET:
        reason = f"balance assist too high (mean {res['mean_assist_n']:.0f} N > {ASSIST_BUDGET:.0f} N budget)"
    else:
        reason = None
    res["success"] = reason is None
    res["fail_reason"] = reason
    return res


def run_trial(controller_path, mass_kg, seed, out_dir, use_assist=True) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    controller_path = os.path.abspath(controller_path)
    cmd = [sys.executable, "-m", "sim.trial", "--_child", controller_path, str(mass_kg), str(seed),
           os.path.abspath(out_dir), "1" if use_assist else "0"]
    err = None
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=WALL_TIMEOUT_S)
        if p.returncode != 0:
            err = "crash: " + (p.stderr.strip().splitlines() or ["?"])[-1][:300]
    except subprocess.TimeoutExpired:
        err = f"wall-clock timeout ({WALL_TIMEOUT_S}s)"
    child_json = os.path.join(out_dir, "child.json")
    if os.path.exists(child_json):
        with open(child_json) as f:
            err = json.load(f).get("error") or err
    traj_path = os.path.join(out_dir, "traj.npz")
    if not os.path.exists(traj_path):
        res = {"success": False, "mass_kg": float(mass_kg), "box_rise_m": 0.0, "held_s": 0.0,
               "max_assist_n": 0.0, "mean_assist_n": 0.0, "peak_tau_frac": 0.0, "max_slip_m": 0.0,
               "fell": False, "dropped": False, "fail_reason": err or "no trajectory written"}
    else:
        traj = dict(np.load(traj_path))
        res = score(traj, mass_kg, err)
    with open(os.path.join(out_dir, "result.json"), "w") as f:
        json.dump(res, f, indent=2)
    return res


def _one(args):
    ctrl, mass, seed, out, assist = args
    return run_trial(ctrl, mass, seed, os.path.join(out, f"m{int(mass):02d}"), assist)


def sweep(controller_path, masses, out, seed=0, use_assist=True, workers=8):
    jobs = [(controller_path, m, seed, out, use_assist) for m in masses]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_one, jobs))
    return results


def print_table(results):
    print(f"{'mass':>5} {'ok':>4} {'rise':>6} {'held':>5} {'assist':>7} {'tau':>5} {'slip':>6}  reason")
    for r in results:
        print(f"{r['mass_kg']:5.0f} {'PASS' if r['success'] else 'fail':>4} {r['box_rise_m']:6.2f} {r['held_s']:5.1f} "
              f"{r['mean_assist_n']:7.1f} {r['peak_tau_frac']:5.2f} {r['max_slip_m']:6.3f}  {r['fail_reason'] or ''}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--_child":
        _, _, ctrl, mass, seed, out, assist = sys.argv
        _child(ctrl, float(mass), int(seed), out, assist == "1")
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("controller")
    ap.add_argument("--masses", default="5,10,15,20,25,30,35,40")
    ap.add_argument("--out", default="runs/sweep")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-assist", action="store_true")
    a = ap.parse_args()
    masses = [float(x) for x in a.masses.split(",")]
    res = sweep(a.controller, masses, a.out, a.seed, not a.no_assist)
    print_table(res)
    with open(os.path.join(a.out, "sweep.json"), "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
