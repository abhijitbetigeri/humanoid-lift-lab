# Implementation and judge Q&A

This is preparation material, not a submission or hardware claim. Source reviewed through `11a6e22`.

## The 20-second implementation answer

“We built a Python orchestration layer around a modified MuJoCo humanoid. It executes a controller, records the
trajectory and telemetry, renders the attempt, and gives that evidence to Gemini Argon. Argon returns a diagnosis
and a complete revised Python controller over our motion API. We execute it again and compute success with a
deterministic scorer. A keep-best rule and regression checks reduce the chance that fixing one payload loses others.”

## What we built versus what we reused

| Reused | Project work |
| --- | --- |
| MuJoCo physics engine | Lifting scene, runtime configuration, assistance and payload setup |
| Menagerie/Unitree G1 geometry and assets | Motion API, inverse kinematics, posture sequencing, grip helper, baseline/reference controllers |
| Gemini Argon/API/SDK | Prompt construction, evidence selection, revision orchestration, controller extraction and validation |
| Gemini TTS | Evidence-grounded voice companion, browser recording/playback, narration pipeline |
| Standard Python/browser/media tools | Deterministic scorer, telemetry summaries, audit/validation/memory utilities, local demo, static results, video |

ASPIRE inspired the optional memory design; its code/harness was not integrated. No model weights were trained.

## Execution path, with implementation details

1. **Input.** `demo/app.py` accepts typed/browser-transcribed requests. A parser extracts lb/kg and a revision
   budget. Bare numbers mean pounds; mass rounds to 0.5 kg. The supported task range is 5..40 kg, not a hardware rating.
2. **Starting controller.** The successful adaptation experiments and live demo start from the hand-written
   `sim/reference_controller.py`. The weak stoop baseline is a separate experiment and did not achieve success.
3. **Execution.** `sim/trial.py` starts a child Python process, constructs `Humanoid`, imports the controller and
   calls `run(robot)`. Placement uses seeded XY jitter of +/-2 cm. The simulation runs at 1 ms with a 30 s cap;
   controller exceptions and physics stops are saved. A wall-clock watchdog is 240 s.
4. **Control API.** `set_posture` interpolates actuator targets; `squat` computes leg angles; `hands_to` uses a damped
   Jacobian IK solve for the arms. It does not ask the LLM for every physics step. Motion calls are sequential.
   State includes known mass, box pose, joint values/limits, CoM, support rectangle and slip. World box positions
   must be converted to pelvis coordinates before becoming hand targets.
5. **Evidence.** The runner records qpos, time, assistance, joint-effort ratios, balance margin, slip and phase at
   30 fps in `traj.npz`. `result.json` contains outcomes; `child.json` records error and sampled jitter.
   `loop/telemetry.py` produces phase summaries, extrema/times and a 1 Hz timeline.
6. **Rendering.** `sim/render.py` replays qpos with `mj_forward`, not a new physics run. Critic videos use hero/side
   views and HUD; typically 960x360 at 10 fps. The Argon video part requests static sampling at 2 fps. Fine contact
   timing may therefore come from numerical telemetry rather than visible frames alone.
7. **Model request.** `loop/argon.py` uses `gemini-4-argon`, medium thinking, background Interactions calls and
   polling. MP4s go through the Files API. Input contains goal, API docs, current code, scores/telemetry, history
   and videos in the video condition. Batch mode selects a small subset of videos but supplies all trial results;
   live mode can include the videos of every completed target-payload attempt.
8. **Response.** The prompt requests timestamped diagnosis, named changes, and a complete fenced Python controller.
   Extraction/compile/AST checks require a top-level `run(robot)`. An invalid response can receive a repair request.
   These checks do not enforce a security sandbox or prove the program's physical correctness.
9. **Retention.** `--keep-best` ranks candidates by pass count plus a bounded partial-height term. A worse candidate
   can be discarded as the next revision's starting point. The live path also tests two anchors selected from
   15,30,20 kg; the requested load must pass without breaking those checks.
10. **Inspection.** Logs retain controllers, critiques, results, trajectories, videos, API usage and costs. The
    live UI shows evidence, diagnosis, diffs and progress. The native viewer replays the same recorded trajectory.

