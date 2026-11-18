#!/bin/bash
# SHEER - pack the player builds for a GitHub release: dist/Sheer-Windows-x64.zip, dist/Sheer-Linux-x64.tar.gz and
# dist/SHA256SUMS.txt. Unity's "do not ship" folders (Burst debug information) are left out.
# usage: tools/package_release.sh [version]   (run from the repository root, after building both players)
set -euo pipefail
cd "$(dirname "$0")/.."
VER="${1:-}"
mkdir -p dist
rm -f dist/Sheer-*.zip dist/Sheer-*.tar.gz dist/SHA256SUMS.txt
# (each archive unpacks into one folder named after it)
if [ -f builds/windows/Sheer.exe ]; then
  W="Sheer-Windows-x64${VER:+-$VER}"
  ln -sfn ../builds/windows "dist/$W"
  (cd dist && zip -qr -9 "$W.zip" "$W" -x "$W/*DoNotShip*/*" -x "$W/*DontShipItWithYourGame*/*" -x "$W/unity_logs/*" -x '*.log')
  rm -f "dist/$W"
fi
if [ -f builds/linux/Sheer.x86_64 ]; then
  L="Sheer-Linux-x64${VER:+-$VER}"
  tar -C builds --exclude='*DoNotShip*' --exclude='*DontShipItWithYourGame*' --exclude='unity_logs' --exclude='*.log' \
      --transform "s,^linux,$L," -czf "dist/$L.tar.gz" linux
fi
(cd dist && sha256sum Sheer-* > SHA256SUMS.txt)
ls -la dist
cat dist/SHA256SUMS.txt
