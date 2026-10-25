import json
from pathlib import Path
import tempfile
import unittest

from evals.audit_runs import audit, compare


class AuditRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_fixture(self, name, *, config=None, code="def run(robot): pass", sweep=False):
        path = self.root / name
        path.mkdir()
        if config is not None:
            (path / 'config.json').write_text(json.dumps(config))
        if sweep:
            (path / 'sweep.json').write_text(json.dumps([{'success': True}]))
        else:
            rd = path / 'round_0'
            rd.mkdir()
            (rd / 'controller.py').write_text(code)
            (rd / 'trials.json').write_text(json.dumps([{'success': True}, {'success': False}]))
        return path

    def config(self, arm, **kwargs):
        return dict(stub=False, arm=arm, split='development', environment_sha256='a' * 64,
                    masses=[10, 20], seed=0, rounds=3, no_assist=False, **kwargs)

    def test_stub_and_unknown_are_not_real_evidence(self):
        self.run_fixture('stub', config={'stub': True, 'arm': 'video'})
        self.run_fixture('unknown', sweep=True)
        rows = {r['run']: r for r in audit(self.root)['runs']}
        self.assertEqual(rows['stub']['backend'], 'stub')
        self.assertEqual(rows['unknown']['backend'], 'unknown')
        self.assertEqual(rows['unknown']['sweep_passes'], 1)
        self.assertTrue(rows['unknown']['warnings'])

    def test_missing_provenance_blocks_identical_successful_runs(self):
        self.run_fixture('v', config={'arm': 'video', 'stub': False})
        self.run_fixture('t', config={'arm': 'text', 'stub': False})
        pair = audit(self.root)['candidate_comparisons'][0]
        self.assertEqual(pair['status'], 'blocked')
        self.assertIn('missing environment provenance', pair['blockers'])

    def test_mismatched_start_and_trial_seed_block_comparison(self):
        self.run_fixture('v', config=self.config('video'), code='video controller')
        text = self.config('text')
        text['seed'] = 99
        self.run_fixture('t', config=text, code='text controller')
        pair = audit(self.root)['candidate_comparisons'][0]
        self.assertIn('starting controller mismatch', pair['blockers'])
        self.assertIn('seed mismatch', pair['blockers'])

    def test_structural_match_does_not_claim_scientific_comparability(self):
        self.run_fixture('v', config=self.config('video'))
        self.run_fixture('t', config=self.config('text'))
        pair = audit(self.root)['candidate_comparisons'][0]
        self.assertEqual(pair['blockers'], [])
        self.assertIn('protocol review still required', pair['status'])
        self.assertIn('prompt equality', pair['limitations'])

    def test_latest_round_order_is_numeric_and_audit_never_writes(self):
        path = self.run_fixture('v', config=self.config('video'))
        for number, passed in [(2, True), (10, False)]:
            rd = path / f'round_{number}'
            rd.mkdir()
            (rd / 'trials.json').write_text(json.dumps([{'success': passed}]))
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        row = audit(self.root)['runs'][0]
        self.assertEqual(row['rounds'][-1]['round'], 10)
        self.assertEqual(row['rounds'][-1]['passes'], 0)
        after = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
