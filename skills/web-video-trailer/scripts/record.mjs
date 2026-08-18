// Deterministic web-to-video renderer.
//
// Renders a self-contained HTML "timeline page" to a real video file using
// Playwright's headless Chromium + its bundled ffmpeg — no system ffmpeg, no
// external services. Instead of recording in real time (headless Chromium
// throttles wall-clock animation and desyncs), it SEEKS the page timeline to an
// exact timestamp, screenshots each frame, and streams the frames straight into
// ffmpeg over its image2pipe/mjpeg path. Output is frame-perfect at a fixed fps.
//
// The HTML page must expose two globals (see assets/template.html):
//   window.__READY__   === true once the timeline is initialised
//   window.__seek(ms)          paints the exact frame for timestamp `ms`
//   window.__DURATION  (opt)   total length in ms (default 30000)
//
// Usage:
//   node record.mjs --in page.html --out out.webm [--fps 30] [--width 1280] [--height 720]
//
// Requires Playwright resolvable from Node (e.g. a global install symlinked to
// ./node_modules, or run from a project that has it).

import { chromium } from 'playwright';
import { resolve, isAbsolute } from 'node:path';
import { mkdirSync, existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { once } from 'node:events';

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : def;
}
const abs = (p) => (isAbsolute(p) ? p : resolve(process.cwd(), p));

const inPath = abs(arg('in', 'src/openbb.html'));
const outPath = abs(arg('out', 'dist/trailer.webm'));
const FPS = Number(arg('fps', '30'));
const W = Number(arg('width', '1280'));
const H = Number(arg('height', '720'));

if (!existsSync(inPath)) { console.error('input not found: ' + inPath); process.exit(1); }
mkdirSync(resolve(outPath, '..'), { recursive: true });

// Locate Playwright's bundled ffmpeg (ships with the browser install).
const pwRoot = process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers';
const ffmpeg = resolve(pwRoot, 'ffmpeg-1011', 'ffmpeg-linux');
if (!existsSync(ffmpeg)) {
  console.error('bundled ffmpeg not found at ' + ffmpeg + ' — set PLAYWRIGHT_BROWSERS_PATH');
  process.exit(1);
}

const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--hide-scrollbars'] });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
await page.goto('file://' + inPath);
await page.waitForFunction('window.__READY__ === true', { timeout: 15000 });
const DURATION = await page.evaluate('window.__DURATION || 30000');
const TOTAL = Math.round((DURATION / 1000) * FPS);

// ffmpeg: read piped MJPEG frames -> encode VP8/webm at a fixed frame rate.
// (Playwright's ffmpeg only carries the mjpeg decoder + libvpx encoder, so this
//  image2pipe/mjpeg route is the one that works — a PNG sequence would fail.)
const enc = spawn(ffmpeg, [
  '-hide_banner', '-loglevel', 'error', '-y',
  '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', 'pipe:0',
  '-c:v', 'libvpx', '-b:v', '2.5M', '-crf', '8',
  '-pix_fmt', 'yuv420p', '-auto-alt-ref', '0',
  outPath,
], { stdio: ['pipe', 'inherit', 'inherit'] });

console.log(`rendering ${TOTAL} frames @ ${FPS}fps (${(DURATION / 1000).toFixed(1)}s, ${W}x${H})…`);
const t0 = Date.now();
for (let i = 0; i < TOTAL; i++) {
  await page.evaluate((ms) => window.__seek(ms), (i / FPS) * 1000);
  const buf = await page.screenshot({ type: 'jpeg', quality: 100, clip: { x: 0, y: 0, width: W, height: H } });
  if (!enc.stdin.write(buf)) await once(enc.stdin, 'drain');
  if (i % 60 === 0) process.stdout.write(`  ${i}/${TOTAL}\r`);
}
enc.stdin.end();
console.log(`\ncaptured ${TOTAL} frames in ${((Date.now() - t0) / 1000).toFixed(1)}s`);

await browser.close();
const [code] = await once(enc, 'close');
if (code !== 0) { console.error('ffmpeg exited ' + code); process.exit(1); }
console.log('wrote ' + outPath);
