# Venture Trader — product films

Videos of the **Venture Trader** market-intelligence dashboard, rendered frame by
frame with Playwright's headless Chromium and scored with a soundtrack synthesized
from scratch. No screen recorder, stock footage or audio samples.

| Film | Length | What it shows | Output |
|------|--------|---------------|--------|
| **Film** | 2 min | The real app, on live market data, operated with a real mouse | `dist/venture-trader-film.mp4` |
| Trailer | 24 s | An earlier hand-built recreation of the dashboard (older UI) | `dist/openbb-30s.mp4`, `.webm` |

Both are 1280×720 at 30 fps with stereo audio. `.mp4` (H.264 + AAC) plays on phones.

## The 2-minute film

Shot on the real dashboard — see [`film/README.md`](film/README.md) for how. Laid out
on a 128 BPM grid (64 bars = 120 s) so scene changes land on downbeats of the music.

| Time | Scene |
|------|-------|
| 0:00 | Hook — three lines, then the logo |
| 0:07 | Overview — briefing, stat cards, Buy Radar, sector heatmap (pages a sector over and back) |
| 0:30 | Stock popup — NVDA, fetched live: 1D / 1Y / 5Y candles, pattern read, key levels, dividends, fundamentals |
| 0:52 | Search — types "tesla", picks the suggestion, opens TSLA |
| 1:00 | Watchlist, then the US market screener (most active / gainers / losers) |
| 1:15 | Crypto — live Kraken candles |
| 1:22 | Signals — Buy Radar, scorecard, Reddit buzz, signals by conviction |
| 1:39 | Fundamentals, News, Discover, Insiders |
| 1:49 | Outro |

AI Analysis, Options Flow, Calendar and the Macro panels are not opened: they need the
owner's own keys or local model.

## Build

```bash
pip install numpy imageio-ffmpeg           # audio synthesis + a full ffmpeg for muxing
ln -sf "$(npm root -g)" ./node_modules     # if Playwright is installed globally

bash render/build.sh            # trailer
bash render/build.sh film       # 2-minute film (the app must be running: film/README.md)
```

## Layout

| Path | What it is |
|------|------------|
| `film/` | Everything for filming the real app: stage, engine, timeline, recorder, app setup scripts. |
| `src/openbb.html` | The trailer page: the earlier dashboard recreation and its 24 s timeline. |
| `render/record.mjs`, `render/snap.mjs` | Renderer and frame-preview tool for the trailer page. |
| `render/synth.py` | Small numpy synth (kick, snare, hats, bass, pluck, pad, whoosh, impact, riser). |
| `render/make_audio.py`, `render/make_audio_film.py` | Soundtrack arrangements for the trailer and the film. |
| `render/build.sh` | Render → synthesize → mux → export MP4. |
| `skills/web-video-trailer/` | The trailer pipeline packaged as a reusable skill. |
