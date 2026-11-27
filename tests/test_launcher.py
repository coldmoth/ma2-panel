"""Unit tests for the safe Windows grandMA2 onPC auto-launcher."""
import io
import json
import subprocess
from pathlib import Path

import pytest

from ma2panel import launcher
from ma2panel.safety import DEFAULT_MA2, validate_settings


def _make_onpc(root: Path, version: str, exe_name: str = "gma2onpc.exe") -> Path:
    folder = root / "MA Lighting Technologies" / "grandma" / f"grandma2 onPC {version}"
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / exe_name
    exe.write_bytes(b"MZ")
    return exe


def _tasklist_output(*names: str):
    stdout = "\r\n".join(f'"{n}","1234","Console","1","12,000 K"' for n in names)
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout, "")


def test_default_ma2_and_validation_accept_auto_launch_and_exe_path():
    assert DEFAULT_MA2["auto_launch"] is True
    assert DEFAULT_MA2["exe_path"] == ""
    # Legacy settings without auto_launch / exe_path stay valid.
    validate_settings({"ma2": {"host": "127.0.0.1", "port": 30000, "user": "Remote"}})
    validate_settings({"ma2": {"host": "127.0.0.1", "auto_launch": False, "exe_path": "C:/MA/gma2onpc.exe"}})
    with pytest.raises(ValueError, match="ma2.auto_launch"):
        validate_settings({"ma2": {"auto_launch": "yes"}})
    with pytest.raises(ValueError, match="ma2.exe_path"):
        validate_settings({"ma2": {"exe_path": 123}})
    with pytest.raises(ValueError, match="ma2.exe_path"):
        validate_settings({"ma2": {"exe_path": "C:/bad\npath.exe"}})


def test_find_onpc_picks_newest_version_numerically(tmp_path):
    pf = tmp_path / "Program Files"
    pf86 = tmp_path / "Program Files (x86)"
    _make_onpc(pf, "3.9.60.7")
    _make_onpc(pf86, "3.9.60.68")
    newest = _make_onpc(pf, "3.10.0.1")
    assert launcher.find_onpc_exe("", program_dirs=[pf, pf86]) == newest


def test_find_onpc_prefers_explicit_exe_path(tmp_path):
    pf = tmp_path / "Program Files"
    _make_onpc(pf, "3.9.60.68")
    custom = tmp_path / "custom" / "gma2onpc_custom.exe"
    custom.parent.mkdir(parents=True)
    custom.write_bytes(b"MZ")
    assert launcher.find_onpc_exe(str(custom), program_dirs=[pf]) == custom


def test_launch_skips_when_already_running(tmp_path):
    pf = tmp_path / "Program Files"
    _make_onpc(pf, "3.9.60.68")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"ma2": {"host": "127.0.0.1"}}), encoding="utf-8")
    started = []
    out = io.StringIO()
    status = launcher.launch_if_needed(
        settings,
        platform="win32",
        program_dirs=[pf],
        runner=_tasklist_output("explorer.exe", "gma2onpc.exe"),
        starter=started.append,
        out=out,
    )
    assert status == "already_running"
    assert started == []
    assert "already running" in out.getvalue().lower()


def test_launch_skips_remote_host(tmp_path):
    pf = tmp_path / "Program Files"
    _make_onpc(pf, "3.9.60.68")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"ma2": {"host": "192.168.0.10"}}), encoding="utf-8")
    started = []
    status = launcher.launch_if_needed(
        settings,
        platform="win32",
        program_dirs=[pf],
        runner=_tasklist_output("explorer.exe"),
        starter=started.append,
        out=io.StringIO(),
    )
    assert status == "remote_host"
    assert started == []


@pytest.mark.parametrize("host", ["", "127.0.0.1", "localhost", "::1", "ma2-unconfigured.invalid"])
def test_launch_starts_for_local_and_unconfigured_hosts(tmp_path, host):
    pf = tmp_path / "Program Files"
    exe = _make_onpc(pf, "3.9.60.68")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"ma2": {"host": host}}), encoding="utf-8")
    started = []
    status = launcher.launch_if_needed(
        settings,
        platform="win32",
        program_dirs=[pf],
        runner=_tasklist_output("explorer.exe"),
        starter=started.append,
        out=io.StringIO(),
    )
    assert status == "launched"
    assert started == [str(exe)]


def test_launch_skips_when_auto_launch_false(tmp_path):
    pf = tmp_path / "Program Files"
    _make_onpc(pf, "3.9.60.68")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"ma2": {"host": "127.0.0.1", "auto_launch": False}}), encoding="utf-8")
    started = []
    status = launcher.launch_if_needed(
        settings,
        platform="win32",
        program_dirs=[pf],
        runner=_tasklist_output("explorer.exe"),
        starter=started.append,
        out=io.StringIO(),
    )
    assert status == "disabled"
    assert started == []


def test_launch_handles_missing_installation_and_start_error_gracefully(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"ma2": {"host": "127.0.0.1"}}), encoding="utf-8")
    out = io.StringIO()
    status = launcher.launch_if_needed(
        settings,
        platform="win32",
        program_dirs=[tmp_path / "empty"],
        runner=_tasklist_output("explorer.exe"),
        starter=lambda p: None,
        out=out,
    )
    assert status == "not_found"
    assert "not found" in out.getvalue().lower()

    pf = tmp_path / "Program Files"
    _make_onpc(pf, "3.9.60.68")
    out2 = io.StringIO()

    def boom(_path):
        raise OSError("Access denied")

    status2 = launcher.launch_if_needed(
        settings,
        platform="win32",
        program_dirs=[pf],
        runner=_tasklist_output("explorer.exe"),
        starter=boom,
        out=out2,
    )
    assert status2 == "launch_error"
    assert "Access denied" in out2.getvalue()


def test_non_windows_exits_quietly_with_zero(tmp_path):
    settings = tmp_path / "settings.json"
    out = io.StringIO()
    status = launcher.launch_if_needed(settings, platform="darwin", out=out)
    assert status == "non_windows"
    assert out.getvalue() == ""
    assert launcher.main(["--settings", str(settings)]) == 0


def test_start_bat_is_ascii_crlf_and_invokes_launcher():
    root = Path(__file__).resolve().parents[1]
    raw = (root / "scripts/win/start.bat").read_bytes()
    raw.decode("ascii")
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("ascii")
    assert "-m ma2panel.launcher --settings" in text
    assert "--no-ma2" in text
    assert ":run_bridge" in text
    assert "if %errorlevel%==3" in text
    assert text.index("ma2panel.launcher") < text.index(":run_bridge")
