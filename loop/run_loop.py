"""Argon lift-controller loop: trials -> videos -> critique -> new controller, per round.

Usage:
  .venv/bin/python loop/run_loop.py --arm video --rounds 10 [--masses 5,10,...,40] [--seed-controller PATH] [--stub]

--rounds N means N critique/fix iterations: rounds 0..N are evaluated. Round 0 is the seed controller, or one
Argon writes from the task and API docs. Output: runs/<arm>/round_<k>/{controller.py, trials.json, critique.md,
videos/*.mp4, argon_reply.md, trials/m<mass>/{traj.npz,result.json}} and runs/<arm>/summary.json. Resumable: every
step is skipped when its output already exists.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib
import json
import os
import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loop import argon, prompts  # noqa: E402
from loop.telemetry import summarize_traj  # noqa: E402

BACKEND = {"trial": "sim.trial", "render": "sim.render"}
MAX_VIDEOS = 2  # renders run in parallel; 4 per round pushed load past 200 and hung the laptop at 13:31
GRID_SIZE = (960, 360)  # hero | side; the critic samples at 2 fps, so 10 fps video is plenty and 3x cheaper to render
VIDEO_FPS = 10


def _say(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ workers (top level for pickling)

def _trial_worker(mod, controller, mass, seed, out_dir, use_assist):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        res = importlib.import_module(mod).run_trial(controller, mass, seed, out_dir, use_assist=use_assist)
    except Exception as e:  # noqa: BLE001
        res = {"success": False, "mass_kg": mass, "fail_reason": f"runner_error: {type(e).__name__}: {e}",
               "runner_traceback": traceback.format_exc()[-1500:]}
    res = dict(res)
    res.setdefault("mass_kg", mass)
    res["trial_dir"] = str(out_dir)
    traj = pathlib.Path(out_dir) / "traj.npz"
    if traj.exists():
        try:
            res["telemetry"] = summarize_traj(traj)
        except Exception as e:  # noqa: BLE001
            res["telemetry"] = {"error": f"summary failed: {e}"}
    return res


def _render_worker(mod, traj, out_mp4):
    """Render to a temp file, then rename, so a killed render never looks finished on resume."""
    os.environ["RENDER_FAST"] = "1"  # critic videos only; demo clips are rendered separately at full quality
    final = pathlib.Path(out_mp4)
    tmp = final.with_name(final.stem + ".partial.mp4")
    _render_grid(mod, traj, tmp)
    os.replace(tmp, final)
    return str(final)


def _render_grid(mod, traj, out_mp4):
    """Hero (left) + side (right) side-by-side grid video."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import imageio.v2 as imageio
    import numpy as np
    rmod = importlib.import_module(mod)
    if hasattr(rmod, "render_grid"):  # W2's native hero|side grid (video time = sim time, plus an end card)
        rmod.render_grid(str(traj), str(out_mp4), size=GRID_SIZE, fps=VIDEO_FPS, hud=True)
        return str(out_mp4)
    render = rmod.render_traj
    out_mp4 = pathlib.Path(out_mp4)
    parts = []
    for cam in ("hero", "side"):
        p = out_mp4.with_name(out_mp4.stem + f"_{cam}.mp4")
        render(str(traj), str(p), camera=cam, hud=True, size=(GRID_SIZE[0] // 2, GRID_SIZE[1]), fps=VIDEO_FPS)
        parts.append(p)
    ra, rb = imageio.get_reader(parts[0]), imageio.get_reader(parts[1])
    with imageio.get_writer(out_mp4, fps=VIDEO_FPS, codec="libx264", quality=6, macro_block_size=8) as w:
        for fa, fb in zip(ra, rb):
            h = min(fa.shape[0], fb.shape[0])
            w.append_data(np.hstack([fa[:h], fb[:h]]))
    ra.close(); rb.close()
    for p in parts:
        p.unlink(missing_ok=True)
    return str(out_mp4)


# ------------------------------------------------------------------ helpers

def select_for_video(trials, cap=MAX_VIDEOS):
    fails = sorted([t for t in trials if not t.get("success")], key=lambda t: t["mass_kg"])
    passes = sorted([t for t in trials if t.get("success")], key=lambda t: t["mass_kg"])
    pick = []
    if passes:
        pick.append(passes[-1])
    if fails:
        order = [fails[0], fails[-1]] + fails[1:-1]  # the boundary failure first, then the heaviest
        for t in order:
            if len(pick) >= cap:
                break
            if t not in pick:
                pick.append(t)
    return sorted(pick, key=lambda t: t["mass_kg"])


def _calls_cost(log_dir, since_line):
    p = pathlib.Path(log_dir) / "calls.jsonl"
    if not p.exists():
        return 0.0, since_line
    lines = p.read_text().splitlines()
    cost = sum(json.loads(l).get("est_cost_usd", 0) or 0 for l in lines[since_line:])
    return round(cost, 4), len(lines)


def _n_calls(log_dir):
    p = pathlib.Path(log_dir) / "calls.jsonl"
    return len(p.read_text().splitlines()) if p.exists() else 0


def progress_score(trials):
    """Passes first; then partial credit for box rise (capped at the 0.45 m bar) so near-misses count as progress."""
    passed = sum(1 for t in trials if t.get("success"))
    rise = sum(min(max(t.get("box_rise_m") or 0.0, 0.0), 0.45) / 0.45 for t in trials if not t.get("success"))
    return round(passed + 0.5 * rise / max(1, len(trials)), 4)


def round_summary(k, trials, masses, cost, wall):
    passed = sorted(t["mass_kg"] for t in trials if t.get("success"))
    assists = [t.get("mean_assist_n") for t in trials if isinstance(t.get("mean_assist_n"), (int, float))]
    return {"round": k, "pass_rate": round(len(passed) / max(1, len(trials)), 3), "passed": passed,
            "masses": masses, "max_mass_passed": max(passed) if passed else None,
            "mean_assist_n": round(sum(assists) / len(assists), 1) if assists else None,
            "argon_cost_usd": cost, "wall_s": round(wall, 1)}


# ------------------------------------------------------------------ main loop

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["video", "text"], required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--masses", default="5,10,15,20,25,30,35,40")
    ap.add_argument("--seed-controller", default=None)
    ap.add_argument("--seed", type=int, default=0, help="base seed; trial seed = base + mass index")
    ap.add_argument("--stub", action="store_true", help="use loop/stubs.py instead of sim/trial.py + sim/render.py")
    ap.add_argument("--run-dir", default=None, help="default runs/<arm>")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4))
    ap.add_argument("--no-assist", action="store_true")
    ap.add_argument("--keep-best", action="store_true", help="revise the best controller so far, not the latest")
    ap.add_argument("--render-timeout", type=float, default=900, help="seconds for all of a round's renders")
    a = ap.parse_args(argv)

    trial_mod = "loop.stubs" if a.stub else BACKEND["trial"]
    render_mod = "loop.stubs" if a.stub else BACKEND["render"]
    for m in {trial_mod, render_mod}:
        importlib.import_module(m)  # fail fast if a backend is missing
    masses = [float(x) if "." in x else int(x) for x in a.masses.split(",")]
    run_dir = pathlib.Path(a.run_dir or ROOT / "runs" / a.arm)
    run_dir.mkdir(parents=True, exist_ok=True)
    argon.set_log_dir(run_dir)
    use_video = a.arm == "video"
    task_md, api_md = prompts.TASK_MD, prompts.api_md()
    (run_dir / "config.json").write_text(json.dumps(vars(a) | {"masses": masses}, indent=2))

    summ_p = run_dir / "summary.json"
    summary = json.loads(summ_p.read_text()) if summ_p.exists() else {"arm": a.arm, "rounds": []}
    done = {r["round"]: r for r in summary["rounds"]}
    history = []
    best = None

    for k in range(a.rounds + 1):
        rd = run_dir / f"round_{k}"
        rd.mkdir(exist_ok=True)
        t0 = time.time()
        mark = _n_calls(run_dir)
        ctrl = rd / "controller.py"

        # 1. controller for this round
        produce_cost = 0.0
        if not ctrl.exists():
            if k == 0:
                if a.seed_controller:
                    ctrl.write_text(pathlib.Path(a.seed_controller).read_text())
                    _say(f"round 0: seed controller {a.seed_controller}")
                else:
                    _say("round 0: Argon writes the first controller")
                    ctrl.write_text(argon.write_controller(task_md, api_md))
                    (rd / "argon_reply.md").write_text(argon._last.get("reply", ""))
                    produce_cost, mark = _calls_cost(run_dir, mark)
            else:
                raise SystemExit(f"{ctrl} missing: the previous round's critique did not finish; rerun to resume")
        elif k in done:
            produce_cost = done[k].get("argon_cost_usd", 0.0)
        code = ctrl.read_text()

        # 2. trials
        tj = rd / "trials.json"
        if tj.exists():
            trials = json.loads(tj.read_text())
        else:
            _say(f"round {k}: {len(masses)} trials ({trial_mod})")
            with cf.ProcessPoolExecutor(max_workers=a.workers) as ex:
                futs = [ex.submit(_trial_worker, trial_mod, str(ctrl), m, a.seed + i,
                                  str(rd / "trials" / f"m{m}"), not a.no_assist) for i, m in enumerate(masses)]
                trials = [f.result() for f in futs]
            tj.write_text(json.dumps(trials, indent=2))
        rs = round_summary(k, trials, masses, produce_cost, time.time() - t0)
        _say(f"round {k}: passed {rs['passed']} (rate {rs['pass_rate']}), mean assist {rs['mean_assist_n']}")

        # 3. videos (both arms render, so the results page has them; only the video arm sends them)
        vd = rd / "videos"
        sel = select_for_video(trials)
        vids, labels = [], []
        for t in sel:
            mp4 = vd / f"m{t['mass_kg']:g}_grid.mp4"
            vids.append(mp4)
            labels.append(f"{t['mass_kg']:g} kg, {'PASS' if t.get('success') else 'FAIL: ' + str(t.get('fail_reason'))[:120]}"
                          f" (left: hero 3/4 view, right: side profile; video time = sim time)")
        todo = [(t, v) for t, v in zip(sel, vids) if not v.exists()]
        if todo:
            vd.mkdir(exist_ok=True)
            _say(f"round {k}: rendering {len(todo)} grid videos")
            import multiprocessing as mp
            procs = []
            for t, v in todo:
                pr = mp.get_context("spawn").Process(
                    target=_render_worker, args=(render_mod, str(pathlib.Path(t["trial_dir"]) / "traj.npz"), str(v)))
                pr.start()
                procs.append((pr, v))
            deadline = time.time() + a.render_timeout
            for pr, v in procs:
                pr.join(max(1.0, deadline - time.time()))
                if pr.is_alive():
                    pr.terminate()
                    pr.join(5)
                    _say(f"render timed out for {v.name} (> {a.render_timeout} s); continuing without it")
                elif pr.exitcode != 0:
                    _say(f"render failed for {v.name} (exit {pr.exitcode})")
        ok_vids = [(v, l) for v, l in zip(vids, labels) if v.exists()]

        # keep-best: Argon revises the best controller so far, so a regressing rewrite can't erase progress
        cur = {"round": k, "code": code, "trials": trials, "ok_vids": ok_vids, "score": progress_score(trials)}
        if a.keep_best and best is not None and cur["score"] < best["score"]:
            _say(f"round {k}: score {cur['score']} < best {best['score']} (round {best['round']}); revising round {best['round']}")
            base = best
        else:
            base = best = cur
        rs["score"], rs["revised_from"] = cur["score"], base["round"]

        # 4. critique and fix -> next round's controller
        crit = rd / "critique.md"
        nxt = run_dir / f"round_{k + 1}" / "controller.py"
        if k < a.rounds and not (crit.exists() and nxt.exists()):
            bv = base["ok_vids"]
            _say(f"round {k}: Argon critique of round {base['round']} ({'video x%d' % len(bv) if use_video else 'text'})")
            hist = [h for h in history]
            if base is not cur:
                hist.append({"round": k, "passed": rs["passed"], "masses": masses, "mean_assist_n": rs["mean_assist_n"],
                             "changes": f"(round {k}'s rewrite scored {cur['score']}, worse than round {base['round']}'s "
                                        f"{base['score']}, so it was discarded. You are revising round {base['round']}'s "
                                        f"controller again; avoid repeating round {k}'s changes.)"})
            critique, new_code = argon.critique_and_fix(
                base["code"], base["trials"], [v for v, _ in bv], use_video=use_video, history=hist,
                task_md=task_md, api_md=api_md, video_labels=[l for _, l in bv])
            nxt.parent.mkdir(exist_ok=True)
            crit.write_text(critique + "\n")
            (rd / "argon_reply.md").write_text(argon._last.get("reply", ""))
            nxt.write_text(new_code)
            crit_cost, mark = _calls_cost(run_dir, mark)
            rs["critique_cost_usd"] = crit_cost
            _say(f"round {k}: critique done, ${crit_cost:.3f}")
        elif crit.exists() and k in done:
            rs["critique_cost_usd"] = done[k].get("critique_cost_usd")
        # the critique cost of round k is the cost that produced round k+1's controller
        if k > 0 and (k - 1) in done and done[k - 1].get("critique_cost_usd") is not None:
            rs["argon_cost_usd"] = done[k - 1]["critique_cost_usd"]
        rs["wall_s"] = round(time.time() - t0, 1) if k not in done else done[k]["wall_s"]
        rs["videos"] = [str(v.relative_to(run_dir)) for v, _ in ok_vids]
        done[k] = rs
        summary["rounds"] = [done[i] for i in sorted(done)]
        summary["total_cost_usd"] = round(sum((r.get("critique_cost_usd") or 0) for r in summary["rounds"])
                                          + (summary["rounds"][0].get("argon_cost_usd") or 0), 4)
        summ_p.write_text(json.dumps(summary, indent=2))
        changes = crit.read_text().split("## Changes", 1)[-1] if crit.exists() else ""
        history.append({"round": k, "passed": rs["passed"], "masses": masses, "mean_assist_n": rs["mean_assist_n"],
                        "changes": changes})
    _say(f"done: {summ_p}")


if __name__ == "__main__":
    main()
