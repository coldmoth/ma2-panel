"""Persistent playback fence and offline recovery for an uncertain Cue overwrite."""

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .commands import ActionError
from .fixtures import save_config
from .hall_trial import ENABLED as HALL_TRIAL
from .scenes import canonical_exec, new_scene


def journal_path(config_path, executor):
    return Path(config_path).with_name(f"scene-write-{executor}.json")


def archived_journal_path(config_path, executor):
    return journal_path(config_path, executor).with_suffix(".json.verified")


def generation_path(config_path, show, executor):
    key = hashlib.sha256(json.dumps(show, ensure_ascii=False).encode()).hexdigest()
    return Path(config_path).with_name(f"scene-generation-{key}-{executor}.json")


def read_record(path, show, executor):
    try:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    if not isinstance(record, dict) or record.get("show") != show or record.get("target") != executor:
        raise ValueError(f"Шоу или Executor не совпадает с записью {path.name}")
    return record


@dataclass
class SceneIdentityState:
    generation: dict | None
    active: dict | None
    pending: list[dict]
    covered_archives: set[str]
    pending_archives: set[str]
    reason: str | None

    def require_confirmed(self, executor):
        if self.reason:
            message = {
                "pending_overwrite": "запись сцены не подтверждена: проверьте резерв и журнал восстановления",
                "generation_mismatch": "поколение Cue не подтверждено для этого плана; проверьте восстановление",
                "write_error": "запись сцены не подтверждена: проверьте резерв и журнал",
            }[self.reason]
            raise ActionError(message, code="action_failed", params={"executor": executor, "reason": self.reason})


def archive_fingerprint(record):
    contents = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(contents.encode()).hexdigest()


def scene_identity_state(config_path, show, executor, scene):
    """Read every record for the target. Only a verified generation can cover archives."""
    journal = journal_path(config_path, executor)
    active = read_record(journal, show, executor)
    generation = read_record(generation_path(config_path, show, executor), show, executor)
    pending = []
    covered_archives = set()
    pending_archives = set()
    verified = generation is not None and generation.get("phase") == "verified"
    if generation is not None:
        if verified:
            identity = generation.get("generation")
            covered = generation.get("covered_archives", [])
            if (not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity)
                    or identity == generation.get("previous_identity")
                    or not isinstance(covered, list)
                    or any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in covered)):
                raise ValueError("Некорректная подтверждённая запись поколения Cue")
            covered_archives.update(covered)
        elif generation.get("phase") == "committing":
            pending.append(generation)
        else:
            raise ValueError("Неизвестная фаза записи поколения Cue")

    archives = sorted(path for path in journal.parent.iterdir() if path.name.startswith(journal.name + "."))
    for path in [journal, *archives]:
        record = active if path == journal else read_record(path, show, executor)
        if record is None and path != journal:
            raise ValueError(f"Журнал {path.name} исчез во время проверки")
        if record is None or record.get("phase") == "preparing":
            continue
        if record.get("phase") not in ("committing", "completed"):
            raise ValueError(f"Неизвестная фаза журнала {path.name}")
        if path != journal:
            fingerprint = archive_fingerprint(record)
            if fingerprint in covered_archives:
                continue
            pending_archives.add(fingerprint)
        pending.append(record)

    reason = None
    if pending:
        reason = "pending_overwrite"
    elif scene is not None:
        if scene.get("write_error"):
            reason = "write_error"
        elif (verified and (generation["generation"] != scene.get("cue_generation")
                            or scene.get("identity") == generation.get("previous_identity"))
              or generation is None and scene.get("cue_generation")):
            reason = "generation_mismatch"
    return SceneIdentityState(generation, active, pending, covered_archives, pending_archives, reason)


def recover_scene(config_path, show, executor, *, verified_label, fixtures):
    """Only run with the bridge stopped, after an operator has verified Cue 1 on MA2."""
    if HALL_TRIAL:
        raise ValueError("Восстановление Cue отключено в тестовой сборке LUMA")
    config_path = Path(config_path)
    executor = canonical_exec(executor)
    original = config_path.read_bytes()
    cfg = json.loads(original.decode("utf-8-sig"))
    if not show or cfg.get("show") != show:
        raise ValueError("Имя шоу не совпадает с рабочим планом")
    rows = [row for row in cfg["scenes"] if row["exec"] == executor]
    if len(rows) != 1 or not verified_label.strip() or any(fid < 1 for fid in fixtures):
        raise ValueError("Нужны единственная строка Executor, проверенное имя и корректные номера приборов")
    journal = journal_path(config_path, executor)
    generation = generation_path(config_path, show, executor)
    row = rows[0]
    state = scene_identity_state(config_path, show, executor, row)
    if not state.pending:
        raise ValueError("Нет записи о неопределённой перезаписи этого Executor")
    spares = {canonical_exec(record["spare"]) for record in state.pending if record.get("spare")}
    spare = next(iter(spares)) if len(spares) == 1 else None
    pending = {"show": show, "target": executor, "phase": "committing", "spare": spare,
               "previous_identity": row.get("identity")}
    # Keep the fence closed through every intermediate write, including journal removal.
    save_config(generation, pending)
    identity = new_scene(executor, verified_label)["identity"]
    row.update(identity=identity, cue_generation=identity, label=verified_label, named=True)
    row.pop("write_error", None)
    if fixtures:
        row["fixtures"] = list(dict.fromkeys(fixtures))
    else:
        row.pop("fixtures", None)
    if spare:
        row["backup_exec"] = spare
    else:
        row.pop("backup_exec", None)

    def check_plan():
        if config_path.read_bytes() != original:
            raise ValueError("Рабочий план изменился во время восстановления")

    save_config(config_path, cfg, before_replace=check_plan)
    if read_record(journal, show, executor) != state.active:
        raise ValueError("Активный журнал изменился во время восстановления")
    if state.active is not None:
        journal.unlink()
    save_config(generation, {**pending, "phase": "verified", "generation": identity,
                             "covered_archives": sorted(state.covered_archives | state.pending_archives)})
    scene_identity_state(config_path, show, executor, row).require_confirmed(executor)
    return identity


def main():
    parser = argparse.ArgumentParser(description="Восстановление сцены при остановленном мосте")
    parser.add_argument("--config", required=True)
    parser.add_argument("--show", required=True)
    parser.add_argument("--executor", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--fixtures", nargs="*", type=int, required=True)
    parser.add_argument("--verified-on-ma2", required=True, action="store_true",
                        help="Cue 1 цели и параметры воспроизведения проверены на MA2")
    args = parser.parse_args()
    try:
        identity = recover_scene(args.config, args.show, args.executor,
                                 verified_label=args.label, fixtures=args.fixtures)
    except (ActionError, OSError, ValueError) as exc:
        parser.exit(1, f"Восстановление не завершено: {exc}\n")
    print(f"Executor {args.executor}: сохранён новый UUID {identity}. Запустите мост и обновите вкладки.")


if __name__ == "__main__":
    main()