## The scorer — memorize these numbers

| Criterion | Threshold |
| --- | --- |
| Maximum tote rise must reach | At least 0.45 m |
| Contiguous hold at sufficient height | At least 3 s |
| Fall | Pelvis below 0.45 m fails |
| Drop | Post-liftoff return-near-floor/slip logic; slip threshold 0.25 m |
| Mean assistance | At most 60 N-equivalent over recorded trajectory |
| Execution | No controller/physics error |

Assistance is a capture-point-based PD force plus angular/vertical support; torque is counted as equivalent force.
Grip uses an inward palm-force helper, IK offset and contact friction. It is not a welded box, but these helpers
are modeling assumptions rather than validated hardware actuators. Grip caps at 450 N per palm.

## Likely questions and defensible answers

**1. What did Argon actually change?**

In the final video adaptation it added a minimum grip preload for light payloads, adjusted clearance/retraction,
added small mass-dependent lift-height compensation, and retained more lean-back for light loads. The grip formula
uses `m_grip=max(10.5,m)`: at 5 kg it requests about 177 N per palm instead of the reference's roughly 84 N.
The final text program made different preload/height changes. Both programs retain the supplied API/reference
structure. The measured result validates the combined program, not a separate causal claim about each edit.

**2. Why could the heavy box pass while the light one failed?**

The reference scaled squeeze with mass, so the light box received much less preload. Argon hypothesized that palm
alignment and torso clearance also disturbed the grip. Its repair introduced a grip floor and clearance changes.
That controller passed on rerun. We have not isolated the contribution of each proposed cause.

**3. What is the strongest measured result?**

Both reference-seeded adaptation conditions improved from 7/8 to 8/8 tested masses after four revisions: 5..40 kg,
one recorded placement per mass/round. Video-arm counts were 7,0,3,6,8; text counts 7,0,0,6,8. The video 5 kg
repair rose 0.6867 m and held 4.966 s. Use `submission/results.json` and controller snapshots as the public evidence.

**4. Does video improve performance?**

Not established. Both conditions ended at 8/8. Video made partial progress sooner in this run, but this single
experiment cannot establish a reliable advantage. A no-HUD video ablation, held-out layouts and repeated generations
would be needed. The HUD contains numbers, so video benefit is not automatically spatial reasoning benefit.

**5. Did you train an RL policy or fine-tune Gemini?**

No. This is inference-time program synthesis/revision over supplied motion primitives. Argon writes Python;
MuJoCo executes it. No demonstrations were used to train weights, and no comparison establishes superiority to RL.

**6. How much robotics work is already supplied?**

A substantial amount: robot model, environment, IK, posture interpolation, grip/assist helpers, API, physics hints
and starting reference. The demonstrated contribution is adaptation of an existing controller, not discovering
humanoid control from scratch. Weak-baseline runs did not achieve a pass in their saved 6–8 revision rounds.

**7. Is it a real G1 lifting 88 pounds?**

No. It is a G1-geometry simulation with increased joint strength and budgeted external assistance. Body mass remains
G1-like. Stock-G1 ratings, unassisted balance, contact realism and hardware safety cannot be inferred from it.

**8. Is the model grading itself? Can it cheat?**

The scorer derives pass/fail from recorded simulator state, not the critique. The criteria are provided to Argon;
“independent” means independent of its textual judgment, not secret tests. The current execution path is not
secured against malicious generated Python. Production needs stronger isolation and capability restrictions.

**9. What prevents regressions?**

The batch runner can revise the best previous candidate; the live demo also checks anchor loads. This preserves
a better starting point, but does not guarantee every new or final candidate improves. The earlier memory pilot
went 0/8 -> 6/8 -> 1/8, which is why we report best and final separately.

**10. Is this a benchmark or a production-ready system?**

It is a development prototype with public recorded outcomes. The same cases informed revisions. Latest adaptation
configs lack frozen historical hashes/split metadata. No held-out generalization, statistical confidence, production
deployment, user traction or revenue is claimed. The evaluation plan describes future work, not completed evidence.

**11. How does skill memory work?**

