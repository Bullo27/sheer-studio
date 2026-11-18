#!/bin/bash
# SHEER - batch captures for the README's media (tools/readme_media.py turns them into the hero GIF and the showreel):
# the hero (the original session's opening, default look) and one clip each for the simulator's main sights and a few of
# the panel's choices. ONE player at a time, on the GPU.
#   bash tools/readme_captures.sh OUT_DIR        (then: python3 tools/readme_media.py SHOWCASE_DIR OUT_DIR docs/img)
set -u
cd "$(dirname "$0")/.."
C=${1:?usage: readme_captures.sh OUT_DIR}
P=builds/linux/Sheer.x86_64
T=tools/sim/ref_data/test_sessions
mkdir -p "$C/logs" "$C/looks"
echo '{"color":{"r":0.80,"g":0.60,"b":0.48,"a":1},"denier":15,"backdrop":4,"floor":2,"skirtStyle":0,"skirtOwnColor":true,"skirtColor":{"r":0.08,"g":0.11,"b":0.24,"a":1}}' > "$C/looks/nude.json"
echo '{"color":{"r":0.02,"g":0.02,"b":0.025,"a":1},"denier":30,"backdrop":6,"floor":5,"skirtStyle":0,"skirtOwnColor":true,"skirtColor":{"r":0.27,"g":0.035,"b":0.06,"a":1}}' > "$C/looks/black.json"
cap() { name=$1; label=$2; from=$3; to=$4; shift 4
  rm -rf "$C/$name"; mkdir -p "$C/$name"
  timeout 2400 $P -batchmode -force-vulkan -sheerReplay -sheerCapture "$C/$name" -sheerFrom $from -sheerTo $to \
     -sheerCapScale 2 -sheerCapFps 30 -sheerCapJpg 92 -logFile "$C/logs/$name.log" "$@" >/dev/null 2>&1
  rc=$?
  [ -n "$label" ] && echo "$label" > "$C/$name/label.txt"
  echo "$name: exit $rc, $(ls "$C/$name" | grep -c u_) frames, $(grep -c Exception "$C/logs/$name.log") exceptions"; }
cap hero "" 0.0 7.0
cap clip_1 "The original demo's session, replayed" 0.0 4.0
cap clip_2 "Pull far and it tears" 7.2 11.0 -sheerSession $T/pulls.json
cap clip_3 "VIEW 02 · a sail at the ankle" 18.4 21.6 -sheerSession $T/pulls.json
# (a view a player can reach: VIEW 01 orbited 55 deg, zoomed out to the limit - not a wide free camera: the body ends a
#  hand above the waistband, and from far out the skirt read as a black box)
cap clip_4 "She shifts her weight · the skirt goes with her" 3.0 7.0 -sheerSession $T/midview.json -sheerCamFree "0:1.294:0.55:-0.906:0.03:0.62:0.0:87"
cap clip_5 "Nude 15 denier" 0.8 4.4 -sheerSession $T/pulls.json -sheerLook "$C/looks/nude.json"
cap clip_6 "Black 30 denier" 5.0 8.6 -sheerSession $T/pulls.json -sheerLook "$C/looks/black.json"
