#!/usr/bin/env bash
# Add actual gutters between camera images without covering source pixels.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 - <<'PY'
import json, subprocess
from pathlib import Path
s=json.loads(Path('src/data/site.json').read_text())
for embodiment in s['adaptation']['videos']['embodiments']:
 for clip in embodiment['clips']:
  src=Path('public'+clip['video'])
  if src.stem.endswith('_grouped'): continue
  if src.stem.endswith('_aligned6'): src=src.with_name(src.stem[:-9]+'.mp4')
  if src.stem.endswith('_gaps'): src=src.with_name(src.stem[:-5]+'.mp4')
  out=src.with_name(src.stem+'_grouped.mp4')
  if embodiment['id']=='franka_single':
   crops=[(288,288,x,0) for x in [0,288,576,864]]
   positions=['0_0','294_0','596_0','890_0']
  else:
   crops=[(384,288,0,0),(192,144,384,0),(192,144,384,144),(384,288,576,0),(192,144,960,0),(192,144,960,144)]
   positions=['0_0','398_0','398_150','604_0','1002_0','1002_150']
  n=len(crops)
  parts=['[0:v]split='+str(n)+''.join(f'[s{i}]' for i in range(n))]
  for i,(w,h,x,y) in enumerate(crops):
   # 392/294 == 384/288: preserve the main camera aspect ratio exactly.
   resize=',scale=392:294:flags=lanczos' if n==6 and i in (0,3) else ''
   parts.append(f'[s{i}]crop={w}:{h}:{x}:{y}{resize},setsar=1[v{i}]')
  parts.append(''.join(f'[v{i}]' for i in range(n))+f'xstack=inputs={n}:layout='+ '|'.join(positions)+':fill=0xFAF9F5[out]')
  if not out.exists():
   subprocess.run(['ffmpeg','-v','error','-n','-i',str(src),'-filter_complex',';'.join(parts),'-map','[out]','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart','-an',str(out)],check=True)
  poster=out.with_name(out.stem+'_poster.jpg')
  if not poster.exists(): subprocess.run(['ffmpeg','-v','error','-n','-i',str(out),'-frames:v','1','-q:v','2',str(poster)],check=True)
  def probe(p): return json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames,r_frame_rate','-of','json',str(p)]))['streams'][0]
  assert probe(src)==probe(out)
  clip['video']='/'+str(out.relative_to('public'))
  clip['poster']='/'+str(poster.relative_to('public'))
Path('src/data/site.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
print('All 13 adaptation clips: gutters added; frame counts and rates unchanged.')
PY
