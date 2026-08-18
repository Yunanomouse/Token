# OpenBB Trader — 30s Trailer

A self-contained, code-driven **30-second trailer** for **OpenBB Trader**,
rendered to a real video file with Playwright's headless Chromium + bundled
ffmpeg. No external services, no design tools — the whole thing is one HTML
file plus a render script.

![status](https://img.shields.io/badge/duration-30.0s-blue) ![res](https://img.shields.io/badge/1280×720-30fps-blue)

## What's here

| Path | What it is |
|------|------------|
| `src/openbb.html` | The trailer itself — a single self-contained HTML file. The whole 30s timeline is driven by one `seek(t)` function (no wall-clock CSS animation), so it renders frame-perfectly. |
| `render/record.mjs` | Deterministic renderer: seeks the timeline frame-by-frame, screenshots each frame, and streams them into ffmpeg (`image2pipe`/mjpeg → VP8/webm). |
| `dist/openbb-30s.webm` | The rendered trailer (1280×720, 30.0s, 30fps). |

## The 30-second cut

| Time | Scene |
|------|-------|
| 0–5s | Logo reveal — *"Desktop Trading Terminal"* |
| 5–11s | Three pillars — Real-time charts · Watchlists & alerts · One-click orders |
| 11–21s | Live terminal — animated price chart, volume histogram, KPIs & watchlist |
| 21–27s | Feature grid — live data · advanced charting · instant execution · desktop-native |
| 27–30s | Outro — logo, CTA, tagline |

## Render it yourself

Playwright (with its bundled Chromium + ffmpeg) is the only dependency:

```bash
node render/record.mjs        # 30 fps (default)
node render/record.mjs 60     # 60 fps
```

Output → `dist/openbb-30s.webm`.

### Design notes

- Dark UI uses the **dataviz** skill's validated palette (accent `#3987e5`,
  status green `#22c58b` / red `#e66767`), so the chart reads cleanly and
  colour-blind-safely.
- Timing is deterministic: every frame is a pure function of `t`, so the output
  is identical on any machine regardless of render speed.

> **Note:** the current cut is a stylized mockup of a trading terminal. To make
> it your real product, drop in OpenBB Trader screenshots/screen-recordings and
> swap the copy in `src/openbb.html`.
