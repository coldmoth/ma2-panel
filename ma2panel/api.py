"""HTTP routes of the bridge: settings, diagnostics, probe, fixture file import, stop/restart.

register() is called at the end of bridge.create_app with a snapshot of its locals (c); the route bodies use the same
names as inside create_app, so they read exactly as they did there."""

import asyncio
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import diagnostic_upload

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from .commands import ActionError, failure
from .fixtures import save_config
from .layout_xml import generate_layout_xml, patch_layout_xml, preview_layout_import
from .link import HALTED, NO_LINK, clean
from .safety import DEFAULT_MA2, DEFAULT_SAFETY, load_secret, read_settings_pair, save_settings_pair, validate_settings, without_passwords

log = logging.getLogger("bridge")
LOOPBACK = ("127.0.0.1", "::1")


DIAG_HINTS = [
    (r"login failed", "Проверьте пользователя и пароль в Настройках."),
    (r"вход не подтверждён", "Посмотрите ответ входа ниже и настройте ma2.login_ok_regex."),
    (r"нет приглашения|результат неизвестен", "Пульт не ответил приглашением ]> вовремя. Проверьте на пульте, выполнилась ли команда, сравните сырые ответы, настройте ma2.timeout или ma2.prompt_regex."),
    (r"ЗАБЛОКИРОВАНО защитой: прибор", "Добавьте прибор в разрешённые приборы (allowed_fixtures) в Настройках."),
    (r"сцена .* не разрешена", "Проверьте разрешённые сцены (allowed_scenes) в Настройках."),
    (r"команда не в списке разрешённых", "Имя атрибута отсутствует в сопоставлении или функция не разрешена в этом режиме."),
    (r"ma2 link:", "Проверьте сеть, адрес и порт пульта; включён ли Telnet на пульте."),
    (r"поздний ответ", "Пульт отвечает медленно: увеличьте ma2.timeout в Настройках."),
    (r"не распознан", "Ответ не распознан: посмотрите сырые ответы пульта."),
]

BARE_CONNECT_S = 3  # silence that ends the diagnostics' bare connect; tests shorten it
PROBE_COMMANDS = ["ListVar", "List Fixture", "List Group 1 Thru 999", "List Preset 4.1 Thru 4.999", "List Preset 2.1 Thru 2.999",
                  "List Sequence", "List Executor 1.1 Thru 1.250", "List Page", "List User",
                  # 2026-10-18 open questions: which fixture types have Pan/Tilt, where the executor range ends, a real executor row
                  "List FixtureType", "List Attribute", "List Executor 1.1 Thru 1.100", "List Executor 1.1 Thru 1.200",
                  "List Executor 1.101 Thru 1.130"]  # read-only: nothing here changes the show


