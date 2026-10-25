"""Stand-ins for sim/trial.py and sim/render.py with the PLAN.md signatures (for testing the loop only).

run_trial executes the controller against a FakeRobot that accepts every PLAN.md API call, so a controller that
calls a non-existent method or crashes is reported as a failure, like the real runner would.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import traceback

import numpy as np

FPS = 30


class FakeRobot:
    def __init__(self, mass):
        self.box_mass_kg = float(mass)
        self.box_size = (0.4, 0.3, 0.25)
        self._t = 0.0
        self._phase = ""
        self._log = []  # (t, phase)
        self._squat = 0.0

    def _adv(self, s):
        s = max(0.0, float(s))
        n = max(1, int(s * FPS))
        for _ in range(n):
            self._t += 1.0 / FPS
            self._log.append((self._t, self._phase, self._squat))
        if self._t > 30:
            raise TimeoutError("30 s sim-time cap")

    # reads
    def box_pose(self): return (np.array([0.45, 0.0, 0.125]), np.array([1.0, 0, 0, 0]))
    def limits(self): return {n: 100.0 for n in self.joint_names()}
    def com(self): return np.array([0.02, 0.0, 0.6])
    def support_polygon(self): return np.array([[-0.08, 0.15], [0.16, 0.15], [0.16, -0.15], [-0.08, -0.15]])
    def joint_names(self): return ["left_hip_pitch_joint", "left_knee_joint", "waist_pitch_joint", "left_elbow_joint"]
    def q(self): return {n: 0.0 for n in self.joint_names()}
    def joint_torques(self): return {n: 0.0 for n in self.joint_names()}
    def hand_box_slip(self): return 0.0
    def time(self): return self._t

    # motion
    def set_posture(self, targets, duration_s, profile="minjerk"): self._adv(duration_s)
    def squat(self, depth_m, duration_s): self._squat = depth_m; self._adv(duration_s)
    def hands_to(self, left_xyz, right_xyz, duration_s): self._adv(duration_s)
    def squeeze(self, force_n): self._adv(0.05)
    def release(self): self._adv(0.05)

    # control
    def wait(self, s): self._adv(s)
    def phase(self, label): self._phase = str(label)
    def abort(self, reason): raise RuntimeError(f"abort: {reason}")


def run_trial(controller_path, mass_kg, seed, out_dir, use_assist=True) -> dict:
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    code = pathlib.Path(controller_path).read_text()
    robot = FakeRobot(mass_kg)
    err = None
    try:
        ns: dict = {}
        exec(compile(code, str(controller_path), "exec"), ns)
        ns["run"](robot)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}\n" + traceback.format_exc(limit=3)[-600:]
    if not robot._log:
        robot._adv(1.0)
    T = len(robot._log)
    t = np.array([x[0] for x in robot._log])
    # fake capability: hashed from the code, so different controllers score differently
    cap = 12 + int(hashlib.md5(code.encode()).hexdigest(), 16) % 25
    ok = err is None and mass_kg <= cap
    frac = np.clip(mass_kg / cap, 0, 2)
    rise = np.clip(t / max(t[-1], 1e-6), 0, 1) * (0.55 if ok else 0.2)
    qpos = np.zeros((T, 50))
    qpos[:, 2] = 0.75 - 0.2 * np.sin(np.pi * t / max(t[-1], 1e-6))
    qpos[:, 43 + 2] = 0.125 + rise  # pretend box freejoint at the end
    nu = 43
    tau = np.clip(np.random.default_rng(seed).uniform(0.2, 0.6, (T, nu)) * frac, 0, 1)
    assist = 20 + 150 * max(0.0, frac - 0.8) * np.sin(np.pi * t / max(t[-1], 1e-6)) ** 2
    com_margin = 0.06 - 0.08 * frac * np.sin(np.pi * t / max(t[-1], 1e-6)) ** 2
    slip = np.cumsum(np.full(T, 0.0005 * max(0.0, frac - 0.9)))
    np.savez(out / "traj.npz", qpos=qpos, time=t, box_mass=float(mass_kg), assist_force=assist, tau_frac=tau,
             com_margin=com_margin, box_slip=slip, phase=np.array([x[1] for x in robot._log]))
    res = {"success": bool(ok), "mass_kg": mass_kg, "box_rise_m": round(float(rise.max()), 3),
           "held_s": 3.5 if ok else 0.0, "max_assist_n": round(float(assist.max()), 1),
           "mean_assist_n": round(float(assist.mean()), 1), "peak_tau_frac": round(float(tau.max()), 2),
           "max_slip_m": round(float(slip.max()), 3), "fell": bool(not ok and frac > 1.3),
           "dropped": bool(not ok and frac <= 1.3 and err is None),
           "fail_reason": None if ok else (("controller_error: " + err) if err else "stub: mass above capability")}
    (out / "result.json").write_text(json.dumps(res, indent=2))
    return res


def render_traj(traj_npz, out_mp4, camera="hero", hud=True, size=(1280, 720), fps=30):
    import imageio.v2 as imageio
    d = np.load(traj_npz, allow_pickle=True)
    t = d["time"]
    W, H = size
    col = (200, 60, 60) if camera == "hero" else (60, 60, 200)
    with imageio.get_writer(out_mp4, fps=fps, codec="libx264", macro_block_size=8) as w:
        for i in range(0, len(t)):
            f = np.full((H, W, 3), 235, np.uint8)
            y = int(H * 0.8 - (d["qpos"][i, 45] - 0.125) * H)
            x = int(W * 0.4)
            f[max(0, y - 20):y + 20, x:x + 60] = col
            w.append_data(f)
    return str(out_mp4)
