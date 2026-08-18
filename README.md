# OpenBB — 30s Trailer (WIP)

A self-contained, code-driven 30-second trailer rendered to a real video file
using Playwright's headless Chromium + bundled ffmpeg (no external services).

## Layout

- `src/openbb.html` — the animated trailer (a single self-contained HTML file;
  scripted 5-scene, 30-second timeline driven by `requestAnimationFrame`).
- `render/record.mjs` — opens the HTML in headless Chromium, records the
  animation, and trims it to exactly 30.0s at 1280×720.
- `dist/openbb-30s.webm` — the rendered video output.

## Render

```bash
# Playwright is expected at the global node install; the render script imports it.
node render/record.mjs
```

Output: `dist/openbb-30s.webm` (1280×720, 30.0s, VP8/webm).

> **Status:** the current draft is a stylized mockup of the OpenBB open-source
> finance platform. Pending real footage/screenshots of the **OpenBB Trader**
> desktop app to rebrand the trailer around the actual product.
