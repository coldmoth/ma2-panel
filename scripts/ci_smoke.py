"""Real HTTP/WS listeners in an isolated application copy; always --mock."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx
from websockets.asyncio.client import connect


ROOT = Path(__file__).resolve().parents[1]


async def receive_until(ws, predicate):
    async with asyncio.timeout(15):
        while True:
            message = json.loads(await ws.recv())
            if predicate(message):
                return message


async def check_websocket(port):
    async with connect(f"ws://127.0.0.1:{port}/ws", open_timeout=5, proxy=None,
                       origin=f"http://127.0.0.1:{port}") as ws:
        status = await receive_until(ws, lambda m: m.get("status", {}).get("ma2") == "logged_in")
        assert status["status"]["mock"] is True, status
        # An initial scene list must arrive on both ports.
        # It may precede logged_in, so reconnect after readiness is established.
    async with connect(f"ws://127.0.0.1:{port}/ws", open_timeout=5, proxy=None,
                       origin=f"http://127.0.0.1:{port}") as ws:
        config = await receive_until(ws, lambda m: "config" in m)
        assert config["config"]["scenes"] == [], config
        await ws.send(json.dumps({"a": "ci_unknown_action"}))
        reply = await receive_until(ws, lambda m: "ok" in m)
        assert reply["ok"] is False and reply.get("err"), reply


def smoke(log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ma2-ci-") as temp:
        app = Path(temp)
        # Explicit inputs only: never copy local credentials, config, or show data.
        for source in ROOT.glob("*.py"):
            shutil.copy2(source, app / source.name)
        shutil.copytree(ROOT / "static", app / "static")
        shutil.copy2(ROOT / "config.example.json", app / "config.json")
        settings = json.loads((ROOT / "settings.example.json").read_text(encoding="utf-8"))
        # The export location is installation-specific; keep mock exports here.
        settings["ma2"]["export_dir"] = str(app)
        # Reserve distinct ephemeral ports together, then release before launch.
        with socket.socket() as full, socket.socket() as simple:
            full.bind(("127.0.0.1", 0))
            simple.bind(("127.0.0.1", 0))
            ports = (full.getsockname()[1], simple.getsockname()[1])
        settings.update(bind="127.0.0.1", port=ports[0], simple_port=ports[1])
        (app / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        env = {k: v for k, v in os.environ.items()
               if k not in {"MA2_PASSWORD", "MA2_MOCK_REAL", "PYTHONPATH", "PYTHONOPTIMIZE"}}
        env["PYTHONUTF8"] = "1"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, str(app / "bridge.py"), "--mock",
                 "--config", str(app / "config.json"), "--settings", str(app / "settings.json")],
                cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                with httpx.Client(timeout=2, trust_env=False) as client:
                    deadline = time.monotonic() + 30
                    for port in ports:
                        while True:
                            if process.poll() is not None:
                                raise RuntimeError(f"bridge exited during startup: {process.returncode}")
                            try:
                                response = client.get(f"http://127.0.0.1:{port}/")
                                response.raise_for_status()
                                break
                            except httpx.TransportError:
                                if time.monotonic() >= deadline:
                                    raise TimeoutError("bridge HTTP startup timed out")
                                time.sleep(.1)
                        assert "<html" in response.text.lower()
                        for asset, mime in (("style.css", "text/css"),
                                            ("app.js" if port == ports[0] else "simple.js", "javascript")):
                            response = client.get(f"http://127.0.0.1:{port}/{asset}")
                            response.raise_for_status()
                            assert mime in response.headers["content-type"], response.headers
                        asyncio.run(check_websocket(port))
                    response = client.post(f"http://127.0.0.1:{ports[0]}/api/stop", headers={"X-Stop": "1"})
                    response.raise_for_status()
                    assert response.json()["ok"] is True
                assert process.wait(timeout=15) == 0, "bridge shutdown failed"
                assert not (app / "bridge.pid").exists(), "bridge left its PID file"
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
    print("HTTP/WS smoke passed: full + simple, mock login, assets, replies, shutdown")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=Path("test-results/mock.log"))
    args = parser.parse_args()
    smoke(args.log.resolve())