def register(app, c, is_loopback):
    HERE = c.HERE
    action_lock, broadcast, cfg, check_show, config_attrs, config_msg, config_path, errors, export_dir, export_folders, import_xml, journal, link, listing, ma2, mask, mode, password, record, run_export_probe, safe_data, safety, save_diag_json, secrets, settings, settings_path, state, throttle = c.action_lock, c.broadcast, c.cfg, c.check_show, c.config_attrs, c.config_msg, c.config_path, c.errors, c.export_dir, c.export_folders, c.import_xml, c.journal, c.link, c.listing, c.ma2, c.mask, c.mode, c.password, c.record, c.run_export_probe, c.safe_data, c.safety, c.save_diag_json, c.secrets, c.settings, c.settings_path, c.state, c.throttle

    @app.post("/api/fixtures/import_file")
    async def import_file(request: Request):
        if not is_loopback(request):
            return JSONResponse(failure("импорт доступен только с самого ПК", "permission_denied"), status_code=403)
        try:
            async with action_lock:
                if state["loading"]:
                    raise ActionError("идёт загрузка шоу", code="show_loading")
                check_show()
                result = import_xml((await request.body()).decode("utf-8-sig"), "file")
                if not result.get("ok"):
                    result = {**result, **failure(mask(result["err"]))}
            await broadcast(config_msg())
        except (ActionError, ValueError, OSError) as e:
            code = e.code if isinstance(e, ActionError) else "plan_io" if isinstance(e, OSError) else None
            result = failure(mask(str(e)), code or "action_failed", getattr(e, "params", None))
        record(request, json.dumps({"a": "fixtures_import_file"}), result)
        return result

    @app.post("/api/fixtures/import_confirm")
    async def import_confirm(request: Request):
        if not is_loopback(request):
            return JSONResponse(failure("импорт доступен только с самого ПК", "permission_denied"), status_code=403)
        try:
            action = await request.json()
            if not isinstance(action, dict):
                raise ValueError("нужен объект подтверждения")
            async with action_lock:
                result = c.confirm_import(action)
            await broadcast(c.status_msg())
            await broadcast(config_msg())
        except (ActionError, ValueError, OSError) as e:
            code = e.code if isinstance(e, ActionError) else "plan_io" if isinstance(e, OSError) else None
            result = failure(mask(str(e)), code or "action_failed", getattr(e, "params", None))
        record(request, json.dumps({"a": "fixtures_import_confirm"}), result)
        return result

    @app.get("/api/layout/ma2/files")
    def layout_ma2_files(request: Request):
        if not is_loopback(request):
            return JSONResponse(failure("импорт и экспорт Layout XML доступны только с самого ПК", "permission_denied"), status_code=403)
        current = cfg.get("ma2_layout")
        has_template = c.load_layout_template(current) is not None
        return {
            "ok": True,
            "export_dir": str(c.layout_write_dir()),
            "files": c.layout_xml_files(),
            "current": current,
            "has_template": has_template,
            "allow_layout_import": safety["allow_layout_import"] is True,
            "ma2_ready": link.ready and not link.halted,
        }

    @app.post("/api/layout/ma2/preview")
    async def layout_ma2_preview(request: Request):
        if not is_loopback(request):
            return JSONResponse(failure("импорт Layout XML доступен только с самого ПК", "permission_denied"), status_code=403)
        try:
            ctype = (request.headers.get("content-type") or "").lower()
            source = "upload"
            source_name = ""
            if "application/json" in ctype:
                body = await request.json()
                if not isinstance(body, dict):
                    raise ActionError("ожидается JSON-объект")
                if isinstance(body.get("xml"), str) and body["xml"].strip():
                    xml_text = body["xml"]
                    source = "upload"
                    source_name = str(body.get("filename") or "")
                elif isinstance(body.get("file"), str) and body["file"].strip():
                    folder_index = body.get("folder_index", 0)
                    xml_text, full_path = c.read_layout_xml_file(body["file"], folder_index)
                    source = "importexport"
                    source_name = Path(full_path).name
                else:
                    raise ActionError("укажите файл из importexport или загрузите XML")
            else:
                xml_text = (await request.body()).decode("utf-8-sig")
                if not xml_text.strip():
                    raise ActionError("пустой XML-файл Layout")
            if len(xml_text.encode("utf-8")) > 10_000_000:
                raise ActionError("файл Layout XML слишком большой (>10 МБ)")
            preview = preview_layout_import(xml_text, cfg["fixtures"])
            import uuid as _uuid
            token = _uuid.uuid4().hex
            state["pending_layout_import"] = {
                "token": token,
                "context": (state["plan_epoch"], c.config_revision()),
                "xml_text": xml_text,
                "source": source,
                "source_name": source_name,
                "preview": preview,
            }
            return {
                "ok": True,
                "preview_token": token,
                "source": source,
                "source_name": source_name,
                "layout_name": preview["layout_name"],
                "xml_fixture_count": preview["xml_fixture_count"],
                "matched_count": len(preview["matched"]),
                "matched": preview["matched"],
                "unmatched_xml_ids": preview["unmatched_xml_ids"],
                "unplaced_plan_ids": preview["unplaced_plan_ids"],
                "extra_elements": preview["extra_elements"],
                "skipped_channel_only": preview["skipped_channel_only"],
                "bounds": preview["bounds"],
            }
        except (ActionError, ValueError, UnicodeDecodeError, OSError) as e:
            code = e.code if isinstance(e, ActionError) else "action_failed"
            return failure(mask(str(e)), code or "action_failed")

    @app.post("/api/layout/ma2/apply")
    async def layout_ma2_apply(request: Request):
        if not is_loopback(request):
            return JSONResponse(failure("импорт Layout XML доступен только с самого ПК", "permission_denied"), status_code=403)
        try:
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("preview_token"), str):
                raise ActionError("нужен preview_token из предпросмотра")
            async with action_lock:
                if state["loading"]:
                    raise ActionError("идёт загрузка шоу", code="show_loading")
                pending = state.get("pending_layout_import")
                if not pending or body["preview_token"] != pending["token"]:
                    raise ActionError("предпросмотр устарел: откройте Layout XML заново")
                if pending["context"] != (state["plan_epoch"], c.config_revision()):
                    state.pop("pending_layout_import", None)
                    raise ActionError("план изменился после предпросмотра: повторите предпросмотр")
                preview = pending["preview"]
                if not preview["matched"]:
                    raise ActionError("нет ни одного совпавшего прибора по Fixture ID")
                template_file = c.save_layout_template(pending["xml_text"])
                by_id = {m["id"]: m for m in preview["matched"]}
                fixtures = []
                for f in cfg["fixtures"]:
                    m = by_id.get(f["id"])
                    if m is None:
                        fixtures.append(f)
                    else:
                        updated = {**f, "x": m["new_x"], "y": m["new_y"]}
                        if m.get("ma2_rot") is not None:
                            updated["rot"] = m["ma2_rot"]
                        fixtures.append(updated)
                layout_meta = {
                    "name": preview["layout_name"] or Path(pending["source_name"]).stem or "MA2 Layout",
                    "source": pending["source"],
                    "source_name": pending["source_name"],
                    "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "template_file": template_file,
                    "bounds": preview["bounds"],
                    "extra_elements": preview["extra_elements"],
                    "matched_count": len(preview["matched"]),
                    "imported_positions": preview["imported_positions"],
                }
                c.save_working_plan({**cfg, "attrs": c.original_attrs, "fixtures": fixtures, "ma2_layout": layout_meta})
                cfg["fixtures"] = fixtures
                cfg["ma2_layout"] = layout_meta
                state.pop("pending_layout_import", None)
                result = {"ok": True, "applied": len(preview["matched"]), "layout": layout_meta}
            await broadcast(config_msg())
        except (ActionError, ValueError, OSError) as e:
            code = e.code if isinstance(e, ActionError) else "plan_io" if isinstance(e, OSError) else "action_failed"
            result = failure(mask(str(e)), code or "action_failed")
        record(request, json.dumps({"a": "layout_ma2_apply"}), result)
        return result

    @app.post("/api/layout/ma2/export")
    async def layout_ma2_export(request: Request):
        if not is_loopback(request):
            return JSONResponse(failure("экспорт Layout XML доступен только с самого ПК", "permission_denied"), status_code=403)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ActionError("ожидается JSON-объект")
            export_mode = body.get("mode", "download")
            if export_mode not in ("download", "save_importexport", "import_to_ma2"):
                raise ActionError("mode должен быть download, save_importexport или import_to_ma2")
            force_new = body.get("force_new") is True
            current_meta = cfg.get("ma2_layout")
            template_xml = None if force_new else c.load_layout_template(current_meta)
            if template_xml is not None and isinstance(current_meta, dict):
                xml_text, summary = patch_layout_xml(template_xml, cfg["fixtures"], current_meta)
                default_name = current_meta.get("name") or cfg.get("show") or "luma_layout"
            else:
                default_name = cfg.get("show") or "luma_layout"
                xml_text, summary = generate_layout_xml(
                    cfg["fixtures"],
                    hall=cfg.get("hall"),
                    name=str(body.get("layout_name") or default_name),
                    show_name=str(cfg.get("show") or ""),
                )
            stem = c.sanitize_layout_stem(body.get("filename") or default_name)
            if export_mode == "download":
                headers = {
                    "Content-Disposition": f'attachment; filename="{stem}.xml"',
                    "X-LUMA-Layout-Mode": summary["mode"],
                    "X-LUMA-Layout-Updated": str(len(summary["updated_ids"])),
                    "X-LUMA-Layout-Extra": str(summary["extra_elements"]),
                }
                return Response(xml_text.encode("utf-8"), media_type="application/xml; charset=utf-8", headers=headers)
            if export_mode == "save_importexport":
                written = c.write_layout_xml_file(xml_text, stem)
                result = {"ok": True, "action": "save_importexport", **written, "summary": summary}
                record(request, json.dumps({"a": "layout_ma2_export", "mode": export_mode}), result)
                return result
            # import_to_ma2: explicit confirmation + safety.allow_layout_import + safe slot check
            if body.get("confirm_import") is not True:
                raise ActionError("для импорта Layout в MA2 требуется отдельное подтверждение", code="confirm_required")
            if safety["allow_layout_import"] is not True:
                raise ActionError("импорт Layout в MA2 запрещён: включите safety.allow_layout_import в настройках", code="permission_denied")
            slot = body.get("slot", 99)
            if type(slot) is not int or not 1 <= slot <= 999:
                raise ActionError("слот Layout должен быть целым числом от 1 до 999")
            async with action_lock:
                if link.halted:
                    raise ActionError(HALTED, code="halted")
                if not link.ready:
                    raise ActionError(NO_LINK, code=link.connection_phase)
                if state["loading"]:
                    raise ActionError("идёт загрузка шоу", code="show_loading")
                check_show()
                await c.check_layout_slot_empty(slot, gen=link._gen, empty_re=c.empty_re)
                written = c.write_layout_xml_file(xml_text, stem)
                imported = await c.import_layout_to_ma2(written["stem"], slot, gen=link._gen, empty_re=c.empty_re, check_slot=False)
                result = {"ok": True, "action": "import_to_ma2", **written, **imported, "summary": summary}
        except (ActionError, ValueError, OSError) as e:
            code = e.code if isinstance(e, ActionError) else "plan_io" if isinstance(e, OSError) else "action_failed"
            result = failure(mask(str(e)), code or "action_failed")
        record(request, json.dumps({"a": "layout_ma2_export", "mode": "import_to_ma2"}), result)
        return result

    @app.get("/api/idle")
    def idle():  # update.py asks this before stopping the bridge: no update while lines are going out
        quiet = time.monotonic() - getattr(app.state, "last_send", -1e9)
        busy = c.update_busy()
        return {"idle": not busy, "quiet_seconds": round(quiet), "ma2": link.state}

    @app.get("/api/log")
    def get_log():
        return list(journal)[::-1]

    @app.post("/api/stop")
    async def stop(request: Request):  # stop.bat only: this PC, with a header a web page cannot add without preflight
        if (request.client.host if request.client else "") not in LOOPBACK or request.headers.get("x-stop") != "1":
            return JSONResponse({"ok": False}, status_code=403)
        log.warning("остановка по запросу stop.bat")
        if server := getattr(app.state, "server", None):
            server.should_exit = True
        return {"ok": True}

    @app.get("/api/settings")
    def get_settings(request: Request):
        if not is_loopback(request):
            return JSONResponse({"ok": False}, status_code=403)
        stored, secret, secret_exists = read_settings_pair(settings_path)
        if not secret_exists:
            secret = secret or password
        # Editable values go back exactly as stored: they are the owner's own settings, and the password never lives in them.
        return {"settings": without_passwords(stored), "password_set": bool(secret),
                "defaults": {"ma2": DEFAULT_MA2, "safety": DEFAULT_SAFETY}, "path": str(settings_path),
                "config_attrs": c.get_config_attrs()}

    @app.post("/api/settings")
    async def put_settings(request: Request):
        if not is_loopback(request):
            return JSONResponse({"ok": False}, status_code=403)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Требуется объект с полем settings")
            proposed = body.get("settings")
            # The channel has its own immediate-save control; stale forms must not reset it.
            if isinstance(proposed, dict):
                stored, _, _ = read_settings_pair(settings_path)
                proposed = {k: v for k, v in proposed.items() if k != 'test_updates'}
                if 'test_updates' in stored:
                    proposed['test_updates'] = stored['test_updates'] is True
            validate_settings(proposed)
            if "password" in body and (not isinstance(body["password"], str) or any(c in body["password"] for c in "\r\n\0")):
                raise ValueError("Пароль должен быть строкой без переноса строки")
            if "clear_password" in body and type(body["clear_password"]) is not bool:
                raise ValueError("clear_password должен быть флажком")
        except (ValueError, TypeError, SystemExit, OverflowError) as e:
            return JSONResponse({"ok": False, "err": mask(f"Неверные настройки: {e}")}, status_code=400)
        try:
            if settings_path.exists():
                folder = settings_path.parent / "backups"
                folder.mkdir(exist_ok=True)
                backup = folder / f"settings-{time.strftime('%Y%m%d-%H%M%S')}.json"
                # Preserve all copies even when two saves happen within one second.
                while backup.exists():
                    backup = backup.with_stem(backup.stem + "-1")
                shutil.copy2(settings_path, backup)
            secret = None
            if "password" in body or body.get("clear_password"):
                secret = "" if body.get("clear_password") else body["password"]
                if secret:
                    secrets.add(secret)
            save_settings_pair(settings_path, proposed, secret)
        except OSError:
            recovery_pending = (settings_path.parent / ".settings-transaction.json").exists()
            err = ("Сохранение прервано: прежняя пара настроек будет восстановлена при чтении или запуске; проверьте доступ к папке"
                   if recovery_pending else "Не удалось сохранить настройки: проверьте доступ к папке")
            return JSONResponse({"ok": False, "err": err, "recovery_pending": recovery_pending}, status_code=500)
        log.info("настройки изменены (без пароля)")
        return {"ok": True, "restart_needed": True}

    @app.post("/api/restart")
    async def restart(request: Request):
        if not is_loopback(request) or request.headers.get("x-stop") != "1":
            return JSONResponse({"ok": False}, status_code=403)
        server = getattr(app.state, "server", None)
        if server is None:
            return JSONResponse({"ok": False, "err": "Перезапуск недоступен: сервер моста не зарегистрирован. Запустите мост через start.bat."}, status_code=503)
        if not await c.update_gate(restart=True):
            reason = c.restart_busy()
            return JSONResponse({"ok": False, "reason": reason, "retry_after": 2,
                                 "err": "Перезапуск отложен: " + reason + ". Повторите после завершения операции."}, status_code=409)
        app.state.exit_code = 3
        server.should_exit = True
        return {"ok": True, "instance": app.state.instance}

    @app.get("/api/restart/status")
    def restart_status(request: Request):
        # Readable across local ports after a settings port change. No credentials
        # or settings are exposed, and arbitrary web origins get no CORS access.
        if not is_loopback(request) or request.url.hostname not in (*LOOPBACK, "localhost"):
            return JSONResponse({"ok": False}, status_code=403)
        origin = request.headers.get("origin", "")
        parsed = urlsplit(origin)
        headers = {"Cache-Control": "no-store", "Vary": "Origin"}
        if parsed.scheme == "http" and parsed.hostname in (*LOOPBACK, "localhost"):
            headers["Access-Control-Allow-Origin"] = origin
        return JSONResponse({"ok": True, "instance": app.state.instance}, headers=headers)

    def export_report():
        """Everything about reading the fixtures that is already known, without sending anything to the console."""
        folders = export_folders()
        probe_txt = HERE / "probe.txt"
        return {"allow_fixture_read": safety["allow_fixture_read"], "dmx_seconds": c.dmx_seconds,
                "export_cmd": ma2["export_cmd"], "export_dir": str(export_dir),
                "export_search": ma2["export_search"], "export_wait": ma2["export_wait"], "console_path": link.vars.get("PATH"),
                "folders": [listing(f, 15) for f in folders], "last_export_file": state["export_file"],
                "last_attempt": state["export_trace"], "active_probe": state["export_probe"], "dmx_read": c.dmx_diagnostics(), "type_reads": state["type_reads"],
                "read_probe_file": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(probe_txt.stat().st_mtime)) if probe_txt.exists() else None}

    @app.get("/api/diag")
    def diagnostics():
        version = HERE / "VERSION"
        if not version.exists():
            version = Path(__file__).parent / "VERSION"
        return safe_data({"ma2": link.state, "login_reply": link.login_reply, "login_vars": link.vars, "last": link.last,
                          "show": state["show"], "export_file": state["export_file"], "raw": list(link.raw)[-50:], "errors": list(errors)[::-1],
                          "version": version.read_text(encoding="utf-8").strip() if version.exists() else "dev",
                          "mode": mode, "host": f'{ma2["host"]}:{ma2["port"]}', "user": ma2["user"], "export": export_report(), "link_attempts": list(link.attempts)[-10:], "link_test": state.get("link_test"),
                          "password_note": "пароль скрыт; короткий пароль скрывается только в строках входа и в secret.env"})

    uploader = c.diagnostic_uploader
    app.state.diagnostic_uploader = uploader

    @app.get("/api/diag/upload")
    def upload_status(request: Request):
        if not is_loopback(request):
            return JSONResponse(failure("Отправка доступна только с самого ПК моста", "permission_denied"), status_code=403)
        return uploader.status()

    @app.post("/api/diag/send")
    @app.post("/api/diag/queue")
    async def upload_diagnostics(request: Request):
        # A foreign web page cannot add this header without preflight; do not enable CORS here.
        origin = request.headers.get("origin")
        try:
            host = urlsplit("http://" + request.headers.get("host", ""))
            parsed = urlsplit(origin or "")
            local_host = host.hostname in ("localhost", "127.0.0.1", "::1")
            valid_origin = not origin or (parsed.scheme in ("http", "https") and parsed.netloc == host.netloc
                                         and not (parsed.path or parsed.query or parsed.fragment or parsed.username))
        except ValueError:
            local_host = valid_origin = False
        if (not is_loopback(request) or not local_host or not valid_origin
                or request.headers.get("x-diag-upload") != "1"):
            return JSONResponse(failure("Откройте диагностику через localhost на самом ПК моста", "permission_denied"), status_code=403)
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 8192:
                    raise ValueError()
            body = json.loads(raw)
            if (not isinstance(body, dict) or "report_id" not in body or set(body) - {"report_id", "description"}
                    or not isinstance(body.get("description", ""), str) or len(body.get("description", "")) > 1000):
                raise ValueError()
        except (ValueError, UnicodeError):
            return JSONResponse({"ok": False, "err": "Нужен идентификатор и описание до 1000 символов (запрос до 8 КБ)"}, status_code=400)
        # Snapshot is built on the event loop; network/filesystem work runs off it, without action_lock.
        private = list(secrets | {link.password})
        for source in (link.vars, ma2, cfg):
            private.extend(str(source.get(k)) for k in ("USER", "USERPROFILE", "SHOWFILE", "PATH", "user", "host", "show")
                           if source.get(k))
        def private_names(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("label", "name", "type", "show") and isinstance(item, str):
                        private.append(item)
                    elif isinstance(item, (list, dict)):
                        private_names(item)
            elif isinstance(value, list):
                for item in value:
                    private_names(item)
        private_names(cfg)
        snapshot = diagnostics()
        readback_snapshot = diagnostic_upload.build_report(snapshot, cfg, private, mock=bool(c.mock)).get('readback')
        config_counts = {key: len(cfg.get(key, [])) for key in ("fixtures", "groups", "scenes")}
        description = body.get("description", "").strip()
        for value in sorted(set(private) - {""}, key=len, reverse=True):
            description = description.replace(value, "[скрыто]")
        captured_at = datetime.now(timezone.utc).isoformat()
        # Only counts and anonymized numeric maps cross into the worker, not the mutable live config.
        def collect():
            report = diagnostic_upload.collect_report(snapshot, {}, private, mock=bool(c.mock), root=HERE,
                                                      readback=readback_snapshot)
            report["counts"] = config_counts
            report["description"] = description
            report["captured_at"] = captured_at
            return report
        if request.url.path == "/api/diag/queue":
            result = await asyncio.to_thread(uploader.enqueue, body["report_id"], collect)
            uploader.wake()
            return result
        return await asyncio.to_thread(uploader.submit, body["report_id"], collect)

    @app.post("/api/diag/link_test")
    async def link_test(request: Request):
        """Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare TCP connect with no login."""
        if not is_loopback(request):
            return JSONResponse(failure("доступно только с самого ПК", "permission_denied"), status_code=403)
        report = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "state": link.state, "attempts": list(link.attempts)[-10:], "target": f"{link.host}:{link.port}"}
        if os.name == "nt":
            for key, cmd in (("netstat", ["netstat", "-ano"]), ("python_processes", ["tasklist", "/fi", "imagename eq python.exe", "/fo", "csv"]),
                             ("ma2_processes", ["tasklist", "/fi", "imagename eq gma2*", "/fo", "csv"])):
                try:
                    out = (await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=15, errors="replace")).stdout
                    keep = [line for line in out.splitlines() if key != "netstat" or f":{link.port} " in line or f":{(settings or {}).get('port', cfg.get('port', 8080))} " in line]
                    report[key] = keep[:60]
                except (OSError, subprocess.SubprocessError) as e:
                    report[key] = f"не выполнено: {type(e).__name__}: {e}"
        if not link.manual:
            report["bare_connect"] = "пропущено: у моста включено автоподключение; чтобы сделать пробное соединение, сначала нажмите на Площадке «Разорвать связь»"
        else:
            started, got, end = time.monotonic(), b"", f"таймаут {BARE_CONNECT_S} с: пульт молчит и держит соединение"
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(link.host, link.port), BARE_CONNECT_S)
                try:
                    while data := await asyncio.wait_for(reader.read(4096), BARE_CONNECT_S):
                        got += data
                        if len(got) > 4096:
                            break
                    else:
                        end = "EOF: пульт закрыл соединение"
                except TimeoutError:
                    pass
                except OSError as e:
                    end = f"{type(e).__name__}: {e}"
                writer.close()
            except (OSError, TimeoutError) as e:
                end = f"не удалось подключиться: {type(e).__name__}: {e}"
            report["bare_connect"] = {"bytes": len(got), "first_text": clean(got)[:200].decode(errors="replace"), "end": end,
                                      "ms": round((time.monotonic() - started) * 1000)}
        state["link_test"] = report
        save_diag_json("link_test.json", safe_data(report))
        return {"ok": True, **report}

    @app.post("/api/diag/export_probe")
    async def export_probe(request: Request):
        # Active: creates a few diagnostic export files in the console's importexport folder; the show, patch and output stay untouched.
        if not is_loopback(request):
            return JSONResponse(failure("доступно только с самого ПК", "permission_denied"), status_code=403)
        if safety["allow_fixture_read"] is not True:
            return failure("экспорт не разрешён: включите «Разрешить получение приборов из MA2» в настройках", "permission_denied")
        async with action_lock:
            if link.halted:
                return failure(HALTED, "halted")
            if not link.ready:
                return failure(NO_LINK, link.connection_phase)
            if state["loading"]:
                return failure("идёт загрузка шоу", "show_loading")
            try:
                return {"ok": True, **await run_export_probe()}
            except OSError as e:
                return failure(mask(f"проверка экспорта прервана: {e}"))

    @app.post("/api/probe")
    async def probe_console():
        async with action_lock:
            if link.halted:
                return failure(HALTED, "halted")
            if not link.ready:
                return failure(NO_LINK, link.connection_phase)
            results = []
            out = [f"ma2 state: {link.state}"]
            for cmd in PROBE_COMMANDS:
                ok, reply = await link.send(cmd)
                reply = mask(reply)
                results.append({"cmd": cmd, "ok": ok, "reply": reply})
                out.append(f"### {cmd}  (ok={ok})\n{reply!r}\n{reply}")
            (HERE / "probe.txt").write_text(mask("\n".join(out)), encoding="utf-8")
            return {"ok": True, "results": results}

    @app.get("/api/diag.zip")
    def diagnostic_package():
        """Only reads what is already on disk or in memory: nothing is sent to the console. One failing part never blocks the rest."""
        files, problems = {}, []

        def part(name, make):
            try:
                files[name] = make()
            except Exception as e:  # a partial report is better than none
                problems.append(f"{name}: {type(e).__name__}: {e}")

        def read(path):
            return path.read_text(encoding="utf-8", errors="replace")

        for name in ("bridge.log", "bridge.log.1", "bridge.log.2", "bridge.log.3", "probe.txt", "update.log"):
            if (HERE / name).exists():
                part(name, lambda name=name: read(HERE / name))
        for name, path in (("settings.json", settings_path), ("config.json", Path(config_path))):
            part(name, lambda path=path: json.dumps(safe_data(without_passwords(json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {})),
                                                    ensure_ascii=False, indent=2))
        diag_dir = Path(config_path).parent / "diag"
        for name in ("last_export.xml", "export_trace.json", "export_probe.json", "link_test.json"):
            if (diag_dir / name).exists():
                part("diag/" + name, lambda name=name: read(diag_dir / name))
        if (diag_dir / "last_export.xml").exists():
            part("diag/last_export.meta.txt", lambda: "изменён " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime((diag_dir / "last_export.xml").stat().st_mtime)))
        for extra in sorted((HERE / "field-data" / "auto").glob("*.txt"))[-3:]:  # replies captured at bridge start
            part("auto/" + extra.name, lambda extra=extra: read(extra))
        for extra in sorted((diag_dir / "export_probe").glob("*.xml"))[:10]:
            part("diag/export_probe/" + extra.name, lambda extra=extra: read(extra))
        diag = {}
        try:
            diag = diagnostics()
            files["diag.json"] = json.dumps(diag, ensure_ascii=False, indent=2)
        except Exception as e:
            problems.append(f"diag.json: {type(e).__name__}: {e}")
        part("journal.json", lambda: json.dumps(safe_data(list(journal)), ensure_ascii=False, indent=2))
        version = HERE / "VERSION"
        if not version.exists():
            version = Path(__file__).parent / "VERSION"
        files["VERSION"] = diag.get("version") or (read(version).strip() if version.exists() else "dev")
        if problems:
            files["collect_errors.txt"] = "\n".join(problems)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, mask(content))
        return Response(buffer.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="ma2-diag-{time.strftime("%Y%m%d-%H%M%S")}.zip"'})

    from . import quality_diagnostics
    def quality_snapshot():
        from copy import deepcopy
        from types import SimpleNamespace
        root = Path(config_path).parent
        pending = quality_diagnostics.recovery_pending(root)
        snapshot = {key: deepcopy(state.get(key, {})) for key in ('show', 'read_freshness', 'type_reads')}
        snapshot.update(values_meta=c.values_meta(), recovery_pending=pending, mock=c.mock)
        connection = SimpleNamespace(ready=link.ready, state=link.state, halted=link.halted, vars=dict(link.vars))
        return deepcopy(cfg), deepcopy({**settings, 'safety': safety, 'dmx_seconds': c.dmx_seconds}), snapshot, connection
    quality_diagnostics.register(app, quality_snapshot, is_loopback, root=Path(config_path).parent)
