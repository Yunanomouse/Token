#!/usr/bin/env bash
# Build a film end-to-end: render the silent video, synthesize the soundtrack,
# mux them (VP8 + Opus .webm), then export a phone-friendly MP4 (H.264 + AAC).
#
#   bash render/build.sh            # the 24 s trailer  -> dist/openbb-30s.{webm,mp4}
#   bash render/build.sh tour       # the 2 min tour    -> dist/venture-2min.{webm,mp4}
#
# Playwright's bundled ffmpeg has no audio encoder, so muxing uses a full
# ffmpeg fetched via imageio-ffmpeg (pip install numpy imageio-ffmpeg).
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-trailer}" in
  trailer) PAGE=src/openbb.html;       NAME=openbb-30s;   AUDIO=render/make_audio.py;      CRF=18 ;;
  tour)    python3 render/make_tour_page.py
           PAGE=src/venture-2min.html; NAME=venture-2min; AUDIO=render/make_audio_tour.py; CRF=21 ;;
  *) echo "usage: build.sh [trailer|tour]" >&2; exit 2 ;;
esac
WEBM="dist/$NAME.webm"; MP4="dist/$NAME.mp4"; WAV="dist/_$NAME.wav"
mkdir -p dist

echo "1/4  rendering video…"
node render/record.mjs --in "$PAGE" --out "$WEBM"          # silent

echo "2/4  synthesizing audio…"
python3 "$AUDIO" "$WAV"

echo "3/4  muxing audio + video…"
FF="$(python3 -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
chmod +x "$FF" || true
"$FF" -hide_banner -loglevel error -y -i "$WEBM" -i "$WAV" \
  -map 0:v -map 1:a -c:v copy -c:a libopus -b:a 128k -shortest dist/_final.webm
mv -f dist/_final.webm "$WEBM"
rm -f "$WAV"

echo "4/4  exporting phone-friendly MP4 (H.264 + AAC)…"
"$FF" -hide_banner -loglevel error -y -i "$WEBM" \
  -c:v libx264 -profile:v high -pix_fmt yuv420p -crf "$CRF" -preset slow \
  -c:a aac -b:a 192k -movflags +faststart "$MP4"

echo "done -> $WEBM  &  $MP4"
"$FF" -hide_banner -i "$MP4" 2>&1 | grep -E "Duration|Stream" || true
ls -lh "$WEBM" "$MP4" | awk '{print $5, $9}'
