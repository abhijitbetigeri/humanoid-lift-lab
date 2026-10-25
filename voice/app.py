"""Local voice companion. Start: .venv/bin/python -m voice.app (127.0.0.1:8791)."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import unquote, urlparse

from voice.service import ARGON_MODEL, TTS_MODEL, ROOT, GeminiVoice, InputError, available_runs, build_context, validate_request

UI = Path(__file__).resolve().parent
MAX_BODY = 4 * 1024 * 1024 + 16384


def static_path(path, root=ROOT):
    path = unquote(urlparse(path).path)
    if path == '/preview.png':
        return Path(root) / 'runs/memory_text/preview/round1_25kg.png'
    if path in ('/', '/index.html', '/client.js', '/style.css'):
        return UI / ('index.html' if path == '/' else path.lstrip('/'))
    if path.startswith('/results/'):
        base = (Path(root) / 'viz').resolve()
        file = (base / (path[len('/results/'):] or 'index.html')).resolve()
        if file.is_relative_to(base) and file.suffix in ('.html', '.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.mp4'):
            return file
    return None


class Jobs:
    def __init__(self, provider=None):
        self.provider = provider or GeminiVoice()
        self.rows = {}
        self.lock = threading.Lock()
        self.busy = threading.BoundedSemaphore(1)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='voice')

    def submit(self, question, audio, context):
        if not self.busy.acquire(blocking=False):
            raise InputError('An answer is already being prepared. Please wait for it to finish.')
        job_id = secrets.token_urlsafe(18)
        with self.lock:
            cutoff = time.monotonic() - 900
            self.rows = {k: v for k, v in self.rows.items() if v['created'] > cutoff}
            if len(self.rows) >= 24:
                oldest = min(self.rows, key=lambda k: self.rows[k]['created'])
                del self.rows[oldest]
            self.rows[job_id] = {'state': 'thinking', 'created': time.monotonic(), 'sources': context['sources'],
                                 'selected_round': context['selected_round'], 'models': [ARGON_MODEL, TTS_MODEL]}
        self.pool.submit(self._work, job_id, question, audio, context)
        return job_id

    def update(self, job_id, **fields):
        with self.lock:
            self.rows[job_id].update(fields)

    def get(self, job_id):
        with self.lock:
            row = self.rows.get(job_id)
            if row and time.monotonic() - row['created'] > 900:
                del self.rows[job_id]
                row = None
            return {k: v for k, v in row.items() if k != 'created'} if row else None

    def _work(self, job_id, question, audio, context):
        try:
            answer = self.provider.answer(question, audio, context)
            self.update(job_id, state='speaking', **answer)
            # Release the input audio after Argon answers; it is never written to disk.
            audio = None
            try:
                speech = self.provider.speak(answer['answer'])
                self.update(job_id, state='done', audio=speech)
            except Exception:
                self.update(job_id, state='done', speech_error='Speech is unavailable. Your text answer is ready.')
        except Exception as exc:
            message = str(exc) if isinstance(exc, RuntimeError) else 'The answer could not be prepared. Please try again.'
            self.update(job_id, state='error', error=message)
        finally:
            self.busy.release()


def handler_factory(jobs, token, root=ROOT):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def allowed(self):
            port = self.server.server_address[1]
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            if self.headers.get('Host') not in hosts:
                return False
            origin = self.headers.get('Origin')
            return not origin or origin in {f'http://{h}' for h in hosts}

        def respond(self, code, payload):
            data = json.dumps(payload, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, {'error': 'Open the local voice app directly.'})
            path = urlparse(self.path).path
            if path == '/api/bootstrap':
                return self.respond(200, {'token': token, 'runs': available_runs(root),
                    'models': {'reasoning': ARGON_MODEL, 'speech': TTS_MODEL}, 'max_recording_seconds': 20})
            if path.startswith('/api/jobs/'):
                row = jobs.get(path.rsplit('/', 1)[-1])
                return self.respond(200 if row else 404, row or {'error': 'This answer has expired. Ask again.'})
            file = static_path(path, root)
            if file is None or not file.is_file():
                return self.respond(404, {'error': 'Not found.'})
            # Media needs byte-range responses for seeking in the existing results page.
            size = file.stat().st_size
            begin, end, status = 0, size - 1, 200
            byte_range = self.headers.get('Range')
            if byte_range:
                import re
                match = re.fullmatch(r'bytes=(\d+)-(\d*)', byte_range)
                if not match:
                    return self.respond(416, {'error': 'Unsupported range.'})
                begin = int(match[1])
                end = min(int(match[2]), size - 1) if match[2] else size - 1
                if begin > end or begin >= size:
                    return self.respond(416, {'error': 'Range outside file.'})
                status = 206
            self.send_response(status)
            self.send_header('Content-Type', mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(end - begin + 1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            if status == 206:
                self.send_header('Content-Range', f'bytes {begin}-{end}/{size}')
            self.end_headers()
            try:
                with file.open('rb') as stream:
                    stream.seek(begin)
                    remaining = end - begin + 1
                    while remaining:
                        block = stream.read(min(remaining, 65536))
                        if not block: break
                        self.wfile.write(block)
                        remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if not self.allowed() or not hmac.compare_digest(self.headers.get('X-Voice-Token', ''), token):
                return self.respond(403, {'error': 'Refresh the local page before asking a question.'})
            if self.path != '/api/ask':
                return self.respond(404, {'error': 'Not found.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.respond(415, {'error': 'Send JSON.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > MAX_BODY:
                    return self.respond(413, {'error': 'The recording is too large. Keep it under 20 seconds.'})
                payload = json.loads(self.rfile.read(length))
                question, audio = validate_request(payload)
                context = build_context(payload.get('run', 'memory_text'), payload.get('round', 'best'),
                                        payload.get('mass'), root=root)
                job_id = jobs.submit(question, audio, context)
                return self.respond(202, {'job_id': job_id})
            except (InputError, ValueError, TypeError) as exc:
                return self.respond(400, {'error': str(exc) if isinstance(exc, InputError) else 'Invalid request.'})
            except Exception:
                return self.respond(500, {'error': 'The local voice service could not prepare the request.'})

    return Handler


def make_server(port=8791, provider=None, root=ROOT):
    jobs = Jobs(provider)
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(('127.0.0.1', port), handler_factory(jobs, token, root))
    server.daemon_threads = True
    server.voice_jobs = jobs
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8791)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'Lift Lab voice: http://127.0.0.1:{server.server_address[1]}', flush=True)
    print('Microphone recordings and selected run evidence go to Google only when you submit a question.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.voice_jobs.pool.shutdown(wait=False)


if __name__ == '__main__':
    main()
