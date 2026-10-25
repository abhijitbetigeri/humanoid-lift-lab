"""Index saved Lift Lab episodes/repairs without running models or simulation.

Large artifacts stay in place; small inputs are snapshotted by content hash.
Unknown provenance stays unknown. Collection never admits skills into memory.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import difflib
import hashlib
import json
import math
from pathlib import Path


class Collector:
    def __init__(self, root, out):
        self.root = Path(root).resolve()
        self.runs = self.root / 'runs'
        self.out = Path(out).resolve()
        self.warnings = []
        self.artifacts = {}
        self.config_cache = {}

    def relative(self, path):
        return Path(path).resolve().relative_to(self.root).as_posix()

    def artifact(self, path, snapshot=False):
        path = Path(path)
        if not path.is_file():
            return None
        relative = self.relative(path)
        if relative in self.artifacts:
            return self.artifacts[relative]
        before = path.stat()
        sha = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                sha.update(block)
        after = path.stat()
        stable = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        record = {'path': relative, 'sha256': sha.hexdigest(), 'bytes': after.st_size,
                  'stable_during_read': stable, 'snapshot_path': None}
        if not stable:
            self.warnings.append(f'artifact changed during collection: {relative}')
        if snapshot and stable:
            # Snapshot and its digest must describe exactly the same bytes.
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() == record['sha256']:
                destination = self.out / 'objects' / (record['sha256'] + path.suffix)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    destination.write_bytes(data)
                record['snapshot_path'] = destination.relative_to(self.out).as_posix()
            else:
                record['stable_during_read'] = False
                self.warnings.append(f'artifact changed before snapshot: {relative}')
        self.artifacts[relative] = record
        return record

    def load(self, path, default=None):
        if not Path(path).is_file():
            return default
        artifact = self.artifact(path, snapshot=True)
        try:
            source = (self.out / artifact['snapshot_path']) if artifact['snapshot_path'] else Path(path)
            return json.loads(source.read_text())
        except (OSError, ValueError) as exc:
            self.warnings.append(f'unreadable JSON {self.relative(path)}: {exc}')
            return default

    def context(self, directory):
        for parent in (directory, *directory.parents):
            if parent == self.root or not parent.is_relative_to(self.runs):
                break
            if (parent / 'config.json').is_file():
                if parent not in self.config_cache:
                    config = self.load(parent / 'config.json', {})
                    self.config_cache[parent] = config if isinstance(config, dict) else {}
                return parent, self.config_cache[parent]
        # Preserve historical sweep identity without inventing a config.
        for parent in (directory, *directory.parents):
            if parent == self.root or not parent.is_relative_to(self.runs):
                break
            if (parent / 'sweep.json').is_file():
                return parent, {}
            if parent.name.startswith('round_') and parent.name[6:].isdigit():
                return parent.parent, {}
        return directory.parent if directory.name.startswith('m') else directory, {}

    def episodes(self):
        episodes = []
        for result_path in sorted(self.runs.rglob('result.json')):
            result = self.load(result_path)
            if not isinstance(result, dict):
                self.warnings.append(f'non-object result: {self.relative(result_path)}')
                continue
            directory = result_path.parent
            run, config = self.context(directory)
            round_dir = next((p for p in directory.parents if p.name.startswith('round_')
                              and p.name[6:].isdigit() and p.is_relative_to(run)), None)
            round_number = int(round_dir.name[6:]) if round_dir else None
            controller = self.artifact(round_dir / 'controller.py', True) if round_dir else None
            child = self.load(directory / 'child.json', {})
            child = child if isinstance(child, dict) else {}
            backend = 'stub' if config.get('stub') is True else (
                'configured-real' if config.get('stub') is False else 'unknown')
            synthetic_hint = any('fake' in p.lower() for p in directory.relative_to(self.runs).parts)
            split = config.get('split', 'unknown')
            if not isinstance(split, str): split = 'unknown'
            declared_seed = child.get('seed')
            seed_source = 'child.seed' if declared_seed is not None else 'unknown'
            # Do not reverse-infer seeds from folder names, jitter, or current loop code.
            for case in config.get('cases', []):
                if isinstance(case, dict) and case.get('directory') == directory.relative_to(run).as_posix():
                    declared_seed, seed_source = case.get('seed'), 'prepared config case'
            mass = result.get('mass_kg')
            valid_mass = isinstance(mass, (int, float)) and not isinstance(mass, bool) and math.isfinite(mass)
            videos = []
            if round_dir and valid_mass:
                videos = [self.artifact(p) for p in sorted((round_dir / 'videos').glob(f'm{mass:g}_*.mp4'))]
            elif not round_dir:
                videos = [self.artifact(p) for p in sorted(directory.glob('*.mp4'))]
            trajectory = self.artifact(directory / 'traj.npz')
            critique = self.artifact(round_dir / 'critique.md', True) if round_dir else None
            tags = outcome_tags(result)
            reasons = []
            if backend != 'configured-real': reasons.append('backend is not explicitly real')
            if split != 'development': reasons.append('not explicitly development data')
            if synthetic_hint: reasons.append('synthetic path hint; requires provenance review')
            if not config.get('environment_sha256'): reasons.append('missing historical environment fingerprint')
            if not controller: reasons.append('no saved controller linked to this episode')
            if not trajectory: reasons.append('missing trajectory')
            if declared_seed is None: reasons.append('missing per-case seed provenance')
            if not valid_mass: reasons.append('missing or invalid mass')
            linked = [self.artifact(result_path), trajectory, controller, critique, *videos]
            if any(a and not a['stable_during_read'] for a in linked): reasons.append('artifact changed during read')
            if any('.partial.' in v['path'] for v in videos): reasons.append('partial video present')
            episode_id = 'ep_' + hashlib.sha256(self.relative(result_path).encode()).hexdigest()[:20]
            episodes.append({'episode_id': episode_id, 'run': self.relative(run), 'round': round_number,
                'split': split, 'backend': backend, 'synthetic_path_hint': synthetic_hint,
                'mass_kg': mass if valid_mass else None, 'seed': declared_seed, 'seed_source': seed_source,
                'run_seed_setting': config.get('seed'), 'placement_jitter_xy': child.get('jitter'),
                'environment_sha256': config.get('environment_sha256'), 'controller': controller,
                'result': self.artifact(result_path), 'trajectory': trajectory, 'videos': videos,
                'critique': critique, 'recorded_outcome': result, 'outcome_tags': tags,
                'api_calls_log': self.artifact(run / 'calls.jsonl', True),
                'collection_role': 'evaluation-only' if split in ('evaluation', 'heldout', 'test') else (
                    'development-candidate' if not reasons else 'review-only'),
                'exclusions': reasons, 'memory_admitted': False})
        return episodes

    def repairs(self, episodes):
        repairs = []
        for critique_path in sorted(self.runs.rglob('critique.md')):
            round_dir = critique_path.parent
            if not round_dir.name.startswith('round_') or not round_dir.name[6:].isdigit():
                continue
            k = int(round_dir.name[6:])
            run = round_dir.parent
            before = self.artifact(round_dir / 'controller.py', True)
            after = self.artifact(run / f'round_{k+1}' / 'controller.py', True)
            critique = self.artifact(critique_path, True)
            prior = [e for e in episodes if e['run'] == self.relative(run) and e['round'] == k]
            later = [e for e in episodes if e['run'] == self.relative(run) and e['round'] == k+1]
            # Pair only explicit mass AND seed matches; unknown seeds cannot establish matched outcomes.
            paired = []
            for first in prior:
                matches = [second for second in later if first['mass_kg'] is not None
                           and second['mass_kg'] == first['mass_kg'] and first['seed'] is not None
                           and second['seed'] == first['seed']]
                if len(matches) == 1:
                    second = matches[0]
                    paired.append({'before_episode': first['episode_id'], 'after_episode': second['episode_id'],
                                   'before_success': first['recorded_outcome'].get('success'),
                                   'after_success': second['recorded_outcome'].get('success')})
            diff_path = None
            if before and after and before['snapshot_path'] and after['snapshot_path']:
                old = (self.out / before['snapshot_path']).read_text().splitlines(True)
                new = (self.out / after['snapshot_path']).read_text().splitlines(True)
                diff = ''.join(difflib.unified_diff(old, new, fromfile=before['path'], tofile=after['path']))
                digest = hashlib.sha256(diff.encode()).hexdigest()
                dest = self.out / 'objects' / (digest + '.diff')
                dest.write_text(diff)
                diff_path = dest.relative_to(self.out).as_posix()
            repairs.append({'repair_id': 'repair_' + hashlib.sha256(self.relative(critique_path).encode()).hexdigest()[:20],
                            'run': self.relative(run), 'from_round': k, 'to_round': k+1,
                            'before_controller': before, 'after_controller': after, 'critique': critique,
                            'diff_path': diff_path, 'before_episode_ids': [e['episode_id'] for e in prior],
                            'after_episode_ids': [e['episode_id'] for e in later], 'matched_outcomes': paired,
                            'diagnosis_status': 'model claim; not a ground-truth cause',
                            'validated_improvement': False,
                            'notes': ['Controller succession does not establish causal improvement.',
                                      'Unknown seeds are not paired. Stub outcomes are not physics evidence.']})
        return repairs

    def collect(self):
        if self.out.is_relative_to(self.runs):
            raise ValueError('collection output must be outside source runs')
        self.out.mkdir(parents=True, exist_ok=False)
        episodes = self.episodes()
        repairs = self.repairs(episodes)
        # Include unlinked videos/logs too. Never read credentials or arbitrary project files.
        names = {'config.json', 'trials.json', 'summary.json', 'sweep.json', 'child.json',
                 'controller.py', 'critique.md', 'argon_reply.md', 'calls.jsonl'}
        for path in sorted(self.runs.rglob('*')):
            if path.is_file() and (path.name in names or path.suffix in ('.npz', '.mp4')):
                self.artifact(path, snapshot=path.name in names)
        self.jsonl('episodes.jsonl', episodes)
        self.jsonl('repairs.jsonl', repairs)
        self.jsonl('failures.jsonl', [{'episode_id': e['episode_id'], 'backend': e['backend'], 'split': e['split'],
                    'observed_outcome_tags': e['outcome_tags'], 'recorded_failure_reason': e['recorded_outcome'].get('fail_reason'),
                    'result': e['result']} for e in episodes if e['recorded_outcome'].get('success') is not True])
        self.jsonl('excluded_from_prompt_data.jsonl', [{'episode_id': e['episode_id'], 'reasons': e['exclusions'],
                    'collection_role': e['collection_role']} for e in episodes if e['collection_role'] != 'development-candidate'])
        self.jsonl('artifacts.jsonl', list(self.artifacts.values()))
        calls = []
        for path in sorted(self.runs.rglob('calls.jsonl')):
            artifact = self.artifact(path, True)
            if not artifact['snapshot_path']:
                self.warnings.append(f'API log changed; skipped parsing: {self.relative(path)}')
                continue
            for line_number, line in enumerate((self.out / artifact['snapshot_path']).read_text().splitlines(), 1):
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict): raise ValueError('not an object')
                    calls.append({'source': artifact, 'line': line_number, 'record': clean(record),
                                  'scope': 'run-level log; no automatic episode attribution'})
                except ValueError:
                    self.warnings.append(f'invalid API log line: {self.relative(path)}:{line_number}')
        self.jsonl('api_calls.jsonl', calls)
        summary = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'schema_version': 1,
                   'episode_count': len(episodes), 'repair_count': len(repairs),
                   'backend_counts': dict(Counter(e['backend'] for e in episodes)),
                   'split_counts': dict(Counter(e['split'] for e in episodes)),
                   'outcome_tag_counts': dict(Counter(t for e in episodes for t in e['outcome_tags'])),
                   'development_candidate_count': sum(e['collection_role'] == 'development-candidate' for e in episodes),
                   'artifact_count': len(self.artifacts), 'warnings': self.warnings,
                   'api_call_log_entries': len(calls),
                   'memory_entries_created': 0,
                   'limitations': ['Saved artifact inventory, not independent verification of physics.',
                       'Unknown provenance and seed fields are not inferred.',
                       'Large artifacts are hashed references, not copied snapshots.',
                       'Sources may change while collecting; this is not an atomic experiment snapshot.']}
        (self.out / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
        (self.out / 'README.md').write_text(self.readme(summary))
        return summary

    def jsonl(self, name, rows):
        with (self.out / name).open('x') as stream:
            for row in rows:
                # Preserve anomalous source values as strings rather than emit nonstandard JSON NaN.
                stream.write(json.dumps(clean(row), sort_keys=True, allow_nan=False) + '\n')

    @staticmethod
    def readme(summary):
        return (f"# Collected Lift Lab artifacts\n\n{summary['episode_count']} episodes, {summary['repair_count']} repair records, "
                f"{summary['artifact_count']} source artifacts.\n\n"
                f"Backend declarations: {json.dumps(summary['backend_counts'])}.\n\n"
                f"Eligible development candidates: {summary['development_candidate_count']}. No memory entries created.\n\n"
                "`episodes.jsonl` links per-trial outcomes, trajectories, controllers, and videos. "
                "`repairs.jsonl` links successive controllers, critiques, diffs, and available outcomes. "
                "`failures.jsonl` contains observed failure labels, not verified root causes. "
                "`excluded_from_prompt_data.jsonl` identifies records requiring exclusion/review.\n\n"
                "Source paths are project-relative; snapshot paths are collection-relative. "
                "Small artifacts are preserved under `objects/`; large videos/trajectories remain in place with SHA256. "
                "A non-partial filename does not establish decodability or actual Argon consumption.\n\n"
                "Never feed this entire index to Argon: held-out, stub, synthetic, and unknown records are indexed "
                "for audit only. No unvalidated guidance is automatically promoted to skill memory. "
                "See `docs/data-collection.md` for refresh and interpretation.\n")


def clean(value):
    if isinstance(value, float) and not math.isfinite(value): return str(value)
    if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list): return [clean(v) for v in value]
    return value


def outcome_tags(result):
    tags = []
    if result.get('success') is True: tags.append('recorded-success')
    if result.get('fell') is True: tags.append('fell')
    if result.get('dropped') is True: tags.append('dropped')
    reason = str(result.get('fail_reason') or '').lower()
    for phrase, tag in (('physics:', 'physics-instability'), ('unstable', 'physics-instability'),
                        ('exception', 'controller-error'), ('controller_error', 'controller-error'),
                        ('runner_error', 'runner-error'), ('crash:', 'runner-error'),
                        ('timeout', 'timeout'), ('box rose only', 'insufficient-rise'),
                        ('held only', 'insufficient-hold'), ('assist too high', 'assist-budget-exceeded')):
        if phrase in reason and tag not in tags: tags.append(tag)
    if result.get('success') is not True and not tags: tags.append('other-or-unknown-failure')
    return tags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path, required=True, help='fresh output directory outside runs/')
    args = parser.parse_args()
    print(json.dumps(Collector(args.root, args.out).collect(), indent=2))


if __name__ == '__main__':
    main()
