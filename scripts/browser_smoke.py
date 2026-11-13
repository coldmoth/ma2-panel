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
import threading

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(output: Path, node: str, script: Path = ROOT / "scripts/browser_smoke.cjs", *, profile=None, bundle=None, mutation=None):
    if mutation not in (None, 'ma2-import', 'color-capability') or mutation and profile not in ('synthetic', 'field-start'):
        raise ValueError('Mutation is restricted to the isolated synthetic profile')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ma2-browser-") as temp:
        app = Path(temp)
        executable = sys.executable
        if bundle:
            shutil.copytree(bundle, app, dirs_exist_ok=True)
            executable = str(app / 'python/python.exe')
        else:
            for source in ROOT.glob("*.py"):
                shutil.copy2(source, app / source.name)
            shutil.copytree(ROOT / "static", app / "static")
            shutil.copytree(ROOT / "ma2panel", app / "ma2panel", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if mutation == 'ma2-import':
            target = app / 'static/app.js'
            text = target.read_text(encoding='utf-8')
            needle = "send({a: 'ma2_import', groups:"
            if text.count(needle) != 1: raise ValueError('Import mutation target changed')
            target.write_text(text.replace(needle, "send({a: 'quality_disabled_import', groups:"), encoding='utf-8')
        elif mutation == 'color-capability':
            target = app / 'ma2panel/fixtures.py'
            text = target.read_text(encoding='utf-8')
            needle = 'key = TYPE_ATTRS.get(attr.upper())'
            if text.count(needle) != 1: raise ValueError('Color mutation target changed')
            target.write_text(text.replace(needle, 'key = TYPE_ATTRS.get(attr.upper()) if attr.upper() == "DIM" else None'), encoding='utf-8')
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
        entry = app / 'bridge.py'
        token = ''
        if profile:
            import uuid
            token = uuid.uuid4().hex
            shutil.copy2(ROOT / 'scripts/concert_demo.py', app / 'concert_demo.py')
            shutil.copy2(ROOT / 'scripts/regression_server.py', app / 'regression_server.py')
            entry = app / 'regression_server.py'
            if profile in ('synthetic', 'field-start'):
                from scripts.concert_demo import demo_data
                config, settings = demo_data(config, settings, app, ports)
                if profile == 'field-start':
                    # Avoid the legacy name-based head guess: motion needs actual type evidence.
                    for fixture in config['fixtures']:
                        if fixture['type'] == '1 Demo Head':
                            fixture['type'] = '1 Profile A'
                    config['dmx_map']['1 Profile A'] = config['dmx_map'].pop('1 Demo Head')
            elif profile == 'field-v2':
                from scripts.quality_dataset import load
                _, config = load(profile)
                settings['safety']['allow_fixture_read'] = True
            elif profile == 'clean':
                config = json.loads((ROOT / 'ma2panel/resources/config.example.json').read_text(encoding='utf-8'))
                settings = json.loads((ROOT / 'ma2panel/resources/settings.example.json').read_text(encoding='utf-8'))
                settings.update(bind='127.0.0.1', port=ports[0], simple_port=ports[1])
                settings['ma2']['export_dir'] = str(app / 'exports')
            else:
                raise ValueError('Unknown test profile')
            (app / '.quality-test').write_text(json.dumps({'token': token, 'profile': profile}))
            (app / '.quality-console.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            if profile in ('field-start', 'field-v2'):
                config = json.loads((ROOT / 'ma2panel/resources/config.example.json').read_text(encoding='utf-8'))
            if profile == 'synthetic':
                config['ma2groups'] = []
            (app / '.quality-initial.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        for name, data in (("config", config), ("settings", settings)):
            (app / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        env = {k: v for k, v in os.environ.items()
               if k not in {"MA2_PASSWORD", "MA2_MOCK_REAL", "PYTHONPATH", "PYTHONOPTIMIZE"}}
        env["PYTHONUTF8"] = "1"
        env['MA2_TEST_TOKEN'] = token
        env['MA2_TEST_PROFILE'] = profile or ''
        with (output / "mock.log").open("w", encoding="utf-8") as log:
            command = [executable, str(entry), "--mock",
                                        "--config", str(app / "config.json"),
                                        "--settings", str(app / "settings.json")]
            def launch():
                return subprocess.Popen(command, cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT)
            process = launch()
            current, stopping, lock = [process], threading.Event(), threading.Lock()
            def supervise():
                while not stopping.wait(.1):
                    with lock:
                        marker = app / '.quality-restart'
                        if not stopping.is_set() and current[0].poll() == 3 and marker.exists():
                            if marker.read_text() == 'reset':
                                shutil.copyfile(app / '.quality-initial.json', app / 'config.json')
                            marker.unlink()
                            current[0] = launch()
            supervisor = threading.Thread(target=supervise, daemon=True)
            supervisor.start()
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
                               env=env, check=True, timeout=300)
            except subprocess.CalledProcessError:
                print((output / 'mock.log').read_text(encoding='utf-8', errors='replace')[-16000:], file=sys.stderr)
                raise
            finally:
                # Own this PID only; never use the stop endpoint of an existing bridge.
                stopping.set()
                with lock:
                    process = current[0]  # include an in-flight restart before cleanup
                supervisor.join(timeout=2)
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
    parser.add_argument('--profile', choices=('clean', 'field-v2', 'synthetic', 'field-start'))
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), args.node, args.script.resolve(), profile=args.profile, bundle=args.bundle)
