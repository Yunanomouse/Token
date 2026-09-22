"""Install and maintain a self-contained local OpenBB, independent of anything else.

OpenBB is open-source software that runs entirely on your own machine — this
script just gives it a private home so nothing else can break it, and keeps it
current without you having to remember to.

    python3 scripts/openbb_local.py install     # one-time setup
    python3 scripts/openbb_local.py status      # installed vs. latest on PyPI
    python3 scripts/openbb_local.py update      # upgrade, verify, roll back if broken
    python3 scripts/openbb_local.py run examples/openbb_quickstart.py
    python3 scripts/openbb_local.py schedule    # how to run `update` automatically

Everything lives in one directory (default ~/.openbb-local), which holds its own
Python virtual environment. Nothing is installed into your system Python, so an
OS-managed package can never block the install and an OpenBB upgrade can never
disturb anything else. Delete that one directory to remove it completely.

`update` is safe to run unattended: it upgrades, imports OpenBB to prove the new
version works, and reinstalls the previous version if it does not.

Standard library only — this script itself has no dependencies.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import venv
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = "openbb"
DEFAULT_HOME = Path.home() / ".openbb-local"
PYPI_JSON = "https://pypi.org/pypi/{package}/json"
STATE_FILE = "state.json"
LOG_FILE = "update.log"

# Long enough for a slow mirror, short enough that a scheduled run cannot hang
# forever on a dead connection.
NETWORK_TIMEOUT = 30
INSTALL_TIMEOUT = 1800


class LocalOpenBBError(Exception):
    """Anything that should stop the command with a readable message."""


def venv_python(home: Path) -> Path:
    """The interpreter inside the managed environment."""
    if os.name == "nt":
        return home / "venv" / "Scripts" / "python.exe"
    return home / "venv" / "bin" / "python"


def read_state(home: Path) -> dict:
    try:
        return json.loads((home / STATE_FILE).read_text())
    except (OSError, ValueError):
        return {}


def write_state(home: Path, **fields: object) -> None:
    state = read_state(home)
    state.update(fields)
    home.mkdir(parents=True, exist_ok=True)
    (home / STATE_FILE).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def log(home: Path, message: str) -> None:
    """Append to the update log so scheduled runs leave a trail."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    try:
        home.mkdir(parents=True, exist_ok=True)
        with (home / LOG_FILE).open("a") as handle:
            handle.write(f"{stamp}  {message}\n")
    except OSError:
        pass  # a log we cannot write is never worth failing an update over


def latest_version(package: str = PACKAGE) -> str:
    """Ask PyPI what the newest release is."""
    url = PYPI_JSON.format(package=package)
    try:
        with urllib.request.urlopen(url, timeout=NETWORK_TIMEOUT) as response:
            return json.load(response)["info"]["version"]
    except urllib.error.HTTPError as exc:
        raise LocalOpenBBError(f"PyPI returned HTTP {exc.code} for {package}") from exc
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        raise LocalOpenBBError(
            f"could not reach PyPI ({exc}). Check your connection; if you are behind "
            "a proxy or firewall it may be blocking pypi.org."
        ) from exc


def installed_version(home: Path, package: str = PACKAGE) -> str | None:
    """The version inside the managed environment, or None if absent."""
    python = venv_python(home)
    if not python.exists():
        return None
    result = subprocess.run(
        [str(python), "-c", f"from importlib.metadata import version; print(version('{package}'))"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def pip_install(home: Path, spec: str, upgrade: bool = False) -> None:
    command = [str(venv_python(home)), "-m", "pip", "install", "--quiet"]
    if upgrade:
        command.append("--upgrade")
    command.append(spec)
    result = subprocess.run(command, capture_output=True, text=True, timeout=INSTALL_TIMEOUT)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-5:]
        raise LocalOpenBBError("pip failed:\n  " + "\n  ".join(tail))


def verify_import(home: Path) -> tuple[bool, str]:
    """Prove the installed OpenBB actually loads before we call an update good.

    The first import builds OpenBB's interface and is slow, so this doubles as
    warming that cache — a scheduled update absorbs the cost instead of you.
    """
    result = subprocess.run(
        [str(venv_python(home)), "-c", "from openbb import obb; obb.equity.price.historical"],
        capture_output=True,
        text=True,
        timeout=INSTALL_TIMEOUT,
    )
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or result.stdout).strip().splitlines()[-1] if (result.stderr or result.stdout).strip() else "import failed"


