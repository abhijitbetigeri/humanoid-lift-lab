# Final-hour demo runbook

## 60-second walkthrough

**0–10 seconds:** “We test whether Argon can diagnose failed simulated humanoid lifts and revise a readable
controller. Physics scores lift height, hold time, falls, drops, and assistance.”

**10–25 seconds:** In the voice companion, select **Earlier memory-assisted pilot**, then **Round 0**: 0/8 passed.
Select **Round 1**: 6/8 passed, covering 10–35 kg. Show the saved 25 kg image. Say: “This condition gives Argon a
validated expert reference. It demonstrates useful reference reuse.”

**25–40 seconds:** Select **Best versus final round**, then **Ask Argon**. Typed input is a reliable backup for
microphone permission problems. Continue the walkthrough while the spoken response is prepared.

**40–55 seconds:** Select **Round 2**: 1/8 passed. “More iterations made this controller worse. We retained the
best development candidate instead of overwriting it. The second revision fixed 5 kg but lost earlier successes.”

**55–60 seconds:** “These are modified, assisted simulation development results. Generalization needs a held-out
evaluation. The independent video and text runs are separate conditions and may use a revised simulator setup.”

## If the network is slow

Keep the saved-evidence panel visible: it requires no model calls. Show best versus final outcomes directly.
If TTS fails, the text answer remains. If Argon is unavailable, do not present a manually written explanation
as a live model response. Saved numerical results and the trial image remain a valid walkthrough.

## Launch and freeze

```bash
.venv/bin/python -m voice.app
```

Open http://127.0.0.1:8791/. A fresh clone uses the committed `data/voice-evidence/snapshot.json` and preview
when ignored `runs/` files are absent. The page labels the snapshot. No Gemini key is needed to inspect the saved
panel; new voice/text answers require a configured key and paid model access.

The separate live-lift demo stays at port 8790 if its owner starts it. Do not start duplicate trial processes
during the presentation. The voice companion explains saved evidence and cannot start a lift.

Final checks:

1. Open the page and inspect one saved result without submitting a question.
2. Confirm microphone permission once; keep a typed question ready.
3. Check the selected run and best/final distinction, video URL, and repository URL.
4. Rehearse once, then freeze the demo's controller/evidence. Keep later runs separately named.

Do not claim stock-G1 payload capability, independent strategy discovery from reference reuse, video superiority
from unmatched setups, or that best-round performance was final-round performance.

Voice/evidence artifacts: `voice/`, `data/voice-evidence/`, `docs/voice.md`, and `reports/memory-pilot-results.md`.
The simulator, live-lift demo, and results-page changes belong to the other active workstreams.
