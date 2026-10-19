// Renders ../icon.svg to icon.png (512) and icon.ico (16-256) using a headless Chromium (Playwright).
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
(async () => {
  const svg = fs.readFileSync(path.join(__dirname, "..", "icon.svg"), "utf8");
  const exe = process.env.CHROMIUM_PATH;
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const sizes = [16, 24, 32, 48, 64, 128, 256], pngs = {};
  for (const s of sizes.concat([512])) {
    const p = await b.newPage({ viewport: { width: s, height: s } });
    await p.setContent("<style>html,body{margin:0;background:transparent}</style>" + svg.replace("<svg ", `<svg width="${s}" height="${s}" `));
    pngs[s] = await p.screenshot({ omitBackground: true });
  }
  await b.close();
  fs.writeFileSync(path.join(__dirname, "icon.png"), pngs[512]);
  // ICO container holding PNG images
  const head = Buffer.alloc(6); head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(sizes.length, 4);
  let offset = 6 + 16 * sizes.length; const dirs = [], datas = [];
  for (const s of sizes) {
    const d = Buffer.alloc(16), png = pngs[s];
    d.writeUInt8(s >= 256 ? 0 : s, 0); d.writeUInt8(s >= 256 ? 0 : s, 1); d.writeUInt16LE(1, 4); d.writeUInt16LE(32, 6);
    d.writeUInt32LE(png.length, 8); d.writeUInt32LE(offset, 12); offset += png.length; dirs.push(d); datas.push(png);
  }
  fs.writeFileSync(path.join(__dirname, "icon.ico"), Buffer.concat([head].concat(dirs, datas)));
  console.log("icons written");
})();
