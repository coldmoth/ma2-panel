"""Failures seen on the real console on 2026-10-18: masking ate digits, the export left no file, the diagnostics could not say why."""
import io
import json
import zipfile
from pathlib import Path

import pytest

from ma2panel import bridge
from ma2panel.fixtures import parse_export
from ma2panel.safety import redact
from test_bridge import ask, bridge_cfg, confirm_fixture_import  # noqa: F401
from test_diag import site  # noqa: F401

READ = {"safety": {"mode": "full", "allow_fixture_read": True}}


def test_redact_hides_by_shape_and_keeps_ordinary_digits():
    text = 'Executing : Login "Remote" "1"\n127.0.0.1 2026-10-18 Fixture 11 MA2_PASSWORD=1'
    out = redact(text, {"1"})
    assert out == 'Executing : Login "Remote" "***"\n127.0.0.1 2026-10-18 Fixture 11 MA2_PASSWORD=1'
    assert redact("MA2_PASSWORD=1", {"1"}) == "MA2_PASSWORD=***"
    assert redact("pw long-secret-1 end", {"long-secret-1"}) == "pw *** end"
    assert redact('Login "a" "quo"te"', {'quo"te'}) == 'Login "a" "***"'


def test_one_character_password_full_settings_cycle(site):
    stored = {"bind": "127.0.0.1", "port": 8080, "ma2": {"host": "127.0.0.1", "port": 30000, "user": "Remote"},
              "safety": {"mode": "full", "allow_fixture_read": False, "allow_master": True}}
    with site(password="1", settings=stored) as s:
        data = s.client.get("/api/settings").json()
        assert data["settings"] == json.loads(s.path.read_text())                       # byte for byte what is on disk
        assert data["password_set"] is True and '"1"' not in json.dumps({k: v for k, v in data.items() if k != "defaults"})
        proposed = json.loads(json.dumps(data["settings"]))
        proposed["safety"]["allow_fixture_read"] = True         # one checkbox, no password field
        secret_before = (s.folder / "secret.env").read_bytes()
        assert s.client.post("/api/settings", json={"settings": proposed}).json()["ok"]
        assert (s.folder / "secret.env").read_bytes() == secret_before
        assert (s.folder / "secret.env").read_text() == "MA2_PASSWORD=1\n"
        again = s.client.get("/api/settings").json()["settings"]
        assert again == proposed and again["bind"] == "127.0.0.1" and again["ma2"]["host"] == "127.0.0.1"
        assert bridge.load_settings(s.path)["safety"]["allow_fixture_read"] is True   # what a restart would read
        # diagnostics: ordinary values survive, the login echo does not show the password
        diag = s.client.get("/api/diag").json()
        assert diag["host"] == "127.0.0.1:30000"
        assert '"1"' not in diag["login_reply"] and "Remote" in diag["login_reply"]
        with zipfile.ZipFile(io.BytesIO(s.client.get("/api/diag.zip").content)) as archive:
            assert json.loads(archive.read("settings.json"))["bind"] == "127.0.0.1"
            assert "secret.env" not in archive.namelist()


def test_empty_new_password_keeps_old_one(site):
    with site(password="1") as s:
        s.client.post("/api/settings", json={"settings": {}, "password": ""})
        assert (s.folder / "secret.env").read_text() == "MA2_PASSWORD=\n"   # an explicit empty string is a real clear, as before
    with site(password="1") as s:
        s.client.post("/api/settings", json={"settings": {}})
        assert (s.folder / "secret.env").read_text() == "MA2_PASSWORD=1\n"


def test_subfixtures_and_pool_index_are_not_fixtures():
    xml = ('<MA xmlns="urn:ma"><Fixture index="0" fixture_id="7" name="Head"><SubFixture index="0" name="cell"/>'
           '<FixtureType name="Spot"/></Fixture></MA>')
    assert [(f["id"], f["type"]) for f in parse_export(xml)] == [(7, "Spot")]
    with pytest.raises(ValueError, match="index"):
        parse_export('<MA><Fixture index="3" name="x"/></MA>')   # the error names what the file does contain


def export_settings(**ma2):
    return {**READ, "ma2": {"export_wait": .6, **ma2}}


def trace(path):
    return json.loads((path.parent / "diag" / "export_trace.json").read_text())


