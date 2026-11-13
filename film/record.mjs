// Film the real Venture Trader dashboard, frame by frame.
//
// The app must already be running (its own dashboard_server.py) — see film/README.md.
// This script opens the stage page at the app's origin, loads the real dashboard into
// it, and for every video frame: runs any scripted input that is due (real mouse
// clicks, real key presses), advances the page's clock by exactly one frame, lets the
// stage move camera/cursor/captions, moves the real mouse to match, and screenshots.
// Because time only moves when we say so, a slow network call or a slow screenshot
// never shows up in the film.
//
//   node film/record.mjs --out dist/film.webm                 full render
//   node film/record.mjs --shots 12,31.5,48 --shotdir /tmp/x  stills only (renders up to the last one)
//
// Flags: --url http://127.0.0.1:8090  --timeline film/timeline.js  --fps 30  --until <seconds>

import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, extname } from 'node:path';
import { readFileSync, mkdirSync, existsSync } from 'node:fs';
import { spawn, execSync } from 'node:child_process';
import { once } from 'node:events';

const here = dirname(fileURLToPath(import.meta.url)), root = resolve(here, '..');
const argv = process.argv.slice(2);
const flag = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };
const APP = (flag('url', process.env.VT_URL || 'http://127.0.0.1:8090')).replace(/\/$/, '');
const TIMELINE = resolve(root, flag('timeline', 'film/timeline.js'));
const FPS = Number(flag('fps', 30)), DT = 1000 / FPS;
const OUT = flag('out', null);
const SHOTS = (flag('shots', '') || '').split(',').filter(Boolean).map(Number);
const SHOTDIR = resolve(flag('shotdir', 'dist/_frames'));
const W = 1280, H = 720;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log(...a);

