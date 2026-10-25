"""Humanoid API for generated lift controllers (W1).

A controller file defines ``def run(robot): ...`` and may only use the methods below.
Every motion call advances physics (MuJoCo, 500 Hz) and records frames at 30 fps.

Physics notes (see docs/calibration.md):
  * Strength is scaled at runtime from the stock Unitree G1 to an Apollo/Atlas-class humanoid
    (STRENGTH table below); the XML is untouched.
  * Balance assist = a PD "hand of god" on the pelvis (horizontal force from the capture point leaving
    the support polygon, roll/pitch damping torque, weak anti-collapse vertical support).
    Its magnitude is logged every step and is what the scorer budgets.
  * Grip is friction only: squeeze(force_n) moves both palms inward (arm IK) and applies an equal and
    opposite inward force pair on the two palms (net zero external force, like an internal actuator),
    capped at GRIP_MAX_N per palm.
"""
from __future__ import annotations

import math
import os

import mujoco
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(HERE, "g1", "scene_lift.xml")

FPS = 30
SIM_CAP_S = 30.0
TIMESTEP = 0.001
NOSLIP_ITERS = 10            # noslip pass: removes soft-constraint creep at the palm/tote friction contacts

# joint-name substring -> (torque limit N·m, position gain kp N·m/rad).  Stock G1 in comments.
STRENGTH = [
    ("hip_pitch", 320.0, 2500.0),      # G1 88
    ("hip_roll", 300.0, 2000.0),       # G1 139
    ("hip_yaw", 200.0, 1500.0),        # G1 88
    ("knee", 400.0, 3000.0),           # G1 139
    ("ankle_pitch", 200.0, 2000.0),    # G1 50
    ("ankle_roll", 150.0, 1500.0),     # G1 50
    ("waist_yaw", 200.0, 2000.0),      # G1 88
    ("waist_roll", 250.0, 2500.0),     # G1 50
    ("waist_pitch", 250.0, 2500.0),    # G1 50
    ("shoulder", 150.0, 1200.0),       # G1 25
    ("elbow", 120.0, 1000.0),          # G1 25
    ("wrist_roll", 60.0, 400.0),       # G1 25
    ("wrist", 40.0, 300.0),            # G1 5 (pitch/yaw)
]
MASS_SCALE = 1.0           # keep G1 link masses (34.4 kg); x2 tested, made balance worse (see docs)
GRIP_MAX_N = 450.0          # max inward squeeze per palm (N)
SQUEEZE_IN_M = 0.03         # extra inward IK offset per palm while squeezing

# balance assist gains
ASSIST_KP = 3000.0          # N per m of capture-point excess outside the (shrunk) support polygon
ASSIST_KD = 300.0           # N per m/s of CoM velocity while outside
ASSIST_MAX_XY = 600.0
ASSIST_ROLLPITCH_D = 30.0   # N·m per rad/s
ASSIST_ROLL_P = 150.0       # N·m per rad (roll only; pitch is free so stoops are possible)
ASSIST_Z_FLOOR = 0.50       # vertical support only below this pelvis height
ASSIST_KZ = 3000.0
ASSIST_MAX_Z = 300.0
ASSIST_TORQUE_LEVER = 0.5   # torque counted as force at this lever arm in the logged magnitude
POLY_SHRINK = 0.02

ARM_JOINTS = ["shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow",
              "wrist_roll", "wrist_pitch", "wrist_yaw"]
PALM_LOCAL = np.array([0.08, 0.0, 0.0])   # palm centre in the wrist_yaw_link frame
FINGER_DIR = np.array([0.97, 0.0, -0.25])   # preferred finger direction (pelvis frame): forward and down


class AbortError(Exception):
    pass


class SimTimeout(Exception):
    pass


class PhysicsDiverged(Exception):
    pass


class BoxEjected(PhysicsDiverged):
    """The tote got wedged between the hands and the legs/pelvis and was squeezed out (a physical failure)."""
    pass


def _minjerk(s):
    s = min(max(s, 0.0), 1.0)
    return 10 * s ** 3 - 15 * s ** 4 + 6 * s ** 5