def test_export_success_is_recorded(bridge_cfg):
    with bridge_cfg(settings=export_settings()) as (ws, mock, path):
        result = confirm_fixture_import(ws, ask(ws, {"a": "fixtures_fetch"}))
        assert result["ok"] and result["total"] >= 4
        t = trace(path)
        assert t["file"]["path"].endswith(".xml") and "fixture-panel_fixtures_" in t["file"]["path"] and "error" not in t and t["sent_ok"]
        assert json.loads(path.read_text())["fixtures_read"]["source"] == "ma2"


def test_export_delayed_file_is_waited_for(bridge_cfg):
    with bridge_cfg(settings=export_settings(export_wait=3)) as (ws, mock, path):
        mock.export_delay = .8
        assert confirm_fixture_import(ws, ask(ws, {"a": "fixtures_fetch"}))["ok"]


@pytest.mark.parametrize("mode,words", [("none", "не появился"), ("reject", "не выполнена")])
def test_export_failures_keep_plan_and_say_why(bridge_cfg, mode, words):
    with bridge_cfg(settings=export_settings()) as (ws, mock, path):
        old = path.read_bytes()
        stale = path.parent / "panel_fixtures.xml"
        stale.write_text("<MA><Fixture fixture_id='99'/></MA>")   # an old export must never pass for a new one
        mock.export_mode = mode
        result = confirm_fixture_import(ws, ask(ws, {"a": "fixtures_fetch"}))
        assert result["ok"] is False and words in result["err"]
        assert str(path.parent) in result["err"] or mode == "reject"
        assert path.read_bytes() == old and stale.exists()  # the unique name never touches an unrelated file
        assert "fixtures_read" not in json.loads(path.read_text())
        assert trace(path)["error"] == result["err"]
        assert "Error #72" in trace(path)["reply"] if mode == "reject" else trace(path)["reply"]


def test_export_corrupt_xml_names_the_file(bridge_cfg):
    with bridge_cfg(settings=export_settings()) as (ws, mock, path):
        old = path.read_bytes()
        mock.export_text = "<MA><Fixture"
        result = confirm_fixture_import(ws, ask(ws, {"a": "fixtures_fetch"}))
        assert not result["ok"] and "не разобран" in result["err"] and "fixture-panel_fixtures_" in result["err"]
        assert path.read_bytes() == old and "битый XML" in trace(path)["parse_error"]


def test_export_with_link_lost(bridge_cfg):
    with bridge_cfg(settings=export_settings()) as (ws, mock, path):
        mock.drop()
        import time
        time.sleep(.1)
        result = confirm_fixture_import(ws, ask(ws, {"a": "fixtures_fetch"}))
        assert not result["ok"] and "нет связи" in result["err"]


def test_active_export_probe_reports_files_and_never_leaves_the_door_open(site):
    with site(settings=READ) as s:
        before = len(s.mock.received)
        data = s.client.post("/api/diag/export_probe").json()
        assert data["ok"] and [r["key"] for r in data["results"]] == ["help", "fixture", "fixture_nc", "channel", "layers"]
        sent = s.mock.received[before:]
        assert all(line.startswith("Export") for line in sent) and len(sent) == 5
        fixture = next(r for r in data["results"] if r["key"] == "fixture")
        assert any(f["path"].endswith(".xml") and "panel_diag_fixture_" in f["path"] for f in fixture["new_files"])
        assert (s.folder / "diag" / "export_probe.json").exists()
        # afterwards a diagnostic line is not allowed out any more
        assert s.link.guard('Export Fixture 1 Thru 9999 "panel_diag_fixture_1"')
        with zipfile.ZipFile(io.BytesIO(s.client.get("/api/diag.zip").content)) as archive:
            names = archive.namelist()
            assert "diag/export_probe.json" in names and any(n.startswith("diag/export_probe/fixture-") for n in names)
            info = json.loads(archive.read("diag.json"))["export"]
            assert info["export_cmd"].startswith("Export Fixture") and info["active_probe"]["results"]


def test_export_probe_needs_flag_and_sends_nothing_without_it(site):
    with site() as s:
        before = list(s.mock.received)
        assert s.client.post("/api/diag/export_probe").json()["ok"] is False
        assert s.mock.received == before


def test_report_downloads_even_when_a_part_fails(site, monkeypatch):
    with site() as s:
        (s.folder / "bridge.log").write_text("x")
        real = Path.read_text

        def broken(self, *a, **k):
            if self.name == "bridge.log":
                raise PermissionError("locked")
            return real(self, *a, **k)

        monkeypatch.setattr(Path, "read_text", broken)
        response = s.client.get("/api/diag.zip")
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert "diag.json" in archive.namelist() and "bridge.log" in archive.read("collect_errors.txt").decode()


