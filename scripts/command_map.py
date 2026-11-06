"""Drive every panel action against the mock console and print the exact MA2 lines each one sends, per safety mode.

    uv run python -m scripts.command_map > docs/outgoing-commands.md
"""
import json
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from ma2panel.bridge import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tests" / "config.test.json").read_text(encoding="utf-8"))
V3_FLAGS = ("allow_fixture_read", "allow_highlight", "allow_show_load", "allow_show_save", "allow_group_store")
SAFETY = {"allowed_fixtures": [12, 14], "allowed_scenes": ["1.101"], "store_execs": ["2.150"]}
SETUP = [{"a": "select_fixtures", "ids": [12, 14]}, {"a": "aim", "pan": 0, "tilt": 0}, {"a": "move_start"}]
CASES = [
    ("LIVE", "Выбор группы/приборов", [{"a": "select_fixtures", "ids": [12, 14]}]),
    ("LIVE", "Снять выбор", [{"a": "select_fixtures", "ids": [12]}, {"a": "clear"}]),
    ("LIVE", "Dim 40", SETUP[:1] + [{"a": "dim", "v": 40}]),
    ("LIVE", "Dim 40, переход 3 с", SETUP[:1] + [{"a": "dim", "v": 40, "fade": 3}]),
    ("LIVE", "Цвет R100 G0 B50", SETUP[:1] + [{"a": "color", "r": 100, "g": 0, "b": 50}]),
    ("LIVE", "Strobe 20", SETUP[:1] + [{"a": "strobe", "v": 20}]),
    ("LIVE", "Шаг Pan +", SETUP[:1] + [{"a": "nudge", "attr": "pan", "dir": 1}]),
    ("LIVE", "Задать позицию", SETUP[:1] + [{"a": "aim", "pan": 0, "tilt": 0}]),
    ("LIVE", "Pan/Tilt (пад)", SETUP + [{"a": "move", "dx": 5, "dy": -5}]),
    ("LIVE", "Zoom 60", SETUP[:1] + [{"a": "zoom", "v": 60}]),
    ("LIVE", "Focus 60", SETUP[:1] + [{"a": "focus", "v": 60}]),
    ("LIVE", "Сцена Go (1.101)", [{"a": "scene_go", "id": "pianist"}]),
    ("LIVE", "Сцена Off (1.101)", [{"a": "scene_off", "id": "pianist"}]),
    ("LIVE", "«Погасить всё»", [{"a": "blackout"}]),
    ("LIVE*", "Общая яркость 50 (allow_master)", [{"a": "master", "v": 50}]),
    ("LIVE*", "Открыть страницу 2 (allow_page_change)", [{"a": "page_go", "n": 2}]),
    ("LIVE", "Остановить передачу", [{"a": "halt"}]),
    ("READ", "Обновить сцены из пульта", [{"a": "scenes_import"}]),
    ("STORE", "Перезапись сцены (отключена)", [{"a": "store_scene", "id": "pianist"}]),
    ("STORE", "Новая сцена (exec+confirm, проверка пустого места)", [{"a": "scene_create", "label": "Тест", "page": 2, "exec": "2.150", "confirm": "2.150"}]),
    ("STORE", "Переименовать сцену", [{"a": "scene_rename", "id": "pianist", "label": "X"}]),
    ("STORE", "Назвать страницу", [{"a": "page_save", "n": 2, "label": "X"}]),
    ("SYSTEM", "fixtures_fetch (после show_bind)", [{"a": "show_bind", "name": "Mock show"}, {"a": "fixtures_fetch"}]),
    ("READ", "show_identify", [{"a": "show_identify"}]),
    ("SYSTEM", "highlight: первый выбор 12 (после edit_begin)", [{"a": "edit_begin"}, {"a": "highlight", "id": 12}]),
    ("SYSTEM", "highlight: смена 12 → 14", [{"a": "edit_begin"}, {"a": "highlight", "id": 12}, {"a": "highlight", "id": 14}]),
    ("SYSTEM", "highlight_off (после edit_begin и highlight 12)", [{"a": "edit_begin"}, {"a": "highlight", "id": 12}, {"a": "highlight_off"}]),
    ("READ", "shows_list", [{"a": "shows_list"}]),
    ("SHOW", 'show_load Demo (confirm_name="Demo", ack_unsaved=true)', [{"a": "show_load", "name": "Demo", "confirm_name": "Demo", "ack_unsaved": True}]),
    ("SHOW", 'show_save (после show_identify, confirm_name="Mock show")', [{"a": "show_identify"}, {"a": "show_save", "confirm_name": "Mock show"}]),
    ("PANEL", "Запомнить пресет (только config.json)", SETUP + [{"a": "move", "dx": 5, "dy": 5}, {"a": "preset_save", "label": "T"}]),
    ("PANEL", "Новая группа панели (только config.json)", [{"a": "group_save", "label": "G", "ids": [12]}]),
    ("PANEL", "Расстановка на плане (только config.json)", [{"a": "layout_save", "pos": [{"id": 12, "x": 0.1, "y": 0.1}]}]),
    ("PANEL", "Убрать сцену из панели (только config.json)", [{"a": "scene_delete", "id": "pianist"}]),
    ("PANEL", "Форма зала (только config.json)", [{"a": "hall_save", "hall": {"w": 18, "d": 14, "stage": "top", "stageDepth": 4}}]),
    ("PANEL", "Служебный прибор (только config.json)", [{"a": "fixture_flag", "id": 12, "service": True}]),
    ("READ", "ma2_read: группы и пресеты MA2", [{"a": "ma2_read"}]),
    ("READ", "ma2_import: группа 1, пресеты (+ запись в config.json)", [{"a": "ma2_import", "groups": [1], "colors": True, "positions": True, "scenes": False}]),
    ("LIVE", "Пресет цвета MA2 4.1 для выбора", [{"a": "ma2_import", "groups": [], "colors": True, "positions": False, "scenes": False},
                                            {"a": "select_fixtures", "ids": [12, 14]}, {"a": "ma2_preset_go", "type": "color", "n": 1}]),
    ("SHOW", "group_store_ma2: группа панели → Group 11 (проверка пустого номера)", [{"a": "group_save", "label": "G", "ids": [12]},
                                            {"a": "group_store_ma2", "id": "g1", "n": 11, "confirm": 11}]),
]


