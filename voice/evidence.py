"""Saved run access with a portable, explicitly labelled snapshot fallback."""
import json
from pathlib import Path

RUNS = {'memory_text': 'Earlier memory-assisted pilot',
        'video_adapt': 'Latest video adaptation', 'text_adapt': 'Latest text adaptation',
        'video_final': 'Revised setup · video', 'text_final': 'Revised setup · text',
        'video': 'Earlier video feedback', 'text': 'Earlier text feedback'}
BUNDLE = Path('data/voice-evidence/snapshot.json')


def read(path, fallback=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return fallback


def metadata(root, run):
    directory = Path(root) / 'runs' / run
    # Never hide a local stub, test split, corrupt file, or active run behind an older bundle.
    if (directory / 'config.json').exists() or (directory / 'summary.json').exists():
        config, summary = read(directory / 'config.json', {}), read(directory / 'summary.json', {})
        return {'config': config if isinstance(config, dict) else {}, 'summary': summary if isinstance(summary, dict) else {},
                'origin': 'local-saved-run', 'captured_at': None, 'bundle': None}
    bundle = read(Path(root) / BUNDLE, {})
    if not isinstance(bundle, dict): return None
    data = bundle.get('runs', {}).get(run) if bundle.get('version') == 1 else None
    if data:
        return {'config': data.get('config', {}), 'summary': data.get('summary', {}),
                'origin': 'packaged-snapshot', 'captured_at': bundle.get('captured_at'), 'bundle': data}
    return None


def round_evidence(root, run, number, meta):
    if meta['bundle'] is not None:
        return meta['bundle'].get('rounds', {}).get(str(number), {})
    rd = Path(root) / 'runs' / run / f'round_{number}'
    def text(name, limit):
        try:
            return (rd / name).read_text()[:limit]
        except OSError:
            return None
    return {'trials': read(rd / 'trials.json', []), 'controller': text('controller.py', 8000),
            'critique': text('critique.md', 2500)}
