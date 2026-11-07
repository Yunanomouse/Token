#!/usr/bin/env node
/*
 * Menu Designer: render built menus to PDF + PNG and check that every page fits.
 *
 * Copyright (c) 2026 Matthew Neil Louis Marinier, operating as Brigade Kitchen
 * Software. All rights reserved. See LICENSE.txt.
 *
 * Usage:
 *   NODE_PATH=/opt/node22/lib/node_modules node render.js [folder-or-html ...]
 *
 * With no arguments every *-print.html / *-phone.html under out/ is rendered.
 * For a print file it writes <slug>-<theme>.pdf and <slug>-<theme>-page<N>.png;
 * for a phone file it writes <slug>-<theme>-phone.png (first screen, 390 px wide),
 * -phone-scrolled.png (mid-menu, sticky tabs) and -phone-full.png (whole page).
 * Exits with code 1 if any page overflows, so you know to move a section.
 *
 * Environment:
 *   CHROMIUM_PATH  browser executable (default /opt/pw-browsers/chromium if present)
 */
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

function collect(args) {
  const roots = args.length ? args : [path.join(__dirname, 'out')];
  const files = [];
  const walk = (p) => {
    const st = fs.statSync(p);
    if (st.isDirectory()) fs.readdirSync(p).sort().forEach((f) => walk(path.join(p, f)));
    else if (/-(print|phone)\.html$/.test(p)) files.push(path.resolve(p));
  };
  roots.forEach(walk);
  return files;
}

// Runs inside the page: returns a list of problems for every .page.
function checkPrintPages() {
  const problems = [];
  const label = (el) => {
    const sec = el.closest('.sec');
    const t = sec && sec.querySelector('.sec-title');
    return t ? `"${t.textContent.trim()}"` : el.className;
  };
  document.querySelectorAll('.page').forEach((page) => {
    const n = page.dataset.page;
    const body = page.querySelector('.page-body');
    const foot = page.querySelector('.foot');
    const pr = page.getBoundingClientRect();
    const br = body.getBoundingClientRect();
    const fr = foot.getBoundingClientRect();
    if (page.scrollHeight > page.clientHeight + 1) problems.push(`page ${n}: page content is taller than the sheet`);
    if (body.scrollHeight > body.clientHeight + 1) problems.push(`page ${n}: content is ${body.scrollHeight - body.clientHeight}px too tall for the columns`);
    if (body.scrollWidth > body.clientWidth + 1) problems.push(`page ${n}: content spills into a third column (too much for two columns)`);
    if (fr.bottom > pr.bottom + 1) problems.push(`page ${n}: footer runs off the bottom of the sheet`);
    const seen = new Set();
    body.querySelectorAll('.sec-title, .item, .choice, .sec-note, .sec-intro').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.height === 0) return;
      const bad = r.bottom > fr.top + 1 || r.bottom > br.bottom + 1 || r.right > br.right + 1 || r.left < br.left - 1;
      const key = label(el);
      if (bad && !seen.has(key)) { seen.add(key); problems.push(`page ${n}: section ${key} overflows (below the footer or outside the columns)`); }
    });
    // Orphaned heading check: a heading must share a column with its first entry.
    body.querySelectorAll('.sec').forEach((sec) => {
      const t = sec.querySelector('.sec-title');
      const first = sec.querySelector('.item, .choice');
      if (t && first && Math.abs(t.getBoundingClientRect().left - first.getBoundingClientRect().left) > 2)
        problems.push(`page ${n}: heading "${t.textContent.trim()}" is separated from its first entry`);
    });
  });
  return problems;
}

(async () => {
  const files = collect(process.argv.slice(2));
  if (!files.length) {
    console.error('render.js: no *-print.html or *-phone.html files found. Run python3 build.py first.');
    process.exit(2);
  }
  const exe = process.env.CHROMIUM_PATH || (fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined);
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  let failed = false;
  try {
    for (const file of files) {
      const dir = path.dirname(file);
      const base = path.basename(file).replace(/-(print|phone)\.html$/, '');
      const kind = /-print\.html$/.test(file) ? 'print' : 'phone';
      if (kind === 'print') {
        const page = await browser.newPage({ viewport: { width: 816, height: 1056 }, deviceScaleFactor: 2 });
        await page.emulateMedia({ media: 'print' });
        await page.goto(pathToFileURL(file).href);
        await page.evaluate(() => document.fonts.ready);
        await page.waitForSelector('html[data-fitted]', { timeout: 15000 }).catch(() => {});
        const theme = await page.$eval('meta[name="menu-theme"]', (m) => m.content).catch(() => 'menu');
        const problems = await page.evaluate(checkPrintPages);
        const pages = await page.$$('.page');
        for (let i = 0; i < pages.length; i++) {
          const png = path.join(dir, `${base}-${theme}-page${i + 1}.png`);
          await pages[i].screenshot({ path: png });
          console.log(`  png  ${path.relative(process.cwd(), png)}`);
        }
        const pdf = path.join(dir, `${base}-${theme}.pdf`);
        await page.pdf({ path: pdf, format: 'Letter', printBackground: true, preferCSSPageSize: true,
          margin: { top: 0, right: 0, bottom: 0, left: 0 } });
        console.log(`  pdf  ${path.relative(process.cwd(), pdf)}`);
        if (problems.length) {
          failed = true;
          console.log(`FIT  ${theme}: ${problems.length} problem(s)`);
          problems.forEach((p) => console.log(`     - ${p}`));
          console.log('     Fix: move a section to another page in "pages", add or remove "column_break_before", or shorten text.');
        } else {
          console.log(`FIT  ${theme}: OK, all ${pages.length} page(s) fit`);
        }
        await page.close();
      } else {
        const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
        await page.goto(pathToFileURL(file).href);
        await page.evaluate(() => document.fonts.ready);
        const theme = await page.$eval('meta[name="menu-theme"]', (m) => m.content).catch(() => 'menu');
        const sw = await page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth));
        const png = path.join(dir, `${base}-${theme}-phone.png`);
        await page.screenshot({ path: png });
        const full = path.join(dir, `${base}-${theme}-phone-full.png`);
        await page.screenshot({ path: full, fullPage: true });
        // Also show the sticky tabs in use, scrolled to the middle of the menu.
        await page.evaluate(() => { const s = document.querySelectorAll('.sec'); s[Math.floor(s.length / 2)].scrollIntoView({ behavior: 'instant' }); });
        await page.waitForTimeout(400);
        const mid = path.join(dir, `${base}-${theme}-phone-scrolled.png`);
        await page.screenshot({ path: mid });
        [png, full, mid].forEach((p) => console.log(`  png  ${path.relative(process.cwd(), p)}`));
        if (sw > 390) { failed = true; console.log(`FIT  ${theme} phone: page is ${sw}px wide at 390px (horizontal scroll)`); }
        else console.log(`FIT  ${theme} phone: OK, no horizontal scroll at 390px`);
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }
  process.exit(failed ? 1 : 0);
})().catch((err) => { console.error(err); process.exit(2); });
