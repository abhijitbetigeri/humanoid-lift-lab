# Reference collection

The compact development context lives in `data/references/argon-reference-pack.md`; source metadata, retrieval date,
runtime version, local source SHA256 values, and retrieval limitations live in `data/references/sources.json`.

Sources are the local API/scorer/model, official MuJoCo documentation, Menagerie G1 README/license, Unitree G1
specifications, and NVIDIA's ASPIRE method page. Local implementation takes precedence for this simulated task.
Upstream `main` and live `stable` URLs are mutable; retrieved notes are dated and local files fingerprinted.
No immutable upstream commit is claimed. No external full-text manuals, videos, or model datasets were copied.

Use the pack as identical background context across compared arms. Record its content hash in experiment manifests.
Never promote it automatically into validated skill memory: external guidance has no local success evidence.
Do not add held-out observations to it. Recollect and rehash after code changes; do not pretend refreshed notes
describe older run environments. The current code and some comments/calibration claims disagree; those discrepancies
are explicitly recorded in the pack rather than silently resolved into unsupported claims.

Collection executed no simulator, Argon API, or hardware commands. The MuJoCo version was read using package metadata.
Version-specific 3.17.0 doc pages were inaccessible through the browser tool; stable references are labelled accordingly.
