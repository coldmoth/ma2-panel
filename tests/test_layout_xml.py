"""Unit & round-trip tests for bidirectional grandMA2 Layout XML (MA2 <-> LUMA)."""
import xml.etree.ElementTree as ET

import pytest

from ma2panel.layout_xml import (
    compute_bounds,
    generate_layout_xml,
    luma_to_ma2,
    ma2_to_luma,
    parse_layout_xml,
    patch_layout_xml,
    preview_layout_import,
)
from ma2panel.safety import DEFAULT_SAFETY, make_guard, validate_settings

SAMPLE_LAYOUT_XML = """<?xml version="1.0" encoding="utf-8"?>
<?xml-stylesheet type="text/xsl" href="styles/layout@html@default.xsl"?>
<MA xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://schemas.malighting.de/grandma2/xml/MA" major_vers="3" minor_vers="9" stream_vers="60">
\t<Info datetime="2026-10-18T18:15:36" showfile="big room v2" />
\t<Group index="0" name="Hall Top View">
\t\t<LayoutData index="0" marker_visible="true" background_color="101010" visible_grid_h="1" visible_grid_w="1">
\t\t\t<SubFixtures>
\t\t\t\t<LayoutSubFix gauge_style="Filled" border_color="5a5a5a" size_w="0.800" size_h="0.800" center_y="5.000" center_x="-4.000" font_size="Small">
\t\t\t\t\t<Subfixture fix_id="1" />
\t\t\t\t</LayoutSubFix>
\t\t\t\t<LayoutSubFix gauge_style="Filled" border_color="5a5a5a" size_w="0.800" size_h="0.800" center_y="5.000" center_x="6.000" font_size="Small">
\t\t\t\t\t<Subfixture fix_id="2" />
\t\t\t\t</LayoutSubFix>
\t\t\t\t<LayoutSubFix gauge_style="Filled" border_color="5a5a5a" size_w="0.800" size_h="0.800" center_y="-5.000" center_x="1.000" font_size="Small">
\t\t\t\t\t<Subfixture fix_id="3" />
\t\t\t\t</LayoutSubFix>
\t\t\t\t<LayoutSubFix gauge_style="Filled" border_color="5a5a5a" size_w="0.800" size_h="0.800" center_y="0.000" center_x="0.000" font_size="Small">
\t\t\t\t\t<Subfixture fix_id="99" />
\t\t\t\t</LayoutSubFix>
\t\t\t\t<LayoutSubFix gauge_style="Filled" border_color="5a5a5a" size_w="0.800" size_h="0.800" center_y="1.000" center_x="2.000" font_size="Small">
\t\t\t\t\t<Subfixture cha_id="5" />
\t\t\t\t</LayoutSubFix>
\t\t\t</SubFixtures>
\t\t\t<CObjects>
\t\t\t\t<LayoutCObject font_size="Large" center_x="0.000" center_y="6.500" size_w="12.000" size_h="0.800" border_color="ffffff" text="STAGE FRONT">
\t\t\t\t\t<CObject name="Stage Label" />
\t\t\t\t</LayoutCObject>
\t\t\t\t<LayoutCObject center_x="-7.500" center_y="-4.000" size_w="2.000" size_h="1.000">
\t\t\t\t\t<CObject name="Macro 12 Blackout" />
\t\t\t\t</LayoutCObject>
\t\t\t\t<LayoutCObject center_x="7.500" center_y="-4.000" size_w="2.000" size_h="1.000">
\t\t\t\t\t<CObject name="Group 1 Heads" />
\t\t\t\t</LayoutCObject>
\t\t\t</CObjects>
\t\t</LayoutData>
\t</Group>
</MA>
"""


