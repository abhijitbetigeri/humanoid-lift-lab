"""Read-only inventory of saved run evidence; never runs a model or simulator."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def read_json(path, warnings):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        warnings.append(f"unreadable {path.name}: {exc}")
        return None


def audit_run(directory, runs_root):
    warnings = []
    config = read_json(directory / "config.json", warnings)
    if not isinstance(config, dict):
        config = {}
        warnings.append("missing or invalid run config")
    backend = "stub" if config.get("stub") is True else (
        "configured-real" if config.get("stub") is False else "unknown")
    env = config.get("environment_sha256")
    if not isinstance(env, str) or len(env) != 64:
        env = None
        warnings.append("missing environment SHA256; historical physics cannot be bound to current source")
    split = config.get("split")
    if split not in ("development", "evaluation", "heldout", "test"):
        split = None
        warnings.append("missing or unrecognized split")
    rounds = []
    for rd in sorted(directory.glob("round_*")):
        if not rd.is_dir() or not rd.name[6:].isdigit():
            continue
        trials = read_json(rd / "trials.json", warnings)
        valid = isinstance(trials, list) and all(isinstance(t, dict) for t in trials)
        rounds.append({"round": int(rd.name[6:]), "controller_sha256": digest(rd / "controller.py"),
                       "trial_count": len(trials) if valid else None,
                       "passes": sum(t.get("success") is True for t in trials) if valid else None})
    rounds.sort(key=lambda r: r["round"])
    sweep = read_json(directory / "sweep.json", warnings)
    sweep_valid = isinstance(sweep, list) and all(isinstance(t, dict) for t in sweep)
    if backend == "stub":
        warnings.append("stub outcomes are harness tests, not physics evidence")
    if sweep_valid and backend == "unknown":
        warnings.append("saved sweep outcomes have no backend/config provenance; inspect as historical development only")
    initial = next((r["controller_sha256"] for r in rounds if r["round"] == 0), None)
    return {"run": directory.relative_to(runs_root).as_posix(), "backend": backend,
            "config_sha256": digest(directory / "config.json"), "environment_sha256": env,
            "split": split, "arm": config.get("arm"), "initial_controller_sha256": initial,
            "conditions": {key: config.get(key) for key in ("masses", "seed", "rounds", "no_assist")},
            "rounds": rounds, "sweep_trial_count": len(sweep) if sweep_valid else None,
            "sweep_passes": sum(t.get("success") is True for t in sweep) if sweep_valid else None,
            "warnings": warnings}


def compare(video, text):
    blockers = []
    if video["backend"] != "configured-real" or text["backend"] != "configured-real":
        blockers.append("both runs must explicitly configure the real backend")
    for key, label in (("initial_controller_sha256", "starting controller"),
                       ("environment_sha256", "environment"), ("split", "split")):
        a, b = video[key], text[key]
        if a is None or b is None:
            blockers.append(f"missing {label} provenance")
        elif a != b:
            blockers.append(f"{label} mismatch")
    for key in ("masses", "seed", "rounds", "no_assist"):
        a, b = video["conditions"][key], text["conditions"][key]
        if a is None or b is None:
            blockers.append(f"missing {key} condition")
        elif a != b:
            blockers.append(f"{key} mismatch")
    return {"video": video["run"], "text": text["run"],
            "status": "blocked" if blockers else "structural checks passed; protocol review still required",
            "blockers": blockers,
            "limitations": "Does not verify model settings, prompt equality, seed isolation, video delivery, or causality."}


def audit(runs_root):
    runs_root = Path(runs_root).resolve()
    candidates = {p.parent for pattern in ("config.json", "summary.json", "sweep.json")
                  for p in runs_root.rglob(pattern)}
    runs = [audit_run(p, runs_root) for p in sorted(candidates)]
    videos = [r for r in runs if r["arm"] == "video"]
    texts = [r for r in runs if r["arm"] == "text"]
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "runs_root": str(runs_root),
            "scope": "Saved artifacts only; no live process, model, or simulator inspection. Files may change during scan.",
            "runs": runs, "candidate_comparisons": [compare(v, t) for v, t in itertools.product(videos, texts)]}


def markdown(report):
    lines = ["# Saved run audit", "", f"Generated: {report['generated_at_utc']}", "", report["scope"], "",
             "Configured-real is a config declaration, not proof of execution or an immutable environment.", "",
             "| Run | Backend | Latest saved passes/trials | Split |", "| --- | --- | --- | --- |"]
    for run in report["runs"]:
        latest = run["rounds"][-1] if run["rounds"] else {}
        passes = latest.get("passes", run["sweep_passes"])
        count = latest.get("trial_count", run["sweep_trial_count"])
        lines.append(f"| {run['run']} | {run['backend']} | {passes}/{count} | {run['split'] or 'unknown'} |")
    for run in report["runs"]:
        lines += ["", f"## {run['run']}", ""]
        lines += [f"- {warning}" for warning in run["warnings"]] or ["No inventory warnings."]
    lines += ["", "## Candidate comparisons", ""]
    for pair in report["candidate_comparisons"]:
        lines += [f"- {pair['video']} vs {pair['text']}: {pair['status']}."]
        lines += [f"  - {b}" for b in pair["blockers"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    root = args.runs.resolve()
    for output in (args.json, args.markdown):
        if output.resolve().is_relative_to(root):
            parser.error("report outputs must be outside the audited runs directory")
    report = audit(root)
    for output, content in ((args.json, json.dumps(report, indent=2) + "\n"),
                            (args.markdown, markdown(report))):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)


if __name__ == "__main__":
    main()
