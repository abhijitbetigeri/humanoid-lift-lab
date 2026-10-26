# Humanoid Lift Lab

**Gemini 4 Argon fixes a humanoid's lift in simulation before deployment: it watches failed lifts in MuJoCo, diagnoses the physics, rewrites a readable controller, and a deterministic physics scorer decides whether the fix holds.**

Humanoids can do the lift-and-shift work of small businesses, workshops and households: boxes, stock and furniture parts, often in cramped spaces where getting extra people to help is hard. Every load is different, and a lift tuned for one box can tip the robot or drop the next. There is no robotics engineer on site to re-tune it, and testing on the real robot risks broken boxes, damaged robots or injuries. Lift Lab finds and fixes those failures in simulation first, so the robot in the field only gets controllers that physics has already passed.

## Demo videos and links

| | Link |
| --- | --- |
| **Results site** (every round, critique and video; embedded 60-second demo) | https://humanoid-lift-lab.onrender.com |
| **60-second narrated demo** (submission video) | https://humanoid-lift-lab.onrender.com/assets/humanoid-lift-lab-60s.mp4 |
| **Live demo, part 1**: a chat/voice request runs in MuJoCo, fails, and Argon watches the video and diagnoses it | https://www.loom.com/share/529241066a694e6c90bc78e6818e0f40 |
| **Live demo, part 2**: Argon's rewrites are re-tested against the 11 lb box and the 33/66 lb regression checks | https://www.loom.com/share/c2def0c1658049b190d012b0ff24cce2 |
| **Replay of the 15:52 live run that passed** (saved real results, labelled REPLAY on screen): 11 lb fixed in 4 attempts, two regressing rewrites discarded | https://www.loom.com/share/e5cbc5935e594e2cb92b87527f2c089a |
| Submission answers | [submission/SUBMISSION.md](submission/SUBMISSION.md) |
| Recorded results | [submission/results.json](submission/results.json) |

The Render site is static. The live demo (`demo.app`) and the voice companion (`voice.app`) are local Python services; see *Run locally*.

## What it does

1. Start with an engineer-written controller or a generated program over the supplied humanoid API.
2. Simulate the lift and record trajectories, grip slip, joint effort, balance, and assistance.
3. Render the actual trajectory as hero/side video with telemetry overlays.
4. Give Argon the controller, trial evidence, and history. The video condition includes rendered video; the text condition receives telemetry only.
5. Execute the rewritten Python controller and score it with fixed criteria. Optional `--keep-best` revises the strongest previous candidate when a new program regresses.

The simulator, scene, inverse kinematics, and motion primitives are supplied engineering. Argon generates task-level control programs; it does not learn motor weights from scratch or infer payload mass from images.

## Recorded adaptation results

Eight tested loads: **11, 22, 33, 44, 55, 66, 77, 88 lb** (5–40 kg in steps of 5 kg). The hand-written reference lifted 22–88 lb but dropped the light 11 lb box. Both conditions started from the same hand-written reference; the seed schedule was base seed 0 plus mass index.

| Condition | Initial controller | Round 4 controller |
| --- | --- | --- |
| Video + telemetry | 7/8 passes | **8/8 passes** |
| Telemetry only | 7/8 passes | **8/8 passes** |

Four revision rounds means five evaluated controller versions, including round 0. Both runs initially regressed before recovering. The video run's 11 lb (5 kg) case improved from a drop to a 0.6867 m rise held for 4.966 s. Final controller snapshots and recorded metrics are in [submission/](submission/).

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

Open http://127.0.0.1:8790/ and type or say a request such as `lift an 11 pound box` (a bare number means pounds; 11–88 lb is accepted). Each attempt also runs 33 and 66 lb regression checks; the page shows what Argon watched, its timestamped diagnosis and the code diff, and a keep-best rule discards rewrites that regress. Loads of 22–88 lb already pass with the deployed controller, so Argon only steps in at the edges (11 lb). New repair attempts make paid Argon calls, and a fix is not guaranteed within the default 3 rounds. Omit `--no-viewer` to launch the native MuJoCo viewer on the development Mac.

**Replay a saved live run** (no new simulation or model calls; labelled REPLAY on the page), while `demo.app` is running:

```bash
.venv/bin/python -m demo.replay 155234_m5
```

Raw `runs/live/` is git-ignored, so this works on the machine that recorded the run.

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
