"""Package explicitly selected development evidence for fresh-clone demos. No API calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from voice.evidence import RUNS, read
from voice.service import ROOT

CONFIG_KEYS = ('stub', 'split', 'rounds', 'masses', 'seed', 'no_assist', 'environment_sha256')
ROUND_KEYS = ('round', 'pass_rate', 'passed', 'max_mass_passed', 'mean_assist_n')
TRIAL_KEYS = ('mass_kg', 'success', 'box_rise_m', 'held_s', 'mean_assist_n', 'max_assist_n',
              'peak_tau_frac', 'max_slip_m', 'fell', 'dropped', 'fail_reason', 'telemetry')


def export(root, names, out):
    root, out = Path(root), Path(out)
    runs, source_hashes = {}, {}
    for name in names:
        if name not in RUNS:
            raise ValueError('Run is not allowlisted: ' + name)
        directory = root / 'runs' / name
        def capture(relative, *, text=False):
            path = directory / relative
            raw = path.read_bytes()
            source_hashes[path.relative_to(root).as_posix()] = hashlib.sha256(raw).hexdigest()
            return raw.decode() if text else json.loads(raw)
        config = capture('config.json')
        if config.get('stub') is not False or config.get('split') != 'development':
            raise ValueError('Export requires explicit real development metadata: ' + name)
        summary = capture('summary.json')
        rows, contents = [], {}
        for row in summary.get('rounds', []):
            number = row.get('round')
            if not isinstance(number, int) or number < 0:
                continue
            trials = capture(f'round_{number}/trials.json')
            if not isinstance(trials, list) or not trials:
                raise ValueError('Incomplete round: ' + name)
            passed = sorted(t['mass_kg'] for t in trials if t.get('success') is True)
            if passed != sorted(row.get('passed', [])) or abs(len(passed) / len(trials) - row['pass_rate']) > 0.001:
                raise ValueError('Summary and trial outcomes differ: ' + name)
            contents[str(number)] = {'trials': [{k: t[k] for k in TRIAL_KEYS if k in t} for t in trials],
                'controller': capture(f'round_{number}/controller.py', text=True)[:8000], 'critique': None}
            if (directory / f'round_{number}/critique.md').is_file():
                contents[str(number)]['critique'] = capture(f'round_{number}/critique.md', text=True)[:2500]
            rows.append({k: row.get(k) for k in ROUND_KEYS})
        if not rows:
            raise ValueError('No completed rounds: ' + name)
        runs[name] = {'config': {k: config[k] for k in CONFIG_KEYS if k in config},
                      'summary': {'rounds': rows}, 'rounds': contents}
    # Recheck sources so an active writer cannot silently produce a mixed capture.
    for relative, digest in source_hashes.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != digest:
            raise ValueError('Source changed while exporting; retry after the round settles: ' + relative)
    payload = {'version': 1, 'captured_at': datetime.now(timezone.utc).isoformat(),
               'scope': 'Historical development evidence; not a new execution or held-out benchmark.',
               'source_sha256': source_hashes, 'runs': runs}
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / 'snapshot.writing.json'
    tmp.write_text(json.dumps(payload, indent=2, allow_nan=False))
    tmp.replace(out / 'snapshot.json')
    preview = root / 'runs/memory_text/preview/round1_25kg.png'
    if 'memory_text' in runs and preview.is_file():
        shutil.copyfile(preview, out / 'preview.png')
    return {'runs': list(runs), 'completed_rounds': sum(len(r['rounds']) for r in runs.values()),
            'snapshot_bytes': (out / 'snapshot.json').stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--runs', nargs='+', choices=list(RUNS), default=['memory_text'])
    parser.add_argument('--out', type=Path, default=ROOT / 'data/voice-evidence')
    args = parser.parse_args()
    print(json.dumps(export(args.root, args.runs, args.out), indent=2))


if __name__ == '__main__': main()
