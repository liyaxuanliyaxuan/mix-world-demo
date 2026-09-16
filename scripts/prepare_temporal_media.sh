#!/usr/bin/env bash
# Preserve the selected RQ3 ceiling comparison and its physical-time playback.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE=".._artifacts/runs/iclr2027-mixworld/20260913_174158_iclr2027-mixworld_fig6-candidate-search_seed780/candidate_02_physical_time.mp4"
OUT="$ROOT/public/media/temporal"
mkdir -p "$OUT"
# Stream-copy all video frames and timestamps; move the MP4 index for web playback.
ffmpeg -v error -y -i "$SOURCE" -map 0:v:0 -c:v copy -an -movflags +faststart "$OUT/candidate02_ceiling_physical_time.mp4"
ffmpeg -v error -y -i "$OUT/candidate02_ceiling_physical_time.mp4" -frames:v 1 -q:v 2 "$OUT/candidate02_ceiling_physical_time.jpg"
python3 - "$SOURCE" "$OUT/candidate02_ceiling_physical_time.mp4" <<'VERIFY'
import json, subprocess, sys

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,width,height,r_frame_rate,nb_frames,duration', '-of', 'json', path]))['streams'][0]

def pixels(path):
    return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', path, '-map', '0:v:0', '-f', 'hash', '-hash', 'sha256', '-']).decode().strip()

source, output = sys.argv[1:]
assert probe(source) == probe(output), 'Video properties changed'
assert pixels(source) == pixels(output), 'Decoded video frames changed'
print('Verified source/output stream properties and decoded frame SHA-256:', probe(output))
VERIFY
