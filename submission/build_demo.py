"""Assemble actual app captures and verified trial footage into a 60-second narrated MP4."""
import json, subprocess, time, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'runs/submission_demo'
OUT=ROOT/'submission/humanoid-lift-lab-60s.mp4'
FF=imageio_ffmpeg.get_ffmpeg_exe()
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD='/System/Library/Fonts/Supplemental/Arial Bold.ttf'
def font(n,bold=False):return ImageFont.truetype(BOLD if bold else FONT,n)
scenes=[
 ('intro.png',7,'Humanoid Lift Lab','Gemini Argon observes, diagnoses and revises robot controllers.','Actual application · saved development evidence',0),
 ('before',11,'BEFORE · 5 kg / 11 lb','The deployed reference drops the light tote.','Recorded MuJoCo trial · reference controller · FAIL',3),
 ('critique.png',12,'ARGON · Watch, diagnose, rewrite','Video + telemetry → grip and clearance diagnosis → Python repair','Saved model critique · hypotheses checked by re-execution',0),
 ('after_5kg.mp4',15,'AFTER · Same 5 kg / 11 lb payload','Revised controller: 0.687 m rise · 4.97 s hold · PASS','Recorded MuJoCo trial · video-adaptation round 4',0),
 ('results.png',9,'RESULTS · Preserve successful behavior','Video and text adaptation: 7/8 → 8/8 across 5–40 kg','Both reached 8/8 · this does not establish video superiority',0),
 ('voice.png',6,'INSPECT · Ask questions by voice','Argon explains saved evidence. Gemini TTS speaks the answer.','Modified, assisted simulation · hardware transfer not established',0),
]
def overlay(index,title,caption,note):
 im=Image.new('RGBA',(1280,720),(0,0,0,0));d=ImageDraw.Draw(im)
 d.rectangle((0,0,1279,111),fill='#f7f6f2');d.rectangle((0,592,1279,719),fill='#f7f6f2')
 d.rectangle((0,0,10,111),fill='#ad4220');d.text((34,17),'HUMANOID LIFT LAB',font=font(14,True),fill='#ad4220')
 d.text((34,43),title,font=font(31,True),fill='#1b1d21');d.text((1210,24),f'{index+1}/6',font=font(17),fill='#5d6470')
 d.text((34,609),caption,font=font(24,True),fill='#1b1d21');d.text((34,648),note,font=font(17),fill='#5d6470')
 d.text((34,688),'github.com/abhijitbetigeri/humanoid-lift-lab',font=font(15),fill='#5d6470')
 path=WORK/f'overlay_{index}.png';im.save(path);return path
for index,(source,duration,title,caption,note,start) in enumerate(scenes):
 if source=='before':source=ROOT/'runs/video_adapt/round_0/videos/m5_grid.mp4'
 else:source=WORK/source
 for _ in range(100):
  if source.exists():break
  time.sleep(1)
 if not source.exists():raise RuntimeError(f'Missing finished artifact: {source}')
 image=source.suffix=='.png';layer=overlay(index,title,caption,note);target=WORK/f'scene_{index}.mp4'
 inputs=['-loop','1','-framerate','24'] if image else ['-stream_loop','-1']
 if start:inputs+=['-ss',str(start)]
 cmd=[FF,'-hide_banner','-loglevel','error','-y',*inputs,'-i',str(source),'-loop','1','-i',str(layer),'-filter_complex','[0:v]scale=1280:480:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:112:color=0xf7f6f2[b];[b][1:v]overlay=0:0:shortest=1','-t',str(duration),'-r','24','-an','-c:v','libx264','-preset','ultrafast','-crf','20','-pix_fmt','yuv420p','-threads','2',str(target)]
 subprocess.run(cmd,check=True);print(f'Scene {index+1}/6 encoded',flush=True)
concat=WORK/'scenes.txt';concat.write_text(''.join(f"file '{(WORK/f'scene_{i}.mp4').as_posix()}'\n" for i in range(6)))
subprocess.run([FF,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-i',str(WORK/'narration.wav'),'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','128k','-af','apad=pad_dur=2','-t','60','-movflags','+faststart',str(OUT)],check=True)
with wave.open(str(WORK/'narration.wav')) as wav:audio_seconds=wav.getnframes()/wav.getframerate()
report={'output':str(OUT.relative_to(ROOT)),'duration_s':60,'resolution':[1280,720],'fps':24,'narration_seconds':audio_seconds,'bytes':OUT.stat().st_size,'source_before':'runs/video_adapt/round_0/videos/m5_grid.mp4','source_after':'runs/video_adapt/round_4/trials/m5/traj.npz','screens':'Actual local results and voice applications; captured without submitting new model questions.','narration':'Gemini TTS','claims':'Development adaptation 7/8 to8/8 in both video and text; modified assisted simulation; no hardware or video-superiority claim.'}
(ROOT/'submission/demo-manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
