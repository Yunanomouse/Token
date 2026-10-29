// Builds the Windows installer: dist/Food Cost Setup <version>.exe
// Usage: node build-win.js [--seed path/to/backup.json] [--electron-dist path/to/unzipped/electron-win32-x64] [--out dir] [--publisher "Name"]
// --publisher sets the company name and copyright in the file details (default: author in package.json).
// Needs: npm packages electron-builder and resedit, and NSIS (makensis) on the PATH.
// Run `python3 ../build.py` first so ../index.html is current.
const fs = require("fs"), path = require("path");
const builder = require("electron-builder");
const { execFileSync } = require("child_process");

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
const here = __dirname, stage = path.join(here, "stage"), out = path.resolve(opt("--out") || path.join(here, "dist"));

fs.rmSync(stage, { recursive: true, force: true });
fs.mkdirSync(path.join(stage, "app"), { recursive: true });
for (const f of ["main.js", "preload.js", "package.json", "icon.png"]) fs.copyFileSync(path.join(here, f), path.join(stage, f));
fs.copyFileSync(path.join(here, "..", "index.html"), path.join(stage, "app", "index.html"));
for (const f of ["icon.svg"]) fs.copyFileSync(path.join(here, "..", f), path.join(stage, "app", f));
const seed = opt("--seed");
if (seed) { JSON.parse(fs.readFileSync(seed, "utf8")); fs.copyFileSync(seed, path.join(stage, "seed.json")); console.log("bundling starting workbook", seed); }

const pkg = require("./package.json"), publisher = opt("--publisher") || pkg.author;
builder.build({
  targets: builder.Platform.WINDOWS.createTarget(["dir"], builder.Arch.x64),
  projectDir: stage,
  config: {
    appId: "app.foodcost.desktop",
    productName: "Food Cost",
    directories: { output: out, buildResources: here },
    electronVersion: "38.8.6",
    electronDist: opt("--electron-dist") || undefined,
    files: ["**/*"],
    asar: true,
    win: { icon: path.join(here, "icon.ico"), signAndEditExecutable: false },
    // set the program icon and file details without Wine
    afterPack: async (ctx) => {
      const ResEdit = require("resedit"), exe = path.join(ctx.appOutDir, "Food Cost.exe");
      const file = ResEdit.NtExecutable.from(fs.readFileSync(exe), { ignoreCert: true });
      const res = ResEdit.NtExecutableResource.from(file);
      const ico = ResEdit.Data.IconFile.from(fs.readFileSync(path.join(here, "icon.ico")));
      ResEdit.Resource.IconGroupEntry.replaceIconsForResource(res.entries, 1, 1033, ico.icons.map((i) => i.data));
      const vi = ResEdit.Resource.VersionInfo.fromEntries(res.entries)[0];
      vi.setStringValues({ lang: 1033, codepage: 1200 }, { ProductName: "Food Cost", FileDescription: "Food Cost", CompanyName: publisher, LegalCopyright: "© 2026 " + publisher, OriginalFilename: "Food Cost.exe", InternalName: "Food Cost" });
      const [a, b, c] = pkg.version.split(".").map(Number);
      vi.setFileVersion(a, b, c, 0, 1033); vi.setProductVersion(a, b, c, 0, 1033);
      vi.outputToResourceEntries(res.entries);
      res.outputResource(file);
      fs.writeFileSync(exe, Buffer.from(file.generate()));
      console.log("icon and version info set on", exe);
    }
  }
}).then(() => {
  // installer made with NSIS directly (per-user install, desktop and Start menu shortcuts)
  const setup = path.join(out, "Food Cost Setup " + pkg.version + ".exe");
  execFileSync("makensis", ["-V2", "-DAPPDIR=" + path.join(out, "win-unpacked"), "-DOUTFILE=" + setup, "-DVERSION=" + pkg.version, "-DPUBLISHER=" + publisher, path.join(here, "installer.nsi")], { stdio: "inherit", cwd: here });
  console.log("built:\n" + setup);
}).catch((e) => { console.error(e); process.exit(1); });