def test_parse_and_preview_matches_fixtures_and_counts_extra_elements():
    plan_fixtures = [
        {"id": 1, "label": "Bar 1", "x": 0.1, "y": 0.1, "physical_pos": {"x": 1.0, "y": 2.0, "z": 5.0}},
        {"id": 2, "label": "Bar 2", "x": 0.9, "y": 0.1},
        {"id": 3, "label": "Head 3", "x": 0.5, "y": 0.9},
        {"id": 4, "label": "Unplaced in XML", "x": 0.2, "y": 0.8},
    ]
    preview = preview_layout_import(SAMPLE_LAYOUT_XML, plan_fixtures)
    assert preview["layout_name"] == "Hall Top View"
    assert [m["id"] for m in preview["matched"]] == [1, 2, 3]
    assert preview["unmatched_xml_ids"] == [99]
    assert preview["unplaced_plan_ids"] == [4]
    assert preview["extra_elements"] == 3  # 3 CObjects (label, macro, group)
    assert preview["skipped_channel_only"] == 1

    # Y is inverted: MA2 y=+5.0 maps near top (v=0.08), MA2 y=-5.0 maps near bottom (v=0.92)
    by_id = {m["id"]: m for m in preview["matched"]}
    assert by_id[1]["new_x"] == pytest.approx(0.08, abs=1e-5)
    assert by_id[1]["new_y"] == pytest.approx(0.08, abs=1e-5)
    assert by_id[2]["new_x"] == pytest.approx(0.92, abs=1e-5)
    assert by_id[3]["new_y"] == pytest.approx(0.92, abs=1e-5)


def test_round_trip_import_move_and_patch_export_preserves_everything_else():
    """Full round-trip: MA2 Layout XML -> import -> move fixture 2 -> patch export -> verify math & untouched XML."""
    plan_fixtures = [
        {"id": 1, "label": "Bar 1", "physical_pos": {"x": -4.0, "y": 5.0, "z": 6.2}},
        {"id": 2, "label": "Bar 2"},
        {"id": 3, "label": "Head 3"},
    ]
    preview = preview_layout_import(SAMPLE_LAYOUT_XML, plan_fixtures)

    # Apply imported 2D coordinates to fixtures (physical_pos stays untouched)
    by_id = {m["id"]: m for m in preview["matched"]}
    for f in plan_fixtures:
        f["x"] = by_id[f["id"]]["new_x"]
        f["y"] = by_id[f["id"]]["new_y"]
    assert plan_fixtures[0]["physical_pos"]["z"] == 6.2

    # Move ONLY fixture 2 to the exact center of the LUMA plan (0.5, 0.5) -> MA2 (1.000, 0.000)
    plan_fixtures[1]["x"] = 0.5
    plan_fixtures[1]["y"] = 0.5

    layout_meta = {
        "bounds": preview["bounds"],
        "extra_elements": preview["extra_elements"],
        "imported_positions": preview["imported_positions"],
    }
    patched_xml, summary = patch_layout_xml(SAMPLE_LAYOUT_XML, plan_fixtures, layout_meta)

    assert summary["mode"] == "patch"
    assert summary["updated_ids"] == [2]
    assert summary["unchanged_ids"] == [1, 3]
    assert summary["extra_elements"] == 3

    # Stylesheet PI, CObjects (text label, macro, group), and channel-only item stay verbatim
    assert '<?xml-stylesheet type="text/xsl" href="styles/layout@html@default.xsl"?>' in patched_xml
    assert 'text="STAGE FRONT"' in patched_xml
    assert 'name="Macro 12 Blackout"' in patched_xml
    assert 'name="Group 1 Heads"' in patched_xml
    assert '<Subfixture cha_id="5" />' in patched_xml

    # Re-parse patched XML and check exact coordinates
    reparsed = parse_layout_xml(patched_xml)
    coords = {item["fixture_id"]: (item["ma2_x"], item["ma2_y"]) for item in reparsed["items"]}
    assert coords[1] == (-4.0, 5.0)     # untouched
    assert coords[2] == (1.0, 0.0)      # moved to center of [-4..6] x [-5..5]
    assert coords[3] == (1.0, -5.0)     # untouched
    assert coords[99] == (0.0, 0.0)     # unmatched fixture in XML untouched!


