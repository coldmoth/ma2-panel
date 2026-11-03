"""Telnet link to grandMA2: login, one line at a time, prompt matching, and the slider Throttle."""

import asyncio
import logging
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable

from commands import is_error_reply
from safety import redact

log = logging.getLogger("bridge")
NO_LINK = "нет связи с пультом"
HALTED = "передача остановлена кнопкой «Остановить передачу»"
UNKNOWN = ("результат неизвестен: пульт не ответил приглашением ]> вовремя. Команда могла выполниться. "
           "Повторно не отправлена: проверьте на пульте")
STALE = "не отправлена: предыдущая команда осталась без ответа, соединение с пультом переоткрыто. Повторите действие"
LOGIN_OK = re.compile(r"(?i)logged\s*in")  # MA2 3.9: "Logged in as User 'Remote'"; ma2.login_ok_regex in settings.json
VALUE_LINE = re.compile(r"(At |Attribute )")
PROMPT = re.compile(rb"\]>\s*$")  # matched on clean() text: MA2 3.9 wraps it as \x1b[32m[Group]>\x1b[37m\x1b[K
# ANSI CSI/escape sequences and Telnet IAC negotiation: removed before any reply is matched, logged or shown
CONTROL = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]|\xff[\xfb-\xfe][\x00-\xff]|\xff[\xf0-\xfa\xff]")
USER_VAR = re.compile(r'(?im)^\s*(?:\w+\s*:\s*)?\$USER\s*[=:]\s*"?([^"\r\n]*?)"?\s*$')
VAR = re.compile(r'(?im)^\s*(?:\w+\s*:\s*)?\$(USER|USERRIGHTS|USERPROFILE|VERSION|SHOWFILE|PATH)\s*[=:]\s*"?([^"\r\n]*?)"?\s*$')


class Throttle:
    def __init__(self, rate_hz: float, send: Callable[[str, dict], Awaitable[None]]):
        self._interval = 1 / rate_hz
        self._send = send
        self._pending: dict[str, dict] = {}
        self.fades: dict[str, asyncio.Task] = {}  # fades the bridge plays as a run of values; clear() and stop() end them

    def put(self, key: str, action: dict) -> None:
        self._pending[key] = action

    def pending(self, key: str) -> dict | None:
        return self._pending.get(key)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.flush_all()
            except Exception:  # one failed send (a tablet gone mid-reply) must not stop every slider until restart
                log.exception("throttle: отправка значения не удалась")

    async def flush_all(self) -> None:
        for key in list(self._pending):  # popped one by one, so flush still sees keys not sent yet
            await self.flush(key)

    async def flush(self, key: str) -> None:
        # No await between pop and execute() taking action_lock: a popped action holds or queues for the lock
        # before any later action can, so callers that then take action_lock run after it.
        action = self._pending.pop(key, None)
        if action is not None:
            await self._send(key, action)

    def stop(self, prefix: str) -> None:
        """End running fades and drop waiting values whose key starts with prefix."""
        for key in [k for k in self.fades if k.startswith(prefix)]:
            self.fades.pop(key).cancel()
        for key in [k for k in self._pending if k.startswith(prefix)]:
            del self._pending[key]

    def clear(self) -> None:
        self.stop("")


RECONNECT_S = 3  # pause before the next connect after a drop; tests shorten it (tests/conftest.py)
REPLY_S = 2  # reply wait when the caller gives none (the bridge passes ma2.timeout)
READY = ("logged_in",)  # the only state in which commands may go out: login confirmed by ListVar $USER


def clean(data: bytes) -> bytes:
    return CONTROL.sub(b"", data).replace(b"\r", b"")


