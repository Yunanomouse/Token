// Food Cost desktop app: a window around ../index.html with the workbook kept in a file on this computer.
const { app, BrowserWindow, ipcMain, Menu, shell, session, dialog } = require("electron");
const fs = require("fs");
const path = require("path");

const DATA_DIR = path.join(app.getPath("documents"), "Food Cost");
const BACKUP_DIR = path.join(DATA_DIR, "backups");
const DATA_FILE = path.join(DATA_DIR, "workbook.json");
const SEED_FILE = path.join(__dirname, "seed.json");
const KEEP_BACKUPS = 60;

function ensureDirs() { fs.mkdirSync(BACKUP_DIR, { recursive: true }); }

// first run: start from the bundled workbook if there is one
function loadWorkbook() {
  ensureDirs();
  if (fs.existsSync(DATA_FILE)) return fs.readFileSync(DATA_FILE, "utf8");
  if (fs.existsSync(SEED_FILE)) { const seed = fs.readFileSync(SEED_FILE, "utf8"); writeAtomic(DATA_FILE, seed); return seed; }
  return "";
}

function writeAtomic(file, text) {
  const tmp = file + ".tmp";
  fs.writeFileSync(tmp, text, "utf8");
  fs.renameSync(tmp, file);
}

// one dated copy per day, oldest pruned
function dailyBackup(text) {
  const day = new Date().toISOString().slice(0, 10);
  const file = path.join(BACKUP_DIR, "workbook-" + day + ".json");
  if (!fs.existsSync(file)) {
    fs.writeFileSync(file, text, "utf8");
    const old = fs.readdirSync(BACKUP_DIR).filter((f) => /^workbook-\d{4}-\d\d-\d\d\.json$/.test(f)).sort();
    old.slice(0, Math.max(0, old.length - KEEP_BACKUPS)).forEach((f) => fs.unlinkSync(path.join(BACKUP_DIR, f)));
  }
}

ipcMain.on("fc-load", (e) => {
  try { e.returnValue = loadWorkbook(); } catch (err) { e.returnValue = ""; dialog.showErrorBox("Food Cost", "Could not read the workbook file:\n" + err.message); }
});
ipcMain.on("fc-save", (e, text) => {
  try { ensureDirs(); writeAtomic(DATA_FILE, text); dailyBackup(text); e.returnValue = true; }
  catch (err) { e.returnValue = false; dialog.showErrorBox("Food Cost", "Could not save the workbook file:\n" + err.message); }
});
ipcMain.on("fc-datadir", (e) => { e.returnValue = DATA_DIR; });

function createWindow() {
  const win = new BrowserWindow({
    width: 1400, height: 900, minWidth: 900, minHeight: 600, title: "Food Cost", backgroundColor: "#f3f3f3",
    icon: path.join(__dirname, "icon.png"),
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false }
  });
  win.loadFile(path.join(__dirname, "app", "index.html"));
  // never leave the app or open web pages
  win.webContents.on("will-navigate", (e) => e.preventDefault());
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
}

const menu = Menu.buildFromTemplate([
  { label: "File", submenu: [
    { label: "Open data folder", click: () => { ensureDirs(); shell.openPath(DATA_DIR); } },
    { label: "Print…", accelerator: "CmdOrCtrl+P", click: (_, w) => w && w.webContents.print() },
    { type: "separator" },
    { role: "quit", label: "Exit" }
  ] },
  { label: "Edit", submenu: [{ role: "undo" }, { role: "redo" }, { type: "separator" }, { role: "cut" }, { role: "copy" }, { role: "paste" }, { role: "selectAll" }] },
  { label: "View", submenu: [{ role: "reload" }, { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }, { type: "separator" }, { role: "togglefullscreen" }] },
  { label: "Help", submenu: [{ label: "About Food Cost", click: () => dialog.showMessageBox({ type: "info", title: "Food Cost", message: "Food Cost " + app.getVersion(), detail: "Runs entirely on this computer. Your workbook is saved in:\n" + DATA_FILE + "\n\nDaily copies are kept in the backups folder next to it." }) }] }
]);

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => { const w = BrowserWindow.getAllWindows()[0]; if (w) { if (w.isMinimized()) w.restore(); w.focus(); } });
  app.whenReady().then(() => {
    // offline by design: only the app's own files may load
    session.defaultSession.webRequest.onBeforeRequest((details, cb) => cb({ cancel: !/^(file|devtools|data|blob):/i.test(details.url) }));
    Menu.setApplicationMenu(menu);
    createWindow();
  });
  app.on("window-all-closed", () => app.quit());
}