def test_patch_preserves_pos_x_pos_y_and_optional_rotation_attributes():
    xml_pos = """<?xml version="1.0" encoding="utf-8"?>
    <MA xmlns="http://schemas.malighting.de/grandma2/xml/MA">
      <Group index="0" name="Pos Style">
        <LayoutData index="0">
          <SubFixtures>
            <LayoutSubFix pos_x="0.000" pos_y="0.000" angle="0.000">
              <Subfixture fix_id="10" />
            </LayoutSubFix>
            <LayoutSubFix pos_x="10.000" pos_y="10.000" angle="45.000">
              <Subfixture fix_id="11" />
            </LayoutSubFix>
          </SubFixtures>
        </LayoutData>
      </Group>
    </MA>"""
    fixtures = [{"id": 10, "label": "F10"}, {"id": 11, "label": "F11"}]
    preview = preview_layout_import(xml_pos, fixtures)
    for f in fixtures:
        m = next(x for x in preview["matched"] if x["id"] == f["id"])
        f["x"], f["y"], f["rot"] = m["new_x"], m["new_y"], m["ma2_rot"]

    # Rotate & move fixture 10
    fixtures[0]["x"] = 0.5
    fixtures[0]["y"] = 0.5
    fixtures[0]["rot"] = 90.0

    patched, summary = patch_layout_xml(xml_pos, fixtures, {
        "bounds": preview["bounds"],
        "imported_positions": preview["imported_positions"],
    })
    assert summary["updated_ids"] == [10]
    assert 'pos_x="5.000"' in patched and 'pos_y="5.000"' in patched and 'angle="90.000"' in patched
    # Fixture 11 untouched
    assert 'pos_x="10.000" pos_y="10.000" angle="45.000"' in patched


def test_generate_fresh_layout_xml_from_scratch():
    fixtures = [
        {"id": 1, "label": "Front L", "x": 0.25, "y": 0.25},
        {"id": 2, "label": "Front R", "x": 0.75, "y": 0.75},
        {"id": 3, "label": "Missing", "x": 0.5, "y": 0.5, "missing": True},
    ]
    xml_text, summary = generate_layout_xml(fixtures, hall={"w": 20, "d": 10}, name="Fresh Hall", show_name="Demo")
    assert summary["mode"] == "new"
    assert summary["updated_ids"] == [1, 2]
    root = ET.fromstring(xml_text)
    assert root.tag.endswith("MA")
    parsed = parse_layout_xml(xml_text)
    coords = {i["fixture_id"]: (i["ma2_x"], i["ma2_y"]) for i in parsed["items"]}
    assert coords[1] == (-5.0, 2.5)
    assert coords[2] == (5.0, -2.5)


def test_bounds_math_exact_inverse_including_collinear_points():
    items = [
        {"fixture_id": 1, "ma2_x": 3.0, "ma2_y": 2.0},
        {"fixture_id": 2, "ma2_x": 3.0, "ma2_y": 2.0},
    ]
    bounds = compute_bounds(items)
    u, v = ma2_to_luma(3.0, 2.0, bounds)
    assert (u, v) == (0.5, 0.5)
    assert luma_to_ma2(u, v, bounds) == (3.0, 2.0)


