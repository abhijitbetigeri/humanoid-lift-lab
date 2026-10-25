import base64
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
import wave

from voice.app import Jobs, static_path
from voice.service import ARGON_MODEL, TTS_MODEL, GeminiVoice, InputError, build_context, parse_answer, safe_error, validate_request


def wav_data():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(24000); out.writeframes(b'\0\0' * 240)
    return base64.b64encode(stream.getvalue()).decode()


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / 'runs/memory_text'
        self.directory.mkdir(parents=True)
        self.write('config.json', {'stub': False, 'split': 'development'})
        self.write('summary.json', {'rounds': [{'round': 0, 'pass_rate': 0, 'mean_assist_n': 60},
                                              {'round': 1, 'pass_rate': .75, 'mean_assist_n': 32},
                                              {'round': 2, 'pass_rate': .125, 'mean_assist_n': 80}]})
        self.write('round_1/trials.json', [{'mass_kg': 10, 'success': True}, {'mass_kg': 40, 'success': False}])
        self.write('round_1/controller.py', 'def run(robot): pass')

    def write(self, path, data):
        p = self.directory / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data) if isinstance(data, (dict, list)) else data)

    def test_best_round_and_mass_are_grounded_without_arbitrary_paths(self):
        context = build_context(mass=10, root=self.root)
        self.assertEqual(context['selected_round'], 1)
        self.assertEqual(len(context['trials']), 1)
        self.assertNotIn('trial_dir', context['trials'][0])
        with self.assertRaises(InputError): build_context(run='../../.env', root=self.root)
        with self.assertRaises(InputError): build_context(round_choice='99', root=self.root)
        with self.assertRaises(InputError): build_context(mass=17, root=self.root)

    def test_stub_and_heldout_contexts_rejected(self):
        for config in ({'stub': True}, {'stub': False, 'split': 'heldout'}, {'stub': False, 'split': 'test'}):
            self.write('config.json', config)
            with self.assertRaises(InputError): build_context(root=self.root)

    def test_audio_format_size_and_empty_requests_rejected(self):
        for payload in ({}, {'question': 22}, {'audio': {'data': 'bad!', 'mime_type': 'audio/wav'}},
                        {'audio': {'data': wav_data(), 'mime_type': 'text/html'}},
                        {'audio': {'data': '', 'mime_type': 'audio/wav'}}):
            with self.subTest(payload=payload), self.assertRaises(InputError): validate_request(payload)
        question, audio = validate_request({'question': ' hello ', 'audio': {'data': wav_data(), 'mime_type': 'audio/webm;codecs=opus'}})
        self.assertEqual(question, 'hello')
        self.assertEqual(audio['mime_type'], 'audio/webm')

    def test_argon_receives_native_audio_and_returns_transcript(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text='{"transcript":"Why did it fail?","answer":"The saved trial dropped the tote."}', id='argon-test')
        provider = GeminiVoice(SimpleNamespace(interactions=SimpleNamespace(create=create)))
        result = provider.answer('', {'data': wav_data(), 'mime_type': 'audio/wav'}, {'sources': ['synthetic']})
        self.assertEqual(calls[0]['model'], ARGON_MODEL)
        self.assertEqual(calls[0]['input'][1]['type'], 'audio')
        self.assertFalse(calls[0]['store'])
        self.assertEqual(result['transcript'], 'Why did it fail?')

    def test_tts_uses_dedicated_model_and_validates_wave(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_audio=SimpleNamespace(data=wav_data()), id='tts-test')
        provider = GeminiVoice(SimpleNamespace(interactions=SimpleNamespace(create=create)))
        result = provider.speak('Six lifts succeeded.')
        self.assertEqual(calls[0]['model'], TTS_MODEL)
        self.assertEqual(calls[0]['response_format'], {'type': 'audio'})
        self.assertEqual(result['mime_type'], 'audio/wav')

    def test_invalid_json_response_does_not_become_an_answer(self):
        with self.assertRaises(RuntimeError): parse_answer('pretend this is JSON')
        with self.assertRaises(RuntimeError): parse_answer('{"answer":null}')
        self.assertEqual(parse_answer('```json\n{"answer":"hello"}\n```', 'question')['transcript'], 'question')

    def test_static_routes_cannot_read_keys_or_project_files(self):
        self.assertIsNone(static_path('/.env', self.root))
        self.assertIsNone(static_path('/results/../../.env', self.root))
        self.assertIsNone(static_path('/results/%2e%2e/%2e%2e/voice/service.py', self.root))
        self.assertTrue(str(static_path('/results/', self.root)).endswith('viz/index.html'))

    def test_sdk_error_does_not_expose_raw_secret(self):
        error = RuntimeError('secret API key and private URL')
        self.assertNotIn('secret', safe_error(error))

    def test_speech_failure_preserves_grounded_text_and_job_expires(self):
        provider = SimpleNamespace(answer=lambda *args: {'answer': 'Saved result', 'transcript': 'Question'},
                                   speak=lambda *args: (_ for _ in ()).throw(RuntimeError('unavailable')))
        jobs = Jobs(provider)
        self.addCleanup(jobs.pool.shutdown)
        job_id = jobs.submit('Question', None, {'sources': ['fixture'], 'selected_round': 1})
        jobs.pool.shutdown(wait=True)
        result = jobs.get(job_id)
        self.assertEqual(result['state'], 'done')
        self.assertEqual(result['answer'], 'Saved result')
        self.assertIn('speech_error', result)
        jobs.rows[job_id]['created'] = time.monotonic() - 901
        self.assertIsNone(jobs.get(job_id))


if __name__ == '__main__': unittest.main()
