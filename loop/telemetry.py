"""Compact telemetry summaries of traj.npz for the critic (both arms get the same text)."""
from __future__ import annotations

import functools
import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]

GROUPS = [  # (group, substrings matched against actuator names)
    ("hip_pitch", ["hip_pitch"]), ("hip_roll_yaw", ["hip_roll", "hip_yaw"]), ("knee", ["knee"]),
    ("ankle", ["ankle"]), ("waist/back", ["waist"]), ("shoulder", ["shoulder"]), ("elbow", ["elbow"]),
    ("wrist", ["wrist"]), ("hand", ["hand_"]),
]


@functools.lru_cache(maxsize=1)
def _model_info():
    """Actuator names, box qpos address and pelvis-z address from the scene (None where unavailable)."""
    import mujoco
    for xml in ("scene_lift.xml", "g1_with_hands.xml"):
        try:
            m = mujoco.MjModel.from_xml_path(str(ROOT / "sim" / "g1" / xml))
        except Exception:
            continue
        names = [m.actuator(i).name for i in range(m.nu)]
        box_adr = pelvis_adr = None
        for j in range(m.njnt):
            if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE:
                if m.joint(j).name == "box":
                    box_adr = int(m.jnt_qposadr[j])
                elif pelvis_adr is None:
                    pelvis_adr = int(m.jnt_qposadr[j])
        return names, box_adr, pelvis_adr
    return None, None, None


def _t(x: float) -> str:
    return f"{int(x // 60)}:{x % 60:04.1f}"


def summarize_traj(npz_path) -> dict:
    d = np.load(npz_path, allow_pickle=True)
    t = d["time"].astype(float)
    out: dict = {"duration_s": round(float(t[-1]), 2) if len(t) else 0.0}
    names = list(d["actuator_names"]) if "actuator_names" in d.files else None
    mnames, box_adr, pelvis_adr = _model_info()
    names = names or mnames
    tau = d["tau_frac"] if "tau_frac" in d.files else None
    if tau is not None and len(t):
        groups = {}
        nu = tau.shape[1]
        if names and len(names) == nu:
            for g, keys in GROUPS:
                idx = [i for i, n in enumerate(names) if any(k in n for k in keys)]
                if idx:
                    sub = tau[:, idx]
                    k = int(np.argmax(sub.max(axis=1)))
                    groups[g] = {"peak": round(float(sub.max()), 2), "at": _t(t[k]),
                                 "s_above_0.9": round(float((sub.max(axis=1) > 0.9).sum() / 30.0), 1)}
        else:
            k = int(np.argmax(tau.max(axis=1)))
            groups["all"] = {"peak": round(float(tau.max()), 2), "at": _t(t[k])}
        out["peak_tau_frac"] = groups
    if "com_margin" in d.files and len(t):
        cm = d["com_margin"].astype(float)
        k = int(np.argmin(cm))
        out["com_margin"] = {"min_m": round(float(cm[k]), 3), "at": _t(t[k]),
                             "s_outside": round(float((cm < 0).sum() / 30.0), 1)}
    if "box_slip" in d.files and len(t):
        s = d["box_slip"].astype(float)
        k = int(np.argmax(s))
        out["slip"] = {"max_m": round(float(s[k]), 3), "at": _t(t[k])}
    if "assist_force" in d.files and len(t):
        a = np.abs(d["assist_force"].astype(float))
        k = int(np.argmax(a))
        out["assist"] = {"mean_n": round(float(a.mean()), 1), "max_n": round(float(a[k]), 1), "at": _t(t[k]),
                         "s_above_50n": round(float((a > 50).sum() / 30.0), 1)}
    qpos = d["qpos"] if "qpos" in d.files else None
    if qpos is not None and len(t):
        if pelvis_adr is not None and qpos.shape[1] > pelvis_adr + 2:
            pz = qpos[:, pelvis_adr + 2]
            k = int(np.argmin(pz))
            out["pelvis_z"] = {"min_m": round(float(pz[k]), 3), "at": _t(t[k])}
        if box_adr is not None and qpos.shape[1] > box_adr + 2:
            bz = qpos[:, box_adr + 2]
            out["box_rise"] = {"max_m": round(float(bz.max() - bz[0]), 3), "at": _t(t[int(np.argmax(bz))])}
    if "phase" in d.files and len(t):
        ph = [str(p) for p in d["phase"]]
        segs, start = [], 0
        for i in range(1, len(ph) + 1):
            if i == len(ph) or ph[i] != ph[start]:
                segs.append(f"{_t(t[start])}-{_t(t[i - 1])} {ph[start] or '-'}")
                start = i
        out["phases"] = segs[:20]
    # 1 Hz timeline of the key signals
    if len(t):
        rows = []
        for ts in np.arange(0, t[-1] + 1e-6, 1.0):
            i = int(np.searchsorted(t, ts))
            i = min(i, len(t) - 1)
            r = [_t(t[i])]
            r.append(str(d["phase"][i]) if "phase" in d.files else "")
            r.append(f"{d['com_margin'][i]:+.3f}" if "com_margin" in d.files else "")
            r.append(f"{abs(d['assist_force'][i]):.0f}" if "assist_force" in d.files else "")
            r.append(f"{tau[i].max():.2f}" if tau is not None else "")
            r.append(f"{d['box_slip'][i]:.3f}" if "box_slip" in d.files else "")
            if qpos is not None and box_adr is not None and qpos.shape[1] > box_adr + 2:
                r.append(f"{qpos[i, box_adr + 2] - qpos[0, box_adr + 2]:+.2f}")
            else:
                r.append("")
            rows.append(r)
        out["timeline"] = rows
    return out


