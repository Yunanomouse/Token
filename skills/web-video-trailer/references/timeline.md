# The seek(t) timeline model

The whole reason this pipeline produces smooth, correctly-timed video is that the
page never relies on wall-clock time. Headless Chromium throttles `requestAnimationFrame`
and CSS `animation`/`transition` when it renders offscreen, so anything driven by
real elapsed time drifts — scenes land late, the total compresses, the outro gets
cut. The fix is to make **every visible thing a pure function of a timestamp** and
let the renderer decide which timestamps to paint.

## The contract the page must satisfy

The renderer (`scripts/record.mjs`) only needs three globals:

| global | meaning |
|--------|---------|
| `window.__READY__` | set to `true` once the timeline is initialised |
| `window.__seek(ms)` | synchronously paint the exact frame for timestamp `ms` |
| `window.__DURATION` | total length in ms (optional; defaults to 30000) |

`record.mjs` walks `i = 0 … DURATION/1000 * fps`, calls `__seek(i/fps*1000)`, screenshots,
and streams the frame to ffmpeg. Because `__seek` is deterministic, the output is
identical on any machine regardless of how fast it renders.

## Rules that keep it deterministic

- **No CSS `animation` or `transition`** on anything that must be timed. Set
  `opacity`/`transform` from JS inside `seek()` instead. (Static decorative CSS —
  gradients, blurs, shadows — is fine; it doesn't move.)
- **No `requestAnimationFrame` for timing.** Any per-frame value (a scrolling
  ticker, a drawing chart) must be computed from the `t` passed to `seek()`, e.g.
  `const offset = ((t/16000) % 1) * width;`.
- **Randomness/`Date.now()` must not affect layout** — seed data once at init so
  every `seek(t)` for the same `t` paints the same pixels.

## The building blocks (in the template)

- `seg(t, start, dur)` → a 0..1 progress value for a tween that begins at `start`
  and lasts `dur` ms. Compose these for staggered entrances.
- Easing: `outCubic` for slides/fades, `outBack` for a slight overshoot "pop".
- `setT(key, opacity, tx, ty, scale)` → writes inline `opacity`/`transform` to the
  element tagged `data-a="key"`.
- Scenes are `[element, start, end]` windows; `sceneOpacity` crossfades them by `XF` ms.

## Adding or editing a scene

1. Add the markup inside a `<section class="scene" id="sN">`, tagging animated
   elements with `data-a="somekey"` and class `anim`.
2. Register the scene window in the `scenes` array.
3. In `seek()`, add a block that drives that scene's elements from `t` using
   `seg()` + `setT()`.
4. Bump `DURATION` if you extended the total length.

## Dropping in real product footage (scene "product screen")

Two good options:

- **Screenshots** — put the image next to the HTML and use
  `<img src="screenshot.png">` inside the `.shot` container. Animate it with a slow
  push-in by driving `scale` from `t` (a "Ken Burns" move) so a still frame feels alive.
- **Screen-recording** — extract frames from the recording and cross-dissolve between
  a few key stills, or drive a sprite of frames by index computed from `t`
  (`const f = Math.floor(seg(t,a,dur) * (frames-1))`). Avoid a `<video>` element:
  its playback is wall-clock and won't stay in sync with `__seek`.

Keep the frame at 1280×720 (or pass `--width/--height` to the renderer to match your
source), and prefer `object-fit: cover` so screenshots fill the panel cleanly.

## Charts and live-data looks

For a dashboard/terminal scene, generate the series once at init and reveal it as a
function of `t` (grow a clip-path or rebuild the path up to `floor(progress*N)` points).
Use one accent hue for a single series; reserve green/up and red/down as status colors
and pair them with an arrow glyph so meaning never rests on color alone. The default
tokens in the template come from the `dataviz` skill's validated palette — run that
skill's `validate_palette.js` if you introduce new categorical colors.
