"""Safe, non-fatal Windows auto-launcher for grandMA2 onPC.

Invoked from start.bat before the bridge starts:
    python -m ma2panel.launcher --settings settings.json

Never blocks bridge startup and always exits with code 0.
"""
import argparse
import csv
import fnmatch
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LOCAL_HOSTS = frozenset({"", "127.0.0.1", "localhost", "::1", "[::1]", "ma2-unconfigured.invalid"})
_MA_REL_DIR = Path("MA Lighting Technologies") / "grandma"
_ONPC_DIR_GLOB = "grandma2 onPC*"
_ONPC_EXE_GLOB = "gma2onpc*.exe"


def is_local_host(host) -> bool:
    """Return True when the configured MA2 host points to this PC (or is not yet configured)."""
    if host is None:
        return True
    if not isinstance(host, str):
        return False
    return host.strip().lower() in LOCAL_HOSTS


def _version_key(path: Path) -> tuple:
    """Sortable version key preferring the highest numeric version and exact gma2onpc.exe."""
    dir_nums = tuple(int(n) for n in re.findall(r"\d+", path.parent.name))
    exe_nums = tuple(int(n) for n in re.findall(r"\d+", path.stem))
    exact_name = 1 if path.name.lower() == "gma2onpc.exe" else 0
    return (dir_nums, exe_nums, exact_name, str(path).lower())


def _default_program_dirs(environ=None) -> list[Path]:
    env = os.environ if environ is None else environ
    dirs = []
    seen = set()
    for key in ("ProgramFiles", "ProgramFiles(x86)"):
        raw = (env.get(key) or "").strip()
        if not raw:
            continue
        norm = raw.lower()
        if norm not in seen:
            seen.add(norm)
            dirs.append(Path(raw))
    return dirs


def find_onpc_exe(exe_path: str = "", program_dirs=None) -> Path | None:
    """Locate grandMA2 onPC executable: explicit exe_path first, else newest installed version."""
    explicit = (exe_path or "").strip() if isinstance(exe_path, str) else ""
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return candidate

    roots = _default_program_dirs() if program_dirs is None else [Path(p) for p in program_dirs]
    candidates: list[Path] = []
    for root in roots:
        grandma_dir = root / _MA_REL_DIR
        if not grandma_dir.is_dir():
            continue
        try:
            entries = list(grandma_dir.iterdir())
        except OSError:
            continue
        for folder in entries:
            if not folder.is_dir() or not fnmatch.fnmatch(folder.name.lower(), _ONPC_DIR_GLOB.lower()):
                continue
            try:
                files = list(folder.iterdir())
            except OSError:
                continue
            for item in files:
                if item.is_file() and fnmatch.fnmatch(item.name.lower(), _ONPC_EXE_GLOB):
                    candidates.append(item)

    if not candidates:
        return None
    candidates.sort(key=_version_key, reverse=True)
    return candidates[0]


def is_onpc_running(runner=subprocess.run) -> bool:
    """Return True if a gma2onpc*.exe process is already running according to tasklist."""
    completed = runner(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        timeout=10,
        errors="replace",
    )
    if completed.returncode != 0:
        return False
    reader = csv.reader(io.StringIO(completed.stdout or ""))
    for row in reader:
        if not row:
            continue
        image_name = row[0].strip().lower()
        if fnmatch.fnmatch(image_name, _ONPC_EXE_GLOB):
            return True
    return False


def _read_ma2_settings(settings_path: Path) -> dict:
    if not settings_path.is_file():
        return {}
    data = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        return {}
    ma2 = data.get("ma2")
    return ma2 if isinstance(ma2, dict) else {}


def _get_windows_shell32():
    import ctypes
    windll = getattr(ctypes, "windll", None)
    return getattr(windll, "shell32", None) if windll is not None else None


def _start_windows_exe(exe: Path) -> None:
    """Launch a Windows executable with exe.parent as working directory via ShellExecuteW, falling back to os.startfile."""
    shell32 = _get_windows_shell32()
    if shell32 is not None:
        rc = shell32.ShellExecuteW(None, "open", str(exe), None, str(exe.parent), 1)
        if rc <= 32:
            raise OSError(f"ShellExecuteW failed with code {rc}")
        return
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise RuntimeError("Windows start API unavailable")
    try:
        startfile(str(exe), cwd=str(exe.parent))
    except TypeError:
        startfile(str(exe))


def launch_if_needed(
    settings_path: Path,
    *,
    platform: str | None = None,
    program_dirs=None,
    runner=subprocess.run,
    starter=None,
    out=None,
) -> str:
    """Check settings/process state and start grandMA2 onPC if appropriate. Returns a short status code."""
    plat = sys.platform if platform is None else platform
    stream = sys.stdout if out is None else out

    def say(msg: str) -> None:
        try:
            print(msg, file=stream)
        except Exception:
            pass

    if plat != "win32":
        return "non_windows"

    try:
        ma2 = _read_ma2_settings(Path(settings_path))
    except Exception as exc:
        say(f"[launcher] Skipped grandMA2 auto-launch (could not read settings: {exc})")
        return "settings_error"

    if ma2.get("auto_launch", True) is False:
        return "disabled"

    host = ma2.get("host", "")
    if not is_local_host(host):
        return "remote_host"

    try:
        if is_onpc_running(runner=runner):
            say("[launcher] grandMA2 onPC is already running.")
            return "already_running"
    except Exception as exc:
        say(f"[launcher] Could not check running processes ({exc}); skipping grandMA2 auto-launch.")
        return "tasklist_error"

    exe = find_onpc_exe(ma2.get("exe_path", ""), program_dirs=program_dirs)
    if exe is None:
        say("[launcher] grandMA2 onPC not found; starting bridge only.")
        return "not_found"

    if starter is None and _get_windows_shell32() is None and getattr(os, "startfile", None) is None:
        say("[launcher] Windows launcher API is unavailable; skipping grandMA2 auto-launch.")
        return "unsupported"

    try:
        if starter is not None:
            starter(str(exe))
        else:
            _start_windows_exe(exe)
        say(f"[launcher] Started grandMA2 onPC: {exe}")
        return "launched"
    except Exception as exc:
        say(f"[launcher] Could not start grandMA2 onPC ({exe}): {exc}")
        return "launch_error"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Safe Windows grandMA2 onPC auto-launcher")
    parser.add_argument("--settings", default="settings.json", help="Path to settings.json")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 0
    try:
        launch_if_needed(Path(args.settings))
    except Exception as exc:
        try:
            print(f"[launcher] Unexpected auto-launch error: {exc}")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
