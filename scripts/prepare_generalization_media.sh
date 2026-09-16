#!/usr/bin/env bash
# Generalization-section media from the 2026-09-15 owner handover package
# (~/Downloads/MiXWorld_网站素材交接_20260915, SHA256SUMS verified).
# Fixed-arm clips: byte-identical copies. Mobile clips: trimmed to the paper
# display window 0-19.2 s of the 96 s rollout (owner README: later drift is
# out of the paper scope); trim is a time cut only, re-encode recorded below.
set -uo pipefail

ROOT="."
GEN="$ROOT/public/media/gen"
HW="~/Downloads/MiXWorld_网站素材交接_20260915"
LOG="$ROOT/reports/media-derivation-record.md"
mkdir -p "$GEN"

ENC="-c:v libx264 -preset veryfast -crf 24 -pix_fmt yuv420p -movflags +faststart -an"

copy () { # copy <src> <out>
  [ -s "$2" ] && { echo "skip $2"; return; }
  cp "$1" "$2" && echo "copied $2"
}

trim19 () { # trim19 <src> <out>
  [ -s "$2" ] && { echo "skip $2"; return; }
  ffmpeg -v error -y -i "$1" -t 19.3 $ENC "$2" && echo "trimmed $2"
}

# fixed-base dual-arm, bottle opening (49 frames @10fps, 4.9 s) — verbatim copies
copy "$HW/02_fig07_fixedarm_scene/room/prediction_grid_full.mp4"     "$GEN/fixed_background.mp4"
copy "$HW/02_fig07_fixedarm_scene/layout/prediction_grid_full.mp4"   "$GEN/fixed_layout.mp4"
copy "$HW/02_fig07_fixedarm_scene/objects/prediction_grid_full.mp4"  "$GEN/fixed_objects.mp4"
copy "$HW/02_fig07_fixedarm_scene/room/initial.png"                  "$GEN/fixed_background_initial.png"
copy "$HW/02_fig07_fixedarm_scene/layout/initial.png"                "$GEN/fixed_layout_initial.png"
copy "$HW/02_fig07_fixedarm_scene/objects/initial.png"               "$GEN/fixed_objects_initial.png"

# mobile dual-arm, chips (961 frames @10fps) — paper window 0-19.2 s
trim19 "$HW/04_fig11_mobile_scene/room/prediction_grid_full.mp4"            "$GEN/mobile_room.mp4"
trim19 "$HW/04_fig11_mobile_scene/layout/prediction_grid_full.mp4"          "$GEN/mobile_layout.mp4"
trim19 "$HW/04_fig11_mobile_scene/background/prediction_grid_full.mp4"      "$GEN/mobile_background.mp4"
trim19 "$HW/04_fig11_mobile_scene/object_arrangement/prediction_grid_full.mp4" "$GEN/mobile_objects.mp4"
copy "$HW/04_fig11_mobile_scene/room/initial.png"                   "$GEN/mobile_room_initial.png"
copy "$HW/04_fig11_mobile_scene/layout/initial.png"                 "$GEN/mobile_layout_initial.png"
copy "$HW/04_fig11_mobile_scene/background/initial.png"             "$GEN/mobile_background_initial.png"
copy "$HW/04_fig11_mobile_scene/object_arrangement/initial.png"     "$GEN/mobile_objects_initial.png"

# posters = first frame of each condition video
for f in "$GEN"/*.mp4; do
  base=$(basename "$f" .mp4)
  [ -s "$GEN/${base}.poster.jpg" ] || ffmpeg -v error -y -i "$f" -frames:v 1 -q:v 4 "$GEN/${base}.poster.jpg"
done

{
echo
echo "## 泛化节素材（$(date '+%F %T')）"
echo "来源: owner交接包 MiXWorld_网站素材交接_20260915（SHA256SUMS 已逐一校验通过）"
echo "- fixed_*: 02_fig07_fixedarm_scene 字节级拷贝（640x288@10fps, 49 帧 / 4.9 s）"
echo "- mobile_*: 04_fig11_mobile_scene 裁剪至论文展示窗 0-19.2 s（原 96 s，后段漂移按owner说明不展示），libx264 crf24"
echo "- *_initial.png: 各条件编辑后的首帧，字节级拷贝"
echo "- 移动条带其他条件/完整 96 s 原片保留在交接包，未上站"
} >> "$LOG"
echo "DONE"

# source-scene reference frames (sparse by nature — displayed as frames, never
# assembled into a fake continuous video)
copy "$HW/02_fig07_fixedarm_scene/shared_source_reference/reference_model_0000.png" "$GEN/fixed_source_t0000.png"
copy "$HW/02_fig07_fixedarm_scene/shared_source_reference/reference_model_0018.png" "$GEN/fixed_source_t0018.png"
copy "$HW/02_fig07_fixedarm_scene/shared_source_reference/reference_model_0024.png" "$GEN/fixed_source_t0024.png"
copy "$HW/02_fig07_fixedarm_scene/shared_source_reference/reference_model_0028.png" "$GEN/fixed_source_t0028.png"
copy "$HW/02_fig07_fixedarm_scene/shared_source_reference/reference_model_0032.png" "$GEN/fixed_source_t0032.png"
copy "$HW/04_fig11_mobile_scene/shared_source_reference/source_future_model_0000_raw_0000.png" "$GEN/mobile_source_t0000.png"
copy "$HW/04_fig11_mobile_scene/shared_source_reference/source_future_model_0024_raw_0120.png" "$GEN/mobile_source_t0024.png"
copy "$HW/04_fig11_mobile_scene/shared_source_reference/source_future_model_0048_raw_0240.png" "$GEN/mobile_source_t0048.png"
copy "$HW/04_fig11_mobile_scene/shared_source_reference/source_future_model_0144_raw_0720.png" "$GEN/mobile_source_t0144.png"
copy "$HW/04_fig11_mobile_scene/shared_source_reference/source_future_model_0168_raw_0840.png" "$GEN/mobile_source_t0168.png"
copy "$HW/04_fig11_mobile_scene/shared_source_reference/source_future_model_0192_raw_0960.png" "$GEN/mobile_source_t0192.png"
