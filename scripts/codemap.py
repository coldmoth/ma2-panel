"""Function index of the project: file:line name. Run: python3 scripts/codemap.py > docs/code-index.md"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
print("# Индекс функций\n\nСобрано `scripts/codemap.py` (не править руками). Описание устройства: `docs/CODEMAP.md`.\n")
for path in sorted((ROOT / "ma2panel").glob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []

    def walk(body, depth):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = (ast.get_docstring(n) or "").split("\n")[0][:90].rstrip()
                out.append(f"{'  ' * depth}- {n.lineno} `{n.name}`" + (f" — {doc}" if doc else ""))
                if depth < 2 or isinstance(n, ast.ClassDef) or n.name == "create_app":
                    walk(n.body, depth + 1)
    walk(tree.body, 0)
    print(f"## {path.relative_to(ROOT).as_posix()}\n" + "\n".join(out) + "\n")
for path in sorted((ROOT / "static").glob("*.js")):
    lines = path.read_text(encoding="utf-8").split("\n")
    out = []
    for i, line in enumerate(lines, 1):
        m = re.match(r"(?:async )?function (\w+)|(SECTIONS\.\w+) = function", line)
        if m:
            out.append(f"- {i} `{m[1] or m[2]}`")
    print(f"## static/{path.relative_to(ROOT).as_posix()}\n" + "\n".join(out) + "\n")
