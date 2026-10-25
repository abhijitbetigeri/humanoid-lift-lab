"""Fake, schema-valid traj.npz for developing the renderer before sim/trial.py exists.

Kinematic only: interpolates the 'stand' keyframe into a squat, grips, stands up with the box, holds.
Usage: .venv/bin/python sim/fake_traj.py runs/w2_fake [--mass 30] [--fail]
"""
import argparse
import json
import os

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(HERE, "g1", "scene_lift.xml")


def smooth(s):
    s = np.clip(s, 0, 1)
    return s * s * s * (10 - 15 * s + 6 * s * s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--mass", type=float, default=30.0)
    ap.add_argument("--fail", action="store_true", help="write a failing result.json")
    ap.add_argument("--seconds", type=float, default=8.0)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    m = mujoco.MjModel.from_xml_path(SCENE)
    d = mujoco.MjData(m)
    key = m.key("stand").id
    q_stand = m.key_qpos[key].copy()

    def jadr(name):
        return m.jnt_qposadr[m.joint(name).id]

    crouch = {
        "left_hip_pitch_joint": -1.25, "right_hip_pitch_joint": -1.25,
        "left_knee_joint": 1.95, "right_knee_joint": 1.95,
        "left_ankle_pitch_joint": -0.65, "right_ankle_pitch_joint": -0.65,
        "waist_pitch_joint": 0.35,
        "left_shoulder_pitch_joint": -0.9, "right_shoulder_pitch_joint": -0.9,
        "left_shoulder_roll_joint": 0.25, "right_shoulder_roll_joint": -0.25,
        "left_elbow_joint": 0.35, "right_elbow_joint": 0.35,
    }
    carry = {
        "left_shoulder_pitch_joint": -0.6, "right_shoulder_pitch_joint": -0.6,
        "left_shoulder_roll_joint": 0.2, "right_shoulder_roll_joint": -0.2,
        "left_elbow_joint": 0.5, "right_elbow_joint": 0.5,
    }
    bz = m.jnt_qposadr[m.joint("box").id]
    box0 = m.body_pos[m.body("box").id].copy()
    foot_ids = [m.body("left_ankle_roll_link").id, m.body("right_ankle_roll_link").id]

    fps = 30
    T = int(a.seconds * fps)
    t = np.arange(T) / fps
    qpos = np.zeros((T, m.nq))
    phase = []
    # timeline: 0-0.8 stand, 0.8-3.0 squat, 3.0-3.8 grip, 3.8-6.0 lift, 6.0-end hold
    foot_ref = None
    for i, ti in enumerate(t):
        q = q_stand.copy()
        if ti < 0.8:
            s, lab = 0.0, "approach"
        elif ti < 3.0:
            s, lab = smooth((ti - 0.8) / 2.2), "squat"
        elif ti < 3.8:
            s, lab = 1.0, "grip"
        elif ti < 6.0:
            s, lab = 1.0 - smooth((ti - 3.8) / 2.2), "lift"
        else:
            s, lab = 0.0, "hold"
        lifted = ti >= 3.8
        for k, v in crouch.items():
            if lifted and k in carry:  # arms go from the grip pose to a carry pose
                q[jadr(k)] = carry[k] + (v - carry[k]) * s
            else:
                q[jadr(k)] = q_stand[jadr(k)] + (v - q_stand[jadr(k)]) * s
        # keep feet planted: forward-kinematics, then shift the pelvis
        d.qpos[:] = q
        mujoco.mj_kinematics(m, d)
        fpos = np.mean([d.xpos[b] for b in foot_ids], axis=0)
        if foot_ref is None:
            foot_ref = fpos.copy()
        q[0:3] += foot_ref - fpos
        # box: on the floor until the lift, then follows the hands
        d.qpos[:] = q
        mujoco.mj_kinematics(m, d)
        if lifted:
            hl = d.xpos[m.body("left_wrist_yaw_link").id]
            hr = d.xpos[m.body("right_wrist_yaw_link").id]
            hc = (hl + hr) / 2
            z = max(0.15, hc[2] - 0.05)
            q[bz:bz + 3] = [box0[0] if ti < 4 else max(box0[0] - 0.1, hc[0] + 0.12), 0.0, max(box0[2], z)]
        else:
            q[bz:bz + 3] = box0
        q[bz + 3:bz + 7] = [1, 0, 0, 0]
        qpos[i] = q
        phase.append(lab)

    lift_s = np.clip((t - 3.8) / 2.2, 0, 1)
    com_margin = 0.06 - 0.07 * np.sin(np.pi * lift_s) * (a.mass / 40.0) + 0.005 * np.sin(7 * t)
    assist = np.where((t > 3.8) & (t < 6.5), 40 * a.mass / 40 * np.sin(np.pi * lift_s) + 5, 2.0)
    tau = np.zeros((T, m.nu))
    load = 0.25 + 0.6 * np.sin(np.pi * np.clip((t - 0.8) / 5.2, 0, 1)) * (0.4 + a.mass / 40)
    for j in range(m.nu):
        tau[:, j] = np.clip(load * (0.6 + 0.4 * ((j * 37) % 11) / 10) + 0.02 * np.sin(3 * t + j), 0, 1.2)
    slip = np.where(t > 3.8, 0.004 * (t - 3.8) * a.mass / 20, 0.0)

    np.savez(os.path.join(a.out_dir, "traj.npz"), qpos=qpos, time=t, box_mass=np.float64(a.mass),
             assist_force=assist, tau_frac=tau, com_margin=com_margin, box_slip=slip, phase=np.array(phase))
    res = {"success": not a.fail, "mass_kg": a.mass, "box_rise_m": 0.5, "held_s": 3.2,
           "max_assist_n": float(assist.max()), "mean_assist_n": float(assist.mean()),
           "peak_tau_frac": float(tau.max()), "max_slip_m": float(slip.max()), "fell": False,
           "dropped": bool(a.fail), "fail_reason": "box slipped from the hands" if a.fail else ""}
    with open(os.path.join(a.out_dir, "result.json"), "w") as f:
        json.dump(res, f, indent=1)
    print("wrote", a.out_dir, qpos.shape)


if __name__ == "__main__":
    main()
