"""Fake grandMA2 Telnet server for --mock and tests."""
import asyncio
import os
import re
import shutil
from pathlib import Path

SAMPLE = Path(__file__).parent / "tests" / "sample_export.xml"
TYPE_LIST = Path(__file__).parent / "tests" / "list_fixturetype_3.9.60.txt"  # hall 2026-10-21, List FixtureType rows
REAL_EXPORT = Path(__file__).parent / "tests" / "real_export_3.9.60.xml"
EMPTY_LIST = "WARNING, NO OBJECTS FOUND FOR LIST"


class MockMA2:
    def __init__(self, user: str, export_dir: str | None):
        self.user = user
        self.export_dir = export_dir
        self.export_text: str | None = None
        self.export_mode = "write"  # test knob: "write" | "none" (accepted, no file appears) | "reject" (error reply)
        self.fixture_dir: str | None = None  # test knob: where Export Fixture writes (the real MA2: ..\\fixtures, not importexport)
        self.export_delay = 0.0     # test knob: the file appears this many seconds after the reply
        self.received: list[str] = []
        self.paused = False
        self.mute = False       # test knob: take commands, never answer (a console that hangs)
        self.no_prompt = False  # test knob: answer without the "]>" prompt
        self.late = 0.0         # test knob: answer every non-login line this many seconds late (a slow console)
        self.echo = False       # test knob: echo the command line back first, as some consoles do
        self.ansi = False       # test knob: MA2 3.9.60 wire format: colour codes, "[Channel]>cmd" echo, prompt + \x1b[K
        self.chunk = 0          # test knob: write every reply in pieces of this many bytes, 20 ms apart
        self.show_name = "Mock show"
        self.shows = ["Mock show", "Demo"]
        self.list_garbage = False
        self.missing_attrs: set[str] = set()  # test knob: these attributes answer Error #14, as Focus on a head without one
        self.rows = {"1.101": "Pianist", "1.102": "Rehearsal"}
        self.groups = {1: "Front"}
        self.dmx: dict[int, int] = {}  # test knob: what getdmx returns, absolute address -> 0-255
        self.fixture_types: dict[int, str] = {}  # test knob: Export FixtureType <no> -> XML text
        self.vars: dict[str, str] = {}  # global variables set by SetVar from the DMX Lua line
        self.lua_error = False  # test knob: the desk refuses the Lua line
        self.patch: dict[int, int] = {}  # Assign Fixture N At Dmx: fixture -> absolute address, applied to the next export
        self.assign_error = False  # test knob: the desk refuses Assign
        # RDM (spec 21). ponytail: the RdmList line layout is invented here; the real one is unknown until the hall reads it.
        self.rdm_devices = [{"uid": "43500F019FCB", "address": 289, "footprint": 10, "label": "ARTIST FL 1000"}]
        self.rdm_error = False  # test knob: the device refuses RdmSetParameter
        self.rdm_global = False  # Assign Root "Settings"."Global" /EnableRDM
        self.rdm_universes = {1: True}  # universe RDM flags the state read reports
        self.presets = {4: {1: "Red"}, 2: {1: "Stage"}}
        self.running: set[str] = set()
        self.port = 0
        self._writers: set[asyncio.StreamWriter] = set()
        # MA2_MOCK_REAL=1: answer like the hall console (onPC 3.9.60.68, show "big room v2", probe 2026-10-18)
        self.real = os.environ.get("MA2_MOCK_REAL") == "1"
        self.exec_ceiling = 200  # real mode: a wider List Executor gets Error #9 (the real ceiling is unknown, 250 failed)
        if self.real:
            self.show_name, self.shows = "big room v2", ["big room v2", "big room", "Demo"]
            self.groups = {1: "HEAD STAGE", 2: "ACME FRONT", 3: "BAR ALL", 4: "FRESNEL", 5: "ACME FRONT", 6: "STAGE HEAD",
                           7: "STAGE BAR", 8: "PAR ALL"}
            self.presets = {4: {1: "red", 2: "green", 3: "blue", 4: "cyan", 5: "yellow", 6: "magenta", 7: "White"}, 2: {}}
            self.export_text = REAL_EXPORT.read_text(encoding="utf-8")

    async def _handle(self, reader, writer):
        if self.paused:
            writer.close()
            return
        self._writers.add(writer)
        try:
            writer.write(self._wire("Welcome to grandMA2 (mock)\r\n[Channel]>").encode())
            while line := await reader.readline():
                text = line.decode(errors="replace").strip()
                self.received.append(text)
                if self.mute and not text.lower().startswith("login"):
                    continue
                reply = self._reply(text)
                if re.fullmatch(r'LoadShow "([^"\r\n]+)" /nosave', text) and not reply.startswith("Error"):
                    # One drop per load, then the normal bridge reconnect/login path.
                    break
                if self.echo:
                    reply = text + "\r\n" + reply
                if self.late and not text.lower().startswith("login"):
                    await asyncio.sleep(self.late)
                data = self._wire(reply.replace("[Channel]>", "") if self.no_prompt else reply).encode()
                for i in range(0, len(data), self.chunk or len(data) or 1):
                    writer.write(data[i:i + (self.chunk or len(data))])
                    await writer.drain()
                    if self.chunk:
                        await asyncio.sleep(0.02)
        except ConnectionError:
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    def _wire(self, reply: str) -> str:
        if not self.ansi:
            return reply
        return "\x1b[37m" + reply.replace("[Channel]>", "\x1b[32m[Channel]>\x1b[37m\x1b[K")

    def _reply(self, text: str) -> str:
        reply = self._answer(text)
        if self.real and not text.lower().startswith("login"):
            reply = f"Executing : {text}\r\n" + reply
        return reply

    def _answer(self, text: str) -> str:
        if text.lower().startswith("login") and text.split('"')[1:2] != [self.user]:
            return "Error: login failed\r\n"
        if text.lower().startswith("login"):
            return f"Logged in as User '{self.user}'\r\n[Channel]>"
        if m := re.fullmatch(r'LoadShow "([^"\r\n]+)" /nosave', text):
            if m[1] not in self.shows:
                return "Error: unknown show\r\n[Channel]>"
            self.show_name = m[1]
            self.running.clear()
            return "OK\r\n[Channel]>"
        name = re.search(r'"([^"]*)"', text)
        if text.startswith("Attribute") and name and name[1] in self.missing_attrs:
            return f"Executing : {text}\r\nError : {text}\r\nError #14: OBJECT DOES NOT EXIST\r\n[Channel]>"
        if text.startswith("Export") and self.export_mode == "reject":
            return f"Executing : {text}\r\nError #72: COMMAND NOT EXECUTED\r\n[Channel]>"
        # real MA2 3.9.60.68 (hall, 2026-10-18): Export Fixture names the file "fixture-<name>.xml" and writes nothing with /o
        if m := re.fullmatch(r'Export FixtureType (\d+) "([^"]+)"', text):  # ponytail: guessed library folder and file name
            if self.export_dir and int(m[1]) in self.fixture_types:
                folder = Path(self.export_dir).parent / "fixture_types"
                folder.mkdir(exist_ok=True)
                (folder / f"{m[2]}.xml").write_text(self.fixture_types[int(m[1])], encoding="utf-8")
                return f"Executing : {text}\r\n[Channel]>"
            return f"Executing : {text}\r\nError #14: OBJECT DOES NOT EXIST\r\n[Channel]>"
        if text.startswith("Export") and self.export_dir and name and self.export_mode != "none" and not re.search(r" /o(verwrite)?$", text, re.I):
            fixture = text.startswith("Export Fixture")
            path = Path(self.fixture_dir if fixture and self.fixture_dir else self.export_dir) / (f"fixture-{name[1]}.xml" if fixture else f"{name[1]}.xml")
            body = self.export_text if text.startswith("Export Fixture") else '<MA xmlns="urn:ma"><Info/></MA>'
            if fixture and self.patch:
                body = body if body is not None else SAMPLE.read_text(encoding="utf-8")
                for fid, address in self.patch.items():  # the export shows the new patch, as the desk's would
                    body = re.sub(rf'(<Fixture[^>]*fixture_id="{fid}".*?<(Address|Patch)>)[^<]*(</\2>)', rf"\g<1>{address}\g<3>", body, count=1, flags=re.S)
            if text.startswith("Export Group"):  # ponytail: guessed layout, see fixtures.parse_group_export
                body = '<MA xmlns="urn:ma">' + "".join(f'<Group index="{n - 1}" name="{g}"><Subfixtures><Subfixture fix_id="{n}"/><Subfixture fix_id="{n + 1}"/></Subfixtures></Group>'
                                                     for n, g in sorted(self.groups.items())) + "</MA>"
            write = (lambda: shutil.copy(SAMPLE, path)) if body is None else (lambda: path.write_text(body, encoding="utf-8"))
            if self.export_delay:
                asyncio.get_running_loop().call_later(self.export_delay, write)
            else:
                write()
        if text.startswith("Lua") and self.lua_error:
            return "Error #72: COMMAND NOT EXECUTED\r\n[Channel]>"
        if m := re.search(r"PANELRDM([0-9a-f]{32})", text):  # RDM state read-back: feedback rows like the real line would
            nonce = m[1]
            rows = [f"PANELRDM{nonce} GLOBAL {'On' if self.rdm_global else 'Off'}"]
            rows += [f"PANELRDM{nonce} UNIVERSE {n} {'On' if on else 'Off'}" for n, on in self.rdm_universes.items()]
            rows.append(f"PANELRDM{nonce} END {len(self.rdm_universes)}")
            return f"Executing : {text}\r\n" + "".join(r + "\r\n" for r in rows) + "[Channel]>"
        if m := re.fullmatch(r'Assign Root "Settings"\."Global" /EnableRDM=(On|Off)', text):
            self.rdm_global = m[1] == "On"
            return f"Executing : {text}\r\n[Channel]>"
        if "PANELLUA" in text:  # the read-back's canary line
            self.vars["PANELLUA"] = "1"
            return f"Executing : {text}\r\n[Channel]>"
        if m := re.match(r"Lua \"local a,n,v=(\d+),(\d+),", text):  # DMX read-back: answers by feedback like the real line would
            a, n = int(m[1]), int(m[2])
            tag = re.search(r"'T([0-9a-f]*) '", text)[1]
            self.vars[f"PANELDMX{a}"] = f"T{tag} {a} " + ",".join(str(self.dmx.get(i, 0)) for i in range(a, a + n))  # by SetVar, as the line asks
            return f"Executing : {text}\r\n[Channel]>"
        if text == "List FixtureType":
            return f"Executing : {text}\r\n" + TYPE_LIST.read_text(encoding="utf-8").replace("\n", "\r\n") + "[Channel]>"
        if m := re.fullmatch(r"Assign Fixture (\d+) At Dmx (\d+)\.(\d+)", text):
            if self.assign_error:
                return f"Executing : {text}\r\nError #72: COMMAND NOT EXECUTED\r\n[Channel]>"
            self.patch[int(m[1])] = (int(m[2]) - 1) * 512 + int(m[3])
            return f"Executing : {text}\r\n[Channel]>"
        if m := re.fullmatch(r"RdmList(?: / UID = (\w+))?", text):
            rows = [d for d in self.rdm_devices if not m[1] or d["uid"] == m[1]]
            return f"Executing : {text}\r\n" + "".join(f"{d['uid']}  {d['label']}  Address {d['address']}  Footprint {d['footprint']}\r\n" for d in rows) + "[Channel]>"
        if m := re.fullmatch(r"RdmSetParameter (dmx_start_address|identify_device) (\d+) / UID = (\w+)", text):
            device = next((d for d in self.rdm_devices if d["uid"] == m[3]), None)
            if self.rdm_error or device is None:
                return f"Executing : {text}\r\nError #72: COMMAND NOT EXECUTED\r\n[Channel]>"
            if m[1] == "dmx_start_address":
                device["address"] = int(m[2])
            return f"Executing : {text}\r\n[Channel]>"
        if m := re.match(r"Delete Executor (\S+)", text):
            self.rows.pop(m[1], None)
        if m := re.match(r"(Go|Off) Executor (\S+)", text):
            (self.running.add if m[1] == "Go" else self.running.discard)(m[2])
        if m := re.match(r"StoreLook Executor (\d+\.\d+)", text):
            self.rows[m[1]] = "New scene"
        if m := re.fullmatch(r'Label Executor (\d+\.\d+) "([^"\r\n]*)"', text):
            if m[1] in self.rows:
                self.rows[m[1]] = m[2]
        if m := re.fullmatch(r'Store Group (\d+) "([^"\r\n]+)"', text):
            if int(m[1]) in self.groups:
                return "Error: group occupied\r\n[Channel]>"
            self.groups[int(m[1])] = m[2]
        # ponytail: ListVar/ListShows reply formats are assumed; verify on MA2 in the hall.
        if text == "ListVar" and not self.list_garbage:
            return (f"Global : $USER = {self.user}\r\nGlobal : $USERRIGHTS = Program\r\nGlobal : $VERSION = 3.9.60.68\r\n"
                    f"Global : $SHOWFILE = {self.show_name}\r\n" + "".join(f"Global : ${k} = {v}\r\n" for k, v in self.vars.items()) + "[Channel]>")
        if text == "ListShows" and not self.list_garbage and self.real:
            return "".join(f"{name} 18:57 18.Oct.2026 {100 + i} KB\r\n" for i, name in enumerate(self.shows)) + "[Channel]>"
        if text == "ListShows" and not self.list_garbage:
            return "\r\n".join(f'"{name}"' for name in self.shows) + "\r\n[Channel]>"
        if text == "List Page" and not self.list_garbage:  # hall 2026-10-18 format: "(N)" only on pages that hold objects
            pages = sorted({int(e.split(".")[0]) for e in self.rows} | {1})
            counts = {p: sum(e.split(".")[0] == str(p) for e in self.rows) for p in pages}
            return "        No.  Name  Info  \r\n" + "".join(f"Page {p:2} {p:<4} Page" + (f"         ({counts[p]})" if counts[p] else "") + "\r\n" for p in pages) + "[Channel]>"
        if text.startswith("List"):
            if self.list_garbage:
                return "???\r\n[Channel]>"
            # ponytail: assumed List Group / List Preset rows, not captured from MA2.
            if self.real and (r := self._real_list(text)) is not None:
                return r
            if m := re.fullmatch(r"List Group (\d+)(?: Thru (\d+))?", text):
                rows = [f'Group {n} "{name}"\r\n' for n, name in self.groups.items()
                        if int(m[1]) <= n <= int(m[2] or m[1])]
                return ("".join(rows) or "No objects found\r\n") + "[Channel]>"
            if m := re.fullmatch(r"List Preset (\d+)\.(\d+)(?: Thru (\d+)\.(\d+))?", text):
                rows = [f'Preset {m[1]}.{n} "{name}"\r\n' for n, name in self.presets.get(int(m[1]), {}).items()
                        if int(m[2]) <= n <= int(m[4] or m[2])]
                return ("".join(rows) or "No objects found\r\n") + "[Channel]>"
            m = re.fullmatch(r"List Executor (\d+\.\d+)(?: Thru (\d+\.\d+))?", text)
            rows = []
            if m:
                key = lambda ex: tuple(map(int, ex.split(".")))
                rows = [(e, n) for e, n in self.rows.items() if key(m[1]) <= key(e) <= key(m[2] or m[1])]
            return ("".join(f"  Executor {e}  {n}  Sequence 1  {'Running' if e in self.running else 'Off'}\r\n"
                            for e, n in rows) or "No objects found\r\n") + "[Channel]>"
        return "OK\r\n[Channel]>"

    def _real_list(self, text: str) -> str | None:
        """Rows as the hall console printed them; executor rows were never captured, so those keep the assumed form."""
        if m := re.fullmatch(r"List Group (\d+)(?: Thru (\d+))?", text):
            rows = [f"Group {n} {n}    {name}\r\n" for n, name in self.groups.items() if int(m[1]) <= n <= int(m[2] or m[1])]
            return ("        No.  Name        Info  \r\n" + "".join(rows) if rows else EMPTY_LIST + "\r\n") + "[Channel]>"
        if m := re.fullmatch(r"List Preset (\d+)\.(\d+)(?: Thru (\d+)\.(\d+))?", text):
            kind = {1: "Dimmer", 2: "Position", 3: "Gobo", 4: "Color", 5: "Beam"}.get(int(m[1]), "All")
            rows = [f"{kind} {m[1]}.{n} {m[1]}.{n}  {name}      Normal\r\n" for n, name in self.presets.get(int(m[1]), {}).items()
                    if int(m[2]) <= n <= int(m[4] or m[2])]
            return ("          No.  Name     Special  Info  \r\n" + "".join(rows) if rows else EMPTY_LIST + "\r\n") + "[Channel]>"
        if (m := re.fullmatch(r"List Executor \d+\.\d+ Thru \d+\.(\d+)", text)) and int(m[1]) > self.exec_ceiling:
            return f"Error : {text}\r\nError #9: NUMBER TOO LARGE\r\n[Channel]>"
        if text.startswith("List Executor") and not any(e for e in self.rows if text.endswith(e) or " Thru " in text):
            return EMPTY_LIST + "\r\n[Channel]>"
        return None

    def drop(self) -> None:
        for w in list(self._writers):
            w.close()


async def start_mock(port: int, user: str, export_dir: str | None = None) -> MockMA2:
    mock = MockMA2(user, export_dir)
    server = await asyncio.start_server(mock._handle, "127.0.0.1", port)
    mock.port = server.sockets[0].getsockname()[1]
    return mock
