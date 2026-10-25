'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let token = '', runOptions = [], busy = false, pendingMic = false, recorder = null, stream = null;
  let chunks = [], recording = null, recordingTimer = null, timerTick = null, startedAt = 0, audioUrl = null;
  let evidenceRequest = 0;
  const setError = message => { $('error').textContent = message; $('error').hidden = !message; };
  const progress = message => { $('progress').textContent = message; $('progress').hidden = !message; };
  const micSupported = () => !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  function controls() {
    $('ask').disabled = busy || pendingMic || !token || recorder?.state === 'recording';
    $('record').disabled = busy || pendingMic || !token || !micSupported();
    for (const id of ['run', 'round', 'mass', 'question']) $(id).disabled = busy || !token;
    $('discard').disabled = busy;
    $('refresh-evidence').disabled = busy || pendingMic || recorder?.state === 'recording';
  }
  function setBusy(value) { busy = value; controls(); }
  function rounds() {
    const run = runOptions.find(r => r.id === $('run').value);
    $('round').replaceChildren(new Option('Best saved round', 'best'), ...(run?.rounds || []).map(r => new Option(`Round ${r}`, String(r))));
  }
  async function savedEvidence() {
    const request = ++evidenceRequest;
    $('evidence-status').textContent = 'Loading saved results…';
    $('evidence-stats').replaceChildren(); $('evidence-cases').replaceChildren();
    try {
      const query = new URLSearchParams({run:$('run').value, round:$('round').value, mass:$('mass').value});
      const response = await fetch(`/api/evidence?${query}`);
      const data = await response.json();
      if (request !== evidenceRequest) return;
      if (!response.ok) throw new Error(data.error || 'Saved evidence is unavailable.');
      const row = data.round_summaries.find(r => r.round === data.selected_round);
      $('evidence-status').textContent = `Round ${data.selected_round} · saved results`;
      const rate = typeof row.pass_rate === 'number' ? `${Math.round(row.pass_rate*1000)/10}% passed` : 'No pass rate';
      const maximum = row.max_mass_passed == null ? 'No successful payload' : `Up to ${row.max_mass_passed} kg`;
      for (const text of [rate,maximum]) { const span=document.createElement('span'); span.textContent=text; $('evidence-stats').append(span); }
      for (const trial of data.trials) {
        const li = document.createElement('li');
        li.textContent = `${trial.mass_kg} kg · ${trial.success ? 'PASS' : 'FAIL'}`;
        li.className = trial.success ? 'case-pass' : 'case-fail';
        li.title = trial.success ? `Rise ${trial.box_rise_m} m; held ${trial.held_s} s` : (trial.fail_reason || 'Saved failure');
        $('evidence-cases').append(li);
      }
      const origin = data.evidence_origin === 'packaged-snapshot' ? `Packaged snapshot · ${new Date(data.captured_at).toLocaleString()}` : 'Local saved run';
      $('evidence-provenance').textContent = `${origin}. Runs may use different setups; compare rounds within a run. These results remain available without a model call.`;
    } catch (error) { if (request === evidenceRequest) $('evidence-status').textContent = error.message; }
  }
  async function bootstrap() {
    const previousRun = $('run').value, previousRound = $('round').value;
    try {
      const response = await fetch('/api/bootstrap');
      if (!response.ok) throw new Error('Could not connect to the local voice service.');
      const data = await response.json();
      token = data.token; runOptions = data.runs;
      if (!runOptions.length) throw new Error('No saved experiment results are available yet.');
      $('run').replaceChildren(...runOptions.map(r => new Option(r.label, r.id)));
      if (runOptions.some(r => r.id === previousRun)) $('run').value = previousRun;
      rounds();
      if ([...$('round').options].some(r => r.value === previousRound)) $('round').value = previousRound;
      controls(); savedEvidence();
      $('connection').textContent = 'Ready'; $('connection').classList.add('ready');
      if (!micSupported()) $('record-status').textContent = 'Microphone recording is unavailable here. Type a question instead.';
    } catch (error) {
      token = ''; controls(); $('connection').textContent = 'Unavailable'; setError(error.message);
    }
  }
  function stopTracks() { stream?.getTracks().forEach(track => track.stop()); stream = null; }
  function clearTimers() { clearTimeout(recordingTimer); clearInterval(timerTick); }
  function discard() { recording = null; $('discard').hidden = true; $('record-status').textContent = 'Up to 20 seconds'; }
  async function toggleRecord() {
    if (recorder?.state === 'recording') { recorder.stop(); return; }
    if (pendingMic) return;
    setError(''); discard(); $('playback').pause(); pendingMic = true; controls();
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm', 'audio/ogg;codecs=opus'].find(t => MediaRecorder.isTypeSupported(t));
      recorder = mime ? new MediaRecorder(stream, {mimeType: mime}) : new MediaRecorder(stream);
      const activeRecorder = recorder;
      let failed = false;
      chunks = []; startedAt = Date.now();
      recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      recorder.onerror = () => { failed = true; clearTimers(); stopTracks(); recorder = null; $('record').textContent = 'Record a question'; $('record').classList.remove('recording-active'); controls(); setError('Recording failed. Please try again or type your question.'); };
      recorder.onstop = () => {
        clearTimers(); stopTracks();
        if (failed) { controls(); return; }
        const blob = new Blob(chunks, {type: activeRecorder.mimeType || mime || 'audio/webm'});
        recorder = null; $('record').textContent = 'Record a question'; $('record').classList.remove('recording-active');
        if (!blob.size || blob.size > 3 * 1024 * 1024) { discard(); setError('The recording is empty or too large. Please try a shorter question.'); }
        else { recording = blob; $('discard').hidden = false; $('record-status').textContent = `Recording ready · ${Math.min(20, Math.round((Date.now() - startedAt) / 1000))}s`; }
        controls();
      };
      recorder.start(); $('record').textContent = 'Stop recording'; $('record').classList.add('recording-active');
      timerTick = setInterval(() => { $('record-status').textContent = `Recording · ${Math.floor((Date.now() - startedAt) / 1000)} / 20s`; }, 200);
      recordingTimer = setTimeout(() => { if (recorder?.state === 'recording') recorder.stop(); }, 20000);
      pendingMic = false; controls();
    } catch (error) { pendingMic = false; stopTracks(); clearTimers(); setError(error.name === 'NotAllowedError' ? 'Microphone access was declined. You can still type a question.' : 'Could not open the microphone. Please type your question.'); controls(); }
  }
  function base64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(new Error('Could not read the recording.')); reader.readAsDataURL(blob);
    });
  }
  function showAnswer(result) {
    $('empty').hidden = true; $('response').hidden = false;
    $('transcript').textContent = result.transcript || '(No transcript returned)';
    $('answer').textContent = result.answer;
    $('answer-scope').textContent = `Round ${result.selected_round} · saved evidence`;
    $('sources').replaceChildren(...(result.sources || []).map(source => { const li = document.createElement('li'); li.textContent = source; return li; }));
  }
  async function ask(event) {
    event.preventDefault(); if (busy) return;
    const question = $('question').value.trim();
    if (!question && !recording) { setError('Type a question or record one first.'); return; }
    setError(''); setBusy(true); progress(recording ? 'Argon is listening and reviewing the selected evidence…' : 'Argon is reviewing the selected evidence…');
    $('playback').pause(); $('playback').hidden = true; $('speech-note').hidden = true;
    if (audioUrl) { URL.revokeObjectURL(audioUrl); audioUrl = null; }
    try {
      const payload = {question, run: $('run').value, round: $('round').value, mass: $('mass').value};
      if (recording) payload.audio = {data: await base64(recording), mime_type: recording.type.split(';')[0]};
      const response = await fetch('/api/ask', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Voice-Token': token}, body: JSON.stringify(payload)});
      const created = await response.json();
      if (!response.ok) throw new Error(created.error || 'The question could not be submitted.');
      discard();
      const deadline = Date.now() + 300000;
      while (Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const poll = await fetch(`/api/jobs/${encodeURIComponent(created.job_id)}`);
        const result = await poll.json();
        if (!poll.ok || result.state === 'error') throw new Error(result.error || 'The answer could not be prepared.');
        if (result.answer) showAnswer(result);
        if (result.state === 'speaking') progress('Your answer is ready. Gemini is preparing the spoken version…');
        if (result.state !== 'done') continue;
        progress('');
        if (result.audio?.data) {
          const bytes = Uint8Array.from(atob(result.audio.data), c => c.charCodeAt(0));
          audioUrl = URL.createObjectURL(new Blob([bytes], {type: result.audio.mime_type}));
          $('playback').src = audioUrl; $('playback').hidden = false;
          if ($('speak').checked) {
            try { await $('playback').play(); }
            catch { $('speech-note').textContent = 'Press play to hear the answer.'; $('speech-note').hidden = false; }
          }
        } else { $('speech-note').textContent = result.speech_error || 'Read the answer above.'; $('speech-note').hidden = false; }
        return;
      }
      throw new Error('This answer is taking longer than expected. Please wait a little before asking again.');
    } catch (error) { progress(''); setError(error.message || 'Connection interrupted. Please try again.'); }
    finally { setBusy(false); }
  }
  $('ask-form').addEventListener('submit', ask);
  $('record').addEventListener('click', toggleRecord);
  $('discard').addEventListener('click', discard);
  $('run').addEventListener('change', () => { rounds(); savedEvidence(); });
  $('refresh-evidence').addEventListener('click', bootstrap);
  $('round').addEventListener('change', savedEvidence);
  $('mass').addEventListener('change', savedEvidence);
  document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => { if (!busy) { $('question').value = button.dataset.question; $('question').focus(); } }));
  $('question').addEventListener('keydown', event => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); $('ask-form').requestSubmit(); } });
  document.querySelector('figure img').addEventListener('error', event => { event.target.closest('figure').hidden = true; });
  window.addEventListener('pagehide', () => { clearTimers(); if (recorder?.state === 'recording') recorder.stop(); stopTracks(); if (audioUrl) URL.revokeObjectURL(audioUrl); });
  bootstrap();
})();
