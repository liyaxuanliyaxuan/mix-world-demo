#!/usr/bin/env bash
# Re-layout the existing, orientation-corrected LIBERO comparisons.
# Preserve every frame and both camera images; only remove canvas padding.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$ROOT/public/media/adaptation"
FILTER='[0:v]split=4[a][b][c][d];[a]crop=288:288:48:0,setsar=1[pm];[b]crop=144:144:408:0,scale=288:288:flags=lanczos,setsar=1[pw];[c]crop=288:288:624:0,setsar=1[gm];[d]crop=144:144:984:0,scale=288:288:flags=lanczos,setsar=1[gw];[pm][pw][gm][gw]hstack=inputs=4[out]'

for episode in 01 02 03; do
  source="$MEDIA/fs_ep${episode}_cmp.mp4"
  output="$MEDIA/fs_ep${episode}_equal_views.mp4"
  poster="$MEDIA/fs_ep${episode}_equal_views_poster.jpg"
  if [[ ! -s "$output" ]]; then
    ffmpeg -v error -n -i "$source" -filter_complex "$FILTER" -map '[out]' \
      -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart -an "$output"
  fi
  if [[ ! -s "$poster" ]]; then
    ffmpeg -v error -n -i "$output" -frames:v 1 -q:v 2 "$poster"
  fi
done
