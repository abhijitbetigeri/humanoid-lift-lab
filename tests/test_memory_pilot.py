import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evals.run_memory_pilot import build_context, check_resume, pilot_environment_files
from loop.skill_memory import environment_hash, file_hash


class MemoryPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.py'
        self.source.write_text('source')
        self.files = {'source.py': str(self.source)}
        self.config = self.root / 'config.json'
        self.data = {'stub': False, 'split': 'development', 'environment_sha256': environment_hash(self.files)}
        self.config.write_text(json.dumps(self.data))

    def test_stale_environment_rejected_before_retrieval(self):
        self.source.write_text('changed')
        with patch('evals.run_memory_pilot.environment_files', return_value=self.files), \
             patch('evals.run_memory_pilot.SkillMemory') as memory:
            with self.assertRaisesRegex(ValueError, 'differs'):
                build_context(self.root / 'memory.json', self.config, 'grip')
            memory.assert_not_called()

    def test_heldout_evidence_rejected(self):
        self.data['split'] = 'test'
        self.config.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'development'):
            build_context(self.root / 'memory.json', self.config, 'grip')

    def test_no_silent_run_when_retrieval_empty(self):
        with patch('evals.run_memory_pilot.environment_files', return_value=self.files):
            with self.assertRaisesRegex(ValueError, 'no matching'):
                build_context(self.root / 'missing.json', self.config, 'grip')

    def test_resume_rejects_changed_condition_and_snapshot(self):
        (self.root / 'skills.frozen.json').write_text('{}')
        (self.root / 'starting_controller.py').write_text('controller')
        metadata = {'memory_sha256': file_hash(self.root / 'skills.frozen.json'),
                    'starting_controller_sha256': file_hash(self.root / 'starting_controller.py'), 'revision_budget': 2}
        (self.root / 'memory-context.json').write_text(json.dumps(metadata))
        check_resume(self.root, metadata)
        with self.assertRaisesRegex(ValueError, 'condition differs'):
            check_resume(self.root, dict(metadata, revision_budget=3))
        (self.root / 'skills.frozen.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'memory changed'):
            check_resume(self.root, metadata)

    def test_generated_presentation_videos_are_not_simulator_inputs(self):
        files = dict(self.files, **{'viz/assets/videos/demo.mp4': 'generated-output',
                                  'viz/assets/floor.png': 'texture-input'})
        with patch('evals.run_memory_pilot.environment_files', return_value=files):
            selected = pilot_environment_files()
        self.assertNotIn('viz/assets/videos/demo.mp4', selected)
        self.assertIn('viz/assets/floor.png', selected)


if __name__ == '__main__': unittest.main()
