"""Own CLI processes and normalize provider-specific events behind the QGIS bridge."""
from ..i18n import tr
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from qgis.PyQt.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal
from .protocol import (SCHEMA, build_system_prompt, claude_stream_input, StreamResponse,
                       CodexStreamResponse, parse_response)


def default_executable():
    return shutil.which("claude") or next((p for p in (
        os.path.expanduser("~/.local/bin/claude"), "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude") if os.path.isfile(p)), "claude")


def default_codex_executable():
    return shutil.which("codex") or next((p for p in (
        "/Applications/ChatGPT.app/Contents/Resources/codex",
        "/Applications/Codex.app/Contents/Resources/codex",
        os.path.expanduser("~/.local/bin/codex"), "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex") if os.path.isfile(p)), "codex")


def valid_endpoint(url):
    url = url.strip()
    if any(char.isspace() for char in url):
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme in ("http", "https") and bool(parts.hostname) and
                parts.port != 0 and not parts.username and not parts.password and
                not parts.fragment and not parts.query)
    except ValueError:
        return False


def cli_environment(provider=None, api_key="", endpoint="default", base_url=""):
    env = QProcessEnvironment.systemEnvironment()
    # Only the key chosen in Qtaro's settings is used, never one inherited from the shell.
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                "CLAUDECODE", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                "CLAUDE_CODE_USE_FOUNDRY", "PYTHONHOME", "PYTHONPATH",
                "OPENAI_API_KEY", "CODEX_API_KEY"):
        env.remove(key)
    if endpoint != "bedrock" and not endpoint.startswith("amazon-bedrock"):
        env.remove("AWS_BEARER_TOKEN_BEDROCK")
    if api_key:
        from .credentials import API_KEY_ENV
        env.insert(API_KEY_ENV[provider], api_key)
    if provider == "claude":
        if endpoint == "custom":
            env.insert("ANTHROPIC_BASE_URL", base_url)
        elif endpoint == "bedrock":
            env.insert("CLAUDE_CODE_USE_BEDROCK", "1")
    return env


# Messages the CLIs print when the subscription login is missing or expired.
LOGIN_ERRORS = {
    "claude": ("not logged in", "please run /login", "oauth token has expired",
               "invalid api key", "authentication_error"),
    "codex": ("not logged in", "401 unauthorized", "please log in", "codex login"),
}


def is_login_error(provider, detail):
    detail = detail.lower()
    return any(marker in detail for marker in LOGIN_ERRORS.get(provider, ()))