def test_safety_guard_blocks_import_unless_allow_layout_import_and_whitelisted():
    cmd = 'Import "luma_layout" At Layout 99'
    full_off = {**DEFAULT_SAFETY, "mode": "full", "allow_layout_import": False}
    full_on = {**DEFAULT_SAFETY, "mode": "full", "allow_layout_import": True}

    assert make_guard(full_off, export_extra={cmd})(cmd) is not None
    assert make_guard(full_on)(cmd) is not None  # not in export_extra
    assert make_guard(full_on, export_extra={cmd})(cmd) is None
    # /Overwrite and path traversal are always blocked
    bad_overwrite = 'Import "luma_layout" At Layout 99 /Overwrite'
    bad_path = 'Import "../evil" At Layout 99'
    assert make_guard(full_on, export_extra={bad_overwrite})(bad_overwrite) is not None
    assert make_guard(full_on, export_extra={bad_path})(bad_path) is not None
    # List Layout N is read-only and allowed in test mode
    assert make_guard(DEFAULT_SAFETY)("List Layout 99") is None

    # Settings validation enforces bool for allow_layout_import
    validate_settings({"safety": {"allow_layout_import": True}})
    with pytest.raises(ValueError):
        validate_settings({"safety": {"allow_layout_import": "yes"}})


