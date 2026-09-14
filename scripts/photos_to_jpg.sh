#!/bin/sh
# Convert the HEIC site photos to 1600-px JPEGs (macOS `sips`) for notebooks / figures.
# Usage: sh scripts/photos_to_jpg.sh
cd "$(dirname "$0")/.." || exit 1
SRC=data/raw/picture; DST=$SRC/jpg
mkdir -p "$DST"
for f in "$SRC"/*.HEIC; do
  b=$(basename "${f%.HEIC}")
  [ -f "$DST/$b.jpg" ] || sips -s format jpeg -Z 1600 "$f" --out "$DST/$b.jpg" >/dev/null
done
ls "$DST"
