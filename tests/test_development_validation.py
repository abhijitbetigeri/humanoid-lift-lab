"""Synthetic scorer fixtures test provenance handling, not robot performance."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from evals.development_validation import prepare, finalize
from loop.skill_memory import SkillMemory
from sim.trial import score


class DevelopmentValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.controller = self.root / 'controller.py'
        self.controller.write_text('def run(robot): pass\n')
        self.scene = self.root / 'scene.xml'
        self.scene.write_text('<mujoco/>')
        self.files = {'scene.xml': str(self.scene)}
        self.out = self.root / 'validation'

    def fixture(self, success=True):
        config = prepare(self.controller, self.out, [(10., 0)], self.files)
        directory = self.out / config['cases'][0]['directory']
        directory.mkdir(parents=True)
        qpos = np.zeros((5, 14))
        qpos[:, 2] = .8
        qpos[:, -5] = .5 if success else .1
        traj = {'time': np.arange(5.), 'qpos': qpos, 'box_z0': np.array(0.),
                'box_mass': np.array(10.), 'assist_force': np.zeros(5),
                'tau_frac': np.zeros((5, 1)), 'box_slip': np.zeros(5)}
        np.savez(directory / 'traj.npz', **traj)
        (directory / 'result.json').write_text(json.dumps(score(traj, 10.)))
        (directory / 'child.json').write_text(json.dumps({'error': None,
            'jitter': np.random.default_rng(0).uniform(-.02, .02, 2).tolist()}))
        return config, directory

    def test_rescored_manifest_accepted_by_memory(self):
        config, _ = self.fixture()
        manifest = finalize(self.out)
        self.assertEqual(manifest['trials'][0]['seed'], 0)
        skill_id = SkillMemory(self.root / 'memory.json').admit(
            title='Fixture grip', guidance='Test fixture only', tags=['grip'],
            controller_path=self.out / 'controller.py', config_path=self.out / 'config.json',
            validation_path=self.out / 'validation.json', environment_files=self.files)
        self.assertTrue(skill_id)
        self.assertEqual(config['split'], 'development')

    def test_environment_and_controller_edits_rejected(self):
        self.fixture()
        self.scene.write_text('<changed/>')
        with self.assertRaisesRegex(ValueError, 'environment/runtime changed'):
            finalize(self.out)
        self.scene.write_text('<mujoco/>')
        (self.out / 'controller.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'controller changed'):
            finalize(self.out)

    def test_failure_does_not_create_manifest(self):
        self.fixture(success=False)
        with self.assertRaisesRegex(ValueError, 'failed development'):
            finalize(self.out)
        self.assertFalse((self.out / 'validation.json').exists())

    def test_false_result_and_wrong_seed_rejected(self):
        _, directory = self.fixture()
        result = directory / 'result.json'
        original = result.read_text()
        data = json.loads(original)
        data['held_s'] = 999
        result.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'independent trajectory rescore'):
            finalize(self.out)
        result.write_text(original)
        (directory / 'child.json').write_text(json.dumps({'error': None, 'jitter': [1, 1]}))
        with self.assertRaisesRegex(ValueError, 'declared seed'):
            finalize(self.out)

    def test_heldout_config_rejected_and_output_not_overwritten(self):
        config, _ = self.fixture()
        with self.assertRaises(FileExistsError):
            prepare(self.controller, self.out, [(10., 0)], self.files)
        config['split'] = 'heldout'
        (self.out / 'config.json').write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'development'):
            finalize(self.out)

    def test_invalid_and_duplicate_cases_rejected(self):
        for cases in ([], [(float('nan'), 0)], [(10., -1)], [(10., 0), (10., 0)]):
            with self.subTest(cases=cases), self.assertRaises(ValueError):
                prepare(self.controller, self.out, cases, self.files)


if __name__ == '__main__':
    unittest.main()
