"""Files the console writes on export (fixtures, fixture types, diagnostics probes): moved out of bridge.create_app.

bind() runs inside create_app with the objects the bridge already owns; the functions are the same closures as before.
"""
import asyncio
import glob
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

from commands import ActionError
from fixtures import parse_fixture_type

log = logging.getLogger("bridge")


def bind(link, ma2, export_dir, export_extra, state, config_path, safe_data):
    def export_folders():
        """Where an export may land: ma2.export_dir first, then every existing folder matching ma2.export_search."""
        # hall 2026-10-18: Export Fixture lands in <install>\fixtures, next to importexport (Layers etc. land in importexport)
        found = [Path(export_dir), Path(export_dir).parent / "fixtures"]
        for pattern in ma2["export_search"]:
            found.extend(Path(d) for d in sorted(glob.glob(pattern)))
        return list(dict.fromkeys(found))

    def listing(folder, newest=30):
        if not folder.is_dir():
            return {"dir": str(folder), "exists": False}
        rows = []
        for entry in folder.iterdir():
            try:
                st = entry.stat()
            except OSError:
                continue
            rows.append({"name": entry.name, "dir": entry.is_dir(), "size": st.st_size,
                         "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)), "_t": st.st_mtime})
        rows.sort(key=lambda r: r["_t"], reverse=True)
        return {"dir": str(folder), "exists": True, "count": len(rows),
                "newest": [{k: v for k, v in r.items() if k != "_t"} for r in rows[:newest]]}

    def save_diag_json(name, data):
        try:
            folder = Path(config_path).parent / "diag"
            folder.mkdir(exist_ok=True)
            (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            log.warning("не удалось записать diag/%s: %s", name, e)

    async def export_type(no):
        """One Export FixtureType under a one-off name. The documentation puts fixture types in their own library folder
        without naming it, so the file is looked for by name in the console's folders and one level below them."""
        unique = f"panel_type{no}_{time.strftime('%H%M%S')}"
        cmd = f'Export FixtureType {no} "{unique}"'
        install = link.vars.get("PATH", "")
        roots = list(dict.fromkeys([Path(export_dir).parent, *([Path(install).parent] if install else []), *export_folders()]))
        trace = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "cmd": cmd, "roots": [str(r) for r in roots]}
        state["type_reads"][str(no)] = trace
        export_extra.add(cmd)
        try:
            ok, reply = await link.send(cmd)
            trace["reply"] = " ".join(reply.split())[:600]
            if not ok:
                raise ActionError(f"экспорт типа не выполнен: {trace['reply'][:200] or 'ошибка пульта'}")
            deadline = time.monotonic() + float(ma2["export_wait"])
            while True:
                hits = [p for r in roots if r.is_dir() for pattern in (f"*{unique}*.xml", f"*/*{unique}*.xml") for p in r.glob(pattern)]
                if hits:
                    await asyncio.sleep(.3)  # MA2 may still be writing
                    text = hits[0].read_text(encoding="utf-8-sig")
                    for p in hits:
                        p.unlink(missing_ok=True)  # our own one-off file
                    (Path(config_path).parent / "diag").mkdir(exist_ok=True)
                    (Path(config_path).parent / "diag" / f"fixture_type_{no}.xml").write_text(text, encoding="utf-8")
                    spec = parse_fixture_type(text)
                    trace.update(file=str(hits[0]), size=len(text), spec=spec)
                    return spec
                if time.monotonic() >= deadline:
                    raise ActionError(f"файл экспорта типа {no} не появился за {ma2['export_wait']} с")
                await asyncio.sleep(.3)
        except Exception as e:
            trace["error"] = str(e)
            raise
        finally:
            export_extra.discard(cmd)

    async def export_once(cmd, kind, parse, trace_file):
        """One export under a name nobody has used, read from the console's folders, then removed. Caller checks the link."""
        name = re.search(r'"([^"/\\]+)"', cmd)
        if not name or name[1] in (".", ".."):
            raise ActionError("нет безопасного имени файла экспорта")
        # hall 2026-10-18: a fixed name made MA2 answer "There already exists" and wait for a click in its window, which froze onPC.
        # A name nobody has used cannot collide; the guard learns this one exact line, like a diagnostics probe line.
        unique = f"{name[1]}_{time.strftime('%H%M%S')}"
        cmd = cmd.replace(f'"{name[1]}"', f'"{unique}"', 1)
        file_name = (f"{unique}.xml", f"{kind}-{unique}.xml")  # MA2 3.9.60 prefixes the object type for Export Fixture
        export_extra.add(cmd)
        folders = export_folders()
        trace = state["export_trace"] = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "cmd": cmd, "expected_file": " | ".join(file_name),
                                         "export_wait": ma2["export_wait"], "folders": [str(f) for f in folders]}
        try:
            return await run_export(cmd, file_name, folders, trace, parse)
        except (ActionError, ValueError) as e:
            trace["error"] = str(e)
            raise
        finally:
            export_extra.discard(cmd)
            for f in folders:
                for n in file_name:
                    try:
                        (f / n).unlink(missing_ok=True)  # our own one-off file, never the console's data
                    except OSError:
                        pass
            save_diag_json(trace_file, safe_data(trace))

    async def run_export(cmd, file_name, folders, trace, parse):
        # An old copy would make MA2 ask for an overwrite confirmation (the guard never lets /Overwrite out) and could be
        # mistaken for a new export: remove our own file name from every folder first.
        for folder in folders:
            try:
                for n in file_name:
                    (folder / n).unlink(missing_ok=True)
            except OSError as e:
                raise ActionError(f"не удалось удалить старый экспорт: {e}") from e
        sent_at = time.time()
        ok, reply = await link.send(cmd)
        trace.update(sent_ok=ok, reply=" ".join(reply.split())[:1500])
        if not ok:
            raise ActionError(f"команда экспорта не выполнена: {' '.join(reply.split())[:300] or 'ошибка пульта'}")
        deadline = time.monotonic() + float(ma2["export_wait"])
        while True:
            file = next((f / n for f in folders for n in file_name if (f / n).is_file()
                         and (f == folders[0] or (f / n).stat().st_mtime >= sent_at)), None)
            if file:
                st = file.stat()
                trace["file"] = {"path": str(file), "size": st.st_size,
                                 "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}
                try:
                    text = file.read_text(encoding="utf-8-sig")
                    log.info("экспорт: %s (%s байт)", file, st.st_size)
                    return parse(text, str(file))
                except (ValueError, UnicodeDecodeError, OSError) as e:
                    trace["parse_error"] = str(e)
                    # MA2 may still be writing: retry only while the size is changing.
                    await asyncio.sleep(.3)
                    if time.monotonic() < deadline and file.is_file() and file.stat().st_size != st.st_size:
                        continue
                    raise ActionError(f"файл экспорта получен ({file}, {st.st_size} байт), но не разобран: {e}") from e
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(.2)
        fresh = [str(p) for f in folders if f.is_dir() for p in f.iterdir() if p.is_file() and p.stat().st_mtime >= sent_at - 1]
        trace["new_files"], trace["folders_exist"] = fresh, {str(f): f.is_dir() for f in folders}
        missing = [str(f) for f in folders if not f.is_dir()]
        raise ActionError(
            f"файл «{' / '.join(file_name)}» не появился за {ma2['export_wait']} с, хотя пульт принял команду без ошибки. "
            f"Искали в: {', '.join(str(f) for f in folders)}"
            + (f". Нет такой папки: {', '.join(missing)}" if missing else "")
            + (f". Новые файлы там: {', '.join(Path(x).name for x in fresh[:5])}" if fresh else ". Новых файлов там нет")
            + ". Скачайте диагностику и запустите «Проверить экспорт» на странице диагностики")

    def snapshot(roots, depth=4, cap=30000):
        """{path: (size, mtime)} of the files under roots, bounded. No disk-wide scan: only the console's own folders."""
        seen, truncated = {}, False
        for root in roots:
            root = Path(root)
            if not root.is_dir():
                continue
            base = len(root.parts)
            for dirpath, dirnames, filenames in os.walk(root):
                if len(Path(dirpath).parts) - base >= depth:
                    dirnames[:] = []
                for n in filenames:
                    path = os.path.join(dirpath, n)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    seen[path] = (st.st_size, st.st_mtime)
                    if len(seen) >= cap:
                        return seen, True
        return seen, truncated

    async def run_export_probe():
        """Active diagnostics: sends a few export lines under unique names and reports which files appeared where."""
        stamp = time.strftime("%H%M%S")
        variants = [("help", "Export /?"),
                    ("fixture", f'Export Fixture 1 Thru 9999 "panel_diag_fixture_{stamp}"'),
                    ("fixture_nc", f'Export Fixture 1 Thru 9999 "panel_diag_fixture_nc_{stamp}" /nc'),
                    ("channel", f'Export Channel 1 Thru 9999 "panel_diag_channel_{stamp}"'),
                    ("layers", f'Export Root LiveSetup.Layers "panel_diag_layers_{stamp}"')]
        folders = export_folders()
        install = link.vars.get("PATH", "")
        roots = [Path(install).parent] if install and Path(install).parent.is_dir() else []
        roots += [f for f in folders if not any(r in f.parents for r in roots)]
        before, truncated = snapshot(roots)
        results = []
        out = Path(config_path).parent / "diag" / "export_probe"
        shutil.rmtree(out, ignore_errors=True)
        try:
            for key, cmd in variants:
                export_extra.add(cmd)
                started = time.time()
                ok, reply = await link.send(cmd)
                await asyncio.sleep(min(float(ma2["export_wait"]), 2))
                after, truncated_now = snapshot(roots)
                new = sorted((p, v) for p, v in after.items() if p not in before or before[p] != v)
                before, truncated = after, truncated or truncated_now
                copied = []
                for path, (size, mtime) in new:
                    if path.lower().endswith(".xml") and size <= 2_000_000 and len(copied) < 3:
                        out.mkdir(parents=True, exist_ok=True)
                        target = out / f"{key}-{Path(path).name}"
                        try:
                            shutil.copyfile(path, target)
                            copied.append(str(target.relative_to(out.parent.parent)))
                        except OSError:
                            pass
                results.append({"key": key, "cmd": cmd, "ok": ok, "reply": " ".join(reply.split())[:1500],
                                "new_files": [{"path": p, "size": v[0], "mtime": time.strftime("%H:%M:%S", time.localtime(v[1]))} for p, v in new[:40]],
                                "copied": copied, "seconds": round(time.time() - started, 1)})
        finally:
            export_extra.clear()
        probe = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "install_path": install, "roots": [str(r) for r in roots],
                 "truncated": truncated, "folders": [listing(f) for f in folders], "results": results}
        state["export_probe"] = probe
        save_diag_json("export_probe.json", safe_data(probe))
        return probe

    return SimpleNamespace(export_folders=export_folders, listing=listing, save_diag_json=save_diag_json, export_type=export_type,
                           export_once=export_once, run_export_probe=run_export_probe)