class AgentProcess(QObject):
    completed = pyqtSignal(dict)
    usage_updated = pyqtSignal(dict)
    progress = pyqtSignal(dict)
    session_opened = pyqtSignal(str)
    failed = pyqtSignal(str)
    login_required = pyqtSignal(str)

    def __init__(self, parent, workdir):
        super().__init__(parent)
        self.process = None
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.cancel(self.label + tr(" response did not finish within 5 minutes")))

    def request(self, executable, prompt, model="", session_id=None, resume=False,
                enable_skills=False, enable_connectors=False, provider="claude", codex_capabilities=None,
                effort="", fast_mode=False, custom_prompt="", images=(), api_key="",
                endpoint="default", base_url="", claude_skills=None):
        if self.process is not None:
            raise RuntimeError(tr("Already waiting for a response"))
        if endpoint == "custom" and not valid_endpoint(base_url):
            raise ValueError(tr("Enter a valid HTTP or HTTPS endpoint URL."))
        from .capabilities import codex_capability_args
        capability_args = codex_capability_args(codex_capabilities or {}) if provider == "codex" else []
        system_prompt = build_system_prompt(provider, custom_prompt)
        self.provider = provider
        self.uses_api_key = bool(api_key)
        self.external_auth = endpoint != "default"
        self.requested_model = model.strip()
        self.label = "Codex" if provider == "codex" else "Claude"
        self.expected_session = session_id if resume or provider == "claude" else None
        self.reported_session = False
        self.stdout = bytearray()
        self.stream = CodexStreamResponse() if provider == "codex" else StreamResponse()
        self.stderr = bytearray()
        process = QProcess(self)
        self.process = process
        process.setWorkingDirectory(str(self.workdir))
        process.setProcessEnvironment(cli_environment(provider, api_key, endpoint, base_url))
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.errorOccurred.connect(self._error)
        process.finished.connect(self._finished)
        stdin = (claude_stream_input(prompt, images) if images and provider != "codex" else prompt).encode("utf-8")
        process.started.connect(lambda: (process.write(stdin), process.closeWriteChannel()))
        if provider == "codex":
            schema_path = self.workdir / "response-schema.json"
            schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
            args = ["exec"] + (["resume"] if resume else [])
            for path in images:
                args += ["--image", str(path)]
            args += capability_args
            args += ["--json", "--skip-git-repo-check", "--output-schema", str(schema_path),
                     "-c", 'sandbox_mode="read-only"', "-c", 'approval_policy="never"',
                     "-c", 'model_reasoning_summary="auto"',
                     "-c", "developer_instructions=" + json.dumps(system_prompt)]
            if endpoint == "default":
                args += ["-c", 'forced_login_method="api"' if api_key else 'forced_login_method="chatgpt"']
            elif endpoint == "custom":
                args += ["-c", 'model_provider="qtaro-endpoint"',
                         "-c", 'model_providers.qtaro-endpoint.name="Qtaro endpoint"',
                         "-c", "model_providers.qtaro-endpoint.base_url=" + json.dumps(base_url.strip()),
                         "-c", 'model_providers.qtaro-endpoint.env_key="CODEX_API_KEY"']
            else:
                args += ["-c", "model_provider=" + json.dumps(endpoint)]
            args += ["-c", 'service_tier="fast"' if fast_mode else 'service_tier="default"']
            if fast_mode:
                args += ["-c", "features.fast_mode=true"]
            if effort:
                args += ["-c", "model_reasoning_effort=" + json.dumps(effort)]
            if model.strip():
                args.extend(["--model", model.strip()])
            if resume:
                args.append(session_id)
            args.append("-")
        else:
            settings = {"disableAllHooks": True, "fastMode": fast_mode}
            if claude_skills:
                settings["skillOverrides"] = claude_skills
            args = ["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                    "--json-schema", json.dumps(SCHEMA), "--setting-sources", "user",
                    "--settings", json.dumps(settings),
                    "--system-prompt", system_prompt,
                    "--tools", "default" if enable_skills or enable_connectors else ""]
            if images:
                args.extend(["--input-format", "stream-json"])
            if effort:
                args.extend(["--effort", effort])
            if not enable_skills:
                args.append("--disable-slash-commands")
            if not enable_connectors:
                args.extend(["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}'])
            if enable_skills or enable_connectors:
                # Non-interactive calls honor existing allow/deny rules without hanging on prompts.
                args.extend(["--permission-mode", "dontAsk"])
            if enable_skills:
                args.extend(["--allowedTools", "Skill"])
            if session_id:
                args.extend(["--resume" if resume else "--session-id", session_id])
            if model.strip():
                args.extend(["--model", model.strip()])
        process.start(os.path.expanduser(executable), args)
        self.timer.start(300000)

    def _read_stdout(self):
        chunk = bytes(self.process.readAllStandardOutput())
        self.stdout.extend(chunk)
        if len(self.stdout) > 2_000_000:
            self.cancel(self.label + tr(" response exceeded the size limit"))
            return
        try:
            preview = self.stream.feed(chunk)
        except (ValueError, UnicodeError, AttributeError) as exc:
            self.cancel(tr("Could not parse streamed response: ") + str(exc))
            return
        try:
            self._report_session()
        except ValueError as exc:
            self.cancel(str(exc))
            return
        if self.process is not None:
            self.progress.emit(preview)

    def _report_session(self):
        session_id = self.stream.session_id
        if session_id and not self.reported_session:
            if self.expected_session and session_id != self.expected_session:
                raise ValueError(self.label + tr(" returned a different session ID"))
            self.reported_session = True
            self.session_opened.emit(session_id)

    def _read_stderr(self):
        self.stderr.extend(bytes(self.process.readAllStandardError()))
        self.stderr = self.stderr[-16000:]

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            detail = self.process.errorString()
            self._release()
            self.failed.emit(self.label + tr(" could not start. Check its executable path and sign-in: ") + detail)

    def _release(self):
        self.timer.stop()
        process, self.process = self.process, None
        process.deleteLater()

    def _finished(self, exit_code, exit_status):
        if self.process is None:
            return
        self._read_stdout()
        if self.process is None:
            return
        self._read_stderr()
        self._release()
        if exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            detail = (self.stderr or self.stdout).decode("utf-8", errors="replace")[-16000:]
            try:
                self.stream.feed(b"", final=True)
                envelope = self.stream.result
                if isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
                    detail = envelope["result"]
            except (ValueError, UnicodeError):
                pass
            if is_login_error(self.provider, detail):
                if self.external_auth and not self.uses_api_key:
                    self.failed.emit(self.label + tr(" could not authenticate with the configured model service: ") + detail)
                    return
                if self.uses_api_key:
                    # Browser sign-in would not fix a rejected key.
                    self.failed.emit(self.label + tr(" rejected the API key. Check it in Qtaro settings: ") + detail)
                    return
                self.login_required.emit(detail)
                return
            self.failed.emit(detail or self.label + tr(" exited unexpectedly"))
            return
        try:
            self.stream.feed(b"", final=True)
            if self.stream.result is None:
                raise ValueError(self.label + tr(" response ended before completion"))
            if self.provider == "codex" and not self.stream.session_id:
                raise ValueError(tr("Could not obtain the Codex session ID"))
            response = parse_response(json.dumps(self.stream.result))
            self._report_session()
        except (ValueError, UnicodeError) as exc:
            self.failed.emit(str(exc))
            return
        usage = self.stream.context_usage
        if usage:
            self.usage_updated.emit({**usage, "model": usage.get("model") or self.requested_model})
        self.completed.emit(response)

    def cancel(self, reason=tr("Stopped")):
        if self.process is None:
            return
        process = self.process
        process.blockSignals(True)
        process.kill()
        process.waitForFinished(1000)
        self._release()
        self.failed.emit(reason)

    def close(self):
        self.cancel()
