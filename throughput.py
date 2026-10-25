"""Times one long background decode on gemini-4-argon.

The task doubles as a seed for idea A: a large multi-file Three.js game.
Writes runs/throughput/{log.txt, output.txt, interaction.json, stats.json}.

Usage: .venv/bin/python throughput.py [max_output_tokens]
"""
import json
import pathlib
import sys
import time

from google import genai

from argon_env import load_env

MAX_OUT = int(sys.argv[1]) if len(sys.argv) > 1 else 262144
POLL_S = 20

PROMPT = """Write a complete, playable browser 3D game as a multi-file project, using Three.js (ES modules from
https://unpkg.com/three@0.160.0) and no build step.

Game: a third-person alpine climbing game. The player ascends a procedurally generated mountain with ice,
snow and rock zones, wind gusts, a fixed rope line they can clip into, a stamina system, falling and
self-arrest, checkpoints, a HUD, a minimap, a pause menu, sound via WebAudio synthesis, and a day/night cycle.

Requirements:
- At least 25 source files with clear module boundaries (terrain, physics, player controller, camera,
  rope system, weather, HUD, audio, input, save state, debug overlay, etc.). Keep interfaces consistent
  across files.
- Write every file in full. No placeholders, no "TODO", no "rest omitted".
- Put each file between markers exactly like:
  ===== FILE: path/to/file.js =====
  <contents>
  ===== END FILE =====
- Include index.html and a README.md that lists every module and its exported interface.
"""


def main():
    load_env()
    out_dir = pathlib.Path(__file__).with_name("runs") / "throughput"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = (out_dir / "log.txt").open("w", buffering=1)

    def say(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        log.write(line + "\n")

    client = genai.Client()
    t0 = time.time()
    interaction = client.interactions.create(
        model="gemini-4-argon",
        input=PROMPT,
        background=True,
        generation_config={"max_output_tokens": MAX_OUT, "thinking_level": "medium"},
        timeout=900,
    )
    say(f"created id={interaction.id} status={interaction.status} max_output_tokens={MAX_OUT}")

    while interaction.status in ("in_progress", "queued"):
        time.sleep(POLL_S)
        try:
            interaction = client.interactions.get(interaction.id, timeout=900)
        except Exception as e:  # transient network errors shouldn't kill a paid run
            say(f"poll error (retrying): {e!r}")
            continue
        steps = getattr(interaction, "steps", None) or getattr(interaction, "outputs", None) or []
        say(f"status={interaction.status} elapsed={time.time() - t0:.0f}s steps={len(steps)}")

    elapsed = time.time() - t0
    (out_dir / "interaction.json").write_text(interaction.model_dump_json(indent=2))
    text = interaction.output_text or ""
    (out_dir / "output.txt").write_text(text)

    u = interaction.usage
    out_tok = (u.total_output_tokens or 0) if u else 0
    think_tok = (u.total_thought_tokens or 0) if u else 0
    stats = {
        "status": interaction.status,
        "elapsed_s": round(elapsed, 1),
        "output_tokens": out_tok,
        "thought_tokens": think_tok,
        "decode_tokens_per_s": round((out_tok + think_tok) / elapsed, 1) if elapsed else None,
        "visible_tokens_per_s": round(out_tok / elapsed, 1) if elapsed else None,
        "files_emitted": text.count("===== FILE:"),
        "output_chars": len(text),
        "est_cost_usd": round((out_tok + think_tok) * 10 / 1e6 + (u.total_input_tokens or 0) * 2 / 1e6, 2) if u else None,
    }
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2))
    say("done " + json.dumps(stats))


if __name__ == "__main__":
    main()
