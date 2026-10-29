# Restaurant

Menu and recipe costing software for restaurants. It is a single web page that runs entirely in your browser: no account, no server, no internet connection needed after it's on your device. Your data never leaves the computer or phone you use it on.

## What it does

| Tab | What you do there |
|---|---|
| **Menu costing** | Build each dish from ingredients and prep recipes. See plate cost, food cost %, profit per sale and the price that hits your target. |
| **Prep recipes** | Sauces, doughs, seasonings, dressings. Each batch gets its cost per kg/L, per cup/tbsp/oz, cost per portion and, if you sell it, a food cost %. Prep costs flow into every dish that uses them. |
| **Ingredients** | Everything you buy, entered the way the invoice reads (item code, unit CS/EA/BG…, pack size like `6X160 G`, unit price) plus usable % for trim and cooking loss. |
| **Order planner** | Pick a dish and a guest count; get what to buy before trim, in packs, with cost. |

Every number recalculates the moment you change a price or an amount. Recipe cards print from any dish or prep recipe.

## Running it

**On one computer (simplest):** double-click `index.html`. It opens in your browser and saves as you work.

**As an installable app (phone, tablet, desktop):** put this folder on any static web host (GitHub Pages, Netlify, Cloudflare Pages, your own site). Open the address once, then use the browser's *Install app* / *Add to Home Screen*. After that it opens like a normal app and works offline.

> Data is stored per browser and per device. Chrome and Safari on the same computer do not share it, and neither does your phone. Use **File & settings → Export backup** and **Load a backup** to move a workbook between them.

## Windows desktop app

`desktop/` wraps the same page in a Windows program (Electron) that never touches the internet:

- The workbook is a real file, `Documents\Restaurant\workbook.json`, written on every change; a dated copy goes to `Documents\Restaurant\backups` once a day (60 kept).
- All network requests are blocked; only the app's own files load.
- The installer is per-user (no admin rights), adds desktop and Start menu shortcuts, and uninstalling leaves the workbook alone.

Build the installer (on Linux or Windows, with Node, NSIS `makensis`, and the npm packages `electron-builder` and `resedit`):

```bash
python3 build.py                       # refresh index.html
cd desktop
node make-icons.js                     # only if icon.svg changed (needs Playwright)
node build-win.js --seed my-backup.json  # optional: starting workbook for first run
# -> dist/Restaurant Setup <version>.exe
```

## Backups

Open **File & settings**:

- **Export backup**: downloads a `.json` file with every ingredient, dish, prep recipe and setting. Keep copies somewhere safe. The status bar reminds you when the last backup is more than 7 days old.
- **Load a backup**: replaces the workbook with a backup file.
- **Menu costs (CSV)** / **Ingredients (CSV)**: open in Excel or Google Sheets, or hand to your accountant.
- **Settings**: business name (title bar and recipe cards), target food cost %, and your menu sections.

Clearing the browser's site data erases the workbook, so back up first.

## Editing the code

The app is assembled from `src/`:

```
src/head.html        page head and styles
src/body.html        layout, tabs and dialogs
src/localdb.js.html  on-device storage (localStorage), backup import/export
src/app.js.html      costing math and the interface
```

After changing anything in `src/`, rebuild `index.html`:

```bash
python3 build.py
```

If you host it as an installable app, also bump `VERSION` in `sw.js` so devices pick up the new copy.

## Selling or sharing a copy

What a buyer gets:

- `Restaurant Setup <version>.exe`: built **without** `--seed`, so it starts with an empty workbook. Pass `--publisher "Your name"` to put your name in the program's file details and the installer's copyright line.
- `LICENSE.txt`: the end-user licence.
- `sample/sample-workbook.json`: a fictional restaurant ("Maple Street Kitchen") buyers can load with **Load a backup** to try the app.
- A quick-start guide.

For the browser version, distribute `index.html`, `manifest.webmanifest`, `sw.js`, `icon.svg`, `icon-192.png` and `icon-512.png`.

Never include your own backup `.json` in a copy you sell or share, because it holds your supplier prices and recipes. `legal/Assignment-Template.txt` is for transferring the whole program to a new owner.
