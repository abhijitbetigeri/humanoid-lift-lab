# Humanoid Lift Lab

**Gemini Argon observes failed simulated lifts, diagnoses the behavior, rewrites a readable controller, and faces a deterministic physics score.**

Warehouse loads change. Even a working lifting program can fail when its grip, clearance, or motion schedule no longer fits the payload. Lift Lab makes that adaptation process visible and measurable in MuJoCo.

[Watch/download the 60-second narrated demo](submission/humanoid-lift-lab-60s.mp4) · [Submission answers](submission/SUBMISSION.md) · [Recorded results](submission/results.json)

Public landing page: https://humanoid-lift-lab.onrender.com/#demo. The embedded demo and direct MP4 are static assets;
the local voice and live-simulation services still run separately.

## What it does

1. Start with an engineer-written controller or a generated program over the supplied humanoid API.
2. Simulate the lift and record trajectories, grip slip, joint effort, balance, and assistance.
3. Render the actual trajectory as hero/side video with telemetry overlays.
4. Give Argon the controller, trial evidence, and history. The video condition includes rendered video; the text condition receives telemetry only.
5. Execute the rewritten Python controller and score it with fixed criteria. Optional `--keep-best` revises the strongest previous candidate when a new program regresses.

The simulator, scene, inverse kinematics, and motion primitives are supplied engineering. Argon generates task-level control programs; it does not learn motor weights from scratch or infer payload mass from images.

## Recorded adaptation results

Eight tested payloads: **5, 10, 15, 20, 25, 30, 35, 40 kg** (approximately 11–88 lb). Both conditions started from the same hand-written reference; the seed schedule was base seed 0 plus mass index.

| Condition | Initial controller | Round 4 controller |
| --- | --- | --- |
| Video + telemetry | 7/8 passes | **8/8 passes** |
| Telemetry only | 7/8 passes | **8/8 passes** |

Four revision rounds means five evaluated controller versions, including round 0. Both runs initially regressed before recovering. The video run's 5 kg case improved from a drop to a 0.6867 m rise held for 4.966 s. Final controller snapshots and recorded metrics are in [submission/](submission/).

**Scope:** these are development trials in a modified G1-based, assisted simulation. Joint strength is increased and assistance is explicitly budgeted. They are not stock-G1 hardware ratings or held-out generalization results. Since both conditions reached 8/8, this experiment does not establish video superiority. Earlier attempts from a weak baseline were unsuccessful; the working reference is an important prior.

Success requires rise >=0.45 m, hold >=3 s, no fall/drop/controller error, and mean balance assistance <=60 N. The numerical scorer decides, not the model's critique. See [calibration](docs/calibration.md) and [evaluation protocol](docs/evaluation-plan.md).

## Run locally

The project was developed on macOS with Python 3.14. Offscreen rendering requires a working graphics environment.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Set `GEMINI_API_KEY` in the environment or an untracked project `.env` for new model requests.

**Saved evidence and voice explanations:**

```bash
.venv/bin/python -m voice.app
```

Open http://127.0.0.1:8791/. The saved-evidence panel works without API calls and has a committed fallback snapshot for fresh clones. New questions use Argon for text/audio understanding and Gemini TTS for speech. [Voice guide](docs/voice.md).

**Live payload request and repair loop:**

```bash
.venv/bin/python -m demo.app --no-viewer
```

Open http://127.0.0.1:8790/ and enter an explicit request such as `try 5 kg`. The existing browser voice input can also supply the request. New repair attempts make paid Argon calls. Omit `--no-viewer` to launch the native MuJoCo viewer on the development Mac.

**Reproduce an adaptation condition in a new output directory:**

```bash
.venv/bin/python -m loop.run_loop --arm video --rounds 4 --keep-best --workers 2 \
  --seed-controller sim/reference_controller.py --run-dir runs/reproduce_video
```

Use `--arm text` and a separate directory for the telemetry condition. These commands run new simulations and paid model requests; they do not guarantee reproduction of the same generated programs. Use the committed [final controller snapshots](submission/controllers/) to inspect the actual submitted programs without regeneration.

**Static results page:** `python3 -m http.server 8080 --directory viz`. Static hosting does not run either local Python service.

## Evidence and memory

`sim/` implements the environment, motion API, scorer, and renderer; `loop/` contains Argon prompting, telemetry, and the revision runner. `evals/` supplies artifact collection, provenance checks, and development validation. Raw `runs/` are ignored; selected evidence, source hashes, the video, and a portable earlier-memory-pilot snapshot are committed.

The optional ASPIRE-inspired memory admits guidance associated with independently scored development trials, checks controller/environment/artifact hashes, and excludes stubs and held-out data. It was tested in a separate expert-reference pilot; it is not automatically enabled in every loop and is not the cause claimed for the latest adaptation result. [Memory documentation](docs/skill-memory.md).

Google products used: Gemini 4 Argon, Gemini API/Interactions and Files API, Gemini 3.8 Flash TTS, MuJoCo, and the Menagerie G1 base model. The live demo's browser speech recognition is distinct from the native Argon-audio voice companion. Third-party model notices remain in [sim/g1/LICENSE](sim/g1/LICENSE). ASPIRE is methodological inspiration, not a claimed reproduction or integrated benchmark.

## Checks

```bash
.venv/bin/python -m unittest discover -s tests -q
node --check voice/client.js
```

The submission video is exactly 60.0 s, H.264/AAC, 1280x720, with Gemini TTS narration and burned-in captions. It combines actual application captures and saved trial replay; it is not a continuous live recording. Its [manifest](submission/demo-manifest.json) identifies the footage.
