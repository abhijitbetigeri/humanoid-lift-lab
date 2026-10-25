"""Isolated, exploratory Argon text+validated-memory pilot using existing loop.

Runs in its own process. Does not edit shared loop code or existing run files.
This is a paid model experiment when executed, not an offline validator.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from evals.development_validation import environment_files
from loop.skill_memory import SkillMemory, environment_hash, file_hash


def pilot_environment_files():
    # The results UI copies generated demonstration videos here. They are not
    # MJCF inputs, textures, controller code, or physics configuration.
    return {name: path for name, path in environment_files().items()
            if not name.startswith('viz/assets/videos/')}


def build_context(memory_path, evidence_config_path, query):
    evidence = json.loads(Path(evidence_config_path).read_text())
    if evidence.get('stub') is not False or evidence.get('split') != 'development':
        raise ValueError('memory requires real development evidence')
    fingerprint = environment_hash(pilot_environment_files())
    if evidence.get('environment_sha256') != fingerprint:
        raise ValueError('evidence environment differs from current simulator')
    text = SkillMemory(memory_path).retrieve(query, environment_sha256=fingerprint, enabled=True, max_chars=3000)
    if not text:
        raise ValueError('no matching validated skill; refusing silent no-memory run')
    return fingerprint, text


def check_resume(out, metadata):
    saved = json.loads((out / 'memory-context.json').read_text())
    if saved != metadata:
        raise ValueError('resume condition differs from frozen pilot')
    if file_hash(out / 'skills.frozen.json') != metadata['memory_sha256']:
        raise ValueError('frozen memory changed')
    if file_hash(out / 'starting_controller.py') != metadata['starting_controller_sha256']:
        raise ValueError('starting controller changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--memory', required=True, type=Path)
    parser.add_argument('--evidence-config', required=True, type=Path)
    parser.add_argument('--seed-controller', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--resume', action='store_true', help='resume exact frozen condition after interrupted API call')
    args = parser.parse_args()
    if not 1 <= args.rounds <= 4 or not 1 <= args.workers <= 2:
        parser.error('pilot permits 1..4 revisions and 1..2 workers')
    fingerprint, context = build_context(args.memory, args.evidence_config, 'payload grip lift posture')
    out = args.out.resolve()
    metadata = {'condition': 'text+validated-development-memory', 'split': 'development', 'stub': False,
                'environment_sha256': fingerprint, 'memory_sha256': file_hash(args.memory),
                'starting_controller_sha256': file_hash(args.seed_controller),
                'retrieval_query': 'payload grip lift posture', 'injected_text': context,
                'comparability': 'exploratory: expert reference guidance; not a held-out or causal memory evaluation',
                'rendering': 'disabled; telemetry-only feedback', 'revision_budget': args.rounds}
    if args.resume:
        check_resume(out, metadata)
    else:
        out.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(args.memory, out / 'skills.frozen.json')
        shutil.copyfile(args.seed_controller, out / 'starting_controller.py')
        (out / 'memory-context.json').write_text(json.dumps(metadata, indent=2))
    from loop import prompts, run_loop
    # Process-local overrides leave active agents' source files and state alone.
    original_task = prompts.TASK_MD
    prompts.TASK_MD += ('\n\n# Additional validated development guidance\n'
        'The following guidance is associated with a hand-written reference controller that passed the listed '
        'development cases. It is a useful starting point, not a guarantee for other masses. '
        'Use actual API names and frames; preserve previously passing behavior.\n\n' + context)
    snapshots = {'task_prompt.md': prompts.TASK_MD, 'api_prompt.md': prompts.api_md(),
                 'base_task_prompt.md': original_task}
    for name, content in snapshots.items():
        if args.resume:
            if (out / name).read_text() != content:
                raise ValueError('prompt changed since frozen pilot: ' + name)
        else:
            (out / name).write_text(content)
    run_loop.select_for_video = lambda trials, cap=4: []
    try:
        run_loop.main(['--arm', 'text', '--rounds', str(args.rounds), '--seed', '0',
                       '--masses', '5,10,15,20,25,30,35,40', '--seed-controller', str(out / 'starting_controller.py'),
                       '--run-dir', str(out), '--workers', str(args.workers)])
    finally:
        config_path = out / 'config.json'
        if config_path.exists():
            config = json.loads(config_path.read_text())
            config.update({'split': 'development', 'environment_sha256': fingerprint,
                           'memory_sha256': metadata['memory_sha256'], 'memory_enabled': True,
                           'condition': metadata['condition'], 'rendering_disabled': True})
            config_path.write_text(json.dumps(config, indent=2))
        final_fingerprint = environment_hash(pilot_environment_files())
        (out / 'environment-check.json').write_text(json.dumps(
            {'before': fingerprint, 'after': final_fingerprint, 'unchanged': final_fingerprint == fingerprint}, indent=2))


if __name__ == '__main__':
    main()
