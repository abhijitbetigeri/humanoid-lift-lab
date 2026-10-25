# Collected Lift Lab artifacts

112 episodes, 2 repair records, 367 source artifacts.

Backend declarations: {"configured-real": 18, "unknown": 54, "stub": 40}.

Eligible development candidates: 0. No memory entries created.

`episodes.jsonl` links per-trial outcomes, trajectories, controllers, and videos. `repairs.jsonl` links successive controllers, critiques, diffs, and available outcomes. `failures.jsonl` contains observed failure labels, not verified root causes. `excluded_from_prompt_data.jsonl` identifies records requiring exclusion/review.

Source paths are project-relative; snapshot paths are collection-relative. Small artifacts are preserved under `objects/`; large videos/trajectories remain in place with SHA256. A non-partial filename does not establish decodability or actual Argon consumption.

Never feed this entire index to Argon: held-out, stub, synthetic, and unknown records are indexed for audit only. No unvalidated guidance is automatically promoted to skill memory. See `docs/data-collection.md` for refresh and interpretation.
