/* Local UI verification. Requires Playwright; intercepts all paid request routes. */
const {chromium} = require(process.env.LIFT_LAB_PLAYWRIGHT || 'playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless:true, channel:'chrome', args:[
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'
  ]});
  const context = await browser.newContext({permissions:['microphone'], viewport:{width:1280,height:1000}});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const submitted = [];
  let textOnly = false;
  const wav = Buffer.alloc(44 + 4800);
  wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8,4); wav.write('WAVE',8); wav.write('fmt ',12);
  wav.writeUInt32LE(16,16); wav.writeUInt16LE(1,20); wav.writeUInt16LE(1,22);
  wav.writeUInt32LE(24000,24); wav.writeUInt32LE(48000,28); wav.writeUInt16LE(2,32); wav.writeUInt16LE(16,34);
  wav.write('data',36); wav.writeUInt32LE(4800,40);
  await page.route('**/api/ask', async route => {
    submitted.push(route.request().postDataJSON());
    await route.fulfill({status:202, contentType:'application/json', body:JSON.stringify({job_id:'browser-fixture'})});
  });
  await page.route('**/api/jobs/*', async route => route.fulfill({status:200, contentType:'application/json', body:JSON.stringify({
    state:'done', transcript:'Synthetic browser test question', answer:'Synthetic browser fixture: six of eight lifts passed.',
    selected_round:1, sources:['synthetic browser fixture'],
    ...(textOnly ? {speech_error:'Speech is unavailable. Your text answer is ready.'} : {audio:{data:wav.toString('base64'),mime_type:'audio/wav'}})
  })}));
  try {
    await page.goto(process.env.LIFT_LAB_VOICE_URL || 'http://127.0.0.1:8791/', {waitUntil:'networkidle'});
    await page.waitForFunction(() => document.getElementById('connection').textContent === 'Ready');
    await page.waitForFunction(() => document.getElementById('evidence-stats').textContent.includes('75%'));
    await page.locator('#round').selectOption('2');
    await page.waitForFunction(() => document.getElementById('evidence-stats').textContent.includes('12.5%'));
    await page.getByRole('button', {name:'Refresh', exact:true}).click();
    await page.waitForFunction(() => document.getElementById('round').value === '2' && document.getElementById('evidence-stats').textContent.includes('12.5%'));
    assert.equal(submitted.length,0,'Inspecting or refreshing evidence must not trigger paid calls');
    await page.locator('#round').selectOption('best');
    await page.waitForFunction(() => document.getElementById('evidence-stats').textContent.includes('75%'));
    await page.screenshot({path:'runs/voice-preview-desktop.png', fullPage:true});
    await page.getByRole('button', {name:'Why did 40 kg fail?'}).click();
    assert.equal(submitted.length,0,'Example selection must not trigger paid requests');
    await page.getByRole('button', {name:'Ask Argon'}).click();
    await page.waitForFunction(() => !document.getElementById('playback').hidden);
    assert.match(await page.locator('#answer').textContent(), /Synthetic browser fixture/);
    await page.waitForFunction(() => !document.getElementById('ask').disabled);
    assert.equal(submitted[0].mass,'all');
    await page.locator('#question').fill('');
    await page.getByRole('button', {name:'Record a question'}).click();
    await page.waitForFunction(() => document.getElementById('record').textContent === 'Stop recording');
    await page.waitForTimeout(1100);
    await page.getByRole('button', {name:'Stop recording'}).click();
    await page.waitForFunction(() => document.getElementById('record-status').textContent.includes('Recording ready'));
    await page.getByRole('button', {name:'Ask Argon'}).click();
    await page.waitForFunction(() => !document.getElementById('ask').disabled);
    assert.ok(submitted[1].audio.data.length > 0);
    assert.match(submitted[1].audio.mime_type, /^audio\//);
    textOnly = true;
    await page.locator('#question').fill('Synthetic TTS fallback check');
    await page.getByRole('button', {name:'Ask Argon'}).click();
    await page.waitForFunction(() => !document.getElementById('speech-note').hidden);
    assert.match(await page.locator('#speech-note').textContent(), /text answer is ready/);
    await page.setViewportSize({width:375,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile must not overflow');
    await page.screenshot({path:'runs/voice-preview-mobile.png', fullPage:true});
    assert.deepEqual(errors,[]);
    const report = {status:'passed',paid_calls:0, checks:['ready state','saved evidence panel','best versus final scores',
      'refresh preserves selection without model calls','example does not submit',
      'typed question','fake-microphone recording','native audio request body','spoken playback controls',
      'TTS failure preserves text','mobile layout','no JavaScript exceptions']};
    fs.writeFileSync('runs/voice-browser-check.json',JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
