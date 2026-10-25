"""Argon (gemini-4-argon) calls for the controller loop.

write_controller(task_md, api_md) -> code
critique_and_fix(code, trials, video_paths, use_video=True, history=None) -> (critique_md, new_code)

Every call is logged to <log_dir>/calls.jsonl (set with set_log_dir). The API key is read from the environment by
google-genai and is never printed or logged here.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loop import prompts  # noqa: E402

MODEL = "gemini-4-argon"
MAX_OUT = 65536
THINKING = "medium"
POLL_S = 5
HTTP_TIMEOUT = 900
VIDEO_FPS = 2
PRICE_IN, PRICE_OUT, PRICE_CACHED = 2.0, 10.0, 0.10  # $/M tokens

_client = None
_log_dir = ROOT / "runs" / "default"


def set_log_dir(path) -> None:
    global _log_dir
    _log_dir = pathlib.Path(path)


def client():
    global _client
    if _client is None:
        from argon_env import load_env
        from google import genai
        load_env()
        _client = genai.Client()
    return _client


# ---------------------------------------------------------------- logging

def _log(rec: dict) -> None:
    _log_dir.mkdir(parents=True, exist_ok=True)
    with (_log_dir / "calls.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _cost(usage) -> dict:
    if usage is None:
        return {}
    tin = usage.total_input_tokens or 0
    tcached = usage.total_cached_tokens or 0
    tout = usage.total_output_tokens or 0
    tthink = usage.total_thought_tokens or 0
    video_in = sum(m.tokens or 0 for m in (usage.input_tokens_by_modality or []) if str(m.modality) == "video")
    cost = (tin - tcached) * PRICE_IN / 1e6 + tcached * PRICE_CACHED / 1e6 + (tout + tthink) * PRICE_OUT / 1e6
    return {"input_tokens": tin, "cached_tokens": tcached, "video_tokens": video_in, "output_tokens": tout,
            "thought_tokens": tthink, "est_cost_usd": round(cost, 4)}


# ---------------------------------------------------------------- core call

def _join_outputs(interaction) -> str:
    texts = []
    for step in interaction.steps or []:
        if getattr(step, "type", None) == "model_output":
            for c in getattr(step, "content", None) or []:
                t = getattr(c, "text", None)
                if t:
                    texts.append(t)
    return "".join(texts) if texts else (interaction.output_text or "")


def call(input_, kind: str, previous_interaction_id: str | None = None, prompt_chars: int | None = None):
    """One background Interactions call, polled to completion. Returns (text, interaction_id, log record)."""
    c = client()
    t0 = time.time()
    kw = dict(model=MODEL, input=input_, background=True,
              generation_config={"max_output_tokens": MAX_OUT, "thinking_level": THINKING}, timeout=HTTP_TIMEOUT)
    if previous_interaction_id:
        kw["previous_interaction_id"] = previous_interaction_id
    it = None
    for attempt in range(3):
        try:
            it = c.interactions.create(**kw)
            break
        except Exception as e:  # transient create errors
            if attempt == 2:
                _log({"kind": kind, "error": repr(e)[:500], "ts": time.time()})
                raise
            time.sleep(5 * (attempt + 1))
    while it.status in ("in_progress", "queued"):
        time.sleep(POLL_S)
        try:
            it = c.interactions.get(it.id, timeout=HTTP_TIMEOUT)
        except Exception:
            continue
    text = _join_outputs(it)
    rec = {"kind": kind, "ts": time.time(), "interaction_id": it.id, "status": it.status,
           "latency_s": round(time.time() - t0, 1), "prompt_chars": prompt_chars, "output_chars": len(text),
           **_cost(it.usage)}
    _log(rec)
    if it.status != "completed" and not text:
        raise RuntimeError(f"Argon interaction {it.id} ended with status {it.status}")
    return text, it.id, rec


# ---------------------------------------------------------------- video

def upload_video(path) -> str:
    """Upload an mp4 through the Files API, wait until ACTIVE, return its URI."""
    c = client()
    f = c.files.upload(file=str(path), config={"mime_type": "video/mp4"})
    t0 = time.time()
    while f.state is not None and str(f.state).endswith("PROCESSING"):
        if time.time() - t0 > 300:
            raise RuntimeError(f"video {path} still processing after 300 s")
        time.sleep(2)
        f = c.files.get(name=f.name)
    if str(f.state).endswith("FAILED"):
        raise RuntimeError(f"video {path} failed processing")
    return f.uri


def video_part(uri: str, fps: float = VIDEO_FPS) -> dict:
    return {"type": "video", "uri": uri, "mime_type": "video/mp4", "processing": {"type": "static", "fps": fps}}


# ---------------------------------------------------------------- code extraction

FENCE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S)
FILE_MARK = re.compile(r"=====\s*FILE:\s*\S*\s*=====\s*\n(.*?)(?:=====\s*END FILE\s*=====|\Z)", re.S)


def validate_code(code: str) -> str | None:
    """Return None if the code compiles and defines top-level run(robot), else an error string."""
    try:
        compile(code, "controller.py", "exec")
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            if len(node.args.args) >= 1:
                return None
            return "`run` must take one argument: def run(robot):"
    return "no top-level `def run(robot):` found"


def extract_code(text: str) -> tuple[str | None, str | None]:
    """Pick the controller out of a reply. Returns (code, error)."""
    cands = [m.group(1) for m in FILE_MARK.finditer(text)] + [m.group(1) for m in FENCE.finditer(text)]
    cands = [c for c in cands if "def run" in c]
    if not cands and "def run(" in text:  # unfenced reply: from the first import/def to the end
        m = re.search(r"^(?:import |from |def |[A-Z_]+ *=)", text, re.M)
        cands = [text[m.start():]] if m else []
    if not cands:
        return None, "no python code block containing `def run(robot):`"
    err = None
    for c in sorted(cands, key=len, reverse=True):  # longest valid candidate wins
        c = c.strip() + "\n"
        err = validate_code(c)
        if err is None:
            return c, None
    return None, err


def _get_code(text: str, iid: str, kind: str, full_input) -> str:
    code, err = extract_code(text)
    if code:
        return code
    fix = prompts.fix_prompt(err)
    try:
        text2, _, _ = call(fix, kind + "_retry", previous_interaction_id=iid, prompt_chars=len(fix))
    except Exception:
        # previous_interaction_id unavailable: resend everything with the error appended
        inp = full_input + "\n\n" + fix if isinstance(full_input, str) else full_input + [{"type": "text", "text": fix}]
        text2, _, _ = call(inp, kind + "_retry_full")
    code, err2 = extract_code(text2)
    if code:
        return code
    raise ValueError(f"Argon returned no valid controller after a retry: {err2}")


# ---------------------------------------------------------------- public API

def write_controller(task_md: str | None = None, api_md: str | None = None) -> str:
    task_md = task_md or prompts.TASK_MD
    api_md = api_md or prompts.api_md()
    p = prompts.writer_prompt(task_md, api_md)
    text, iid, _ = call(p, "write", prompt_chars=len(p))
    _last["reply"] = text
    return _get_code(text, iid, "write", p)


def format_trials(trials: list[dict]) -> str:
    """Trials are result.json dicts, optionally with a 'telemetry' summary dict (see loop/telemetry.py)."""
    from loop.telemetry import format_trials_md
    return format_trials_md(trials)


def format_history(history: list[dict] | None) -> str:
    if not history:
        return ""
    lines = []
    for h in history:
        lines.append(f"- round {h['round']}: passed {h.get('passed', [])} of {h.get('masses', [])}; "
                     f"mean assist {h.get('mean_assist_n')} N. Changes made after it: {h.get('changes', '').strip()[:600]}")
    return "\n".join(lines)


_last: dict = {}


def critique_and_fix(code: str, trials: list[dict], video_paths: list | None = None, use_video: bool = True,
                     history: list[dict] | None = None, task_md: str | None = None,
                     api_md: str | None = None, video_labels: list[str] | None = None) -> tuple[str, str]:
    task_md = task_md or prompts.TASK_MD
    api_md = api_md or prompts.api_md()
    video_paths = [pathlib.Path(v) for v in (video_paths or [])] if use_video else []
    labels = video_labels or [v.stem for v in video_paths]
    index_md = "\n".join(f"{i + 1}. {lab}" for i, lab in enumerate(labels))
    p = prompts.critic_prompt(task_md, api_md, code, format_trials(trials), format_history(history),
                              use_video and bool(video_paths), index_md)
    if video_paths:
        inp = [{"type": "text", "text": p}]
        t0 = time.time()
        for v, lab in zip(video_paths, labels):
            inp.append({"type": "text", "text": f"Video: {lab}"})
            inp.append(video_part(upload_video(v)))
        _log({"kind": "upload", "n_videos": len(video_paths), "latency_s": round(time.time() - t0, 1),
              "bytes": sum(v.stat().st_size for v in video_paths), "ts": time.time()})
    else:
        inp = p
    text, iid, _ = call(inp, "critique_video" if video_paths else "critique_text", prompt_chars=len(p))
    _last["reply"] = text
    code_new = _get_code(text, iid, "critique", inp)
    # critique = everything before the final code block
    cut = text.rfind("```python")
    critique = (text[:cut] if cut > 0 else text).strip()
    return critique, code_new
