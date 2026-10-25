"""Replay a saved live run through the live page and MuJoCo viewer, step by step, clearly labelled as a replay.

  .venv/bin/python -m demo.replay 155234_m5 [--speed 1.0]

Nothing is re-simulated or re-generated: verdicts, videos, Argon's critiques and code come from runs/live/<run>/.
Run it while demo.app is serving the page (it writes runs/live/state.json, which the page and viewer follow).
"""
from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.live import LIVE, State, verdict  # noqa: E402
from loop.run_loop import progress_score  # noqa: E402

LB = 2.20462


def load(p: pathlib.Path):
    return json.loads(p.read_text()) if p.exists() else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--speed", type=float, default=1.0, help=">1 plays faster")
    a = ap.parse_args(argv)
    src = LIVE / a.run
    rounds = sorted(int(p.name.split("_")[1]) for p in src.glob("round_*"))
    t0 = load(src / "round_0" / "trial" / "result.json")
    mass = float(t0["mass_kg"]) if t0 and "mass_kg" in t0 else float(a.run.split("_m")[1])
    hhmm = f"{a.run[:2]}:{a.run[2:4]}"
    cost = sum(json.loads(l).get("est_cost_usd", 0) or 0 for l in (src / "calls.jsonl").read_text().splitlines()) \
        if (src / "calls.jsonl").exists() else 0.0

    def wait(s):
        time.sleep(s / a.speed)

    st = State(LIVE / "state.json", mass, len(rounds) - 1, src / "round_0" / "controller.py")
    st.d.update(run=f"replay_{a.run}", src_run=a.run, replay=hhmm)
    lat = [json.loads(l).get("latency_s") for l in (src / "calls.jsonl").read_text().splitlines()
           if json.loads(l).get("kind", "").startswith("critique")] if (src / "calls.jsonl").exists() else []
    n_crit = 0
    tag = f"(replay of the {hhmm} live run)"
    st.stage(f"replaying the {hhmm} live run: {mass * LB:.0f} lb box, real saved results")
    best = None
    for k in rounds:
        rd = src / f"round_{k}"
        t = load(rd / "trial" / "result.json")
        checks = [load(c / "result.json") for c in sorted(rd.glob("check_m*"))]
        checks = [c for c in checks if c]
        att = {"round": k, "status": "running"}
        st.d["attempts"].append(att)
        st.stage(f"round {k}: robot lifts the {mass * LB:.0f} lb box in MuJoCo "
                 f"(+ regression checks at {', '.join(f'{c['mass_kg'] * LB:.0f}' for c in checks)} lb) {tag}")
        wait(4)
        broke = [c for c in checks if not c.get("success")]
        att.update(verdict=verdict(t), success=bool(t.get("success")) and not broke, box_rise_m=t.get("box_rise_m"),
                   mean_assist_n=t.get("mean_assist_n"), peak_tau_frac=t.get("peak_tau_frac"),
                   checks=[{"lb": round(c["mass_kg"] * LB), "verdict": verdict(c)} for c in checks])
        chk = ", ".join(f"{c['lb']} lb {'PASS' if c['verdict'] == 'PASS' else 'FAIL'}" for c in att["checks"])
        st.stage(f"round {k}: physics scorer says {att['verdict']} (checks: {chk})")
        if (rd / "video.mp4").exists():
            att["video"] = f"{a.run}/round_{k}/video.mp4"
        st.save()
        wait(3)
        crit = rd / "critique.md"
        if att["success"] or not crit.exists():
            att["status"] = "done"
            break
        trials = [t] + checks
        score = progress_score(trials)
        if best is not None and score < best["score"]:
            att["discarded"] = True
            st.stage(f"round {k}: worse than attempt {best['round'] + 1}; Argon revises attempt {best['round'] + 1} instead")
            base = best["round"]
        else:
            best, base = {"round": k, "score": score}, k
        vids = [f"attempt {j + 1}: {mass:g} kg" for j in range(k + 1) if (src / f"round_{j}" / "video.mp4").exists()]
        att["argon"] = {"status": "watching", "videos": vids, "started": time.time(),
                        "evidence": [f"{x['mass_kg'] * LB:.0f} lb: {verdict(x)}" for x in trials]}
        st.stage(f"round {k}: Argon watches the video and diagnoses the physics")
        wait(8)
        critique = crit.read_text()
        old = (src / f"round_{base}" / "controller.py").read_text()
        new = (src / f"round_{k + 1}" / "controller.py").read_text()
        diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "before", "Argon's rewrite", n=1, lineterm=""))
        diag, _, changes = critique.partition("## Changes")
        att["videos_seen"] = len(vids)
        secs = round(lat[n_crit]) if n_crit < len(lat) and lat[n_crit] else None
        n_crit += 1
        att["argon"].update(status="done", seconds=secs, diff="\n".join(diff[2:400]),
                            lines_changed=sum(1 for l in diff[2:] if l[:1] in "+-" and l[:3] not in ("+++", "---")))
        att.update(diagnosis=diag.replace("## Diagnosis", "").strip(), changes=changes.strip(), status="done")
        st.stage(f"round {k}: Argon rewrote the controller; re-testing")
        wait(6)
    final = st.d["attempts"][-1]
    st.d.update(done=True, final=final["verdict"], argon_cost_usd=round(cost, 3))
    st.stage(f"done: {final['verdict']} after {len(st.d['attempts'])} attempt(s), Argon cost ${cost:.2f} {tag}")


if __name__ == "__main__":
    main()
