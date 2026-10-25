# Portable voice-demo evidence

This bundle preserves the **earlier memory-assisted development pilot**, not the revised-physics final/adaptation
runs. It lets a fresh clone display and discuss saved evidence even though `runs/` is intentionally ignored.

- `snapshot.json`: three completed rounds and 24 recorded outcomes, bounded controller/critique context, saved
  configuration fields, capture timestamp, and original source-file SHA256 values.
- `preview.png`: a saved image of the round-1 25 kg trial. It is a visualization, not audio/video sent to Argon.

Best round: 1, six of eight payloads passed (10–35 kg). Final round: 2, one of eight passed (5 kg). Round 1 largely
reused the supplied hand-written reference program. Keep that additional expert guidance explicit in any claim.

These are historical recorded results. This bundle does not contain full trajectories, rerun a simulator, establish
new validation, or prove held-out generalization. The source hashes identify originals but are not a substitute
for those originals when independently rescoring physics. See `reports/memory-pilot-results.md`.

The voice app labels fallback usage as `packaged-snapshot`. It prefers actual local saved runs. Local held-out,
stub, or corrupt metadata is never silently replaced with an older snapshot. No credentials, recordings, or API
keys are included. Refresh explicitly selected development evidence with `python -m voice.export_evidence`.