const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--hide-scrollbars'] });
const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, serviceWorkers: 'block' });
const page = await context.newPage();
const errors = [];
page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 300)));
page.on('response', r => { if (r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url().slice(0, 160)}`); });

// ---- routing -------------------------------------------------------------
// 1. the stage's own files, served at the app's origin so the stage may look inside the frame
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8' };
await page.route(u => u.origin === APP && u.pathname.startsWith('/__film/'), route => {
  const name = new URL(route.request().url()).pathname.slice('/__film/'.length);
  const file = name === 'timeline.js' ? TIMELINE : resolve(here, name);
  route.fulfill({ status: 200, contentType: TYPES[extname(file)] || 'text/plain', body: readFileSync(file) });
});
// 2. the dashboard document: the app forbids being framed (a sensible default for a private
//    dashboard). Inside this recorder's own browser, and only here, those two headers are
//    dropped so the page can sit on the stage. The app itself is not modified.
await page.route(u => u.origin === APP && ['/', '/index.html', '/dashboard.html'].includes(u.pathname), async route => {
  const resp = await route.fetch();
  const headers = { ...resp.headers() };
  delete headers['x-frame-options']; delete headers['content-security-policy'];
  await route.fulfill({ response: resp, headers });
});
// 3. the app's data calls (ticker lookup, suggestions): fetched for real, but handed to the page
//    a fixed film-time after the request, so loading always takes the same time on screen
const LATENCY = { '/lookup': 650, '/details': 200, '/intraday': 300, '/suggest': 160, '/search': 300 };
let filmNow = 0; const holds = [];
await page.route(u => u.origin === APP && u.pathname in LATENCY, async route => {
  const path = new URL(route.request().url()).pathname;
  const hold = { at: filmNow + LATENCY[path], path, done: false };
  hold.ready = route.fetch().then(r => { hold.resp = r; }).catch(e => { hold.err = e; });
  hold.route = route; holds.push(hold);
});
async function releaseHolds() {
  for (const h of holds) if (!h.done && h.at <= filmNow) {
    await h.ready; h.done = true;
    if (h.err) await h.route.abort().catch(() => {}); else await h.route.fulfill({ response: h.resp }).catch(() => {});
    await sleep(60);                                   // let the page consume the response
  }
}

// ---- clock ----------------------------------------------------------------
await context.clock.install({ time: new Date() });
await page.goto(APP + '/__film/stage.html', { waitUntil: 'load' });
await page.waitForFunction('window.__READY__ === true', null, { timeout: 15000, polling: 100 }).catch(async () => {
  throw new Error('stage did not start: ' + errors.join(' | '));
});
await context.clock.pauseAt(new Date(Date.now() + 1000));

const DURATION = await page.evaluate(() => window.__DURATION);
const actions = await page.evaluate(() => window.__ACTIONS);
const until = Number(flag('until', SHOTS.length ? Math.max(...SHOTS) + 0.05 : DURATION / 1000));
const TOTAL = Math.round(until * FPS);
const app = () => page.frames().find(f => f !== page.mainFrame());

let mouse = [W / 2, H / 2, 0, 0];           // screen x,y and the same point in app coordinates
async function poll(fn, what, ms = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await fn().catch(() => false)) return; await sleep(80); }
  throw new Error('timed out waiting for ' + what);
}
async function act(a) {
  switch (a.type) {
    case 'load':                                       // put the real dashboard on the stage
      await page.evaluate(() => window.__loadApp());
      await poll(() => app()?.evaluate(() => typeof showTab === 'function' && document.readyState === 'complete'), 'the dashboard to load');
      break;
    case 'click': {                                    // a real click, after checking what is under the cursor
      await page.mouse.move(mouse[0], mouse[1]);
      if (a.arg) {
        const hit = await app().evaluate(([x, y, sel]) => { const el = document.elementFromPoint(x, y);
          return el && el.closest(sel) ? null : (el ? el.tagName + '#' + el.id + '.' + String(el.className).slice(0, 40) : 'nothing'); }, [mouse[2], mouse[3], a.arg]);
        if (hit) throw new Error(`click at ${(a.t / 1000).toFixed(2)}s expected ${a.arg} but the cursor is over ${hit}`);
      }
      await page.mouse.down(); await page.mouse.up(); break;
    }
    case 'key': await page.keyboard.press(a.arg); break;
    case 'text': await page.keyboard.insertText(a.arg); break;
    case 'app': await app().evaluate(a.arg); break;    // call something in the app page (e.g. its own softRefresh)
    case 'exec': execSync(a.arg, { stdio: 'inherit', cwd: root }); break;
    case 'wait': await poll(() => app().evaluate(a.arg), a.opt || a.arg); break;
    default: throw new Error('unknown action ' + a.type);
  }
}

// ---- output ---------------------------------------------------------------
let enc = null, closed = null;
if (OUT) {
  const ffmpeg = resolve(process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers', 'ffmpeg-1011', 'ffmpeg-linux');
  mkdirSync(dirname(resolve(root, OUT)), { recursive: true });
  enc = spawn(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS),
    '-c:v', 'mjpeg', '-i', 'pipe:0', '-c:v', 'libvpx', '-b:v', '3M', '-crf', '8', '-pix_fmt', 'yuv420p', '-auto-alt-ref', '0',
    resolve(root, OUT)], { stdio: ['pipe', 'inherit', 'inherit'] });
  closed = new Promise(res => { enc.on('close', res); });
}
if (SHOTS.length) mkdirSync(SHOTDIR, { recursive: true });
const shotFrames = new Map(SHOTS.map(s => [Math.round(s * FPS), s]));

log(`filming ${TOTAL} frames @ ${FPS}fps (${(TOTAL / FPS).toFixed(1)}s of ${(DURATION / 1000).toFixed(1)}s)…`);
const t0 = Date.now(); let next = 0;
for (let i = 0; i < TOTAL; i++) {
  filmNow = i * DT;
  while (next < actions.length && actions[next].t <= filmNow) { await act(actions[next]); next++; }
  await releaseHolds();
  await context.clock.runFor(DT);
  const m = await page.evaluate(([t, dt]) => window.__frame(t, dt), [filmNow, DT]);
  if (m) { mouse = m; await page.mouse.move(m[0], m[1]); }
  if (enc || shotFrames.has(i)) {
    const png = shotFrames.has(i);
    const buf = await page.screenshot(png && !enc ? { type: 'png' } : { type: 'jpeg', quality: 100 });
    if (enc && !enc.stdin.write(buf)) await once(enc.stdin, 'drain');
    if (png) { const { writeFileSync } = await import('node:fs'); writeFileSync(resolve(SHOTDIR, `t_${shotFrames.get(i)}.${enc ? 'jpg' : 'png'}`), buf); }
  }
  if (i % 150 === 0) process.stdout.write(`  ${i}/${TOTAL}\n`);
}
if (enc) { enc.stdin.end(); }
await browser.close();
if (enc) { const code = await closed; if (code !== 0) { console.error('ffmpeg exited ' + code); process.exit(1); } }
log(`done in ${((Date.now() - t0) / 1000).toFixed(1)}s` + (OUT ? ` -> ${OUT}` : ''));
if (errors.length) { console.error('PAGE ERRORS:\n' + [...new Set(errors)].slice(0, 12).join('\n')); }
