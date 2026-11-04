"""Clodex protocol and budget regressions; never contact a provider."""
import io
import json
import math
import urllib.error

import pytest

from scripts import clodex


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.setattr(clodex, "LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(clodex, "MAX_OUT", 100)
    cfg = {"CLODEX_API_KEY": "test-secret", "CLODEX_BUDGET_USD": "5"}
    monkeypatch.setattr(clodex, "env", lambda: cfg)
    requests = []

    def run(response, *, model="claude-opus-5-5", pricing=None, budget="5"):
        cfg["CLODEX_BUDGET_USD"] = budget
        pricing = {"usage_fixed_price": 0.5, "usage_fixed_price_unit": "per_1m_total_tokens"} if pricing is None else pricing

        def urlopen(req, **kwargs):
            requests.append(req)
            if req.get_method() == "GET":
                return io.BytesIO(json.dumps({"data": [{"id": model, "pricing": pricing}]}).encode())
            if isinstance(response, Exception):
                raise response
            return io.BytesIO(json.dumps(response).encode())

        monkeypatch.setattr(clodex.urllib.request, "urlopen", urlopen)
        monkeypatch.setattr(clodex.sys, "argv", ["clodex.py", model])
        monkeypatch.setattr(clodex.sys, "stdin", io.StringIO("Проверь патч"))
        return clodex.main()

    return run, requests


def message(**changes):
    return {"content": [{"type": "text", "text": "Часть 1"}, {"type": "text", "text": "Часть 2"}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 20, "output_tokens": 10,
            "cache_read_input_tokens": 30, "cache_creation_input_tokens": 40}, **changes}


def test_claude_uses_messages_catalog_and_counts_cached_tokens(runner, capsys):
    run, requests = runner
    run(message())
    assert [r.full_url for r in requests] == [clodex.BASE + "/models", clodex.BASE + "/messages"]
    for req in requests:
        assert req.get_header("X-api-key") == "test-secret"
        assert req.get_header("Anthropic-version") == "2023-06-01"
        assert req.get_header("Authorization") is None
    body = json.loads(requests[-1].data)
    assert body == {"model": "claude-opus-5-5", "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Проверь патч"}]}
    assert capsys.readouterr().out == "Часть 1\nЧасть 2\n"
    row = json.loads(clodex.LOG.read_text())
    assert row["tokens"] == 100
    assert row["usd"] == pytest.approx(0.00005)
    assert row["status"] == "completed"
    assert "test-secret" not in clodex.LOG.read_text()


def test_openai_route_still_works(runner, capsys):
    run, requests = runner
    run({"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
         "usage": {"total_tokens": 42}}, model="gpt-6.1-sol")
    assert requests[-1].full_url.endswith("/chat/completions")
    assert all(r.get_header("Authorization") == "Bearer test-secret" for r in requests)
    assert json.loads(requests[-1].data)["reasoning_effort"] == "low"
    assert capsys.readouterr().out == "OK\n"
    assert json.loads(clodex.LOG.read_text())["tokens"] == 42


def test_claude_thinking_is_not_printed_as_answer(runner, capsys):
    run, _ = runner
    run(message(content=[{"type": "thinking", "thinking": "internal"},
                         {"type": "redacted_thinking", "data": "hidden"},
                         {"type": "text", "text": "Итог"}]))
    assert capsys.readouterr().out == "Итог\n"


def test_truncated_openai_answer_fails_with_recorded_cost(runner, capsys):
    run, _ = runner
    with pytest.raises(SystemExit):
        run({"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}],
             "usage": {"total_tokens": 42}}, model="gpt-6.1-sol")
    assert capsys.readouterr().out == ""
    assert json.loads(clodex.LOG.read_text())["status"] == "incomplete"


def test_missing_model_refuses_before_generation(runner, monkeypatch):
    monkeypatch.setattr(clodex.urllib.request, "urlopen",
                        lambda *args, **kwargs: io.BytesIO(b'{"data":[]}'))
    with pytest.raises(SystemExit, match="Нет модели"):
        clodex.price("test-secret", "claude-opus-5-5")


@pytest.mark.parametrize("changes", [
    {"stop_reason": "max_tokens"}, {"stop_reason": "tool_use"}, {"stop_reason": None},
    {"content": []}, {"content": [{"type": "text", "text": "  "}]},
    {"content": [{"type": "tool_use", "name": "shell"}]},
])
def test_incomplete_claude_answer_is_charged_but_not_printed(runner, capsys, changes):
    run, _ = runner
    with pytest.raises(SystemExit):
        run(message(**changes))
    assert capsys.readouterr().out == ""
    assert json.loads(clodex.LOG.read_text())["usd"] == pytest.approx(0.00005)


@pytest.mark.parametrize("usage", [{}, {"input_tokens": 20}, {"input_tokens": -1, "output_tokens": 2},
                                    {"input_tokens": True, "output_tokens": 2}])
def test_invalid_usage_retains_reservation(runner, usage):
    run, _ = runner
    with pytest.raises(SystemExit):
        run(message(usage=usage))
    row = json.loads(clodex.LOG.read_text())
    assert row["status"] == "unknown"
    assert row["usd"] > 0


@pytest.mark.parametrize("pricing", [
    {}, {"usage_fixed_price": 0.5},
    {"usage_fixed_price": -1, "usage_fixed_price_unit": "per_1m_total_tokens"},
    {"usage_fixed_price": math.nan, "usage_fixed_price_unit": "per_1m_total_tokens"},
])
def test_unknown_price_never_posts(runner, pricing):
    run, requests = runner
    with pytest.raises(SystemExit):
        run(message(), pricing=pricing)
    assert len(requests) == 1
    assert not clodex.LOG.exists()


def test_budget_refusal_before_post_includes_provider_upper_rate(runner):
    run, requests = runner
    pricing = {"usage_fixed_price": 0.35, "usage_floor_price": 0.55,
               "usage_fixed_price_unit": "per_1m_total_tokens",
               "provider_routes": [{"usage_fixed_price": 1.3}]}
    with pytest.raises(SystemExit):
        run(message(), pricing=pricing, budget="0.0002")
    assert len(requests) == 1
    assert not clodex.LOG.exists()


def test_upper_rate_used_in_local_estimate(runner):
    run, _ = runner
    run(message(), pricing={"usage_fixed_price": 0.35, "usage_floor_price": 0.55,
        "usage_fixed_price_unit": "per_1m_total_tokens", "provider_routes": [{"usage_fixed_price": 1.3}]})
    assert json.loads(clodex.LOG.read_text())["usd"] == pytest.approx(0.00013)


@pytest.mark.parametrize("error", [TimeoutError("test-secret"), urllib.error.HTTPError(
    "https://example.invalid", 500, "test-secret", {}, None)])
def test_network_error_reserves_cost_without_retry_or_secret(runner, capsys, error):
    run, requests = runner
    with pytest.raises(SystemExit) as exc:
        run(error)
    assert len(requests) == 2  # one GET, exactly one paid POST attempt
    row = json.loads(clodex.LOG.read_text())
    assert row["status"] == "unknown" and row["usd"] > 0
    assert "test-secret" not in str(exc.value) + str(capsys.readouterr()) + clodex.LOG.read_text()


def test_spent_reads_legacy_and_reserved_entries(runner, monkeypatch, capsys):
    clodex.LOG.write_text('{"usd":0.1}\n{"usd":0.2,"status":"unknown"}\n')
    monkeypatch.setattr(clodex.sys, "argv", ["clodex.py", "--spent"])
    clodex.main()
    assert "$0.3000 из $5.0" in capsys.readouterr().out