Optional JSON entries contain guidance, tags, controller/environment hashes and validation artifact references.
Admission requires explicitly real, development-only passing evidence. Retrieval is deterministic lexical matching,
bounded and environment-filtered; it is off unless enabled. A trusted host must create validation records. It is
ASPIRE-inspired, not ASPIRE integration, and the latest 8/8 adaptation did not depend on that memory module.

**12. Is the memory improvement proven?**

No isolated memory effect is proven. The separate memory pilot provided the entire expert reference program,
and the first successful rewrite's function matched it. That shows useful reference reuse. Guidance associated
with passing evidence is not itself a proven physical law; transfer needs a controlled comparison.

**13. How does voice work?**

There are two paths. The live command page uses browser speech recognition plus a mass parser. Separately, the
voice companion sends recorded audio directly to Argon, grounds its answer in selected saved evidence, then uses
Gemini 3.8 Flash TTS for WAV speech. Argon itself does not generate that speech. Keys stay on the local server.

**14. Is the Render page running the robot or the voice server?**

No. Render serves static HTML/JSON/media, including the verified 60-second video. Local port 8790 runs live trials;
8791 runs evidence Q&A. A fresh clone's packaged voice evidence covers the earlier memory pilot, clearly labelled.

**15. Is the demo live, recorded, or replayed?**

All exist and must be labelled. The one-minute submission video combines recorded trial replay and actual app
captures with narration. `demo.replay.py` presents a saved live run with saved outcomes/critiques/code; it makes no
new model or physics calls. A new `demo.app` request does run physics and potentially Argon calls. Saved live run
`155234_m5` passed on attempt 4: 5 kg rose 0.6942 m and held 4.8 s, while 15 and 30 kg checks also passed.
Another saved run, `162353_m5`, ended in a fall. A successful example does not guarantee the next live repair.

**16. What did the solver fixes do?**

The team investigated numerical blow-ups and changed the integrator from implicitfast to implicit while retaining
noslip. Error handling distinguishes a drop/fall that already happened from a later solver failure. These changes
create a different physics setup, so old memory/baseline curves must not be combined with new adaptation curves.

**17. How expensive and fast is it?**

Logged model-cost estimates for four adaptation revisions were about $0.26 for video and $0.18 for text. These
are not total project costs or real-time latency claims. Simulation, video rendering, uploads and generation all
contribute to wall time; a single high-quality render took about 270 seconds. The native viewer plays saved motion.

**18. Why Argon specifically? What about million-token output?**

The implementation uses its coding/reasoning and multimodal APIs to turn execution evidence into a controller.
We did not prove it beats other models, and these small controllers do not require million-token output. A separate
39,434-token throughput probe informed developer feedback; it is not the robotics evaluation.

**19. What is new relative to ASPIRE or other program-repair systems?**

The broad execution-feedback/skill-reuse pattern has prior art. Our implemented slice is inspectable humanoid
payload adaptation with video/text conditions, explicit assistance accounting, regression checks and accessible
evidence/voice tooling. Do not claim invention of agentic robotic program repair or reproduction of ASPIRE results.

**20. What would you do next?**

Freeze the simulator and prompts; use disjoint development/test conditions; repeat independent controller generations;
vary placement, friction and tote geometry; compare video without numeric HUD; audit duration-sensitive assistance
metrics; then investigate physically calibrated unassisted/hardware transfer. Add stronger execution isolation.

## Short answers to keep ready

- **What is the product?** A controller-adaptation and debugging workbench for robotics teams.
- **Who is the user?** Initially the engineer adapting robot behavior; small-business lift-and-shift is the motivating use case.
- **What is the central evidence?** Reference-seeded adaptation: 7/8 to 8/8 recorded development payloads in both conditions.
- **What is the key limitation?** Modified, assisted simulation and seen development cases; no hardware/generalization claim.
- **What is the honest video claim?** Working video-conditioned repair pipeline; no measured superiority over text yet.
- **What makes the result inspectable?** Saved code, diffs, critiques, videos, trajectories, scorer outputs and source hashes.

Use `submission/PITCH_3_MIN.md` for the spoken pitch and `docs/AGENT_CONTEXT.md` for the cross-agent architecture map.
