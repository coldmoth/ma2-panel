import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
const cwd = fileURLToPath(new URL("../", import.meta.url));
const backend = Number(process.env.LUMA_BACKEND_PORT || 18781),
  simple = Number(process.env.LUMA_SIMPLE_PORT || 18782),
  ui = Number(process.env.LUMA_UI_PORT || 5178);
for (const port of [backend, simple, ui])
  await new Promise((ok, no) => {
    const s = createServer();
    s.once("error", () =>
      no(new Error(`Порт ${port} занят. Укажите свободный LUMA_*_PORT.`)),
    );
    s.listen(port, "127.0.0.1", () => s.close(ok));
  });
const env = {
  ...process.env,
  LUMA_BACKEND_PORT: String(backend),
  LUMA_SIMPLE_PORT: String(simple),
  LUMA_UI_PORT: String(ui),
};
const children = new Set();
let stopping = false;
function signal(p, name) {
  try {
    if (process.platform === "win32") p.kill(name);
    else process.kill(-p.pid, name);
  } catch {}
}
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const p of children) signal(p, "SIGTERM");
  setTimeout(() => {
    for (const p of children) signal(p, "SIGKILL");
    process.exit(code);
  }, 2500).unref();
}
function run(cmd, args, workdir, onExit) {
  const p = spawn(cmd, args, {
    cwd: workdir,
    stdio: "inherit",
    env,
    detached: process.platform !== "win32",
  });
  children.add(p);
  p.on("error", (e) => {
    console.error(e.message);
    stop(1);
  });
  p.on("exit", (code) => {
    children.delete(p);
    if (!stopping) onExit(code);
  });
  return p;
}
function startBackend() {
  run(
    "uv",
    ["run", "python", "luma-lab/scripts/mock_backend.py"],
    resolve(cwd, ".."),
    (code) => {
      if (code === 3) {
        console.log("LUMA: штатный перезапуск mock-моста…");
        setTimeout(() => {
          if (!stopping) startBackend();
        }, 350);
      } else stop(code || 0);
    },
  );
}
startBackend();
run("node", [resolve(cwd, "node_modules/vite/bin/vite.js")], cwd, (code) =>
  stop(code || 0),
);
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());
console.log(
  `\nLUMA lab · только mock\nhttp://127.0.0.1:${ui}\nШтатная панель: http://127.0.0.1:${backend}\nCtrl+C останавливает оба процесса.\n`,
);
