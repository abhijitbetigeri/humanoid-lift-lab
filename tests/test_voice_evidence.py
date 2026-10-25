import json
from pathlib import Path
import shutil
import tempfile
import unittest

from voice.app import static_path
from voice.export_evidence import export
from voice.service import InputError, available_runs, build_context


class PortableEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / 'runs/memory_text'
        self.out = self.root / 'data/voice-evidence'
        self.write('config.json', {'stub': False, 'split': 'development', 'api_key': 'do-not-export'})
        self.write('summary.json', {'rounds': [{'round': 0, 'pass_rate': 0., 'passed': [], 'max_mass_passed': None},
                                              {'round': 1, 'pass_rate': 1., 'passed': [10], 'max_mass_passed': 10}]})
        for number in (0, 1):
            self.write(f'round_{number}/trials.json', [{'mass_kg': 10, 'success': bool(number),
                                                      'trial_dir': '/private/not-portable'}])
            self.write(f'round_{number}/controller.py', 'def run(robot): pass')

    def write(self, path, value):
        file = self.directory / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(value) if not isinstance(value, str) else value)

    def test_fresh_clone_can_load_best_round_from_packaged_evidence(self):
        export(self.root, ['memory_text'], self.out)
        shutil.rmtree(self.root / 'runs')  # synthetic temporary fixture only
        result = build_context(root=self.root)
        self.assertEqual(result['evidence_origin'], 'packaged-snapshot')
        self.assertEqual(result['selected_round'], 1)
        self.assertEqual(result['trials'][0]['success'], True)
        self.assertTrue(result['captured_at'])
        self.assertEqual(available_runs(self.root)[0]['id'], 'memory_text')

    def test_export_excludes_private_config_and_absolute_trial_paths(self):
        report = export(self.root, ['memory_text'], self.out)
        snapshot = (self.out / 'snapshot.json').read_text()
        self.assertNotIn('do-not-export', snapshot)
        self.assertNotIn('/private/not-portable', snapshot)
        self.assertNotIn(str(self.root), snapshot)
        self.assertEqual(report['completed_rounds'], 2)

    def test_local_stub_or_heldout_never_uses_packaged_fallback(self):
        export(self.root, ['memory_text'], self.out)
        for config in ({'stub': True}, {'stub': False, 'split': 'heldout'}):
            self.write('config.json', config)
            with self.assertRaises(InputError): build_context(root=self.root)
            self.assertEqual(available_runs(self.root), [])

    def test_export_requires_explicit_development_split(self):
        self.write('config.json', {'stub': False})
        with self.assertRaisesRegex(ValueError, 'development'):
            export(self.root, ['memory_text'], self.out)

    def test_export_rejects_summary_trial_disagreement(self):
        self.write('round_1/trials.json', [{'mass_kg': 10, 'success': False}])
        with self.assertRaisesRegex(ValueError, 'differ'):
            export(self.root, ['memory_text'], self.out)

    def test_local_evidence_takes_precedence_and_preview_falls_back(self):
        export(self.root, ['memory_text'], self.out)
        self.assertEqual(build_context(root=self.root)['evidence_origin'], 'local-saved-run')
        (self.out / 'preview.png').write_bytes(b'fixture')
        self.assertEqual(static_path('/preview.png', self.root), self.out / 'preview.png')

    def test_newer_runs_are_available_without_mixing_them(self):
        other = self.root / 'runs/video_final'
        other.mkdir()
        (other / 'config.json').write_text(json.dumps({'stub': False}))
        (other / 'summary.json').write_text(json.dumps({'rounds': [{'round': 0, 'pass_rate': 0}]}))
        self.assertIn('video_final', [r['id'] for r in available_runs(self.root)])
        self.assertEqual(build_context(root=self.root)['run'], 'memory_text')


if __name__ == '__main__': unittest.main()
