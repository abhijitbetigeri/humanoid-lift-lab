"""Paid synthetic audio round-trip test. No project code/results are sent.

.venv/bin/python -m voice.smoke --out runs/voice_smoke
"""
import argparse
import base64
import io
import json
from pathlib import Path
import wave

from voice.service import ARGON_MODEL, TTS_MODEL, GeminiVoice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    provider = GeminiVoice()
    question = 'How many lifts succeeded in round one?'
    print('1/3: Gemini TTS is generating a synthetic spoken question.', flush=True)
    spoken_question = provider.speak(question)
    (args.out / 'question.wav').write_bytes(base64.b64decode(spoken_question['data']))
    print('2/3: Argon is receiving that audio and a synthetic six-of-eight fixture.', flush=True)
    answer = provider.answer('', {'data': spoken_question['data'], 'mime_type': 'audio/wav'},
        {'scope': 'Synthetic integration fixture, not a real robot result.',
         'round_summaries': [{'round': 0, 'passed': [], 'pass_rate': 0},
                             {'round': 1, 'passed': [10, 15, 20, 25, 30, 35], 'pass_rate': 0.75}],
         'trial_count_per_round': 8, 'sources': ['synthetic fixture']})
    print('3/3: Gemini TTS is generating the spoken answer.', flush=True)
    speech = provider.speak(answer['answer'])
    raw = base64.b64decode(speech['data'])
    (args.out / 'answer.wav').write_bytes(raw)
    with wave.open(io.BytesIO(raw), 'rb') as wav:
        audio_info = {'channels': wav.getnchannels(), 'sample_rate': wav.getframerate(),
                      'duration_s': wav.getnframes() / wav.getframerate()}
        if wav.getnframes() <= 0: raise RuntimeError('Empty spoken answer')
    record = {'status': 'completed', 'synthetic': True, 'models': [ARGON_MODEL, TTS_MODEL],
              'transcript': answer['transcript'], 'answer': answer['answer'], 'audio': audio_info,
              'argon_interaction_id': answer['argon_interaction_id'],
              'tts_interaction_id': speech['tts_interaction_id']}
    (args.out / 'result.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == '__main__': main()
