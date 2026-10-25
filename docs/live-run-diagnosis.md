# Development run diagnosis — 2026-10-25

Read-only inspection of saved `runs/video` rounds 0–2 and `runs/text` rounds 0–1,
their controllers/telemetry, and current `sim/humanoid_api.py`. These are development runs.
No simulator or model was launched for this diagnosis. Sources may continue changing.

## Observed outcomes

| Saved condition | Passes | Concrete result |
| --- | --- | --- |
| Video round 0 | 0/8 | Common baseline: near-zero lift at 5–30 kg; heavy cases unstable/fall |
| Text round 0 | 0/8 | Same saved baseline outcomes |
| Video round 1 | 0/8 | All rises at most 0.0138 m; slip 0.631–0.714 m |
| Text round 1 | 0/8 | Rises at most 0.0424 m, with heavy instability |
| Video round 2 | 0/8 | 5 kg reaches 0.5483 m but holds only 0.967 s and drops; other masses fail |

Round-1 mean assistance falls substantially, but the boxes remain on the floor.
Low assistance alone is not progress toward the lifting objective. Use pass/hold/rise as primary evidence.

At video round 1, 5 kg shoulder torque is saturated (`peak=1`, 10.0 s above 0.9);
at text round 1, 10 kg shoulders saturate for 10.1 s. This supports an arm-target/pose problem,
but cannot alone distinguish unreachable targets, unfavorable leverage, and contact interference.
The model's video critique says the palms hover above the sides; that is a hypothesis from its interpretation,
not an independently verified contact diagnosis in this read-only check.

## API-contract facts that matter

There is no obvious nonexistent-method or argument mismatch in the inspected controller versions:
`box_pose()["pos"]`, `world_to_pelvis_frame`, `squat(..., torso_pitch=..., hip_back=...)`, and
`set_posture({"waist_pitch": ...})` are valid. The principal problem is behavior/parameter choice.

1. `hands_to` returns `left_err_m` and `right_err_m`. The inspected controllers ignore both.
   A target being commanded does not mean the palms achieved it. Add bounded recovery/reach checks to a future
   controller and log their values; do not blindly proceed to lifting after an unreachable grasp.
2. `squat` alters hip/knee/ankle targets. It does not set the waist target; other joints retain their targets.
   Round-1 rewrites remove the baseline's explicit waist flexion and leave the waist at its prior/default target.
   Video round 2 restores some flexion; a light lift then occurs, though it still fails the hold/drop criteria.
   This temporal association is not a causal ablation.
3. `squeeze` already adds `SQUEEZE_IN_M=0.03` inward to each hand target through `hands_to`.
   Video round 2 requests `half_w - 0.035`, then squeezing adds another 0.03 m target inset on each side.
   The total requested inset is 0.065 m per palm relative to the side coordinate. This is an IK target,
   not measured palm penetration. Excessive target inset may cause saturation or contact trouble.
4. Grip force is silently capped at 450 N per palm and the method returns the actual capped value.
   Video round 2 computes an upper bound of 480 N, so its planned force and executed force can differ.
5. Motion primitives execute sequentially. A call to `hands_to`, followed by `squat`, does not continuously
   recompute hand IK during the squat. Small interleaved steps can maintain a less abrupt trajectory.

## What the working reference contributes

The handwritten reference contains a more conservative tested trajectory:

- Grasp posture: depth 0.25 m, hip torso pitch 0.5 rad, waist pitch 0.45 rad, hip-back 0.10 m.
- World-to-pelvis conversion for the initial grasp; 0.005 m explicit inward target inset, rather than 0.035 m.
- Ten small lift stages; hand x moves from 0.36 to 0.26 m rather than immediately to 0.18–0.24 m.
- Coordinated waist extension and gradual hip/leg changes; final hold 3.6 s.

Historical v3 sweeps record passes at 10–35 kg for seed 0 and 10–30 kg in the inspected seed-1 subset.
They do not establish provenance for today's source version. Main-session prospective validation must confirm
specific cases before admitting guidance to memory. Do not advertise 5 or 40 kg success from these records.

The reference avoids the most aggressive inward tuck seen in the generated controllers. Tucking toward the knees
while still low could cause leg collisions; the API has explicit `BoxEjected` handling for that event.
That is a hypothesis for some generated-controller failures, not a demonstrated explanation for every drop.

## Recommended next prompt guidance

Use only in a separate development/memory-assisted condition; do not change active comparison prompts mid-run:

> Preserve a real-validated grasp/waist configuration and make small, bounded trajectory changes. Remember that
> squeeze already adds 3 cm of inward IK target offset and caps at 450 N. Inspect hand IK residuals before lift;
> if poor, recover posture/targets before increasing squeeze. Lift in short interleaved leg/waist/arm stages,
> maintaining clearance from knees. Demonstrate box rise and continuous hold; low balance assist with an empty
> grasp is not success. A successful reference supplies prior guidance, not proof that all its rules generalize.

If the memory arm receives the handwritten reference's strategy while the original arms do not, label it
expert-guidance augmentation. Its success would not isolate the benefit of persistent memory or video alone.

## Parallel-work boundary

Only this diagnosis document was written. No existing source, run configuration, controller, trial artifact,
prompt, scorer, or active process was modified. No reserved held-out cases were inspected.
