"""Live judging demo: a judge picks a tote mass; Argon watches the robot try it, diagnoses the physics, rewrites the
controller, and the physics scorer re-checks it. Progress streams to a local page at http://localhost:8790.

Usage:
  .venv/bin/python -m demo.live --mass 20 [--rounds 2] [--controller PATH] [--no-server]

Each round: trial (MuJoCo) -> render (hero | side, with HUD) -> Argon watches the video + telemetry and rewrites
-> next trial. The physics scorer (sim/trial.py) decides PASS/FAIL; Argon never scores itself.
Output: runs/live/<timestamp>_m<mass>/round_<k>/{controller.py, trial/, video.mp4, critique.md}, state.json.
"""
from __future__ import annotations

import argparse
import difflib
import concurrent.futures as cf
import functools
import http.server
import json
import pathlib
import shutil
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loop import argon, prompts  # noqa: E402
from loop.run_loop import _render_worker, _trial_worker  # noqa: E402

CHECK_KG = [15.0, 30.0, 20.0]  # regression-check loads inside the deployed controller's working range
PORT = 8790  # 8765 is taken by another local service on this laptop
LIVE = ROOT / "runs" / "live"


def default_controller() -> pathlib.Path:
    """The robot's deployed controller: the engineer-tuned reference, which lifts about 22-77 lb (10-35 kg).
    Loads outside that range are where Argon has to adapt it."""
    return ROOT / "sim" / "reference_controller.py"


class State:
    def __init__(self, path: pathlib.Path, mass: float, rounds: int, controller: pathlib.Path):
        self.path = path
        self.d = {"mass_kg": mass, "mass_lb": round(mass * 2.20462, 1), "rounds": rounds, "controller": str(controller),
                  "stage": "starting", "log": [], "attempts": [], "done": False, "started": time.time()}
        self.save()

    def stage(self, msg: str):
        self.d["stage"] = msg
        self.d["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        print(self.d["log"][-1], flush=True)
        self.save()

    def save(self):
        self.d["elapsed_s"] = round(time.time() - self.d["started"], 1)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, indent=2))
        tmp.replace(self.path)


