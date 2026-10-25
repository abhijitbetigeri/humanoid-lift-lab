import json
from pathlib import Path
import tempfile
import unittest
from loop.skill_memory import SkillMemory, environment_hash, file_hash


class SkillMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.controller = self.write('controller.py', 'def run(robot): pass\n')
        self.environment = self.write('scene.xml', '<scene/>')
        self.env_files = {'scene.xml': self.environment}
        self.env_hash = environment_hash(self.env_files)
        self.config = self.write_json('config.json', {'stub': False, 'split': 'development'})
        self.result = self.write_json('result.json', {'success': True, 'fail_reason': None})
        self.trajectory = self.write('traj.npz', 'fixture trajectory bytes')
        self.validation_data = {
            'backend': 'sim.trial', 'split': 'development', 'validator': 'independent-physics-scorer',
            'controller_sha256': file_hash(self.controller), 'environment_sha256': self.env_hash,
            'trials': [{'result_path': 'result.json', 'result_sha256': file_hash(self.result),
                        'trajectory_path': 'traj.npz', 'trajectory_sha256': file_hash(self.trajectory)}]}
        self.validation = self.write_json('validation.json', self.validation_data)
        self.memory = SkillMemory(self.root / 'memory.json')

    def write(self, name, content):
        p = self.root / name
        p.write_text(content)
        return p

    def write_json(self, name, value):
        return self.write(name, json.dumps(value))

    def admit(self, **kwargs):
        values = dict(title='Heavy payload grip', guidance='Ramp grip before lifting.', tags=['grip', 'payload'],
                      controller_path=self.controller, config_path=self.config,
                      validation_path=self.validation, environment_files=self.env_files)
        values.update(kwargs)
        return self.memory.admit(**values)

    def retrieve(self, **kwargs):
        values = dict(environment_sha256=self.env_hash, enabled=True)
        values.update(kwargs)
        return self.memory.retrieve('payload grip', **values)

    def test_persistent_idempotent_admission_and_opt_in(self):
        skill_id = self.admit()
        self.assertEqual(skill_id, self.admit())
        self.assertEqual(len(json.loads(self.memory.path.read_text())['skills']), 1)
        self.assertIn(skill_id, self.retrieve())
        self.assertEqual(self.retrieve(enabled=False), '')
        self.assertEqual(self.retrieve(environment_sha256='other-env'), '')

    def test_stub_and_heldout_configs_rejected(self):
        for config in ({'stub': True, 'split': 'development'}, {'stub': False, 'split': 'test'},
                       {'stub': False, 'split': 'heldout'}, {'split': 'development'}):
            with self.subTest(config=config):
                self.write_json('config.json', config)
                with self.assertRaises(ValueError): self.admit()

    def test_heldout_validation_and_model_self_grading_rejected(self):
        for field, value in [('split', 'test'), ('backend', 'loop.stubs'), ('validator', 'argon-critic')]:
            with self.subTest(field=field):
                self.write_json('validation.json', dict(self.validation_data, **{field: value}))
                with self.assertRaises(ValueError): self.admit()

    def test_controller_and_environment_provenance_required(self):
        self.controller.write_text('changed controller')
        with self.assertRaises(ValueError): self.admit()
        self.controller.write_text('def run(robot): pass\n')
        self.environment.write_text('<changed/>')
        with self.assertRaises(ValueError): self.admit()

    def test_failures_never_promoted_even_with_correct_hash(self):
        self.write_json('result.json', {'success': False, 'fail_reason': 'fell'})
        self.validation_data['trials'][0]['result_sha256'] = file_hash(self.result)
        self.write_json('validation.json', self.validation_data)
        with self.assertRaises(ValueError): self.admit()

    def test_tampered_evidence_rejected_at_admission_and_retrieval(self):
        self.trajectory.write_text('different bytes')
        with self.assertRaises(ValueError): self.admit()
        self.trajectory.write_text('fixture trajectory bytes')
        self.admit()
        self.result.write_text('{}')
        with self.assertRaises(ValueError): self.retrieve()

    def test_retrieval_is_relevant_deterministic_bounded_and_read_only(self):
        self.admit()
        self.admit(title='Unrelated camera', guidance='Keep camera fixed.', tags=['camera'])
        before = self.memory.path.read_bytes()
        text = self.retrieve()
        self.assertEqual(text, self.retrieve())
        self.assertIn('Ramp grip', text)
        self.assertNotIn('camera', text)
        self.assertEqual(self.retrieve(max_chars=5), '')
        self.assertLessEqual(len(self.retrieve(max_chars=150)), 150)
        self.assertEqual(before, self.memory.path.read_bytes())


if __name__ == '__main__': unittest.main()
