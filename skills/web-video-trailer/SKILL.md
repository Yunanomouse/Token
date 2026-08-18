---
name: web-video-trailer
description: >-
  Create a short animated promo/trailer/teaser/explainer VIDEO — an actual
  rendered video file (.webm) — from code, using Playwright's headless Chromium
  plus its bundled ffmpeg. No external services, no editing app, no stock
  footage. Use this WHENEVER the user asks to "make a video", "trailer",
  "promo", "teaser", "demo video", "product launch video", "animated explainer",
  "motion graphic", "hype reel", or wants to turn an app / screenshots / a
  landing page into a short shareable clip — even if they don't say the word
  "video" outright. Especially reach for it when a real video FILE is wanted and
  only a headless browser + ffmpeg are available. The output is frame-perfect and
  reproducible because the whole timeline is a pure function of time.
---

# Web-video trailer

Build a short motion video by animating a self-contained HTML page and rendering
it to a real `.webm` file. The craft that makes this reliable — and the reason
this skill exists rather than "just record the screen" — is that the animation is
**seek-driven**: every frame is a pure function of a timestamp, so headless
Chromium's animation throttling can't desync it and the result is identical on any
machine.

## When to use

Any request for a short (roughly 10–60s) animated video: product trailers, feature
teasers, launch/hype reels, animated explainers, or turning an app, a set of
screenshots, or a landing page into a shareable clip. If the user wants an actual
video file and you have a headless browser available, this is the tool.

## What you produce

- `src/<name>.html` — a self-contained timeline page (start from `assets/template.html`).
- a rendered `dist/<name>.webm` (default 1280×720, 30fps).
- optionally a tiny README documenting `node record.mjs --in … --out …`.

## Workflow

1. **Scope the cut.** Decide length and a 3–6 scene beat sheet (e.g. logo →
   value props → product screen → features → outro). Keep each scene 3–6s; a 30s
   film is usually five scenes.

2. **Author the page from the template.** Copy `assets/template.html` to
   `src/<name>.html` and build the scenes. The non-negotiable rule: **drive all
   motion from the `seek(t)` function — never CSS `animation`/`transition` or
   `requestAnimationFrame` for timing.** `references/timeline.md` explains the
   model, the `seg()`/easing/`setT()` helpers, how to add scenes, how to drop in
   real screenshots/recordings, and how to animate charts. Read it before writing
   a non-trivial scene.

3. **Brand it.** Swap the CSS color tokens at the top of the page. The defaults
   are the `dataviz` skill's validated, colorblind-safe dark palette — if you add
   categorical chart colors, validate them with that skill rather than eyeballing.
   Match real product screenshots by using the app's actual accent color.

4. **Make sure Playwright resolves.** The renderer imports `playwright`. If it's a
   global install, symlink it once: `ln -sf "$(npm root -g)" ./node_modules`
   (Playwright's bundled ffmpeg is found automatically via `PLAYWRIGHT_BROWSERS_PATH`,
   default `/opt/pw-browsers`).

5. **Render.**
   ```bash
   node scripts/record.mjs --in src/<name>.html --out dist/<name>.webm --fps 30
   ```
   The script seeks the page frame-by-frame, screenshots each frame, and streams
   them into ffmpeg via its `image2pipe`/`mjpeg` path (the one route Playwright's
   stripped-down ffmpeg supports — a PNG sequence fails, and wall-clock video
   recording desyncs). Output is exactly `__DURATION` long at the chosen fps.

6. **Verify visually — always.** Extract a frame from the middle of each scene and
   look at it, because the render is silent about layout:
   ```bash
   FF="$PLAYWRIGHT_BROWSERS_PATH/ffmpeg-1011/ffmpeg-linux"
   for t in 2.5 8 16 24 28.5; do "$FF" -y -ss $t -i dist/<name>.webm -frames:v 1 frame_$t.png; done
   ```
   Check scene boundaries land on time, text doesn't overflow, and colors read.
   Fix the page and re-render until each beat is clean.

7. **Deliver** the `.webm` to the user (and commit the page + script so the video
   is reproducible).

## Environment notes

- Playwright + a Chromium build + a bundled ffmpeg are required. In Claude Code
  web sessions these are pre-installed (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`);
  do not run `playwright install`.
- That bundled ffmpeg carries only the `mjpeg` decoder and `libvpx` (VP8) encoder,
  so the deliverable format is `.webm`. If the user needs `.mp4`/H.264 and a full
  ffmpeg is available, transcode as a final step; otherwise `.webm` plays in every
  modern browser and most players.
- Render cost is roughly one screenshot per frame (~30–50s for a 30s clip at 30fps).
  Raise `--fps 60` for extra smoothness at ~2× the frames.

## Files

- `assets/template.html` — a minimal 3-scene, seek-driven starting point.
- `scripts/record.mjs` — the deterministic frame-by-frame renderer (`--in/--out/--fps/--width/--height`).
- `references/timeline.md` — the timeline model, helpers, and recipes (footage, charts). Read for anything beyond the template.
