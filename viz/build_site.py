#!/usr/bin/env python3
"""Build viz/data.json and copy a few videos into viz/assets/videos/ from runs/.

Read-only on runs/. Re-runnable: run it again after the arms finish.
    python3 viz/build_site.py
"""
import json
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
VIZ = ROOT / "viz"
VID_OUT = VIZ / "assets" / "videos"
ARMS = {"video": "video_adapt", "text": "text_adapt"}  # page arm key -> run dir: adapt the deployed (reference) controller, keep-best
REFS = {"baseline": "w1_baseline_v4", "reference": "w1_reference_v4"}
DEFAULT_MASSES = [5, 10, 15, 20, 25, 30, 35, 40]
VIDEO_BUDGET_MB = 45.0
VIDEO_RE = re.compile(r"^m(\d+)_grid\.mp4$")  # skips *.partial.writing-*.mp4


def load_json(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def read_text(p):
    try:
        return Path(p).read_text()
    except Exception:
        return None


def valid_mp4(p):
    """H.264 mp4 written completely: > 1 KB, ftyp box first, moov box present."""
    try:
        if p.stat().st_size <= 1024:
            return False
        with open(p, "rb") as f:
            head = f.read(64)
            if head[4:8] != b"ftyp":
                return False
            if b"moov" in head:
                return True
            # moov may sit at the end (no faststart): scan the last 4 MB
            f.seek(max(0, p.stat().st_size - 4 * 1024 * 1024))
            return b"moov" in f.read()
    except Exception:
        return False


def per_mass(trials):
    out = {}
    for t in trials or []:
        m = int(round(float(t.get("mass_kg", 0))))
        out[str(m)] = {
            "success": bool(t.get("success")),
            "fail_reason": t.get("fail_reason"),
            "mean_assist_n": t.get("mean_assist_n"),
            "max_assist_n": t.get("max_assist_n"),
            "box_rise_m": t.get("box_rise_m"),
            "held_s": t.get("held_s"),
            "peak_tau_frac": t.get("peak_tau_frac"),
            "max_slip_m": t.get("max_slip_m"),
            "fell": t.get("fell"),
            "dropped": t.get("dropped"),
        }
    return out


def stats(pm):
    if not pm:
        return None, None, None
    passed = sorted(int(m) for m, r in pm.items() if r["success"])
    rate = len(passed) / len(pm)
    assists = [r["mean_assist_n"] for r in pm.values() if r["mean_assist_n"] is not None]
    return rate, (max(passed) if passed else None), (sum(assists) / len(assists) if assists else None)


def build_arm(arm):
    d = RUNS / ARMS[arm]
    cfg = load_json(d / "config.json") or {}
    summ = load_json(d / "summary.json") or {}
    summ_rounds = {r.get("round"): r for r in summ.get("rounds", [])}
    n_planned = int(cfg.get("rounds", 0) or 0)
    found = sorted(int(p.name.split("_")[1]) for p in d.glob("round_*") if p.name.split("_")[1].isdigit())
    n = max([n_planned] + [k + 1 for k in found]) if (found or n_planned) else 0
    rounds = []
    for k in range(n):
        rd = d / f"round_{k}"
        trials = load_json(rd / "trials.json")
        pm = per_mass(trials) if isinstance(trials, list) else {}
        rate, maxm, assist = stats(pm)
        s = summ_rounds.get(k, {})
        if not rd.exists():
            status = "pending"
        elif trials is None:
            status = "running"
        else:
            status = "done"
        vids = {}
        if (rd / "videos").is_dir():
            for v in sorted((rd / "videos").iterdir()):
                mm = VIDEO_RE.match(v.name)
                if mm and valid_mp4(v):
                    vids[mm.group(1)] = v
        rounds.append({
            "round": k,
            "status": status,
            "pass_rate": rate,
            "max_mass_passed": maxm,
            "mean_assist_n": assist,
            "per_mass": pm,
            "argon_cost_usd": s.get("argon_cost_usd"),
            "critique_cost_usd": s.get("critique_cost_usd"),
            "wall_s": s.get("wall_s"),
            "critique": read_text(rd / "critique.md"),
            "controller": read_text(rd / "controller.py"),
            "_videos": vids,
        })
    return {
        "arm": arm,
        "planned_rounds": n_planned,
        "masses": cfg.get("masses") or DEFAULT_MASSES,
        "total_cost_usd": summ.get("total_cost_usd"),
        "rounds": rounds,
    }


def build_ref(name, dirname):
    sweep = load_json(RUNS / dirname / "sweep.json")
    if not isinstance(sweep, list):
        return None
    pm = per_mass(sweep)
    rate, maxm, assist = stats(pm)
    return {"name": name, "source": f"runs/{dirname}", "pass_rate": rate,
            "max_mass_passed": maxm, "mean_assist_n": assist, "per_mass": pm}


def pick_videos(arms):
    """Round 0 and the last round with videos, for each arm (video arm first)."""
    picks = []
    for arm in arms:
        with_vids = [r for r in arm["rounds"] if r["_videos"]]
        if not with_vids:
            continue
        chosen = [with_vids[0]] + ([with_vids[-1]] if with_vids[-1] is not with_vids[0] else [])
        for r in chosen:
            for mass, src in sorted(r["_videos"].items(), key=lambda kv: int(kv[0])):
                picks.append((arm["arm"], r["round"], mass, src))
    return picks


def main():
    arms = [build_arm(a) for a in ARMS if (RUNS / ARMS[a]).is_dir()]
    refs = {k: build_ref(k, v) for k, v in REFS.items()}

    VID_OUT.mkdir(parents=True, exist_ok=True)
    for old in VID_OUT.glob("*.mp4"):  # only our own copies live here
        old.unlink()
    budget = VIDEO_BUDGET_MB * 1024 * 1024
    used = 0
    videos = []
    for arm, rnd, mass, src in pick_videos(arms):
        size = src.stat().st_size
        if used + size > budget:
            print(f"skip (budget) {src}")
            continue
        name = f"{arm}_r{rnd}_m{mass}.mp4"
        shutil.copyfile(src, VID_OUT / name)
        used += size
        videos.append({"arm": arm, "round": rnd, "mass_kg": int(mass),
                       "src": f"assets/videos/{name}", "bytes": size})

    for a in arms:
        for r in a["rounds"]:
            r.pop("_videos", None)

    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "assist_budget_n": 60.0,
        "success_rule": "box rises >= 0.45 m and is held >= 3 s, robot does not fall (pelvis z > 0.45 m), "
                        "box not dropped, mean balance assist <= 60 N",
        "arms": {a["arm"]: a for a in arms},
        "refs": refs,
        "videos": videos,
    }
    (VIZ / "data.json").write_text(json.dumps(data, indent=1))
    total = sum(p.stat().st_size for p in VIZ.rglob("*") if p.is_file())
    for a in arms:
        done = [r for r in a["rounds"] if r["status"] == "done"]
        print(f"{a['arm']}: {len(done)}/{len(a['rounds'])} rounds done; "
              f"max mass by round: {[r['max_mass_passed'] for r in done]}")
    print(f"videos copied: {len(videos)} ({used / 1e6:.1f} MB); viz/ total {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