class MA2Link:
    """One Telnet connection. Sends go one at a time; a drop discards everything waiting.

    States: down, tcp (socket open, login not answered yet), login_failed (error reply, or ListVar shows another user),
    login_unknown (no error, but ListVar did not confirm the user: nothing is sent, retried in 30 s), logged_in (the login
    reply had no error and ListVar returned $USER equal to the configured user), manual_off (dropped by the operator's
    button, no reconnect until link_connect). A prompt or an open port alone never counts as a login.
    Every sent line ends as one of: sent (the prompt came back and the reply has no error words: NOT proof the console did
    what was meant), error (error words in the reply), unknown (no prompt in time: the line may or may not have run).
    Nothing is ever sent twice: an unknown line is reported and never retried.
    """

    def __init__(self, host: str, port: int, user: str, password: str, on_state: Callable[[str], None],
                 guard: Callable[[str], str | None] | None = None, require_prompt: bool = True,
                 prompt: re.Pattern = PROMPT, login_ok: re.Pattern = LOGIN_OK, timeout: float | None = None,
                 on_result: Callable[[dict], None] | None = None):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.on_state = on_state
        self.on_result = on_result or (lambda entry: None)
        self.guard = guard
        self.require_prompt = require_prompt
        self.prompt = prompt
        self.login_ok = login_ok
        self.timeout = REPLY_S if timeout is None else timeout
        self.state = "down"
        self.login_reply = ""  # raw login answer, password masked: diagnostics show it
        self.vars: dict[str, str] = {}
        self.listvar = ""  # the login check's ListVar reply: the show name is read from it, no second ListVar  # $USER, $USERRIGHTS, $USERPROFILE, $VERSION, $SHOWFILE from the login check
        self.last: dict | None = None  # the last line's result, for the status bar
        self.attempts: deque[dict] = deque(maxlen=30)  # one row per connection attempt: stage, exact exception, bytes, timing
        self._stage, self._rx, self._end = "idle", 0, ""
        self.raw: deque[dict] = deque(maxlen=200)  # raw replies, password masked: diagnostics package
        self._targeted = False  # a Fixture line went out in this action: value lines are refused without one
        self._halted = False  # "Остановить передачу": no line leaves the bridge until resume
        self._stop_epoch = 0  # a stop/resume cycle cannot revive an already admitted line
        self.manual = False  # "Разорвать связь с MA2": only this bridge's Telnet session, no reconnect until link_connect
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._writer: asyncio.StreamWriter | None = None
        self._buf = b""
        self._got = asyncio.Event()
        self._closed = asyncio.Event()
        self._stale = False  # the previous line timed out: its late answer may still arrive and must not count for the next
        self._gen = 0  # bumped on every drop: commands queued before it never run

    @property
    def ready(self) -> bool:
        return self.state in READY

    @property
    def halted(self) -> bool:
        return self._halted

    @halted.setter
    def halted(self, value):
        if value:
            self._stop_epoch += 1
        self._halted = value

    def mask(self, text: str) -> str:
        return redact(text, {self.password})

    def _set(self, state: str) -> None:
        if state != self.state:
            log.info("ma2 %s", state)
            self.state = state
            self.on_state(state)

    async def run(self) -> None:
        while True:
            if self.manual:
                self._set("manual_off")
                self._wake.clear()
                while self.manual:
                    await self._wake.wait()
                    self._wake.clear()
                continue
            loop = asyncio.get_running_loop()
            attempt = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "stage": "connect", "target": f"{self.host}:{self.port}"}
            self.attempts.append(attempt)
            started = loop.time()
            self._stage, self._rx, self._end = "connect", 0, ""
            try:
                reader, self._writer = await asyncio.open_connection(self.host, self.port)
                attempt["local"] = str(self._writer.get_extra_info("sockname"))
                attempt["peer"] = str(self._writer.get_extra_info("peername"))
                self._buf = b""
                self._stale = False
                self._closed.clear()
                pump = asyncio.create_task(self._pump(reader))
                try:
                    self._set("tcp")
                    self.vars = {}
                    self._stage = "greeting"
                    greeting, _ = await self._collect(2)  # ends at the greeting's prompt, so it is not read as the login reply
                    if self._closed.is_set():  # nothing to log in to: do not write the login line into a dead socket
                        raise ConnectionError("пульт закрыл соединение до приветствия")
                    if greeting.strip():
                        self._raw("(приветствие пульта)", "late", greeting)
                    self._stage = "login"
                    state = await self._login()
                    self._set(state)
                    if state != "logged_in":
                        self._gen += 1
                        await self._sleep(30)  # password fixed on the console: no bridge restart needed
                        continue
                    self._stage = "logged_in"
                    await self._closed.wait()
                    attempt.update(stage="logged_in", error="соединение закрыто", bytes_received=self._rx,
                                   ms_since_connect=round((loop.time() - started) * 1000), connection_end=self._end)
                    log.warning("ma2 link: соединение закрыто после %s с работы: %s", attempt["ms_since_connect"] // 1000, self._end)
                finally:
                    pump.cancel()
                    self._writer.close()
            except OSError as e:
                attempt.update(stage=self._stage, error=f"{type(e).__name__}: {e}", bytes_received=self._rx,
                               ms_since_connect=round((loop.time() - started) * 1000), connection_end=self._end or "не завершено удалённой стороной")
                log.warning("ma2 link: этап «%s»: %s: %s; получено %s байт, через %s мс после подключения; конец соединения: %s",
                            self._stage, type(e).__name__, e, self._rx, attempt["ms_since_connect"], attempt["connection_end"])
            self._gen += 1
            if not self.manual:
                self._set("down")
                await self._sleep(RECONNECT_S)

    async def _login(self) -> str:
        """logged_in only when the login reply has no error AND ListVar names the configured user."""
        # the password is written to the socket only: not logged, not stored, not sent to browsers (the echo is masked)
        reply, seen = await self._exchange(f'login "{self.user}" "{self.password}"', self.timeout)
        self.login_reply = self.mask(reply)
        flat = " ".join(self.login_reply.split())
        self._raw("login (пароль скрыт)", "error" if is_error_reply(reply) else "sent" if seen else "unknown", reply)
        if is_error_reply(reply):
            log.error("ma2 login failed: %s", flat)
            return "login_failed"
        if not seen:  # the late rest of the login reply must not be read as the ListVar answer
            log.warning("после login нет приглашения ]> за %s с: вход не подтверждён (ответ: %s)", self.timeout, flat)
            return "login_unknown"
        if not self.login_ok.search(reply):
            log.warning("ответ входа не совпал с login_ok_regex (%s): проверяю пользователя через ListVar", flat)
        listvar, seen = await self._exchange("ListVar", max(5.0, self.timeout))
        self._raw("ListVar (проверка входа)", "sent" if seen else "unknown", listvar)
        self.vars = {k.upper(): v.strip() for k, v in VAR.findall(listvar)}
        self.listvar = listvar if seen else ""
        user = self.vars.get("USER")
        if seen and user is not None and user.casefold() == self.user.casefold():
            log.info("вход подтверждён: пользователь %s, права %s, профиль %s, MA2 %s, шоу %s", user,
                     self.vars.get("USERRIGHTS", "?"), self.vars.get("USERPROFILE", "?"), self.vars.get("VERSION", "?"),
                     self.vars.get("SHOWFILE", "?"))
            return "logged_in"
        if user:
            log.error("ma2 login failed: ListVar сообщает пользователя %r, в настройках %r", user, self.user)
            return "login_failed"
        log.warning("вход не подтверждён: ListVar не вернул $USER%s", "" if seen else " (нет приглашения ]>)")
        return "login_unknown"

    async def _sleep(self, seconds: float) -> None:
        """Waits before the next attempt; link_connect cuts it short."""
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), seconds)
        except TimeoutError:
            pass

    def disconnect(self) -> None:
        """Closes only this bridge's Telnet session. The console, its network and other sessions are not touched."""
        self.manual = True
        self._wake.set()
        self.close()

    def connect(self) -> None:
        self.manual = False
        self._wake.set()

    def new_action(self) -> None:
        self._targeted = False

    def close(self) -> None:
        if self._writer:
            self._writer.close()

    def _raw(self, cmd: str, status: str, reply: str) -> None:
        self.raw.append({"t": time.strftime("%H:%M:%S"), "cmd": cmd, "status": status, "reply": self.mask(reply)})

    def _result(self, cmd: str, status: str, text: str) -> None:
        self.last = {"t": time.strftime("%H:%M:%S"), "cmd": cmd, "status": status, "text": self.mask(text)}
        self.on_result(self.last)

    async def send(self, cmd: str, quiet: bool = False, gen: int | None = None) -> tuple[bool, str]:
        """(ok, reply or reason). ok means status "sent". gen: the link generation the caller started under; a drop
        and reconnect in between refuses the line."""
        if self.halted:
            return False, HALTED
        if self.guard and (why := self.guard(cmd)):
            log.error("ЗАБЛОКИРОВАНО защитой: %s (%s)", cmd, why)
            self._result(cmd, "not_sent", f"заблокировано защитой: {why}")
            return False, f"заблокировано защитой: {why}"
        stop_epoch = self._stop_epoch
        gen = self._gen if gen is None else gen
        async with self._lock:
            if self.halted or stop_epoch != self._stop_epoch:
                return False, HALTED
            if not self.ready or gen != self._gen or self._closed.is_set():
                return False, NO_LINK
            if VALUE_LINE.match(cmd) and not self._targeted:
                log.error("ЗАБЛОКИРОВАНО: %s без строки Fixture в этом действии", cmd)
                return False, "значение без явного выбора приборов"
            try:
                if self._stale and not await self._drain():
                    self.close()  # the reconnect logs in afresh; nothing waiting is resent
                    log.warning("-> %s | НЕ ОТПРАВЛЕНО: предыдущая команда так и осталась без ответа, соединение переоткрыто", cmd)
                    self._result(cmd, "not_sent", STALE)
                    return False, STALE
                if self.halted or stop_epoch != self._stop_epoch:  # stop/resume also invalidates this line
                    return False, HALTED
                if not self.ready or gen != self._gen or self._closed.is_set():
                    self._result(cmd, 'not_sent', NO_LINK)
                    return False, NO_LINK
                # Recheck after the transport lock and any late-reply drain.
                # No await lies between this gate and the actual write in _exchange.
                if not getattr(self, 'admission', lambda: True)():
                    return False, 'идёт обновление программы'
                reply, seen = await self._exchange(cmd, self.timeout)
            except OSError:
                self._result(cmd, "unknown", "связь оборвалась во время команды: выполнилась ли она, неизвестно")
                return False, NO_LINK
        error = is_error_reply(reply)
        status = "error" if error else "sent" if seen else "unknown"
        self._raw(cmd, status, reply)
        if cmd.startswith("Fixture "):
            self._targeted = status == "sent"
        if status == "unknown":
            self._stale = True
            log.warning("-> %s | РЕЗУЛЬТАТ НЕИЗВЕСТЕН %s", cmd, " ".join(self.mask(reply).split()))
            self._result(cmd, status, UNKNOWN)
            return False, UNKNOWN
        if not quiet or error:  # a background poll is neither the operator's last command nor activity for /api/idle
            log.info("-> %s | %s%s", cmd, "ERROR " if error else "", " ".join(self.mask(reply).split()))
            self._result(cmd, status, reply)
        return not error, reply

    async def _drain(self) -> bool:
        """Late answer to a timed-out line, so it is not read as the next line's answer. True when its prompt came;
        False means the answer is still outstanding and the session must not be used any more."""
        late, seen = await self._collect(max(1, self.timeout))
        if late.strip():
            log.warning("поздний ответ на предыдущую команду: %s", " ".join(self.mask(late).split()))
            self._raw("(поздний ответ)", "late", late)
        self._stale = not seen
        return seen

    async def _pump(self, reader: asyncio.StreamReader) -> None:
        try:
            while data := await reader.read(4096):
                self._buf += data
                self._rx += len(data)
                self._got.set()
            self._end = "EOF: пульт закрыл соединение"
        except OSError as e:
            self._end = f"{type(e).__name__}: {e}"
        finally:
            self._closed.set()
            self._got.set()

    async def _exchange(self, cmd: str, timeout: float) -> tuple[str, bool]:
        if leftover := clean(self._buf).strip():  # unsolicited text between replies: kept for diagnostics, never an answer
            self._raw("(сообщение пульта между командами)", "late", leftover.decode(errors="replace"))
        self._buf = b""
        self._stage = "listvar" if cmd == "ListVar" else "login" if cmd.lower().startswith("login") else "command"
        self._writer.write(cmd.encode() + b"\r\n")
        await self._writer.drain()
        result = await self._collect(timeout)
        if self._closed.is_set():
            raise ConnectionError(f"пульт закрыл соединение во время «{self._stage}»")
        return result

    async def _collect(self, timeout: float) -> tuple[str, bool]:
        """(reply, prompt seen). The reply ends at the command prompt ("[Channel]>").

        With require_prompt off, 200 ms of silence also ends the reply and counts as prompt seen.
        ponytail: формат приглашения проверить в зале (Диагностика); require_prompt=false в settings.json, если его нет
        """
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        seen = False
        while (left := end - loop.time()) > 0 and not self._closed.is_set():
            text = clean(self._buf)
            # The reply is complete at a prompt at the very end that follows a line break: a bare re-printed prompt
            # or the echo "[Channel]>cmd" arriving in its own TCP chunk is not the end of the answer.
            if (m := self.prompt.search(text)) and b"\n" in text[:m.start()]:
                seen = True
                break
            self._got.clear()
            try:
                await asyncio.wait_for(self._got.wait(), left if self.require_prompt else min(0.2, left))
            except TimeoutError:
                if not self.require_prompt:
                    break
        reply, self._buf = clean(self._buf).decode(errors="replace"), b""
        return reply, seen or not self.require_prompt