def run(mode, actions, flags_on=False):
    cfg = json.loads(json.dumps(CFG))
    with tempfile.TemporaryDirectory() as tmp:
        cfg["ma2"]["export_dir"] = tmp
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False))
        settings = {"safety": {**SAFETY, "mode": mode, "allow_master": True, "allow_page_change": True} if mode != "test" else
                    {**SAFETY, "mode": "test", "allow_master": True, "allow_page_change": True}, "rate_hz": 10}
        if flags_on:
            settings["safety"].update(dict.fromkeys(V3_FLAGS, True))
        # Keep the highlight zone identical in all modes, including full.
        settings["highlight"] = {"exclude": [f["id"] for f in cfg["fixtures"] if f["id"] not in (12, 14)]}
        with TestClient(create_app(cfg, True, str(path), settings)) as client, client.websocket_connect("/ws") as ws:
            def recv():
                while "status" not in (m := ws.receive_json()) or m["status"]["ma2"] != "logged_in":
                    pass
            recv()
            mock = client.app.state.mock
            reply = {}
            for i, action in enumerate(actions):
                last = i == len(actions) - 1
                before = len(mock.received)
                ws.send_json(action)
                if action["a"] in ("dim", "color", "strobe", "move", "zoom", "focus", "master"):
                    time.sleep(0.4)
                    reply = {"ok": True}
                    while True:
                        try:
                            break
                        except Exception:
                            break
                else:
                    while "ok" not in (m := ws.receive_json()):
                        pass
                    reply = m
                # A refused prerequisite must remain visible (not an idle highlight_off).
                if last or reply.get("ok") is False:
                    lines = mock.received[before:]
                    return reply, lines
    return {}, []


def main():
    print("# Что программа отправляет в MA2: каждое действие панели\n")
    print("Сгенерировано `scripts/command_map.py` на имитации пульта (mock): это реальные строки, которые уходят в Telnet.")
    print("Приборы 12 и 14 и сцена 1.101 разрешены, `store_execs` = 2.150, allow_master и allow_page_change включены.")
    print("Классы: LIVE живой свет; LIVE* отдельный флаг; READ только чтение; STORE запись данных MA2; "
          "SHOW загрузка/сохранение шоу; SYSTEM экспорт/подсветка; PANEL только конфиг панели.\n")
    print("Зона подсветки ограничена приборами 12 и 14 через highlight.exclude во всех режимах; level=100.")
    print("Каждая ячейка — отдельный запуск; показаны строки последнего действия, без первоначального входа и подготовки; повторный вход и ListVar внутри show_load включены. "
          "При отказе подготовки показана его причина; последующее действие не запускается. "
          "При отказе после отправки показаны и строки, и причина. Результат mock не подтверждает работу настоящей MA2.\n")
    for flags_on in (False, True):
        print("## Новые флаги " + ("включены" if flags_on else "выключены (по умолчанию)") + "\n")
        print(", ".join(f"`{flag}`" for flag in V3_FLAGS) + " = " + ("true" if flags_on else "false") + ".\n")
        print("| Класс | Действие панели | test | store | full |")
        print("|---|---|---|---|---|")
        for cls, label, actions in CASES:
            cells = []
            for mode in ("test", "store", "full"):
                reply, lines = run(mode, actions, flags_on)
                cell = "<br>".join(f"`{x}`" for x in lines)
                if reply.get("ok") is False:
                    cell = (cell + "<br>" if cell else "") + "ОТКАЗ: " + reply.get("err", "")
                cells.append((cell or "ничего не уходит").replace("|", "&#124;").replace("\n", "<br>"))
            print(f"| {cls} | {label} | " + " | ".join(cells) + " |")
        if not flags_on:
            print()


if __name__ == "__main__":
    main()
