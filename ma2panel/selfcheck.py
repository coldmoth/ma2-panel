"""Read-only self-check of a running bridge: python\\python.exe selfcheck.py [http://127.0.0.1:8080]

Passive: reads cached readiness and static resources over HTTP. No console commands,
exports, selection, WebSocket actions, safety changes or log-based proof of success.
Report: selfcheck-report.txt next to this file (no password in it).
"""
import json, sys, time, urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:8080"
HERE = Path(__file__).resolve().parent.parent
rows = []


def check(name, ok, detail=""):
    rows.append((name, ok, detail))
    print(("ОК     " if ok else "ОШИБКА ") + name + (" - " + detail if detail else ""))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.status, r.read()


def main():
    """Read cached readiness; never run WS actions or infer safety from missing logs."""
    d = json.loads(get("/api/diag")[1])
    check("мост отвечает, версия", True, d["version"])
    report = json.loads(get("/api/quality/readiness")[1])
    checks = report.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("нет пассивного отчёта готовности; обновите программу целиком")
    for item in checks:
        passed = item.get("status") == "pass"
        check(item.get("id", "неизвестная проверка"), passed,
              item.get("reason", "") + ("" if passed else " " + item.get("action", "")))
    for page in ("/", "/settings.html", "/diag.html", "/app.js", "/light.js", "/move.js", "/plan.js"):
        try:
            code, body = get(page)
            check(f"страница {page}", code == 200 and len(body) > 100, f"{len(body)} байт")
        except Exception as error:
            check(f"страница {page}", False, str(error))


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
