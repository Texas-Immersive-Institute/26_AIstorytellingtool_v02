"""Text-generation backends shared by the apps (ADR-0003).

Three interchangeable backends, all without per-call API keys:
- Ollama: a local model over HTTP (http://127.0.0.1:11434 by default).
- Claude CLI: `claude -p` with tools disabled, on the user's Claude subscription.
- Codex CLI: `codex exec` in a read-only sandbox, on the user's ChatGPT subscription.

`backend="auto"` (the default) uses the first one that is ready, in that order: local first,
so nothing spends a subscription when a local model is running.

CLI calls run in a worker thread (subprocess.run), so they work on any asyncio event loop.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

BackendName = Literal["ollama", "claude_cli", "codex_cli"]
BackendChoice = Literal["auto", "ollama", "claude_cli", "codex_cli", "none"]
AUTO_ORDER: tuple[BackendName, ...] = ("ollama", "claude_cli", "codex_cli")
CHECK_TIMEOUT_S = 8.0


class AiSettings(BaseModel):
    backend: BackendChoice = "auto"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    claude_model: str = ""  # empty = the CLI's default model
    codex_model: str = ""
    timeout_s: float = Field(default=30, ge=2, le=300)


class Availability(BaseModel):
    backend: BackendName
    label: str
    ok: bool
    detail: str


class AiError(Exception):
    pass


class Backend(ABC):
    name: BackendName
    label: str

    @abstractmethod
    async def check(self) -> Availability: ...

    @abstractmethod
    async def complete(self, system: str, prompt: str, timeout: float) -> str: ...

    def _avail(self, ok: bool, detail: str) -> Availability:
        return Availability(backend=self.name, label=self.label, ok=ok, detail=detail)


# --- Ollama ----------------------------------------------------------------------------


class OllamaBackend(Backend):
    name = "ollama"
    label = "Ollama (local)"

    def __init__(self, url: str, model: str, transport: httpx.AsyncBaseTransport | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.url, timeout=timeout, transport=self._transport)

    async def check(self) -> Availability:
        try:
            async with self._client(3) as client:
                r = await client.get("/api/tags")
                r.raise_for_status()
                names = [m.get("name", "") for m in r.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            return self._avail(
                False,
                f"Ollama is not running at {self.url}. Install it from ollama.com, then run: ollama pull {self.model}",
            )
        wanted = {self.model, f"{self.model}:latest"}
        if not any(n in wanted for n in names):
            have = ", ".join(names[:5]) or "none"
            return self._avail(
                False,
                f"Ollama is running but model '{self.model}' is not pulled (have: {have}). Run: ollama pull {self.model}",
            )
        return self._avail(True, f"{self.model} at {self.url}")

    async def complete(self, system: str, prompt: str, timeout: float) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0.8},
        }
        try:
            async with self._client(timeout) as client:
                r = await client.post("/api/chat", json=body)
                r.raise_for_status()
                return str(r.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise AiError(f"Ollama call failed: {exc}") from exc


# --- CLIs ------------------------------------------------------------------------------


def _run(
    args: list[str], stdin: str, timeout: float, cwd: str | None = None
) -> subprocess.CompletedProcess[str]:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        return subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            creationflags=flags,
        )
    except subprocess.TimeoutExpired as exc:
        raise AiError(f"{Path(args[0]).stem} took longer than {timeout:.0f}s") from exc
    except OSError as exc:
        raise AiError(f"Could not start {args[0]}: {exc}") from exc


class ClaudeCliBackend(Backend):
    name = "claude_cli"
    label = "Claude CLI"

    def __init__(self, model: str = "", exe: str | None = None):
        self.model = model
        self.exe = exe or shutil.which("claude")

    def args(self, system: str) -> list[str]:
        assert self.exe
        args = [
            self.exe,
            "-p",
            "--output-format",
            "json",
            "--tools",
            "",
            "--no-session-persistence",
            "--system-prompt",
            system,
        ]
        if self.model:
            args += ["--model", self.model]
        return args

    async def check(self) -> Availability:
        # Installed is not enough: `claude -p` fails with "Not logged in" until the CLI itself
        # has been signed in (the desktop app's sign-in does not count).
        if not self.exe:
            return self._avail(False, "The claude command was not found on PATH.")
        try:
            out = await asyncio.to_thread(
                _run, [self.exe, "auth", "status", "--json"], "", CHECK_TIMEOUT_S
            )
        except AiError as exc:
            return self._avail(False, str(exc))
        return parse_claude_auth(out.stdout, out.stderr, out.returncode, self._avail)

    async def complete(self, system: str, prompt: str, timeout: float) -> str:
        if not self.exe:
            raise AiError("The claude command was not found on PATH.")
        out = await asyncio.to_thread(_run, self.args(system), prompt, timeout)
        return parse_claude_output(out.stdout, out.stderr, out.returncode)


def parse_claude_auth(stdout: str, stderr: str, code: int, avail: Any) -> Availability:
    try:
        data = json.loads(stdout)
    except ValueError:
        return avail(
            False,
            f"Could not read `claude auth status` (exit {code}): {(stderr or stdout).strip()[:160]}",
        )
    if not data.get("loggedIn"):
        return avail(
            False,
            "The Claude CLI is installed but not signed in. In a terminal, run: claude auth login",
        )
    return avail(True, f"signed in ({data.get('authMethod', 'account')})")


def parse_codex_login(stdout: str, stderr: str, code: int, avail: Any) -> Availability:
    text = (stdout + stderr).strip()
    if code != 0 or "not logged in" in text.lower():
        return avail(
            False, "The Codex CLI is installed but not signed in. In a terminal, run: codex login"
        )
    return avail(True, text.splitlines()[0] if text else "signed in")


def parse_claude_output(stdout: str, stderr: str, code: int) -> str:
    try:
        data = json.loads(stdout)
    except ValueError:
        raise AiError(
            f"claude returned no JSON (exit {code}): {(stderr or stdout).strip()[:200]}"
        ) from None
    if data.get("is_error") or code != 0:
        raise AiError(f"claude reported an error: {str(data.get('result') or stderr)[:200]}")
    return str(data.get("result", ""))


class CodexCliBackend(Backend):
    name = "codex_cli"
    label = "Codex CLI"

    def __init__(self, model: str = "", exe: str | None = None):
        self.model = model
        self.exe = exe or shutil.which("codex")

    def args(self, workdir: str, out_file: str) -> list[str]:
        assert self.exe
        args = [
            self.exe, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral",
            "--color", "never", "-C", workdir, "-o", out_file,
        ]  # fmt: skip
        if self.model:
            args += ["-m", self.model]
        return [*args, "-"]  # prompt from stdin: nothing user-written passes through a .cmd shim

    async def check(self) -> Availability:
        if not self.exe:
            return self._avail(False, "The codex command was not found on PATH.")
        try:
            out = await asyncio.to_thread(_run, [self.exe, "login", "status"], "", CHECK_TIMEOUT_S)
        except AiError as exc:
            return self._avail(False, str(exc))
        return parse_codex_login(out.stdout, out.stderr, out.returncode, self._avail)

    async def complete(self, system: str, prompt: str, timeout: float) -> str:
        if not self.exe:
            raise AiError("The codex command was not found on PATH.")
        with tempfile.TemporaryDirectory(prefix="story-codex-") as workdir:
            out_file = str(Path(workdir) / "answer.txt")
            stdin = (
                f"{system}\n\nAnswer only with the requested JSON. Do not run commands.\n\n{prompt}"
            )
            out = await asyncio.to_thread(
                _run, self.args(workdir, out_file), stdin, timeout, workdir
            )
            path = Path(out_file)
            if out.returncode != 0 or not path.is_file():
                raise AiError(
                    f"codex failed (exit {out.returncode}): {(out.stderr or out.stdout).strip()[-200:]}"
                )
            return path.read_text(encoding="utf-8", errors="replace")


# --- choosing a backend ------------------------------------------------------------------


def make_backend(name: BackendName, settings: AiSettings) -> Backend:
    if name == "ollama":
        return OllamaBackend(settings.ollama_url, settings.ollama_model)
    if name == "claude_cli":
        return ClaudeCliBackend(settings.claude_model)
    return CodexCliBackend(settings.codex_model)


async def check_all(settings: AiSettings) -> list[Availability]:
    return list(await asyncio.gather(*(make_backend(n, settings).check() for n in AUTO_ORDER)))


async def choose_backend(settings: AiSettings) -> tuple[Backend | None, str]:
    """The backend to use and a sentence saying why (shown in Settings and Debug)."""
    if settings.backend == "none":
        return None, "AI is off in settings; AI lines play their default line."
    names = AUTO_ORDER if settings.backend == "auto" else (settings.backend,)
    reasons = []
    for name in names:
        backend = make_backend(name, settings)
        avail = await backend.check()
        if avail.ok:
            why = "chosen automatically" if settings.backend == "auto" else "set in settings"
            return backend, f"{avail.label} ({why}): {avail.detail}"
        reasons.append(f"{avail.label}: {avail.detail}")
    return None, "No AI backend is ready, so AI lines play their default line. " + " ".join(reasons)


# --- JSON answers ------------------------------------------------------------------------

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_answer(text: str) -> dict[str, Any]:
    """Models wrap JSON in prose or code fences; take the first {...} object."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(cleaned[start : i + 1])
                        if isinstance(data, dict):
                            return data
                    except ValueError:
                        break
                    break
        start = cleaned.find("{", start + 1)
    raise AiError(f"The AI's answer was not JSON: {text.strip()[:160]}")


async def ask_json(
    backend: Backend, system: str, prompt: str, timeout: float
) -> tuple[dict[str, Any], float]:
    """Ask for a JSON object; returns it with the call's duration in seconds."""
    started = time.monotonic()
    text = await backend.complete(system, prompt, timeout)
    return parse_json_answer(text), time.monotonic() - started
