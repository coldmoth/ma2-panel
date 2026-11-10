"""Read-only self-check of a running bridge: python\\python.exe selfcheck.py [http://127.0.0.1:8080]

Sends nothing that changes MA2: no LoadShow, no Store, no light values. Only the panel's own read actions run (ListShows,
Export Fixture to a one-off file, which the bridge deletes). Afterwards it proves that from bridge.log: every command the
bridge sent during the run is on the read-only list. Refuses to run actions unless the bridge is in mode "test".
Report: selfcheck-report.txt next to this file (no password in it).
"""
import json, re, sys, time, urllib.request
from pathlib import Path

from websockets.sync.client import connect

BASE = "http://127.0.0.1:8080"
HERE = Path(__file__).resolve().parent.parent
READ_ONLY = re.compile(r'^(ListVar|ListShows|Export Fixture 1 Thru 9999 "panel_fixtures_\d+"|List Group 1 Thru 999|List Preset \d\.1 Thru \d\.999'
                       r'|login "[^"]*" "[^"]*"|Login "[^"]*" "[^"]*")\s*$')
rows = []


def check(name, ok, detail=""):
    rows.append((name, ok, detail))
    print(("ОК     " if ok else "ОШИБКА ") + name + (" - " + detail if detail else ""))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.status, r.read()


def log_lines():
    p = HERE / "bridge.log"
    return p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []


def ask(ws, msg, want="ok"):
    ws.send(json.dumps(msg))
    end = time.time() + 40
    while time.time() < end:
        m = json.loads(ws.recv(timeout=40))
        if want in m and (m.get("a") == msg["a"] or "a" not in m):
            return m
    return {"ok": False, "err": "нет ответа за 40 с"}


def fixtures_report():
    with connect(BASE.replace("http", "ws", 1) + "/ws") as ws:
        fixtures = next((m["config"] for m in (json.loads(ws.recv(timeout=10)) for _ in range(3)) if "config" in m), {}).get("fixtures", [])
    check("панель получила список приборов", bool(fixtures), f"{len(fixtures)} шт.")
    with_address = [f for f in fixtures if f.get("address")]
    check("адреса приборов прочитаны (Patch/Address)", len(with_address) == len(fixtures) > 0,
          f"{len(with_address)} из {len(fixtures)}" + (f", например {with_address[0]['id']} -> {with_address[0]['address']}" if with_address else
                                                         "; нажмите «Получить снова» на Площадке после обновления"))
    heads = [f for f in fixtures if f.get("moves") is True or any(re.search("pan|tilt", str(p), re.I) for p in f.get("params") or [])]
    check("головы отмечены (нужны для «Позиция и луч»)", bool(heads),
          (", ".join(f'{f["id"]} {f.get("label") or f.get("name", "")}' for f in heads) or "нет") +
          ("" if heads else "; MA2 не передаёт Pan/Tilt в экспорте: отметьте головы в «Зале» → «Расстановка» кнопкой «Голова»"))
    return fixtures


def main():
    d = json.loads(get("/api/diag")[1])
    check("мост отвечает, версия", True, d["version"])
    check("вход в MA2 подтверждён", d["ma2"] == "logged_in", f'состояние {d["ma2"]}, пользователь {d["user"]}')
    show_before = d["show"].get("name")
    check("шоу определено", bool(show_before), str(show_before))
    for page in ("/", "/settings.html", "/diag.html", "/app.js", "/light.js", "/move.js", "/plan.js"):
        try:
            code, body = get(page)
            check(f"страница {page}", code == 200 and len(body) > 100, f"{len(body)} байт")
        except Exception as e:
            check(f"страница {page}", False, str(e))
    if d["mode"] != "test":
        fixtures_report()  # reads the panel's own config only: works in any mode
        check("режим test (иначе действия не запускаются)", False, f'режим {d["mode"]}: проверка действий пропущена')
        return
    start = len(log_lines())
    with connect(BASE.replace("http", "ws", 1) + "/ws") as ws:
        r = ask(ws, {"a": "shows_list"})
        check("список шоу на пульте разобран", r.get("ok") and bool(r.get("names")), ", ".join(r.get("names", [])) or r.get("err", ""))
        check("текущее шоу есть в списке", show_before in r.get("names", []), str(show_before))
        r = ask(ws, {"a": "fixtures_fetch"})
        check("получение приборов из MA2", bool(r.get("ok")), f'всего {r.get("total")}' if r.get("ok") else r.get("err", ""))
        r2 = ask(ws, {"a": "fixtures_fetch"})
        check("повторное получение не теряет приборов", bool(r2.get("ok")) and r2.get("total") == r.get("total"), f'{r.get("total")} -> {r2.get("total")}')
        r = ask(ws, {"a": "ma2_read"})
        check("группы MA2 разобраны (List Group)", bool(r.get("groups")), ", ".join(g["name"] for g in r.get("groups", [])[:8]) or r.get("err", "0 групп"))
        check("цветовые пресеты MA2 разобраны (List Preset 4.x)", bool(r.get("colors")), f'{len(r.get("colors", []))} шт.')
    fixtures = fixtures_report()
    with connect(BASE.replace("http", "ws", 1) + "/ws") as ws:
        r = ask(ws, {"a": "select_fixtures", "ids": [f["id"] for f in fixtures[:2]]})
        check("выбор приборов (в режиме test без allowed_fixtures допустим отказ)", True, "разрешён" if r.get("ok") else "отказ: " + str(r.get("err", ""))[:150])
    time.sleep(1)
    d2 = json.loads(get("/api/diag")[1])
    check("шоу на пульте то же, что до проверки", d2["show"].get("name") == show_before, str(d2["show"].get("name")))
    sent = [re.sub(r"^.*? -> ", "", l).split(" | ")[0] for l in log_lines()[start:] if " -> " in l]
    bad = [c for c in sent if not READ_ONLY.match(c)]
    check("за время проверки на пульт ушли только команды чтения", not bad, f"{len(sent)} команд" + (f"; лишние: {bad[:3]}" if bad else ""))


def cli(argv=None):
    global BASE
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = sys.argv[1:] if argv is None else argv
    BASE = (args[0] if args else "http://127.0.0.1:8080").rstrip("/")
    rows.clear()
    try:
        main()
    except Exception as e:
        check("проверка завершилась без сбоя", False, f"{type(e).__name__}: {e}")
    fail = [r for r in rows if not r[1]]
    report = "\n".join(("ОК     " if ok else "ОШИБКА ") + n + (" - " + dt if dt else "") for n, ok, dt in rows)
    try:
        (HERE / "selfcheck-report.txt").write_text(time.strftime("%Y-%m-%d %H:%M:%S") + f"\nОшибок: {len(fail)} из {len(rows)}\n\n" + report + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Не удалось сохранить отчёт selfcheck: {exc}", file=sys.stderr)
        return 1
    print(f"\nОшибок: {len(fail)} из {len(rows)}. Отчёт: selfcheck-report.txt")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(cli())
