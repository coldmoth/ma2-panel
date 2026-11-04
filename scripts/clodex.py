"""Ask a Clodex model one question and keep the project's spend under budget.

Usage:
  python3 scripts/clodex.py MODEL [FILE ...] < prompt.txt
  python3 scripts/clodex.py --spent

The prompt is read from stdin; each FILE is appended to it with its path as a header.
Prints only a completed text answer. Calls are logged to .clodex-usage.jsonl.
Costs are conservative local estimates, not provider invoices. Unknown calls retain
their reservation; reconcile them against provider usage before adjusting the log.
Reads CLODEX_API_KEY and CLODEX_BUDGET_USD from .env in the project root.
"""
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / ".clodex-usage.jsonl"
BASE = "https://clodex.xyz/v1"
MAX_OUT = int(os.environ.get("CLODEX_MAX_OUT", 8000))


def env():
    out = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def spent():
    if not LOG.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in LOG.read_text().splitlines() if line.strip())


def call(path, key, body=None, *, claude=False):
    headers = {"Content-Type": "application/json"}
    if claude:
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    else:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def price(key, model):
    for m in call("/models", key, claude=model.startswith("claude-"))["data"]:
        if m["id"] == model:
            p = m.get("pricing", {})
            rates = [p.get("usage_fixed_price")]
            if p.get("usage_fixed_price_unit") != "per_1m_total_tokens":
                sys.exit("Стоп: неизвестная единица тарифа Clodex")
            rates += [p["usage_floor_price"]] if "usage_floor_price" in p else []
            rates += [r.get("usage_fixed_price") for r in p.get("provider_routes", [])]
            if any(type(r) not in (int, float) or not math.isfinite(r) or r <= 0 for r in rates):
                sys.exit("Стоп: нет проверенного фиксированного тарифа Clodex")
            return max(rates)  # scope may select a route other than the default
    sys.exit(f"Нет модели {model} в каталоге Clodex")


def token_usage(response, claude):
    usage = response["usage"]
    if claude:
        values = [usage["input_tokens"], usage["output_tokens"],
                  usage.get("cache_creation_input_tokens", 0), usage.get("cache_read_input_tokens", 0)]
    else:
        values = [usage["total_tokens"]]
    if any(type(n) is not int or n < 0 for n in values):
        raise ValueError("invalid token usage")
    return sum(values)


def answer(response, claude):
    if claude:
        reason = response.get("stop_reason")
        blocks = response.get("content", [])
        if reason != "end_turn" or any(b.get("type") not in ("text", "thinking", "redacted_thinking") for b in blocks):
            sys.exit("Clodex: ответ Claude не завершён или содержит неподдерживаемые блоки")
        text = "\n".join(b["text"] for b in blocks if b.get("type") == "text")
    else:
        choice = response["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("tool_calls"):
            sys.exit("Clodex: ответ не завершён или требует инструментов")
        text = choice["message"].get("content")
    if not isinstance(text, str) or not text.strip():
        sys.exit("Clodex: пустой текстовый ответ")
    return text


def save_entry(rows, entry):
    """Sequential calls only. Replace the reservation atomically; retain it on failure."""
    temp = LOG.with_suffix(".tmp")
    temp.write_text("".join(rows) + json.dumps(entry) + "\n", encoding="utf-8")
    temp.replace(LOG)


def main():
    cfg = env()
    budget = float(cfg.get("CLODEX_BUDGET_USD", 5))
    if not math.isfinite(budget) or budget < 0 or MAX_OUT <= 0:
        sys.exit("Стоп: некорректный бюджет или лимит выхода")
    if sys.argv[1:] == ["--spent"]:
        print(f"${spent():.4f} из ${budget}")
        return
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    model, files = sys.argv[1], sys.argv[2:]
    key = cfg["CLODEX_API_KEY"]
    claude = model.startswith("claude-")
    usd_per_m = price(key, model)
    prompt = sys.stdin.read() + "".join(f"\n\n=== {f} ===\n{Path(f).read_text()}" for f in files)
    # Conservative byte estimate plus protocol overhead; not a provider billing guarantee.
    worst = (len(prompt.encode("utf-8")) + 128 + MAX_OUT) * usd_per_m / 1e6
    if spent() + worst > budget:
        sys.exit(f"Стоп: потрачено ${spent():.4f}, вызов может стоить до ${worst:.4f}, бюджет ${budget}")
    body = {"model": model, "max_tokens": MAX_OUT, "messages": [{"role": "user", "content": prompt}]}
    if not claude:
        body["reasoning_effort"] = "low"
    rows = LOG.read_text(encoding="utf-8").splitlines(keepends=True) if LOG.exists() else []
    entry = {"t": time.strftime("%F %T"), "model": model, "tokens": None, "usd": worst,
             "status": "unknown", "rate_upper_usd_per_m": usd_per_m}
    save_entry(rows, entry)  # never lose an attempted request from the local budget
    try:
        r = call("/messages" if claude else "/chat/completions", key, body, claude=claude)
        total = token_usage(r, claude)
    except Exception as exc:
        sys.exit(f"Clodex: результат/расход неизвестен ({type(exc).__name__}); резерв сохранён, повтора нет")
    usd = total * usd_per_m / 1e6
    entry.update(tokens=total, usd=usd, status="incomplete")
    save_entry(rows, entry)  # even a rejected/truncated answer has a cost
    try:
        text = answer(r, claude)
    except (KeyError, TypeError, ValueError, IndexError):
        sys.exit("Clodex: неподдерживаемая структура ответа; расход учтён")
    entry["status"] = "completed"
    save_entry(rows, entry)
    print(text)
    print(f"\n[clodex] {model}: {total} токенов, оценка до ${usd:.4f}; "
          f"всего ${spent():.4f} из ${budget}; завершено", file=sys.stderr)


if __name__ == "__main__":
    main()
