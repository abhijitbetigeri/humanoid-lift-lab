# Lift Lab voice companion

Start from the project root:

```bash
.venv/bin/python -m voice.app
```

Open **http://127.0.0.1:8791/**. The companion serves the existing results page at `/results/` and does not change
the separate live simulation demo on port 8790. It is a local application; the static Render deployment cannot
run these server endpoints. No public hosting configuration was changed.

Choose an experiment, round, and optional payload. Type a question or record up to 20 seconds, stop, then select
**Ask Argon**. The recording is sent only on submission. A recognized transcript and text explanation appear first;
spoken playback follows. Autoplay can be disabled, and audio controls allow replay without another API call.
Microphone denial/unavailability leaves typed questions usable. The browser asks for microphone permission.

## Models and data flow

1. The Python server builds a bounded context from the selected saved development run: round statistics, selected
   trials/telemetry, controller text, and any saved critique (explicitly labelled a hypothesis).
2. `gemini-4-argon` receives that evidence plus the typed question or native inline audio. It returns a transcript
   and a short explanation. It receives no video through this interface.
3. `gemini-3.8-flash-tts`, voice `Kore`, converts the explanation to WAV audio. Argon itself does not generate speech.

The server reads `GEMINI_API_KEY` from the environment or existing project `.env` through `argon_env.load_env`.
It never sends that key to the browser or serves the project root. The current environment has `google-genai==2.33.0`;
the voice component's dependency is recorded in `voice/requirements.txt`. Existing simulation packages are unchanged.

Every submitted question makes paid Google API calls. No model calls occur on page load, example selection, or
cached playback. The page states what is sent before submission. Recordings are not saved to disk; jobs and
generated audio are ephemeral in server memory, expire after 15 minutes, and are capped at 24 jobs. Provider-side
handling follows the configured Google service; requests explicitly use `store=False`.

Requests are restricted to loopback hosts and matching origins, and submission requires a per-server token.
The service supports one active answer at a time. Body size is capped, MIME types are allowlisted, and the browser
recording duration is capped at 20 seconds. The server enforces a 3 MB audio limit but does not inspect duration of
manually crafted API uploads. Raw provider errors are not returned to the browser.

## Scope

This is a question/answer interface for saved evidence. It cannot execute controllers, start simulations, flash
hardware, modify files, or update skill memory. It rejects explicitly marked held-out/test/evaluation runs and stub
runs. Legacy video/text runs without split labels are described as historical development evidence; no held-out
generalization claims are authorized. Only known run IDs are accepted; the user cannot supply arbitrary file paths.

If Google TTS fails, the grounded text answer remains available. If Argon fails, a visible error is shown rather
than an invented answer. The saved 25 kg preview is an existing simulation image, not video observed during the
voice conversation. Best-round answers are labelled with the actual selected round; final-round comparisons use
the supplied round summaries.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -p test_voice.py -v
node --check voice/client.js
```

A live synthetic round trip was completed using TTS → Argon audio input → TTS. It sent a generic question and a
synthetic six-of-eight fixture, not project controllers, run telemetry, or microphone recordings. Argon correctly
transcribed the question and answered six of eight; generated answer audio was mono 24 kHz WAV. Artifacts are in
`runs/voice_smoke/`. Synthetic fixture statements are not new robotics results.

To repeat that **paid** test with a fresh output path:

```bash
.venv/bin/python -m voice.smoke --out runs/voice_smoke_002
```

`voice/browser_check.cjs` verifies the UI in Chrome with a fake microphone and intercepts all paid request routes.
It covers typed/audio requests, playback, text fallback, mobile overflow, and JavaScript errors. It requires an
existing Playwright installation (`LIFT_LAB_PLAYWRIGHT` may specify its module path) and the running local server.
Reports/screenshots are under `runs/voice-*`. Actual physical-microphone capture still requires a user browser check.

## Official API references

- [Argon model capabilities](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon)
- [Native inline audio input](https://ai.google.dev/gemini-api/docs/audio)
- [Gemini speech generation](https://ai.google.dev/gemini-api/docs/speech-generation)

Implementation: `voice/service.py` (context and model adapters), `voice/app.py` (local server/jobs), and
`voice/index.html`, `voice/client.js`, `voice/style.css` (browser interface). No changes to controller/scorer APIs
or existing demo files were needed.
