# Venture Trader — product films

Code-driven videos of the **Venture Trader** market-intelligence dashboard.
Each film is one HTML page whose whole timeline is a pure function of time,
rendered frame by frame with Playwright's headless Chromium, with a soundtrack
synthesized from scratch. No screen recording, stock footage or audio samples.

| Film | Length | Output |
|------|--------|--------|
| Trailer | 24 s | `dist/openbb-30s.webm`, `dist/openbb-30s.mp4` |
| Guided tour | 2 min | `dist/venture-2min.mp4` |

Both are 1280×720 at 30 fps with stereo audio. The `.mp4` files (H.264 + AAC)
play on phones; `.webm` is VP8 + Opus.

## The 2-minute tour

Laid out on a 128 BPM grid (64 bars = 120 s) so every scene change lands on a
downbeat of the music.

| Time | Scene |
|------|-------|
| 0:00 | Hook — three lines, then the logo |
| 0:07 | Overview — daily briefing, stat cards, market heatmap |
| 0:30 | Stock card — timeframes (1W / 6M / 1Y redraw the chart), performance, fundamentals, trend line |
| 0:52 | Signals — high conviction, medium, Buy Radar; the lists scroll |
| 1:15 | AI Analysis — the AI take types in, then the three analysts |
| 1:34 | The remaining tabs, shown in the nav bar |
| 1:39 | Auto-refresh — heatmap and briefing update |
| 1:49 | Outro |

Only screens whose real layout was available are recreated (Overview, the
stock card, Signals, AI Analysis). The other tabs appear by name in the nav bar
and are not opened.

## Build

```bash
pip install numpy imageio-ffmpeg           # audio synthesis + a full ffmpeg for muxing
ln -sf "$(npm root -g)" ./node_modules     # if Playwright is installed globally

bash render/build.sh            # trailer
bash render/build.sh tour       # 2-minute tour
```

Preview single frames without a full render (also sweeps the whole timeline for
script errors):

```bash
node render/snap.mjs --in src/venture-2min.html --out dist/_frames 12 45.5 80
```

## Layout

| Path | What it is |
|------|------------|
| `src/openbb.html` | The trailer page: dashboard recreation + its 24 s timeline. |
| `render/tour_script.js` | The tour's timeline: captions, cursor path, camera keyframes, per-scene animation. |
| `render/make_tour_page.py` | Assembles `src/venture-2min.html` from the trailer's markup/styles and the tour timeline. |
| `render/record.mjs` | Renderer: seeks the page frame by frame and pipes JPEG frames into ffmpeg. |
| `render/snap.mjs` | Frame preview tool. |
| `render/synth.py` | Small numpy synth (kick, snare, hats, bass, pluck, pad, whoosh, impact, riser). |
| `render/make_audio.py`, `render/make_audio_tour.py` | Soundtrack arrangements for the trailer and the tour. |
| `render/build.sh` | Render → synthesize → mux → export MP4. |
| `skills/web-video-trailer/` | The same pipeline packaged as a reusable skill. |

## How it stays in sync

Headless Chromium throttles wall-clock animation, so nothing on the page uses
CSS animations or `requestAnimationFrame` for timing. The page exposes
`window.__seek(ms)`; the renderer calls it for every frame and screenshots the
result, so the output is identical on any machine. The camera (push-ins, pans,
3D tilt) is a transform on one wrapper element driven by keyframes, and the
music is arranged on the same bar grid as the picture.
