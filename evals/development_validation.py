"""Prospective provenance and independent rescoring for development skill evidence.

No simulation or model calls. Prepare BEFORE running sim.trial, finalize AFTER.
Never retroactively label an old trajectory with the current environment hash.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import shutil

from loop.skill_memory import environment_hash, file_hash

ROOT = Path(__file__).resolve().parents[1]


def _write_new(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)


def environment_files(root=ROOT):
    """Conservative source/assets inventory; includes visual dependencies as well."""
    root = Path(root)
    files = {}
    for directory in ('sim', 'viz/assets'):
        for path in (root / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                files[path.relative_to(root).as_posix()] = str(path.resolve())
    for name in ('evals/development_validation.py', 'loop/skill_memory.py'):
        files[name] = str((root / name).resolve())
    return files


def runtime():
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'numpy': importlib.metadata.version('numpy'),
            'mujoco': importlib.metadata.version('mujoco')}


def prepare(controller, out, cases, files=None):
    """Create a fresh development-only record. Does not launch cases."""
    normalized = []
    for mass, seed in cases:
        if not math.isfinite(mass) or mass <= 0 or not isinstance(seed, int) or seed < 0:
            raise ValueError('cases require finite positive mass and nonnegative integer seed')
        case = {'mass_kg': float(mass), 'seed': seed}
        if case in normalized:
            raise ValueError('duplicate development case')
        normalized.append(case)
    if not normalized:
        raise ValueError('at least one case is required')
    files = environment_files() if files is None else files
    if not files:
        raise ValueError('environment inventory is empty')
    fingerprint = environment_hash(files)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(controller, out / 'controller.py')
    for index, case in enumerate(normalized):
        case['directory'] = f'trials/case_{index:04d}_m{case["mass_kg"]:g}_s{case["seed"]}'
    config = {'stub': False, 'split': 'development', 'backend': 'sim.trial',
              'controller_sha256': file_hash(out / 'controller.py'),
              'environment_sha256': fingerprint, 'environment_files': files,
              'runtime': runtime(), 'use_assist': True, 'cases': normalized,
              'prepared_at': datetime.now(timezone.utc).isoformat()}
    _write_new(out / 'config.json', config)
    return config


def finalize(out):
    """Rescore fresh real trajectories; emit admission manifest only if ALL pass.

    Trusted host operation. It verifies artifacts and provenance; it is not a
    security boundary against an agent allowed to forge host records.
    """
    import numpy as np
    from sim.trial import score

    out = Path(out).resolve()
    config = json.loads((out / 'config.json').read_text())
    if config.get('stub') is not False or config.get('split') != 'development' or config.get('backend') != 'sim.trial':
        raise ValueError('only prepared real development trials are accepted')
    files = config['environment_files']
    if environment_hash(files) != config['environment_sha256'] or runtime() != config['runtime']:
        raise ValueError('environment/runtime changed after preparation; rerun with a fresh preparation')
    if file_hash(out / 'controller.py') != config['controller_sha256']:
        raise ValueError('controller changed after preparation')
    trials = []
    for case in config['cases']:
        directory = out / case['directory']
        trajectory = directory / 'traj.npz'
        result_path = directory / 'result.json'
        child = json.loads((directory / 'child.json').read_text())
        expected_jitter = np.random.default_rng(case['seed']).uniform(-0.02, 0.02, size=2)
        if not np.allclose(child['jitter'], expected_jitter, rtol=0, atol=1e-12):
            raise ValueError('placement does not match declared seed')
        with np.load(trajectory, allow_pickle=False) as archive:
            traj = dict(archive)
        required = ('time', 'qpos', 'assist_force', 'box_slip', 'tau_frac', 'box_z0', 'box_mass')
        if any(key not in traj or not np.isfinite(traj[key]).all() for key in required):
            raise ValueError('missing/nonfinite trajectory values')
        if len(traj['time']) < 2 or not (np.diff(traj['time']) > 0).all():
            raise ValueError('trajectory needs strictly increasing timestamps')
        if float(traj['box_mass']) != case['mass_kg']:
            raise ValueError('trajectory mass differs from prepared case')
        rescored = score(traj, case['mass_kg'], child.get('error'))
        recorded = json.loads(result_path.read_text())
        if rescored != recorded:
            raise ValueError('recorded outcome does not match independent trajectory rescore')
        if rescored['success'] is not True:
            raise ValueError('failed development trials cannot validate a skill')
        trials.append({'mass_kg': case['mass_kg'], 'seed': case['seed'],
                       'result_path': str(result_path.relative_to(out)), 'result_sha256': file_hash(result_path),
                       'trajectory_path': str(trajectory.relative_to(out)), 'trajectory_sha256': file_hash(trajectory)})
    if not trials:
        raise ValueError('no prepared trials')
    # Catch concurrent edits during verification too.
    if environment_hash(files) != config['environment_sha256']:
        raise ValueError('environment changed during rescoring')
    manifest = {'backend': 'sim.trial', 'split': 'development', 'validator': 'independent-physics-scorer',
                'controller_sha256': config['controller_sha256'],
                'environment_sha256': config['environment_sha256'], 'trials': trials}
    _write_new(out / 'validation.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    begin = commands.add_parser('prepare')
    begin.add_argument('--controller', required=True)
    begin.add_argument('--out', required=True)
    begin.add_argument('--case', action='append', required=True, help='development MASS:SEED; repeat for each case')
    end = commands.add_parser('finalize')
    end.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        cases = [(float(value.split(':')[0]), int(value.split(':')[1])) for value in args.case]
        result = prepare(args.controller, args.out, cases)
        print(json.dumps({'status': 'prepared; simulation not launched', 'cases': result['cases']}, indent=2))
    else:
        result = finalize(args.out)
        print(json.dumps({'status': 'validated', 'trials': len(result['trials'])}))


if __name__ == '__main__':
    main()