def test_guard_still_refuses_overwrite_and_foreign_exports():
    from ma2panel.safety import make_guard
    cmd = 'Export Fixture 1 Thru 9999 "panel_fixtures"'
    extra = {'Export Channel 1 Thru 9999 "panel_diag_channel_1"'}
    guard = make_guard({"mode": "full", "allow_fixture_read": True, "allowed_fixtures": [], "allowed_scenes": [], "store_execs": [],
                        "allow_master": False, "allow_page_change": False, "extra_allowed_regex": []}, export_cmd=cmd, export_extra=extra)
    assert guard(cmd) is None and guard(next(iter(extra))) is None
    assert guard(cmd + " /Overwrite") and guard('Export Macro 1 "x"') and guard('Export Channel 1 Thru 9999 "other"')
    extra.clear()
    assert guard('Export Channel 1 Thru 9999 "panel_diag_channel_1"')


def test_immediate_close_is_logged_with_stage_and_reason(caplog):
    import asyncio
    from ma2panel.mock import start_mock

    async def go():
        mock = await start_mock(0, "Remote")
        mock.paused = True  # accepts, then closes at once: what the real console did on 2026-10-18
        link = bridge.MA2Link("127.0.0.1", mock.port, "Remote", "", lambda state: None)
        task = asyncio.create_task(link.run())
        await asyncio.sleep(.6)
        task.cancel()
        return link, mock

    link, mock = asyncio.run(go())
    attempt = link.attempts[0]
    assert attempt["stage"] == "greeting" and "до приветствия" in attempt["error"] and attempt["bytes_received"] == 0
    assert "EOF" in attempt["connection_end"] and "ms_since_connect" in attempt
    assert any("этап «greeting»" in r.message and "EOF" in r.message for r in caplog.records)
    assert not any(line.lower().startswith("login") for line in mock.received)  # nothing is written into the dead socket


def test_link_test_endpoint_is_read_only(site):
    with site() as s:
        before = list(s.mock.received)
        data = s.client.post("/api/diag/link_test").json()
        assert data["ok"] and data["state"] == "logged_in" and "пропущено" in data["bare_connect"] and data["attempts"]
        assert s.mock.received == before
        assert (s.folder / "diag" / "link_test.json").exists()
        assert s.client.get("/api/diag").json()["link_attempts"]


def test_link_test_bare_connect_only_when_auto_connect_is_off(site):
    import time as t
    with site() as s:
        assert "автоподключение" in s.client.post("/api/diag/link_test").json()["bare_connect"]
        s.link.disconnect()
        t.sleep(.3)
        data = s.client.post("/api/diag/link_test").json()
        assert data["bare_connect"]["end"].startswith("таймаут") and "Welcome" in data["bare_connect"]["first_text"]


def test_export_cmd_with_overwrite_flag_still_yields_file(bridge_cfg):
    # hall 2026-10-18: a config.json carrying "... /o" got "Executing" from MA2 but no file; the flag must be dropped
    cmd = 'Export Fixture 1 Thru 9999 "panel_fixtures" /o'
    with bridge_cfg(settings=export_settings(export_cmd=cmd)) as (ws, mock, path):
        assert confirm_fixture_import(ws, ask(ws, {"a": "fixtures_fetch"}))["ok"]
        assert not any(c.rstrip().lower().endswith("/o") for c in mock.received if c.startswith("Export"))


def test_fixture_export_is_found_in_the_fixtures_folder(bridge_cfg, tmp_path):
    # hall 2026-10-18: MA2 3.9.60 wrote the file to <install>\\fixtures while the bridge only watched <install>\\importexport
    export, fixtures = tmp_path / "importexport", tmp_path / "fixtures"
    export.mkdir(), fixtures.mkdir()
    with bridge_cfg(settings=export_settings(export_dir=str(export))) as (ws, mock, path):
        mock.export_dir, mock.fixture_dir = str(export), str(fixtures)
        result = confirm_fixture_import(ws, ask(ws, {"a": "fixtures_fetch"}))
        assert result["ok"] and result["total"] >= 4
        assert not list(fixtures.iterdir())  # our one-off file is removed afterwards
