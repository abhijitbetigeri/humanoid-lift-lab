# Submission form — ready to paste

Project: **Humanoid Lift Lab**

Remaining required value: a publicly accessible demo URL. The MP4 is ready; the Render embed is being published.

## Project Description

Humanoid Lift Lab: Gemini Argon as a robot-control engineer.

Warehouse loads change, and even a working lifting controller can fail on a different payload. We built a closed loop that runs a humanoid lift in MuJoCo, renders the attempt, gives Argon video and numerical telemetry, and asks it to diagnose failures and rewrite a readable Python controller. A deterministic scorer then checks the next attempt; the model does not grade itself.

Starting from an engineer-written reference, both video-plus-telemetry and telemetry-only adaptation improved from 7/8 to 8/8 successful tested payloads after four revision rounds, across 5–40 kg (about 11–88 lb). The video controller repaired a 5 kg drop while retaining the heavier lifts. Success requires at least 0.45 m rise, a 3-second hold, no fall/drop/error, and mean balance assistance at or below 60 N. A keep-best loop preserves progress when a rewrite regresses.

The project includes a live payload-request demo, traceable controller/critique/results artifacts, optional validated skill memory, and spoken questions about saved evidence with generated speech responses.

These are development results in a modified, assisted G1-based simulation—not hardware validation or held-out generalization. Both feedback conditions reached 8/8, so we do not claim video superiority.

## Public Project GitHub Repository

https://github.com/abhijitbetigeri/humanoid-lift-lab

## 1-Minute Demo Video

**ADD THE VERIFIED HOSTED VIDEO URL HERE.**

Video file: `submission/humanoid-lift-lab-60s.mp4` (60.0 s, 1280x720, H.264/AAC, narrated and captioned).

## Describe your use of Google products

Gemini 4 Argon (gemini-4-argon) is the controller critic and code generator. Through the Gemini API's Interactions API, it receives the task, motion-API documentation, current Python controller, scored trial results, telemetry, and revision history. The video condition uploads MuJoCo renders through the Files API so Argon can inspect the attempts before returning a complete revised controller. Background calls support the controller-revision workflow.

The voice companion sends recorded questions directly to Argon as audio, grounded in selected saved experiment evidence. Gemini 3.8 Flash TTS (gemini-3.8-flash-tts) speaks the resulting explanation and also generated the submission video's narration.

Google DeepMind's MuJoCo supplies simulation and trajectory replay. We use the Menagerie G1 model as a base, with explicitly documented strength scaling and budgeted balance assistance. No model weights were trained, and no hardware deployment is claimed.

## Feedback for the Google DeepMind team on Argon

Argon was most useful when it had an explicit motion API, numerical outcomes, execution history, and a working reference program. Both video and telemetry-only adaptation reached 8/8 tested payloads from a 7/8 reference. Revisions could also regress sharply; plausible explanations did not guarantee successful physics. Preserving the best controller and checking every rewrite were essential.

We would value smaller targeted code edits, explicit preservation constraints for previously passing cases, and video diagnoses that distinguish visible evidence from inferred causes and express timestamp/causal uncertainty.

For longer calls, incremental progress and clearer token accounting would improve the developer experience. In a separate long-output probe we measured 39,434 output tokens in 328 seconds, about 120 tokens/second, while the reported thought-token count was zero. Clarifying when that field should be zero would help.

Our experiment does not yet show a video advantage over telemetry. We plan disjoint evaluation conditions and repeated runs to measure it rigorously.

## Final handoff

- Public repository verified through the unauthenticated GitHub API: private=false.
- Final adaptation claims checked against all 16 individual recorded final trial results.
- Exact demo duration/codecs and full audio/video decode checked.
- Both arms reached 8/8. No video-superiority, hardware, or unseen-condition claim.
- Latest adaptation config files lack explicit split/environment hashes. Results are disclosed as development evidence; do not present them as a frozen benchmark.
- Current simulator differs from the earlier memory pilot; do not merge those results into one learning curve.
- No Managed Agents integration is claimed. ASPIRE inspired optional memory; it is not a packaged dependency or reproduced benchmark.
- Upstream G1 model/meshes are reused with notices. Describe the simulation/loop/UI/evaluation work as the project contribution.
- Static results hosting and the local Python voice/live services are different deployment modes.
- Watch the hosted video without signing in. If the form enforces YouTube specifically, upload the ready MP4 there and replace the video URL.
- No form was submitted and no YouTube upload is claimed by this packet.