def ensure_venv(home: Path, recreate: bool = False) -> None:
    target = home / "venv"
    if target.exists() and recreate:
        shutil.rmtree(target)
    if not venv_python(home).exists():
        home.mkdir(parents=True, exist_ok=True)
        print(f"Creating a private Python environment in {target} ...")
        venv.EnvBuilder(with_pip=True, upgrade_deps=True).create(target)


def cmd_install(args: argparse.Namespace) -> int:
    home = args.home
    ensure_venv(home, recreate=args.recreate)

    spec = f"{PACKAGE}=={args.pin}" if args.pin else PACKAGE
    print(f"Installing {spec} (this downloads a few hundred MB the first time) ...")
    pip_install(home, spec, upgrade=not args.pin)

    version = installed_version(home)
    if version is None:
        raise LocalOpenBBError("install finished but OpenBB is not importable")

    print("Verifying the install ...")
    ok, detail = verify_import(home)
    if not ok:
        raise LocalOpenBBError(f"OpenBB {version} installed but failed to import: {detail}")

    write_state(home, version=version, installed_at=datetime.now(timezone.utc).isoformat())
    log(home, f"install -> {version}")

    print(f"\nOpenBB {version} is installed in {home}")
    print(f"Its Python is {venv_python(home)}")
    print("\nNext:")
    print(f"  python3 {Path(__file__).name} run examples/openbb_quickstart.py")
    print(f"  python3 {Path(__file__).name} schedule     # keep it updated automatically")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    home = args.home
    current = installed_version(home)
    if current is None:
        print(f"No local OpenBB found in {home}")
        print(f"Run:  python3 {Path(__file__).name} install")
        return 1

    print(f"Location:  {home}")
    print(f"Installed: {PACKAGE} {current}")

    state = read_state(home)
    if state.get("last_update_check"):
        print(f"Last check: {state['last_update_check']}")

    try:
        newest = latest_version()
    except LocalOpenBBError as exc:
        print(f"Latest:    unknown ({exc})")
        return 0

    if newest == current:
        print(f"Latest:    {newest}  (up to date)")
    else:
        print(f"Latest:    {newest}  (update available)")
        print(f"\nRun:  python3 {Path(__file__).name} update")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    home = args.home
    current = installed_version(home)
    if current is None:
        raise LocalOpenBBError(f"no local OpenBB in {home} — run `install` first")

    newest = latest_version()
    write_state(home, last_update_check=datetime.now(timezone.utc).isoformat())

    if newest == current:
        if not args.quiet:
            print(f"OpenBB {current} is already the latest.")
        log(home, f"check -> already current ({current})")
        return 0

    if args.check_only:
        print(f"Update available: {current} -> {newest}")
        return 0

    print(f"Updating OpenBB {current} -> {newest} ...")
    try:
        pip_install(home, PACKAGE, upgrade=True)
    except LocalOpenBBError as exc:
        log(home, f"update {current} -> {newest} FAILED during install: {exc}")
        raise

    ok, detail = verify_import(home)
    if not ok:
        # A broken upgrade is worse than an old version, so put back what worked.
        print(f"OpenBB {newest} does not import ({detail}); rolling back to {current} ...")
        log(home, f"update {current} -> {newest} FAILED verification: {detail}; rolling back")
        pip_install(home, f"{PACKAGE}=={current}")
        rolled_back, _ = verify_import(home)
        if not rolled_back:
            raise LocalOpenBBError(
                f"OpenBB {newest} failed to import and the rollback to {current} also "
                f"failed. Reinstall from scratch:  python3 {Path(__file__).name} "
                "install --recreate"
            )
        write_state(home, version=current, last_failed_version=newest)
        raise LocalOpenBBError(f"update to {newest} rejected; still on {current}")

    write_state(home, version=newest, updated_at=datetime.now(timezone.utc).isoformat())
    log(home, f"update {current} -> {newest} OK")
    print(f"Updated to OpenBB {newest}.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    home = args.home
    python = venv_python(home)
    if not python.exists():
        raise LocalOpenBBError(f"no local OpenBB in {home} — run `install` first")
    if not args.script:
        raise LocalOpenBBError("give a script to run, e.g. examples/openbb_quickstart.py")
    return subprocess.run([str(python), *args.script]).returncode


def cmd_schedule(args: argparse.Namespace) -> int:
    """Print the exact scheduler entry for this machine.

    Printing rather than installing: a scheduled job is the user's own system
    configuration, and silently editing a crontab or task list is not ours to do.
    """
    home = args.home
    script = Path(__file__).resolve()
    runner = sys.executable or "python3"
    command = f'"{runner}" "{script}" update --home "{home}" --quiet'
    system = platform.system()

    print("To keep OpenBB current on its own, run `update` on a schedule.\n")

    if system == "Windows":
        print("Windows — run this once in an elevated Command Prompt:\n")
        print(f'  schtasks /create /tn "OpenBB self-update" /tr {command} /sc weekly /d SUN /st 03:00')
        print("\nCheck it later with:  schtasks /query /tn \"OpenBB self-update\"")
    elif system == "Darwin":
        plist = home / "com.openbb.selfupdate.plist"
        print(f"macOS — write this to {plist}, then load it:\n")
        print(f"""  <?xml version="1.0" encoding="UTF-8"?>
  <plist version="1.0"><dict>
    <key>Label</key><string>com.openbb.selfupdate</string>
    <key>ProgramArguments</key>
      <array><string>{runner}</string><string>{script}</string>
      <string>update</string><string>--home</string><string>{home}</string>
      <string>--quiet</string></array>
    <key>StartCalendarInterval</key>
      <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>3</integer></dict>
  </dict></plist>""")
        print(f"\n  launchctl load {plist}")
    else:
        print("Linux — add this line to your crontab (`crontab -e`):\n")
        print(f"  0 3 * * 0 {command}")
        print("\nOr, with systemd, a timer unit calling the same command.")

    print(f"\nEach run appends to {home / LOG_FILE}, so you can see what it did:")
    print(f"  tail {home / LOG_FILE}")
    print("\nAn update that fails to import is rolled back automatically, so an")
    print("unattended run cannot leave you with a broken OpenBB.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openbb_local.py",
        description="Install and maintain a self-contained local OpenBB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scripts/openbb_local.py install\n"
            "  python3 scripts/openbb_local.py status\n"
            "  python3 scripts/openbb_local.py update --quiet\n"
            "  python3 scripts/openbb_local.py run examples/openbb_quickstart.py\n"
        ),
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(os.environ.get("OPENBB_LOCAL_HOME", DEFAULT_HOME)),
        help=f"where the private environment lives (default: {DEFAULT_HOME})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="create the environment and install OpenBB")
    install.add_argument("--pin", help="install this exact version instead of the newest")
    install.add_argument(
        "--recreate", action="store_true", help="delete and rebuild an existing environment"
    )
    install.set_defaults(func=cmd_install)

    status = sub.add_parser("status", help="show the installed version and whether one is newer")
    status.set_defaults(func=cmd_status)

    update = sub.add_parser("update", help="upgrade to the newest version, verifying it works")
    update.add_argument(
        "--check-only", action="store_true", help="report whether an update exists, change nothing"
    )
    update.add_argument("--quiet", action="store_true", help="say nothing when already current")
    update.set_defaults(func=cmd_update)

    run = sub.add_parser("run", help="run a script against the local OpenBB")
    run.add_argument("script", nargs=argparse.REMAINDER, help="script path and its arguments")
    run.set_defaults(func=cmd_run)

    schedule = sub.add_parser("schedule", help="print the scheduler entry for automatic updates")
    schedule.set_defaults(func=cmd_schedule)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except LocalOpenBBError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("error: the operation timed out", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
