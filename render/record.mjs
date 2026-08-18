// Deterministic renderer for src/openbb.html.
//
// Headless Chromium throttles wall-clock animation, so instead of recording in
// real time we SEEK the page timeline to an exact timestamp, screenshot each
// frame, and stream the frames straight into Playwright's bundled ffmpeg via
// its image2pipe/mjpeg path. Result: a frame-perfect 30.0s clip at a fixed fps,
// independent of how fast the machine renders.
//
// Usage:  node render/record.mjs [fps]
// Output: dist/openbb-30s.webm  (1280x720)

import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdirSync, existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { once } from 'node:events';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const htmlPath = resolve(root, 'src', 'openbb.html');
const outDir = resolve(root, 'dist');

const W = 1280, H = 720;
const FPS = Number(process.argv[2]) || 30;

const ffmpeg = resolve(
  process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers',
  'ffmpeg-1011', 'ffmpeg-linux'
);
if (!existsSync(ffmpeg)) { console.error('ffmpeg not found at ' + ffmpeg); process.exit(1); }

mkdirSync(outDir, { recursive: true });
const dest = resolve(outDir, 'openbb-30s.webm');

// ---- ffmpeg: read piped MJPEG frames, encode VP8/webm at a fixed frame rate ----
const enc = spawn(ffmpeg, [
  '-hide_banner', '-loglevel', 'error', '-y',
  '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', 'pipe:0',
  '-c:v', 'libvpx', '-b:v', '2.5M', '-crf', '8',
  '-pix_fmt', 'yuv420p', '-auto-alt-ref', '0',
  dest,
], { stdio: ['pipe', 'inherit', 'inherit'] });

// ---- browser: seek + screenshot each frame ----
const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--hide-scrollbars'] });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
await page.goto('file://' + htmlPath);
await page.waitForFunction('window.__READY__ === true', { timeout: 10000 });

const DURATION_MS = await page.evaluate(() => window.__DURATION || 30000);
const TOTAL = Math.round((DURATION_MS / 1000) * FPS);

console.log(`rendering ${TOTAL} frames @ ${FPS}fps (${(DURATION_MS/1000).toFixed(1)}s)…`);
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
console.log('wrote ' + dest);
