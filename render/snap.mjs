// Preview single frames without a full render.
// Usage: node render/snap.mjs --in src/venture-2min.html --out <dir> 3.5 12 45.2 ...   (seconds)
import { chromium } from 'playwright';
import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';

const argv = process.argv.slice(2);
const flag = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv.splice(i, 2)[1] : d; };
const page_ = resolve(flag('in', 'src/openbb.html'));
const out = resolve(flag('out', 'dist/_frames'));
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--hide-scrollbars'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
const errs = []; page.on('pageerror', e => errs.push(String(e))); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await page.goto('file://' + page_);
await page.waitForFunction('window.__READY__ === true', { timeout: 10000 }).catch(() => {});
if (errs.length) { console.error('PAGE ERRORS:\n' + errs.join('\n')); }
for (const s of argv) {
  await page.evaluate((ms) => window.__seek(ms), Number(s) * 1000);
  await page.screenshot({ path: resolve(out, `t_${s}.png`) });
}
// a full sweep catches errors that only occur at particular timestamps
const dur = await page.evaluate(() => window.__DURATION);
await page.evaluate((d) => { for (let t = 0; t <= d; t += 250) window.__seek(t); }, dur);
if (errs.length) { console.error('ERRORS DURING SWEEP:\n' + [...new Set(errs)].join('\n')); process.exitCode = 1; }
else console.log(`ok: ${argv.length} frames, sweep of ${(dur / 1000).toFixed(1)}s clean`);
await browser.close();
