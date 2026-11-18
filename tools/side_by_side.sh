#!/bin/bash
# Original (game view cropped from the source video) | ours (composited MP4), synchronized, 30 fps.
# Usage: side_by_side.sh ORIGINAL.mp4 OURS.mp4 OUT.mp4 [height]
ORIG="$1"; OURS="$2"; OUT="$3"; H="${4:-756}"
ffmpeg -v error -y -i "$ORIG" -i "$OURS" -filter_complex \
 "[0:v]fps=30,crop=1150:2010:20:150,scale=-2:${H},setsar=1,drawtext=text='ORIGINAL (Unity 6)':x=10:y=10:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.5[a]; \
  [1:v]scale=-2:${H},setsar=1,drawtext=text='RECREATION (Blender Cycles)':x=10:y=10:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.5[b]; \
  [a][b]hstack=inputs=2:shortest=1" -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p -an "$OUT"
echo "wrote $OUT"
