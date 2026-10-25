"""Live demo app: chat or voice in the browser starts a run; the page and the MuJoCo viewer follow it.

  .venv/bin/python -m demo.app            # page at http://localhost:8790, opens the MuJoCo viewer window too
  .venv/bin/python -m demo.app --no-viewer

Type or say e.g. "lift a 50 pound box", "try 40", "25 kilos, 3 rounds". A bare number means pounds. Each request runs demo/live.py in a
subprocess (trial -> render -> Argon critique and rewrite -> re-test), which writes runs/live/state.json.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import pathlib
import re
import shutil
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE = ROOT / "runs" / "live"
PORT = 8790
MIN_KG, MAX_KG = 5.0, 40.0
WORDS = {"five": 5, "ten": 10, "fifteen": 15, "twenty": 20, "twenty five": 25, "twenty-five": 25, "thirty": 30,
         "thirty five": 35, "thirty-five": 35, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80}

_proc: subprocess.Popen | None = None
_lock = threading.Lock()


def parse(text: str):
    """-> (mass_kg or None, rounds, note). Accepts digits or common number words, kg/kilos or lb/pounds; no unit means pounds."""
    t = text.lower()
    for w in sorted(WORDS, key=len, reverse=True):
        t = re.sub(rf"\b{w}\b", str(WORDS[w]), t)
    rounds = 3
    m = re.search(r"(\d+)\s*(?:rounds?|tries|attempts|iterations)", t)
    if m:
        rounds = max(1, min(4, int(m.group(1))))
        t = t[:m.start()] + t[m.end():]
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kilo\w*|lb|lbs|pounds?)?", t)
    if not m:
        return None, rounds, "Tell me how heavy the box is, e.g. \"lift a 50 pound box\" or \"try 30 pounds\"."
    val, unit = float(m.group(1)), (m.group(2) or "lb")
    kg = val * 0.453592 if unit.startswith(("lb", "pound")) else val
    kg = round(kg * 2) / 2  # nearest 0.5 kg
    if not MIN_KG <= kg <= MAX_KG:
        said = f"{val:g} lb" if unit.startswith(("lb", "pound")) else f"{val:g} kg ({val * 2.20462:.0f} lb)"
        return None, rounds, (f"{said} is outside what this robot class is rated for: about "
                              f"{MIN_KG * 2.20462:.0f}-{MAX_KG * 2.20462:.0f} lb ({MIN_KG:g}-{MAX_KG:g} kg). Pick a box in that range.")
    return kg, rounds, None


def start(kg: float, rounds: int) -> str:
    global _proc
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return "A run is still going; wait for it to finish."
        log = open(LIVE / "last_run.log", "w")
        _proc = subprocess.Popen([sys.executable, "-m", "demo.live", "--mass", f"{kg:g}", "--rounds", str(rounds),
                                  "--no-server"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    return (f"Starting: {kg * 2.20462:.0f} lb box ({kg:g} kg), up to {rounds} Argon fix round(s). "
            "The robot tries it first, then Argon watches the video and rewrites the controller.")


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            text = json.loads(self.rfile.read(n) or b"{}").get("text", "")
        except Exception:  # noqa: BLE001
            text = ""
        kg, rounds, err = parse(text)
        body = {"reply": err, "started": False} if kg is None else {"reply": start(kg, rounds), "started": True}
        if kg is not None and body["reply"].startswith("A run"):
            body["started"] = False
        out = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-viewer", action="store_true")
    a = ap.parse_args(argv)
    LIVE.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "demo" / "index.html", LIVE / "index.html")
    viewer = None
    if not a.no_viewer:
        mjpython = pathlib.Path(sys.executable).with_name("mjpython")
        viewer = subprocess.Popen([str(mjpython), "-m", "demo.viewer"], cwd=ROOT)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Handler, directory=str(LIVE)))
    print(f"live demo: http://localhost:{PORT}/  (Ctrl-C to quit)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if _proc is not None and _proc.poll() is None:
            _proc.terminate()
        if viewer is not None:
            viewer.terminate()


if __name__ == "__main__":
    main()
