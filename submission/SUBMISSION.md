# Submission form — ready to paste

Project: **Humanoid Lift Lab**

All five form values are filled below. The demo uses a direct hosted MP4; the form shows YouTube as an example, so verify that it accepts this host.

## Project Description

Humanoid Lift Lab: Gemini 4 Argon fixes a humanoid's lift in simulation before deployment.

Humanoids can do the lift-and-shift work of small businesses, workshops and households: boxes, stock and furniture parts, often in cramped spaces where getting extra people to help is hard. Every load is different, and a lift tuned for one box can tip the robot or drop the next. There is no robotics engineer on site to re-tune it, and testing on the real robot risks broken boxes, damaged robots or injuries. Our loop finds and fixes those failures in MuJoCo first: the robot attempts the lift, we render the attempt, Argon watches the video with numerical telemetry, diagnoses the physics and rewrites a readable Python controller. A deterministic physics scorer checks the next attempt; the model never grades itself, and a keep-best rule discards any rewrite that regresses.

Starting from an engineer-written controller that lifted 22–88 lb but dropped a light 11 lb box, both video-plus-telemetry and telemetry-only adaptation went from 7/8 to 8/8 tested loads (11–88 lb) in four revision rounds, fixing the 11 lb drop without losing the heavier lifts. Success requires at least 0.45 m of rise, a 3-second hold, no fall or drop, and mean balance assist at or below 60 N. Starting instead from a textbook stoop-lift controller, no arm reached a pass in 6–8 rounds; that is our stated limit.

The live demo takes a request by chat or voice ("lift an 11 pound box"), runs it in MuJoCo with regression checks at 33 and 66 lb, shows Argon's timestamped diagnosis and the exact code diff it made, and re-tests. A results site shows every round, critique and video, and a voice companion answers spoken questions about the saved evidence.

These are development results in a modified, assisted G1-based simulation (torques scaled to full-size humanoid class, in-place lift only), not hardware validation or held-out generalization. Both feedback conditions reached 8/8, so we do not claim video superiority.

## Public Project GitHub Repository

https://github.com/abhijitbetigeri/humanoid-lift-lab

## 1-Minute Demo Video

https://humanoid-lift-lab.onrender.com/assets/humanoid-lift-lab-60s.mp4

Video file: `submission/humanoid-lift-lab-60s.mp4` (60.0 s, 1280x720, H.264/AAC, narrated and captioned).

## Describe your use of Google products

Gemini 4 Argon (gemini-4-argon) is the controller critic and code generator. In the live demo each call carries the video of every attempt so far in one context. Through the Gemini API's Interactions API, it receives the task, motion-API documentation, current Python controller, scored trial results, telemetry, and revision history. The video condition uploads MuJoCo renders through the Files API so Argon can inspect the attempts before returning a complete revised controller. Background calls support the controller-revision workflow.

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
