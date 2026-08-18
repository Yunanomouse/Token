#!/usr/bin/env bash
# Build the full trailer end-to-end: render the silent video, synthesize the
# soundtrack, then mux them into dist/openbb-30s.webm (VP8 video + Opus audio).
#
# Playwright's bundled ffmpeg has no audio encoder, so muxing uses a full
# ffmpeg fetched via imageio-ffmpeg (cached after first run).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "1/3  rendering video…"
node render/record.mjs                       # -> dist/openbb-30s.webm (silent)

echo "2/3  synthesizing audio…"
python3 render/make_audio.py                 # -> dist/track.wav

echo "3/3  muxing audio + video…"
python3 - <<'PY'
import imageio_ffmpeg
print(imageio_ffmpeg.get_ffmpeg_exe())
PY
FF="$(python3 -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
chmod +x "$FF" || true
"$FF" -hide_banner -loglevel error -y \
  -i dist/openbb-30s.webm -i dist/track.wav \
  -map 0:v -map 1:a -c:v copy -c:a libopus -b:a 128k -shortest \
  dist/_final.webm
mv -f dist/_final.webm dist/openbb-30s.webm
rm -f dist/track.wav

echo "done -> dist/openbb-30s.webm"
"$FF" -hide_banner -i dist/openbb-30s.webm 2>&1 | grep -E "Duration|Stream" || true
