// Render src/openbb.html to a real video file using Playwright's built-in
// video recording (Chromium + bundled ffmpeg, both already installed).
//
// Usage: node render/record.mjs
// Output: dist/openbb-30s.webm  (1280x720, ~30s)

import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { readdirSync, renameSync, mkdirSync, rmSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const htmlPath = resolve(root, 'src', 'openbb.html');
const outDir = resolve(root, 'dist');
const tmpDir = resolve(root, 'dist', '_rec');

const W = 1280, H = 720;
const DURATION_MS = 30000;
const SETTLE_MS = 700; // record a touch past the end so the outro fully lands

mkdirSync(outDir, { recursive: true });
rmSync(tmpDir, { recursive: true, force: true });
mkdirSync(tmpDir, { recursive: true });

const browser = await chromium.launch({
  args: ['--force-color-profile=srgb', '--disable-lcd-text', '--hide-scrollbars'],
});

const context = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 1,
  recordVideo: { dir: tmpDir, size: { width: W, height: H } },
});

// The video starts recording when the first page loads in the context.
const ctxStart = Date.now();
const page = await context.newPage();
await page.goto('file://' + htmlPath);

// Wait until the animation controller has booted, then restart its clock so
// t=0 lines up with the point we will trim from.
await page.waitForFunction('window.__READY__ === true', { timeout: 10000 });
await page.evaluate('window.__resetClock()');
const leadInSec = (Date.now() - ctxStart) / 1000;

console.log(`recording… (lead-in ${leadInSec.toFixed(2)}s)`);
await page.waitForTimeout(DURATION_MS + SETTLE_MS);

// Close context to flush the video file to disk.
await context.close();
await browser.close();

const files = readdirSync(tmpDir).filter((f) => f.endsWith('.webm'));
if (!files.length) {
  console.error('No video produced.');
  process.exit(1);
}
const raw = resolve(tmpDir, files[0]);
const dest = resolve(outDir, 'openbb-30s.webm');

// Trim the lead-in and clamp to exactly 30.0s using Playwright's bundled ffmpeg.
const ffmpeg = resolve(
  process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers',
  'ffmpeg-1011',
  'ffmpeg-linux'
);
if (existsSync(ffmpeg)) {
  rmSync(dest, { force: true });
  execFileSync(
    ffmpeg,
    [
      '-hide_banner', '-loglevel', 'error', '-y',
      '-ss', leadInSec.toFixed(3),
      '-i', raw,
      '-t', '30',
      '-c:v', 'libvpx', '-b:v', '2M', '-crf', '10',
      '-an', dest,
    ],
    { stdio: 'inherit' }
  );
  rmSync(tmpDir, { recursive: true, force: true });
} else {
  renameSync(raw, dest);
  rmSync(tmpDir, { recursive: true, force: true });
}
console.log('wrote ' + dest);