def serve(directory: pathlib.Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def verdict(t: dict) -> str:
    return "PASS" if t.get("success") else f"FAIL: {t.get('fail_reason')}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mass", type=float, required=True, help="tote mass in kg (the judge's pick)")
    ap.add_argument("--rounds", type=int, default=3, help="Argon fix rounds; rounds+1 trials in total")
    ap.add_argument("--controller", default=None, help="starting controller (default: best saved one)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-server", action="store_true")
    a = ap.parse_args(argv)

    ctrl0 = pathlib.Path(a.controller) if a.controller else default_controller()
    run = LIVE / f"{time.strftime('%H%M%S')}_m{a.mass:g}"
    run.mkdir(parents=True)
    LIVE.mkdir(exist_ok=True)
    shutil.copy(ROOT / "demo" / "index.html", LIVE / "index.html")
    argon.set_log_dir(run)
    st = State(LIVE / "state.json", a.mass, a.rounds, ctrl0)
    st.d["run"] = run.name
    if not a.no_server:
        serve(LIVE)
        print(f"live page: http://localhost:{PORT}/", flush=True)

    from loop.run_loop import progress_score
    code = ctrl0.read_text()
    history = []
    best = None
    # the judge's box plus two regression checks from the controller's working range, all simulated in parallel:
    # Argon sees which loads hold and which fail, and a fix only counts if it doesn't break the loads that worked
    anchors = [m for m in CHECK_KG if abs(m - a.mass) >= 2.5][:2]
    masses = [a.mass] + anchors
    st.d["checks_kg"] = anchors
    for k in range(a.rounds + 1):
        rd = run / f"round_{k}"
        rd.mkdir()
        (rd / "controller.py").write_text(code)
        att = {"round": k, "status": "running"}
        st.d["attempts"].append(att)

        st.stage(f"round {k}: robot lifts the {a.mass * 2.20462:.0f} lb box in MuJoCo "
                 f"(+ regression checks at {', '.join(f'{m * 2.20462:.0f}' for m in anchors)} lb)")
        with cf.ProcessPoolExecutor(max_workers=len(masses)) as ex:
            futs = [ex.submit(_trial_worker, "sim.trial", str(rd / "controller.py"), m, a.seed,
                              str(rd / ("trial" if i == 0 else f"check_m{m:g}")), True) for i, m in enumerate(masses)]
            trials = [f.result() for f in futs]
        t, checks = trials[0], trials[1:]
        broke = [c for c in checks if not c.get("success")]
        att.update(verdict=verdict(t), success=bool(t.get("success")) and not broke, box_rise_m=t.get("box_rise_m"),
                   mean_assist_n=t.get("mean_assist_n"), peak_tau_frac=t.get("peak_tau_frac"),
                   checks=[{"lb": round(c["mass_kg"] * 2.20462), "verdict": verdict(c)} for c in checks])
        chk = ", ".join(f"{c['lb']} lb {'PASS' if c['verdict'] == 'PASS' else 'FAIL'}" for c in att["checks"])
        st.stage(f"round {k}: physics scorer says {att['verdict']} (checks: {chk})")

        traj = rd / "trial" / "traj.npz"
        if traj.exists():
            st.stage(f"round {k}: rendering video")
            try:
                _render_worker("sim.render", str(traj), str(rd / "video.mp4"))
                att["video"] = f"{run.name}/round_{k}/video.mp4"
            except Exception as e:  # noqa: BLE001
                st.stage(f"round {k}: render failed ({e}); Argon gets telemetry only")
        st.save()

        if att["success"] or k == a.rounds:
            att["status"] = "done"
            break

        # keep-best (same rule as loop/run_loop.py): if this rewrite did worse, Argon revises the best attempt instead
        score = progress_score(trials)
        if best is not None and score < best["score"]:
            att["discarded"] = True
            st.stage(f"round {k}: worse than attempt {best['round'] + 1}; Argon revises attempt {best['round'] + 1} instead")
            history.append({"round": k, "passed": [x["mass_kg"] for x in trials if x.get("success")], "masses": masses,
                            "mean_assist_n": t.get("mean_assist_n"),
                            "changes": f"(this rewrite did worse than attempt {best['round'] + 1}, so it was discarded; "
                                       f"you are revising attempt {best['round'] + 1}'s controller again; avoid repeating "
                                       f"this attempt's changes.)"})
            code, trials, base = best["code"], best["trials"], best["round"]
        else:
            best = {"round": k, "code": code, "trials": trials, "score": score}
            base = k

        st.stage(f"round {k}: Argon watches the video and diagnoses the physics")
        # every attempt so far goes into one context, oldest first, so Argon can compare what each rewrite changed
        vids, labels = [], []
        for j, prev in enumerate(st.d["attempts"]):
            mp4 = run / f"round_{j}" / "video.mp4"
            if mp4.exists():
                tag = "the attempt whose controller you are revising" if j == base else f"attempt {j + 1}"
                vids.append(mp4)
                labels.append(f"{tag}: {a.mass:g} kg, {prev['verdict'][:120]} "
                              "(left: hero 3/4 view, right: side profile; video time = sim time)")
        # what Argon is given, shown on the page while it thinks
        att["argon"] = {"status": "watching", "videos": labels, "started": time.time(),
                        "evidence": [f"{x['mass_kg'] * 2.20462:.0f} lb: {verdict(x)}" for x in trials]}
        st.save()
        old_code = code
        critique, code = argon.critique_and_fix(code, trials, vids, use_video=bool(vids), history=history,
                                                task_md=prompts.TASK_MD, api_md=prompts.api_md(), video_labels=labels)
        att["videos_seen"] = len(vids)
        diff = list(difflib.unified_diff(old_code.splitlines(), code.splitlines(), "before", "Argon's rewrite", n=1, lineterm=""))
        att["argon"].update(status="done", seconds=round(time.time() - att["argon"]["started"]), diff="\n".join(diff[2:400]),
                            lines_changed=sum(1 for l in diff[2:] if l[:1] in "+-" and l[:3] not in ("+++", "---")))
        (rd / "critique.md").write_text(critique + "\n")
        diag, _, changes = critique.partition("## Changes")
        att.update(diagnosis=diag.replace("## Diagnosis", "").strip(), changes=changes.strip(), status="done")
        history.append({"round": k, "passed": [x["mass_kg"] for x in trials if x.get("success")], "masses": masses,
                        "mean_assist_n": t.get("mean_assist_n"), "changes": changes})
        st.stage(f"round {k}: Argon rewrote the controller; re-testing")

    final = st.d["attempts"][-1]
    cost = 0.0
    calls = run / "calls.jsonl"
    if calls.exists():
        cost = sum(json.loads(l).get("est_cost_usd", 0) or 0 for l in calls.read_text().splitlines())
    verdict_txt = final["verdict"]
    broken = [c for c in final.get("checks", []) if c["verdict"] != "PASS"]
    if verdict_txt == "PASS" and broken:
        verdict_txt = "FAIL: lifted it, but broke the " + ", ".join(f"{c['lb']} lb" for c in broken) + " check"
    st.d.update(done=True, final=verdict_txt, argon_cost_usd=round(cost, 3))
    st.stage(f"done: {verdict_txt} after {len(st.d['attempts'])} attempt(s), Argon cost ${cost:.2f}")
    if not a.no_server:
        print("page stays up; Ctrl-C to quit", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
