# Saved run audit

Generated: 2026-10-25T21:21:15.646886+00:00

Saved artifacts only; no live process, model, or simulator inspection. Files may change during scan.

Configured-real is a config declaration, not proof of execution or an immutable environment.

| Run | Backend | Latest saved passes/trials | Split |
| --- | --- | --- | --- |
| w1_baseline | unknown | 0/4 | unknown |
| w1_baseline_v2 | unknown | 0/8 | unknown |
| w1_reference | unknown | 4/8 | unknown |
| w1_reference_v2 | unknown | 4/8 | unknown |
| w3_integ | configured-real | 0/2 | unknown |
| w3_test/dry | stub | 5/8 | unknown |
| w3_text | stub | 0/8 | unknown |
| w3_video | stub | 0/8 | unknown |

## w1_baseline

- missing or invalid run config
- missing environment SHA256; historical physics cannot be bound to current source
- missing or unrecognized split
- saved sweep outcomes have no backend/config provenance; inspect as historical development only

## w1_baseline_v2

- missing or invalid run config
- missing environment SHA256; historical physics cannot be bound to current source
- missing or unrecognized split
- saved sweep outcomes have no backend/config provenance; inspect as historical development only

## w1_reference

- missing or invalid run config
- missing environment SHA256; historical physics cannot be bound to current source
- missing or unrecognized split
- saved sweep outcomes have no backend/config provenance; inspect as historical development only

## w1_reference_v2

- missing or invalid run config
- missing environment SHA256; historical physics cannot be bound to current source
- missing or unrecognized split
- saved sweep outcomes have no backend/config provenance; inspect as historical development only

## w3_integ

- missing environment SHA256; historical physics cannot be bound to current source
- missing or unrecognized split

## w3_test/dry

- missing environment SHA256; historical physics cannot be bound to current source
- missing or unrecognized split
- stub outcomes are harness tests, not physics evidence

## w3_text

- missing environment SHA256; historical physics cannot be bound to current source
- missing or unrecognized split
- stub outcomes are harness tests, not physics evidence

## w3_video

- missing environment SHA256; historical physics cannot be bound to current source
- missing or unrecognized split
- stub outcomes are harness tests, not physics evidence

## Candidate comparisons

- w3_integ vs w3_test/dry: blocked.
  - both runs must explicitly configure the real backend
  - starting controller mismatch
  - missing environment provenance
  - missing split provenance
  - masses mismatch
- w3_integ vs w3_text: blocked.
  - both runs must explicitly configure the real backend
  - starting controller mismatch
  - missing environment provenance
  - missing split provenance
  - masses mismatch
  - rounds mismatch
- w3_video vs w3_test/dry: blocked.
  - both runs must explicitly configure the real backend
  - missing environment provenance
  - missing split provenance
  - rounds mismatch
- w3_video vs w3_text: blocked.
  - both runs must explicitly configure the real backend
  - starting controller mismatch
  - missing environment provenance
  - missing split provenance
