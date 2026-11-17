import json

import httpx
import pytest
from aistory_core import ai
from aistory_core.ai import (
    AiError,
    AiSettings,
    Availability,
    ClaudeCliBackend,
    CodexCliBackend,
    OllamaBackend,
    choose_backend,
    parse_claude_output,
    parse_json_answer,
)


def test_parse_json_answer_handles_fences_and_prose():
    assert parse_json_answer('{"line": "hi"}') == {"line": "hi"}
    assert parse_json_answer('```json\n{"line": "hi"}\n```') == {"line": "hi"}
    assert parse_json_answer('Sure! Here it is: {"line": "a {b}"} Hope that helps.') == {
        "line": "a {b}"
    }
    with pytest.raises(AiError):
        parse_json_answer("no json here")


def test_parse_claude_output():
    out = json.dumps({"type": "result", "is_error": False, "result": '{"line": "x"}'})
    assert parse_claude_output(out, "", 0) == '{"line": "x"}'
    with pytest.raises(AiError):
        parse_claude_output(json.dumps({"is_error": True, "result": "limit reached"}), "", 1)
    with pytest.raises(AiError):
        parse_claude_output("not json", "boom", 1)


def test_sign_in_checks():
    avail = ClaudeCliBackend(exe="claude")._avail
    out = ai.parse_claude_auth('{"loggedIn": false, "authMethod": "none"}', "", 0, avail)
    assert not out.ok and "claude auth login" in out.detail
    assert ai.parse_claude_auth('{"loggedIn": true, "authMethod": "claude.ai"}', "", 0, avail).ok
    assert not ai.parse_claude_auth("garbage", "", 1, avail).ok
    avail = CodexCliBackend(exe="codex")._avail
    assert ai.parse_codex_login("Logged in using ChatGPT", "", 0, avail).ok
    assert not ai.parse_codex_login("", "Not logged in", 1, avail).ok


def test_cli_command_lines_disable_tools_and_writes():
    claude = ClaudeCliBackend(model="haiku", exe="claude")
    args = claude.args("SYSTEM")
    assert args[:2] == ["claude", "-p"]
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--system-prompt") + 1] == "SYSTEM"
    assert args[-2:] == ["--model", "haiku"]
    codex = CodexCliBackend(exe="codex")
    args = codex.args("C:/tmp/w", "C:/tmp/w/answer.txt")
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in args and args[-1] == "-"


async def test_missing_cli_reports_not_found():
    backend = ClaudeCliBackend()
    backend.exe = None
    avail = await backend.check()
    assert not avail.ok and "not found" in avail.detail
    with pytest.raises(AiError):
        await backend.complete("s", "p", 1)


def ollama(handler) -> OllamaBackend:
    return OllamaBackend(
        "http://ollama.test", "llama3.2:3b", transport=httpx.MockTransport(handler)
    )


async def test_ollama_check_and_complete():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})
        body = json.loads(request.content)
        assert body["format"] == "json" and body["messages"][0]["role"] == "system"
        return httpx.Response(200, json={"message": {"content": '{"line": "hello"}'}})

    backend = ollama(handler)
    assert (await backend.check()).ok
    assert await backend.complete("s", "p", 5) == '{"line": "hello"}'


async def test_ollama_missing_model_and_not_running():
    missing = ollama(lambda r: httpx.Response(200, json={"models": [{"name": "mistral:latest"}]}))
    avail = await missing.check()
    assert not avail.ok and "ollama pull llama3.2:3b" in avail.detail

    def down(request):
        raise httpx.ConnectError("refused")

    avail = await ollama(down).check()
    assert not avail.ok and "not running" in avail.detail


class FakeBackend(ai.Backend):
    def __init__(self, name, ok):
        self.name, self.label, self.ok = name, name, ok

    async def check(self):
        return Availability(backend=self.name, label=self.label, ok=self.ok, detail="fake")

    async def complete(self, system, prompt, timeout):
        return "{}"


async def test_auto_prefers_local_then_claude_then_codex(monkeypatch):
    ready = {"ollama": False, "claude_cli": True, "codex_cli": True}
    monkeypatch.setattr(ai, "make_backend", lambda name, s: FakeBackend(name, ready[name]))
    backend, reason = await choose_backend(AiSettings())
    assert backend.name == "claude_cli" and "chosen automatically" in reason
    ready["ollama"] = True
    backend, _ = await choose_backend(AiSettings())
    assert backend.name == "ollama"
    backend, reason = await choose_backend(AiSettings(backend="codex_cli"))
    assert backend.name == "codex_cli" and "set in settings" in reason
    backend, reason = await choose_backend(AiSettings(backend="none"))
    assert backend is None and "off" in reason
    ready.update(ollama=False, claude_cli=False, codex_cli=False)
    backend, reason = await choose_backend(AiSettings())
    assert backend is None and "default line" in reason