class Humanoid:
    def __init__(self, box_mass_kg=10.0, box_offset=(0.0, 0.0), use_assist=True, scene=SCENE):
        self.m = mujoco.MjModel.from_xml_path(scene)
        m = self.m
        self._apply_strength()
        bid = m.body("box").id
        m.body_mass[bid] = float(box_mass_kg)
        gid = m.geom("box").id
        size = m.geom_size[gid].copy()
        m.body_inertia[bid] = box_mass_kg / 3.0 * np.array(
            [size[1] ** 2 + size[2] ** 2, size[0] ** 2 + size[2] ** 2, size[0] ** 2 + size[1] ** 2])
        m.opt.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
        m.opt.impratio = 5.0
        m.opt.noslip_iterations = NOSLIP_ITERS
        m.opt.timestep = TIMESTEP
        self.d = mujoco.MjData(m)
        self.d_ik = mujoco.MjData(m)
        mujoco.mj_resetDataKeyframe(m, self.d, m.key("stand").id)
        self.d.qpos[m.jnt_qposadr[m.joint("box").id] + 0] += box_offset[0]
        self.d.qpos[m.jnt_qposadr[m.joint("box").id] + 1] += box_offset[1]
        self.d.ctrl[:] = m.key_ctrl[m.key("stand").id]
        mujoco.mj_forward(m, self.d)

        self.box_mass_kg = float(box_mass_kg)
        self.box_size = tuple(float(2 * s) for s in size)  # full x, y, z extents (m)
        self.use_assist = use_assist
        self._names = [m.actuator(i).name for i in range(m.nu)]
        self._act_dof = np.array([m.jnt_dofadr[m.actuator_trnid[i, 0]] for i in range(m.nu)])
        self._act_jnt = np.array([m.actuator_trnid[i, 0] for i in range(m.nu)])
        self._lim = np.array([m.jnt_actfrcrange[j, 1] for j in self._act_jnt])
        self._target = self.d.ctrl.copy()
        self._pelvis = m.body("pelvis").id
        self._box = bid
        self._box_qadr = m.jnt_qposadr[m.joint("box").id]
        self._box_dadr = m.jnt_dofadr[m.joint("box").id]
        self._hand = {s: m.body(f"{s}_wrist_yaw_link").id for s in ("left", "right")}
        self._arm_act = {s: [self._names.index(f"{s}_{j}_joint") for j in ARM_JOINTS] for s in ("left", "right")}
        self._foot_geoms = [g for g in range(m.ngeom)
                            if "ankle_roll" in m.body(m.geom_bodyid[g]).name and m.geom_contype[g]]
        # reference orientation of each hand's local y axis (pelvis frame) from the stand pose
        self._hand_y_ref = {s: np.array([0.0, 1.0, 0.0]) * np.sign(self.d.xmat[self._hand[s]].reshape(3, 3)[1, 1])
                            for s in self._hand}
        self._grip_n = 0.0
        self._hand_targets = None
        self._slip_ref = None
        self._phase = "start"
        self._assist_now = 0.0
        self._next_frame_t = 0.0
        self.log = {k: [] for k in ("qpos", "time", "assist_force", "tau_frac", "com_margin",
                                     "box_slip", "phase")}
        self._record()

    # ------------------------------------------------------------------ setup
    def _apply_strength(self):
        m = self.m
        # Apollo/Atlas-class body: scale the G1 links' mass and inertia (35 kg -> ~70 kg)
        for b in range(1, m.nbody):
            if m.body(b).name != "box":
                m.body_mass[b] *= MASS_SCALE
                m.body_inertia[b] *= MASS_SCALE
        for i in range(m.nu):
            j = m.actuator_trnid[i, 0]
            name = m.joint(j).name
            if "hand" in name:
                continue
            for key, lim, kp in STRENGTH:
                if key in name:
                    old_kp = m.actuator_gainprm[i, 0]
                    m.jnt_actfrcrange[j] = [-lim, lim]
                    m.actuator_gainprm[i, 0] = kp
                    m.actuator_biasprm[i, 1] = -kp
                    m.actuator_biasprm[i, 2] *= math.sqrt(kp / old_kp)
                    break

    # ------------------------------------------------------------------ reads
    def joint_names(self):
        return list(self._names)

    def q(self):
        return {n: float(self.d.qpos[self.m.jnt_qposadr[j]]) for n, j in zip(self._names, self._act_jnt)}

    def joint_torques(self):
        return {n: float(self.d.qfrc_actuator[a]) for n, a in zip(self._names, self._act_dof)}

    def limits(self):
        m = self.m
        return {n: {"torque_nm": float(self._lim[i]),
                    "range_rad": (float(m.jnt_range[j, 0]), float(m.jnt_range[j, 1]))}
                for i, (n, j) in enumerate(zip(self._names, self._act_jnt))}

    def time(self):
        return float(self.d.time)

    def box_pose(self):
        """World position (x, y, z) and quaternion (w, x, y, z) of the tote centre."""
        q = self.d.qpos[self._box_qadr:self._box_qadr + 7]
        return {"pos": tuple(float(v) for v in q[:3]), "quat": tuple(float(v) for v in q[3:])}

    def com(self):
        """Whole-system centre of mass (robot + held box counts only via contact; this is the robot's
        CoM plus the box if the box is off the floor), world frame."""
        return tuple(float(v) for v in self._com_world())

    def _com_world(self):
        d, m = self.d, self.m
        rob = d.subtree_com[self._pelvis] * m.body_subtreemass[self._pelvis]
        mass = m.body_subtreemass[self._pelvis]
        if self._box_lifted():
            rob = rob + d.xipos[self._box] * m.body_mass[self._box]
            mass += m.body_mass[self._box]
        return rob / mass

    def _box_lifted(self):
        return self.d.xpos[self._box][2] > self._box_z0 + 0.01 if hasattr(self, "_box_z0") else False

    def support_polygon(self):
        """Axis-aligned support rectangle of both feet (world xy corners, CCW)."""
        xmin, xmax, ymin, ymax = self._poly()
        return [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]

    def _poly(self):
        p = self.d.geom_xpos[self._foot_geoms]
        r = 0.005
        return (float(p[:, 0].min() - r), float(p[:, 0].max() + r),
                float(p[:, 1].min() - r), float(p[:, 1].max() + r))

    def com_margin(self):
        xmin, xmax, ymin, ymax = self._poly()
        c = self._com_world()
        return float(min(c[0] - xmin, xmax - c[0], c[1] - ymin, ymax - c[1]))

    def _palm_world(self, side):
        b = self._hand[side]
        return self.d.xpos[b] + self.d.xmat[b].reshape(3, 3) @ PALM_LOCAL

    def hand_box_slip(self):
        """Box displacement (m) relative to the midpoint of the palms since the squeeze started."""
        if self._slip_ref is None:
            return 0.0
        rel = self.d.xpos[self._box] - 0.5 * (self._palm_world("left") + self._palm_world("right"))
        return float(np.linalg.norm(rel - self._slip_ref))

    def pelvis_height(self):
        return float(self.d.qpos[2])

    # ------------------------------------------------------------------ physics loop
    def _assist(self):
        d, m = self.d, self.m
        d.xfrc_applied[:] = 0.0
        mag = 0.0
        if self.use_assist:
            mr = m.body_subtreemass[self._pelvis]
            c = d.subtree_com[self._pelvis].copy()
            v = d.subtree_linvel[self._pelvis].copy()
            if self._box_lifted():  # a held load counts toward the balance point
                mb = m.body_mass[self._box]
                c = (mr * c + mb * d.xipos[self._box]) / (mr + mb)
                v = (mr * v + mb * d.qvel[self._box_dadr:self._box_dadr + 3]) / (mr + mb)
            omega = math.sqrt(9.81 / max(c[2], 0.2))
            cp = c[:2] + v[:2] / omega
            xmin, xmax, ymin, ymax = self._poly()
            s = POLY_SHRINK
            inside = np.array([min(max(cp[0], xmin + s), xmax - s), min(max(cp[1], ymin + s), ymax - s)])
            exc = cp - inside
            f = np.zeros(3)
            if np.any(exc != 0):
                f[:2] = -ASSIST_KP * exc - ASSIST_KD * v[:2] * (exc != 0)
                n = np.linalg.norm(f[:2])
                if n > ASSIST_MAX_XY:
                    f[:2] *= ASSIST_MAX_XY / n
            z = d.qpos[2]
            if z < ASSIST_Z_FLOOR:
                f[2] = min(ASSIST_KZ * (ASSIST_Z_FLOOR - z) - 50.0 * d.qvel[2], ASSIST_MAX_Z)
                f[2] = max(f[2], 0.0)
            w = d.qvel[3:6]  # pelvis angular velocity (local frame)
            R = d.xmat[self._pelvis].reshape(3, 3)
            w_world = R @ w
            roll = math.atan2(R[2, 1], R[2, 2])
            tau = np.zeros(3)
            tau[:2] = -ASSIST_ROLLPITCH_D * w_world[:2]
            tau[0] += -ASSIST_ROLL_P * roll
            d.xfrc_applied[self._pelvis, :3] = f
            d.xfrc_applied[self._pelvis, 3:] = tau
            mag = float(np.linalg.norm(f) + np.linalg.norm(tau) / ASSIST_TORQUE_LEVER)
        if self._grip_n > 0:
            pl, pr = self._palm_world("left"), self._palm_world("right")
            u = pr - pl
            u[2] = 0.0
            n = np.linalg.norm(u)
            if n > 1e-6:
                u /= n
                d.xfrc_applied[self._hand["left"], :3] += self._grip_n * u
                d.xfrc_applied[self._hand["right"], :3] -= self._grip_n * u
        self._assist_now = mag

    def _step(self, n=1):
        for _ in range(n):
            if self.d.time >= SIM_CAP_S:
                raise SimTimeout(f"sim time cap {SIM_CAP_S}s reached")
            self._assist()
            mujoco.mj_step(self.m, self.d)
            if (not np.isfinite(self.d.qacc).all() or np.abs(self.d.qvel[:6]).max() > 50.0
                    or np.abs(self.d.qvel[self._box_dadr:self._box_dadr + 6]).max() > 50.0):
                legs = [self.m.body(self.m.geom_bodyid[g]).name for c in self.d.contact[:self.d.ncon]
                        for g in (c.geom1, c.geom2)
                        if self._box in (self.m.geom_bodyid[c.geom1], self.m.geom_bodyid[c.geom2])
                        and any(k in self.m.body(self.m.geom_bodyid[g]).name for k in ("knee", "hip", "pelvis"))]
                if legs and np.isfinite(self.d.qacc).all():
                    raise BoxEjected("tote jammed against the legs (%s) and was squeezed out of the hands"
                                     % ", ".join(sorted(set(legs))))
                raise PhysicsDiverged("simulation became unstable (contact explosion)")
            if not hasattr(self, "_box_z0"):
                self._box_z0 = float(self.d.xpos[self._box][2])
            if self.d.time + 1e-9 >= self._next_frame_t:
                self._record()

    def _record(self):
        d = self.d
        if not hasattr(self, "_box_z0"):
            self._box_z0 = float(d.xpos[self._box][2])
        L = self.log
        L["qpos"].append(d.qpos.copy())
        L["time"].append(float(d.time))
        L["assist_force"].append(self._assist_now)
        L["tau_frac"].append(np.minimum(np.abs(d.qfrc_actuator[self._act_dof]) / self._lim, 1.0))
        L["com_margin"].append(self.com_margin())
        L["box_slip"].append(self.hand_box_slip())
        L["phase"].append(self._phase)
        self._next_frame_t += 1.0 / FPS

    def trajectory(self):
        L = self.log
        return {
            "qpos": np.array(L["qpos"]), "time": np.array(L["time"]),
            "box_mass": np.float64(self.box_mass_kg),
            "assist_force": np.array(L["assist_force"]),
            "tau_frac": np.array(L["tau_frac"]), "com_margin": np.array(L["com_margin"]),
            "box_slip": np.array(L["box_slip"]), "phase": np.array(L["phase"], dtype=str),
            "joint_names": np.array(self._names, dtype=str),
        }

    # ------------------------------------------------------------------ motion
    def set_posture(self, targets, duration_s=1.0, profile="minjerk"):
        """Move the listed joints (name -> rad; '_joint' suffix optional) to targets over duration_s."""
        start = self._target.copy()
        goal = start.copy()
        for k, v in targets.items():
            name = k if k.endswith("_joint") else k + "_joint"
            if name not in self._names:
                raise KeyError(f"unknown joint {k}")
            i = self._names.index(name)
            lo, hi = self.m.actuator_ctrlrange[i]
            goal[i] = min(max(float(v), lo), hi)
        steps = max(1, int(round(duration_s / self.m.opt.timestep)))
        for k in range(1, steps + 1):
            s = k / steps
            a = _minjerk(s) if profile == "minjerk" else s
            self._target = start + a * (goal - start)
            self.d.ctrl[:] = self._target
            self._step()

    def _leg_angles(self, depth_m, hip_back=0.0):
        L1, L2 = 0.337, 0.300
        h = max(L1 + L2 - depth_m, 0.25)
        # hip_back = how far the hip sits behind the ankle (m).
        # L2 sin b - L1 sin a = -hip_back ; L1 cos a + L2 cos b = h
        lo, hi = 0.0, math.pi / 2
        a = b = 0.0
        for _ in range(60):
            a = 0.5 * (lo + hi)
            b = math.asin(min(1.0, max(-1.0, (L1 * math.sin(a) - hip_back) / L2)))
            if L1 * math.cos(a) + L2 * math.cos(b) > h:
                lo = a
            else:
                hi = a
        return a, b

    def squat(self, depth_m, duration_s=1.5, torso_pitch=0.0, hip_back=0.0):
        """Lower the pelvis by depth_m (0 = stand). hip_back (m) sits the hips back behind the ankles;
        torso_pitch (rad, > 0 = forward) leans the trunk via the hips. Other joints keep their targets."""
        a, b = self._leg_angles(depth_m, hip_back)
        t = {}
        for s in ("left", "right"):
            t[f"{s}_hip_pitch"] = -a - torso_pitch
            t[f"{s}_knee"] = a + b
            t[f"{s}_ankle_pitch"] = -b
        self.set_posture(t, duration_s)

    def _ik(self, side, target, iters=80):
        m, d = self.m, self.d_ik
        d.qpos[:] = self.d.qpos
        d.qpos[0:3] = 0.0
        d.qpos[3:7] = [1, 0, 0, 0]
        for i, j in enumerate(self._act_jnt):
            d.qpos[m.jnt_qposadr[j]] = self._target[i]
        acts = self._arm_act[side]
        qadr = [m.jnt_qposadr[self._act_jnt[i]] for i in acts]
        dadr = [m.jnt_dofadr[self._act_jnt[i]] for i in acts]
        b = self._hand[side]
        yref = self._hand_y_ref[side]
        jacp = np.zeros((3, m.nv))
        jacr = np.zeros((3, m.nv))
        lam = 0.05
        for _ in range(iters):
            mujoco.mj_kinematics(m, d)
            mujoco.mj_comPos(m, d)
            R = d.xmat[b].reshape(3, 3)
            p = d.xpos[b] + R @ PALM_LOCAL
            e_p = np.asarray(target) - p
            e_r = 0.5 * (np.cross(R[:, 1], yref) + np.cross(R[:, 0], FINGER_DIR)) * 0.3
            mujoco.mj_jac(m, d, jacp, jacr, p, b)
            J = np.vstack([jacp[:, dadr], 0.3 * jacr[:, dadr]])
            e = np.concatenate([e_p, e_r])
            if np.linalg.norm(e_p) < 1e-3:
                break
            dq = J.T @ np.linalg.solve(J @ J.T + lam ** 2 * np.eye(6), e)
            for k, qa in enumerate(qadr):
                jid = self._act_jnt[acts[k]]
                lo, hi = m.jnt_range[jid]
                d.qpos[qa] = min(max(d.qpos[qa] + dq[k], lo), hi)
        sol = {self._names[i]: float(d.qpos[qa]) for i, qa in zip(acts, qadr)}
        return sol, float(np.linalg.norm(e_p))

    def hands_to(self, left_xyz, right_xyz, duration_s=1.0):
        """Move the palm centres to points in the pelvis frame (x forward, y left, z up) by arm IK.
        Returns the residual IK error (m) per hand."""
        self._hand_targets = (np.array(left_xyz, float), np.array(right_xyz, float))
        lt, rt = self._hand_targets
        if self._grip_n > 0:
            lt = lt + np.array([0, -SQUEEZE_IN_M, 0])
            rt = rt + np.array([0, SQUEEZE_IN_M, 0])
        sl, el = self._ik("left", lt)
        sr, er = self._ik("right", rt)
        sl.update(sr)
        self.set_posture(sl, duration_s)
        return {"left_err_m": el, "right_err_m": er}

    def squeeze(self, force_n):
        """Press the palms inward on the box with force_n per palm (capped at GRIP_MAX_N)."""
        self._grip_n = float(min(max(force_n, 0.0), GRIP_MAX_N))
        if self._hand_targets is not None:
            self.hands_to(*self._hand_targets, duration_s=0.3)
        rel = self.d.xpos[self._box] - 0.5 * (self._palm_world("left") + self._palm_world("right"))
        self._slip_ref = rel.copy()
        return self._grip_n

    def release(self):
        self._grip_n = 0.0
        self._slip_ref = None
        if self._hand_targets is not None:
            lt, rt = self._hand_targets
            self.hands_to(lt + [0, 0.06, 0], rt + [0, -0.06, 0], duration_s=0.5)

    def wait(self, s):
        self._step(max(1, int(round(s / self.m.opt.timestep))))

    def phase(self, label):
        self._phase = str(label)

    def abort(self, reason):
        raise AbortError(str(reason))

    def pelvis_frame_to_world(self, xyz):
        R = self.d.xmat[self._pelvis].reshape(3, 3)
        return tuple(float(v) for v in self.d.xpos[self._pelvis] + R @ np.asarray(xyz))

    def world_to_pelvis_frame(self, xyz):
        R = self.d.xmat[self._pelvis].reshape(3, 3)
        return tuple(float(v) for v in R.T @ (np.asarray(xyz) - self.d.xpos[self._pelvis]))
