import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evals.collect_data import Collector, outcome_tags


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runs = self.root / 'runs'
        self.runs.mkdir()

    def write(self, name, value):
        path = self.runs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) if isinstance(value, (dict, list)) else value)
        return path

    def episode(self, run='video', k=0, seed=None, split='unknown', stub=True):
        config = {'stub': stub, 'environment_sha256': 'a' * 64}
        if split != 'unknown': config['split'] = split
        self.write(f'{run}/config.json', config)
        self.write(f'{run}/round_{k}/controller.py', f'def run(robot): robot.wait({k+1})\n')
        prefix = f'{run}/round_{k}/trials/m10'
        self.write(f'{prefix}/result.json', {'mass_kg': 10, 'success': k == 1,
            'fail_reason': None if k == 1 else 'dropped', 'dropped': k == 0})
        self.write(f'{prefix}/child.json', {'seed': seed, 'jitter': [0, 0]})
        self.write(f'{prefix}/traj.npz', 'fixture bytes; collector does not claim physics validation')
        return prefix

    def collect(self):
        out = self.root / 'collection'
        report = Collector(self.root, out).collect()
        rows = lambda name: [json.loads(line) for line in (out / name).read_text().splitlines()]
        return out, report, rows

    def test_stub_and_unknown_split_never_become_prompt_data(self):
        self.episode()
        _, report, rows = self.collect()
        episode = rows('episodes.jsonl')[0]
        self.assertEqual(episode['backend'], 'stub')
        self.assertEqual(episode['split'], 'unknown')
        self.assertEqual(episode['collection_role'], 'review-only')
        self.assertFalse(episode['memory_admitted'])
        self.assertEqual(report['development_candidate_count'], 0)
        self.assertEqual(len(rows('excluded_from_prompt_data.jsonl')), 1)

    def test_evaluation_data_indexed_but_excluded(self):
        self.episode(seed=1, split='heldout', stub=False)
        _, report, rows = self.collect()
        self.assertEqual(rows('episodes.jsonl')[0]['collection_role'], 'evaluation-only')
        self.assertEqual(report['development_candidate_count'], 0)

    def test_repair_snapshots_diff_and_unknown_seeds_not_paired(self):
        self.episode(k=0)
        self.episode(k=1)
        self.write('video/round_0/critique.md', 'Argon claims grip was insufficient.')
        out, _, rows = self.collect()
        repair = rows('repairs.jsonl')[0]
        self.assertEqual(repair['matched_outcomes'], [])
        self.assertFalse(repair['validated_improvement'])
        self.assertIn('-def run', (out / repair['diff_path']).read_text())
        artifact = repair['critique']
        self.assertEqual(hashlib.sha256((out / artifact['snapshot_path']).read_bytes()).hexdigest(), artifact['sha256'])

    def test_explicit_seed_pairs_but_does_not_validate_improvement(self):
        self.episode(k=0, seed=7, split='development', stub=False)
        self.episode(k=1, seed=7, split='development', stub=False)
        self.write('video/round_0/critique.md', 'model diagnosis')
        _, _, rows = self.collect()
        repair = rows('repairs.jsonl')[0]
        self.assertEqual(len(repair['matched_outcomes']), 1)
        self.assertFalse(repair['validated_improvement'])

    def test_collection_preserves_sources_and_lists_partial_videos(self):
        self.episode()
        self.write('video/round_0/videos/m10_grid.partial.mp4', 'partial bytes')
        before = {p: p.read_bytes() for p in self.runs.rglob('*') if p.is_file()}
        out, _, rows = self.collect()
        self.assertEqual(before, {p: p.read_bytes() for p in self.runs.rglob('*') if p.is_file()})
        self.assertIn('partial video present', rows('episodes.jsonl')[0]['exclusions'])
        with self.assertRaises(FileExistsError): Collector(self.root, out).collect()
        with self.assertRaises(ValueError): Collector(self.root, self.runs / 'bad').collect()

    def test_sweep_does_not_borrow_current_controller_or_infer_seed(self):
        self.write('reference/seed1/m10/result.json', {'mass_kg': 10, 'success': True})
        self.write('reference/seed1/sweep.json', [])
        _, _, rows = self.collect()
        episode = rows('episodes.jsonl')[0]
        self.assertEqual(episode['backend'], 'unknown')
        self.assertIsNone(episode['controller'])
        self.assertIsNone(episode['seed'])

    def test_failure_labels_do_not_treat_critique_as_truth(self):
        self.assertEqual(outcome_tags({'success': False, 'fail_reason': 'physics: simulation became unstable'}),
                         ['physics-instability'])
        self.assertEqual(outcome_tags({'success': False}), ['other-or-unknown-failure'])


if __name__ == '__main__': unittest.main()
