"""Launch actual browser checks against an isolated mock; never a working show."""
import argparse
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

ROOT = Path(__file__).resolve().parents[1]


def run(output: Path, node: str, script: Path = ROOT / "scripts/browser_smoke.cjs"):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ma2-browser-") as temp:
        app = Path(temp)
        for source in ROOT.glob("*.py"):
            shutil.copy2(source, app / source.name)
        shutil.copytree(ROOT / "static", app / "static")
        shutil.copytree(ROOT / "ma2panel", app / "ma2panel", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        config = json.loads((ROOT / "ma2panel/resources/config.example.json").read_text(encoding="utf-8"))
        config.update(show="Mock show", hall={"w": 18, "d": 14, "stage": "top", "stageDepth": 4}, fixtures=[{"id": 1, "label": "Тестовая голова", "type": "Mock head", "moves": True,
                                 "params": ["Dimmer", "Pan", "Tilt", "Zoom", "Focus"], "x": .5, "y": .5}],
                      groups=[{"id": "smoke-head", "label": "Тестовая группа", "fixtures": [1]}],
                      scenes=[{"id": "smoke-scene", "exec": "1.101", "label": "Тестовая сцена"}])
        settings = json.loads((ROOT / "ma2panel/resources/settings.example.json").read_text(encoding="utf-8"))
        settings["ma2"]["export_dir"] = str(app / "exports")
        (app / "exports").mkdir()
        settings["safety"]["mode"] = "full"
        with socket.socket() as full, socket.socket() as simple:
            full.bind(("127.0.0.1", 0))
            simple.bind(("127.0.0.1", 0))
            ports = full.getsockname()[1], simple.getsockname()[1]
        settings.update(bind="127.0.0.1", port=ports[0], simple_port=ports[1])
        for name, data in (("config", config), ("settings", settings)):
            (app / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        env = {k: v for k, v in os.environ.items()
               if k not in {"MA2_PASSWORD", "MA2_MOCK_REAL", "PYTHONPATH", "PYTHONOPTIMIZE"}}
        env["PYTHONUTF8"] = "1"
        with (output / "mock.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, str(app / "bridge.py"), "--mock",
                                        "--config", str(app / "config.json"),
                                        "--settings", str(app / "settings.json")],
                                       cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                with httpx.Client(timeout=1, trust_env=False) as client:
                    deadline = time.monotonic() + 30
                    for port in ports:
                        while True:
                            if process.poll() is not None:
                                raise RuntimeError(f"mock exited: {process.returncode}; see {output / 'mock.log'}")
                            try:
                                client.get(f"http://127.0.0.1:{port}/").raise_for_status()
                                break
                            except httpx.HTTPError:
                                if time.monotonic() > deadline:
                                    raise TimeoutError("mock startup timed out")
                                time.sleep(.1)
                subprocess.run([node, str(script),
                                *(f"http://127.0.0.1:{port}" for port in ports), str(output)],
                               env=env, check=True, timeout=180)
            finally:
                # Own this PID only; never use the stop endpoint of an existing bridge.
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(tempfile.gettempdir()) / "ma2-browser-preflight")
    parser.add_argument("--node", default="node")
    parser.add_argument("--script", type=Path, default=ROOT / "scripts/browser_smoke.cjs")
    args = parser.parse_args()
    run(args.output.resolve(), args.node, args.script.resolve())