def test_http_layout_xml_round_trip_and_safety_gate(tmp_path):
    """End-to-end API test: preview -> apply -> drag/move -> patch download -> save_importexport -> gated import_to_ma2."""
    import json
    from fastapi.testclient import TestClient
    from ma2panel.bridge import create_app

    cfg_path = tmp_path / "config.json"
    export_dir = tmp_path / "importexport"
    export_dir.mkdir()
    cfg = {
        "show": "Hall Test",
        "hall": {"w": 16, "d": 12, "stage": "top", "stageDepth": 4},
        "fixtures": [
            {"id": 1, "label": "Bar 1", "name": "Bar 1", "type": "LED Bar", "x": 0.1, "y": 0.1, "physical_pos": {"x": 1.0, "y": 2.0, "z": 5.5}},
            {"id": 2, "label": "Bar 2", "name": "Bar 2", "type": "LED Bar", "x": 0.9, "y": 0.1},
            {"id": 3, "label": "Head 3", "name": "Head 3", "type": "Moving Head", "x": 0.5, "y": 0.9},
        ],
        "groups": [],
        "scenes": [],
        "attrs": {
            "color": {"mode": "rgb", "names": ["ColorRGB1", "ColorRGB2", "ColorRGB3"]},
            "pan": {"cmd": 'Attribute "Pan" At {v}', "min": -270, "max": 270},
            "tilt": {"cmd": 'Attribute "Tilt" At {v}', "min": -135, "max": 135},
            "zoom": {"cmd": 'Attribute "Zoom" At {v}', "min": 0, "max": 100},
            "focus": {"cmd": 'Attribute "Focus" At {v}', "min": 0, "max": 100},
            "strobe": {"cmd": 'Attribute "Strobe" At {v}', "min": 0, "max": 100},
        },
        "master": {"cmd": "Master 2.1 At {v}"},
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    (export_dir / "hall_top.xml").write_text(SAMPLE_LAYOUT_XML, encoding="utf-8")

    # 1) Safety disabled: download & save_importexport work, import_to_ma2 is blocked
    settings_off = {
        "ma2": {"export_dir": str(export_dir), "export_search": []},
        "safety": {"mode": "full", "allow_layout_import": False},
        "poll_seconds": 0,
        "dmx_seconds": 0,
    }
    app_off = create_app(json.loads(cfg_path.read_text(encoding="utf-8")), False, str(cfg_path), settings=settings_off)
    client = TestClient(app_off, client=("127.0.0.1", 50000))

    files = client.get("/api/layout/ma2/files").json()
    assert files["ok"] and any(f["name"] == "hall_top.xml" for f in files["files"])
    assert files["allow_layout_import"] is False

    # Preview from importexport folder (does not alter plan yet)
    prev = client.post("/api/layout/ma2/preview", json={"file": "hall_top.xml", "folder_index": 0}).json()
    assert prev["ok"] and prev["matched_count"] == 3 and prev["unmatched_xml_ids"] == [99] and prev["extra_elements"] == 3
    before_apply = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert before_apply["fixtures"][0]["x"] == 0.1

    # Apply preview
    applied = client.post("/api/layout/ma2/apply", json={"preview_token": prev["preview_token"]}).json()
    assert applied["ok"] and applied["applied"] == 3
    after_apply = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert after_apply["fixtures"][0]["x"] == pytest.approx(0.08, abs=1e-5)
    assert after_apply["fixtures"][0]["physical_pos"]["z"] == 5.5  # untouched!
    assert after_apply["ma2_layout"]["template_file"].endswith(".xml")

    # Simulate operator dragging fixture 2 to center (0.5, 0.5)
    after_apply["fixtures"][1]["x"] = 0.5
    after_apply["fixtures"][1]["y"] = 0.5
    cfg_path.write_text(json.dumps(after_apply), encoding="utf-8")

    # Reload app to verify template persists across restarts
    app2 = create_app(json.loads(cfg_path.read_text(encoding="utf-8")), False, str(cfg_path), settings=settings_off)
    client2 = TestClient(app2, client=("127.0.0.1", 50000))

    dl = client2.post("/api/layout/ma2/export", json={"mode": "download", "filename": "Hall_Patched"})
    assert dl.status_code == 200
    assert dl.headers["x-luma-layout-mode"] == "patch"
    assert dl.headers["x-luma-layout-updated"] == "1"
    assert 'text="STAGE FRONT"' in dl.text
    reparsed = parse_layout_xml(dl.text)
    coords = {i["fixture_id"]: (i["ma2_x"], i["ma2_y"]) for i in reparsed["items"]}
    assert coords[2] == (1.0, 0.0)
    assert coords[1] == (-4.0, 5.0)

    saved = client2.post("/api/layout/ma2/export", json={"mode": "save_importexport", "filename": "Hall_Patched"}).json()
    assert saved["ok"] and (export_dir / "Hall_Patched.xml").is_file()

    # import_to_ma2 blocked without confirm_import and without allow_layout_import
    no_confirm = client2.post("/api/layout/ma2/export", json={"mode": "import_to_ma2", "slot": 99}).json()
    assert not no_confirm["ok"] and no_confirm["code"] == "confirm_required"
    no_flag = client2.post("/api/layout/ma2/export", json={"mode": "import_to_ma2", "slot": 99, "confirm_import": True}).json()
    assert not no_flag["ok"] and no_flag["code"] == "permission_denied"

    # With allow_layout_import enabled and a connected mock desk: occupied slot 1 is refused, empty slot 99 succeeds
    settings_on = {
        "ma2": {"export_dir": str(export_dir), "export_search": []},
        "safety": {"mode": "full", "allow_layout_import": True},
        "poll_seconds": 0,
        "dmx_seconds": 0,
    }
    cfg_on = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg_on["show"] = "Mock show"
    cfg_path.write_text(json.dumps(cfg_on), encoding="utf-8")
    app3 = create_app(cfg_on, True, str(cfg_path), settings=settings_on)
    with TestClient(app3, client=("127.0.0.1", 50000)) as client3:
        # Wait briefly for mock Telnet login
        import time as _time
        for _ in range(40):
            st = client3.get("/api/layout/ma2/files").json()
            if st.get("ma2_ready"):
                break
            _time.sleep(0.05)
        assert st["ma2_ready"] is True and st["allow_layout_import"] is True
        occupied = client3.post("/api/layout/ma2/export", json={"mode": "import_to_ma2", "slot": 1, "confirm_import": True, "filename": "Should_Not_Write"}).json()
        assert not occupied["ok"] and occupied["code"] == "slot_occupied"
        assert not (export_dir / "Should_Not_Write.xml").exists()
        ok_imp = client3.post("/api/layout/ma2/export", json={"mode": "import_to_ma2", "slot": 99, "confirm_import": True, "filename": "Hall_Patched"}).json()
        assert ok_imp["ok"] and ok_imp["slot"] == 99 and ok_imp["cmd"] == 'Import "Hall_Patched" At Layout 99'

