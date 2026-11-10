"""Reply boundaries tested without sockets or a console."""
import asyncio

import pytest

from ma2panel.link import MA2Link


class Writer:
    def __init__(self, link, respond):
        self.link, self.respond = link, respond
        self.lines = []
        self.closed = False

    def write(self, data):
        self.lines.append(data.decode().strip())
        self.respond(len(self.lines))

    async def drain(self):
        pass

    def close(self):
        self.closed = True
        self.link._closed.set()


def feed(link, data):
    link._buf += data
    link._got.set()


@pytest.mark.parametrize("complete", [False, True])
def test_error_without_boundary_drains_before_next_write(complete):
    async def go():
        link = MA2Link("unused", 0, "panel", "", lambda _: None, timeout=.01)
        link.state = "logged_in"
        loop = asyncio.get_running_loop()

        def respond(n):
            if n == 1:
                feed(link, b"Error #9: NUMBER TOO LARGE\n" + (b"[Group]>" if complete else b""))
            else:
                feed(link, b"second answer\n[Group]>")

        writer = link._writer = Writer(link, respond)
        ok, reply = await link.send("List Executor 1.1 Thru 1.250")
        assert not ok and "Error #9" in reply and link.last["status"] == "error"
        assert link._stale is not complete
        if not complete:
            def late():
                assert len(writer.lines) == 1
                feed(link, b"late tail\n[Group]>")
            loop.call_later(.02, late)
        assert await link.send("List Page") == (True, "second answer\n[Group]>")
        assert len(writer.lines) == 2 and not writer.closed
        assert not link._stale
    asyncio.run(go())


@pytest.mark.parametrize("event", ["timeout", "eof", "halt", "reconnect"])
def test_incomplete_error_never_repeats_or_writes_after_invalidated_drain(event):
    async def go():
        link = MA2Link("unused", 0, "panel", "", lambda _: None, timeout=.005)
        link.state = "logged_in"
        writer = link._writer = Writer(link, lambda _: feed(link, b"Error #9\n"))
        assert not (await link.send("List Executor 1.1 Thru 1.250"))[0]

        def invalidate():
            if event == "eof":
                link._closed.set()
                link._got.set()
            elif event == "halt":
                link.halted = True
                link.halted = False
            elif event == "reconnect":
                link._gen += 1
            if event in ("halt", "reconnect"):
                feed(link, b"tail\n[Group]>")

        asyncio.get_running_loop().call_later(.01, invalidate)
        assert not (await link.send("List Page"))[0]
        assert writer.lines == ["List Executor 1.1 Thru 1.250"]
    asyncio.run(go())


@pytest.mark.parametrize("split", range(1, len(b"Executing : List Page\r\n\x1b[32m[Group]>\x1b[0m")))
def test_collect_preserves_frame_across_timeout_at_every_byte(split):
    async def go():
        link = MA2Link("unused", 0, "panel", "", lambda _: None)
        wire = b"Executing : List Page\r\n\x1b[32m[Group]>\x1b[0m"
        feed(link, wire[:split])
        _, first_seen = await link._collect(.001)
        feed(link, wire[split:])
        reply, seen = await link._collect(.001)
        if not first_seen:
            assert seen
            assert reply == "Executing : List Page\n[Group]>"
        else:
            assert not seen  # a trailing ANSI reset is not a second reply
    asyncio.run(go())


@pytest.mark.parametrize("prefix", [b"", b"[Group]>", b"[Group]>List Page"])
def test_bare_prompt_or_echo_does_not_complete_frame(prefix):
    async def go():
        link = MA2Link("unused", 0, "panel", "", lambda _: None)
        feed(link, prefix)
        assert not (await link._collect(.001))[1]
        feed(link, b"\r\n[Group]>")
        assert (await link._collect(.001))[1]
    asyncio.run(go())


def test_incomplete_error_with_only_late_prompt_keeps_connection():
    async def go():
        link = MA2Link("unused", 0, "panel", "", lambda _: None, timeout=.005)
        link.state = "logged_in"
        def respond(n):
            feed(link, b"Error #9\r\n" if n == 1 else b"new answer\n[Group]>")
        writer = link._writer = Writer(link, respond)
        assert not (await link.send("List Executor 1.1 Thru 1.250"))[0]
        asyncio.get_running_loop().call_later(.01, feed, link, b"[Group]>")
        assert await link.send("List Page") == (True, "new answer\n[Group]>")
        assert len(writer.lines) == 2 and not writer.closed
    asyncio.run(go())


@pytest.mark.parametrize('outcome',['success','refused','timeout'])
def test_late_second_greeting_prompt_is_not_the_login_reply(outcome):
    """onPC 3.9.63.11 sends a guest prompt, then a separate Please login frame."""
    async def go():
        link=MA2Link('unused',0,'panel','synthetic',lambda _:None,timeout=.1)
        loop=asyncio.get_running_loop()
        def respond(n):
            if n==1:
                feed(link,b'Please login !\r\n\r [LayoutSelection]>\x1b[K')
                if outcome!='timeout':
                    payload=(b"Logged in as User 'panel'\r\n[LayoutSelection]>" if outcome=='success'
                             else b'Login incorrect\r\n[LayoutSelection]>')
                    loop.call_later(.01,feed,link,payload)
            else:
                loop.call_later(.01,feed,link,b'Global : $USER = panel\r\n[LayoutSelection]>')
        writer=link._writer=Writer(link,respond)
        state=await link._login()
        assert state=={'success':'logged_in','refused':'login_failed','timeout':'login_unknown'}[outcome]
        assert writer.lines==(['login "panel" "synthetic"','ListVar'] if outcome=='success'
                              else ['login "panel" "synthetic"'])
    asyncio.run(go())