RESULT_KEYS = ["success", "mass_kg", "box_rise_m", "held_s", "max_assist_n", "mean_assist_n", "peak_tau_frac",
               "max_slip_m", "fell", "dropped", "fail_reason"]


def format_trials_md(trials: list[dict]) -> str:
    lines = ["| mass kg | success | box rise m | held s | mean assist N | max assist N | peak tau_frac | max slip m | fell | dropped | fail_reason |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(trials, key=lambda r: r.get("mass_kg", 0)):
        lines.append("| " + " | ".join(str(r.get(k, "")) for k in ["mass_kg", "success", "box_rise_m", "held_s",
                                                                       "mean_assist_n", "max_assist_n", "peak_tau_frac",
                                                                       "max_slip_m", "fell", "dropped", "fail_reason"]) + " |")
    passes = [r["mass_kg"] for r in trials if r.get("success")]
    heaviest_pass = max(passes) if passes else None
    for r in sorted(trials, key=lambda r: r.get("mass_kg", 0)):
        tel = r.get("telemetry")
        detailed = (not r.get("success")) or r.get("mass_kg") == heaviest_pass
        if not tel:
            continue
        lines += ["", f"### {r.get('mass_kg')} kg ({'PASS' if r.get('success') else 'FAIL'}) telemetry"]
        extra = {k: v for k, v in r.items() if k not in RESULT_KEYS and k not in ("telemetry", "trial_dir") and v not in (None, "")}
        if extra:
            lines.append("- other result fields: " + json.dumps(extra, default=str)[:1500])
        if "peak_tau_frac" in tel:
            lines.append("- peak tau_frac by joint group: " + ", ".join(
                f"{g} {v['peak']} @{v['at']}" + (f" ({v['s_above_0.9']} s >0.9)" if v.get("s_above_0.9") else "")
                for g, v in tel["peak_tau_frac"].items()))
        for k, lab in [("com_margin", "CoM margin"), ("assist", "assist"), ("slip", "slip"), ("pelvis_z", "pelvis z"),
                       ("box_rise", "box rise")]:
            if k in tel:
                lines.append(f"- {lab}: " + ", ".join(f"{a}={b}" for a, b in tel[k].items()))
        if tel.get("phases"):
            lines.append("- phases: " + "; ".join(tel["phases"]))
        if tel.get("timeline") and detailed:
            lines.append("- 1 Hz timeline (t | phase | com_margin m | assist N | max tau_frac | slip m | box dz m):")
            lines += ["  " + " | ".join(row) for row in tel["timeline"]]
    return "\n".join(lines)
