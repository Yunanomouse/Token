#!/usr/bin/env python3
"""Build Paper Trading as a program of its own for the computer this runs on.

    python -m pip install "pyinstaller>=6.10,<7" "pywebview>=5,<7" pillow tzdata
    python paper_trading/packaging/build.py

Writes dist/paper-trading-<os>-<arch>/ and a .zip of it, at the top of the
repository (both folders are git-ignored).  The folder holds
"Paper Trading.exe" (Python, the page and the window included, nothing to
install), README.md and LICENSE.  The program keeps the account in the
user's own folder (%APPDATA%\\Paper Trading on Windows; see window.py), not
in this folder, so replacing or uninstalling the program leaves it alone.

On Windows, paper_trading/packaging/installer.iss turns the folder into
"Paper Trading Setup.exe".  PyInstaller does not cross-compile: build on
Windows for Windows.  .github/workflows/paper-trading-app.yml does that on
GitHub, tests the result and publishes it.

Pillow (for the icon) is needed only here, not by the built program.
Neither the quantum package nor numpy is used, and the build fails if
either ends up in the program.
"""
from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent      # paper_trading/
ROOT = APP.parent                                 # the repository
NAME = "Paper Trading"
WINDOWS = sys.platform.startswith("win")


def target() -> str:
    osname = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = platform.machine().lower().replace("amd64", "x64").replace("x86_64", "x64").replace("aarch64", "arm64")
    return f"paper-trading-{osname}-{arch}"


def make_icon(path: Path) -> Path:
    """A rounded green square with a white rising line, drawn separately at
    each size (16, 24, 32, 48, 64, 128, 256 px) so the small ones stay crisp."""
    from PIL import Image, ImageDraw

    def draw(size: int) -> Image.Image:
        s = 8  # draw large, then shrink: smooth edges
        big = size * s
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        pad = max(1, round(size * 0.03)) * s
        d.rounded_rectangle([pad, pad, big - pad - 1, big - pad - 1], radius=round(big * 0.22),
                            fill=(22, 128, 84, 255))
        # The line: thicker relative to the icon when it is small, fewer turns.
        if size <= 24:
            pts = [(0.20, 0.74), (0.45, 0.50), (0.60, 0.62), (0.82, 0.28)]
            width = 0.15
        else:
            pts = [(0.17, 0.74), (0.36, 0.52), (0.50, 0.63), (0.66, 0.40), (0.83, 0.25)]
            width = 0.09 if size >= 64 else 0.11
        xy = [(round(x * big), round(y * big)) for x, y in pts]
        w = max(s, round(width * big))
        d.line(xy, fill=(255, 255, 255, 255), width=w, joint="curve")
        r = w // 2
        for x, y in (xy[0], xy[-1]):  # round ends
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))
        return img.resize((size, size), Image.LANCZOS)

    sizes = [256, 128, 64, 48, 32, 24, 16]
    images = [draw(n) for n in sizes]
    path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(path, format="ICO", sizes=[(n, n) for n in sizes], append_images=images[1:])
    images[0].save(path.with_suffix(".png"))  # for looking at it
    return path


def check_bundle(out: Path) -> None:
    """The page must sit where the frozen paper_app looks for it, and nothing
    from the trading bots (quantum, numpy) may have been pulled in."""
    internal = out / "_internal"
    base = internal if internal.is_dir() else out  # PyInstaller 6 puts everything in _internal/
    if not (base / "paper_page.html").is_file():
        raise SystemExit(f"paper_page.html is not in {base}: the program would show 'missing'")
    found = [p for p in base.rglob("*") if p.name.split(".")[0].lower() in ("numpy", "quantum")]
    if found:
        raise SystemExit(f"numpy/quantum ended up in the program: {found[:5]}")
    if WINDOWS:
        for need in ("tzdata", "webview"):
            if not (base / need).is_dir():
                raise SystemExit(f"{need} data is missing from {base}")


def main() -> int:
    missing = [m for m in ("PyInstaller", "PIL", "webview") if importlib.util.find_spec(m) is None]
    if WINDOWS and importlib.util.find_spec("tzdata") is None:
        missing.append("tzdata")  # Windows has no time-zone database of its own
    if missing:
        print(f"missing: {', '.join(missing)}.  Install with:\n  python -m pip install "
              '"pyinstaller>=6.10,<7" "pywebview>=5,<7" pillow tzdata')
        return 1

    work = ROOT / "build" / "paper_trading"
    dist = ROOT / "dist"
    out = dist / target()
    tmp = dist / (target() + ".tmp")
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    icon = make_icon(work / "paper_trading.ico")
    sep = ";" if WINDOWS else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller", str(APP / "window.py"),
        "--name", NAME, "--onedir", "--windowed", "--noconfirm", "--clean",
        "--paths", str(APP),
        # Beside the frozen paper_app module (sys._MEIPASS), where PAGE_FILE points.
        "--add-data", f"{APP / 'paper_page.html'}{sep}.",
        "--exclude-module", "numpy", "--exclude-module", "quantum",
        "--distpath", str(tmp), "--workpath", str(work / "pyinstaller"), "--specpath", str(work),
    ]
    if sys.platform in ("win32", "darwin"):  # PyInstaller ignores --icon elsewhere
        cmd += ["--icon", str(icon)]
    if importlib.util.find_spec("tzdata") is not None:
        cmd += ["--collect-data", "tzdata", "--hidden-import", "tzdata"]
    subprocess.run(cmd, check=True, cwd=ROOT)
    produced = tmp / NAME
    if sys.platform == "darwin" and not produced.exists():
        produced = tmp / f"{NAME}.app"
    shutil.move(str(produced), str(out))
    shutil.rmtree(tmp)
    check_bundle(out)
    shutil.copy2(APP / "README.md", out / "README.md")
    shutil.copy2(APP / "LICENSE", out / "LICENSE")
    archive = shutil.make_archive(str(dist / target()), "zip", root_dir=dist, base_dir=target())
    print(f"built {out}\nzipped {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
