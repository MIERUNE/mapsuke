"""Own CLI processes and normalize provider-specific events behind the QGIS bridge."""
import json
import os
import shutil
from pathlib import Path

from qgis.PyQt.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal
from .protocol import SCHEMA, build_system_prompt, StreamResponse, CodexStreamResponse, parse_response


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


class AgentProcess(QObject):
    completed = pyqtSignal(dict)
    progress = pyqtSignal(dict)
    session_opened = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent, workdir):
        super().__init__(parent)
        self.process = None
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.cancel(self.label + "の応答が5分以内に完了しませんでした"))

    def request(self, executable, prompt, model="", session_id=None, resume=False,
                enable_skills=False, enable_connectors=False, provider="claude", codex_capabilities=None):
        if self.process is not None:
            raise RuntimeError("既に応答待ちです")
        from .capabilities import codex_capability_args
        capability_args = codex_capability_args(codex_capabilities or {}) if provider == "codex" else []
        system_prompt = build_system_prompt()
        self.provider = provider
        self.label = "Codex" if provider == "codex" else "Claude"
        self.expected_session = session_id if resume or provider == "claude" else None
        self.reported_session = False
        self.stdout = bytearray()
        self.stream = CodexStreamResponse() if provider == "codex" else StreamResponse()
        self.stderr = bytearray()
        process = QProcess(self)
        self.process = process
        process.setWorkingDirectory(str(self.workdir))
        env = QProcessEnvironment.systemEnvironment()
        # Use the user's subscription login rather than an inherited API key.
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                    "CLAUDECODE", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                    "CLAUDE_CODE_USE_FOUNDRY", "PYTHONHOME", "PYTHONPATH",
                    "OPENAI_API_KEY", "CODEX_API_KEY"):
            env.remove(key)
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.errorOccurred.connect(self._error)
        process.finished.connect(self._finished)
        process.started.connect(lambda: (process.write(prompt.encode("utf-8")), process.closeWriteChannel()))
        if provider == "codex":
            schema_path = self.workdir / "response-schema.json"
            schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
            codex_instructions = system_prompt.replace(
                "You cannot run tools yourself: return Python code for the bridge to execute.",
                "Use returned Python code for ALL live QGIS operations. Available supporting tools "
                "follow Codex permissions. Never bypass denied tools through the Python bridge.")
            args = ["exec"] + (["resume"] if resume else [])
            args += capability_args
            args += ["--json", "--skip-git-repo-check", "--output-schema", str(schema_path),
                     "-c", 'sandbox_mode="read-only"', "-c", 'approval_policy="never"',
                     "-c", 'forced_login_method="chatgpt"',
                     "-c", "developer_instructions=" + json.dumps(codex_instructions)]
            if model.strip():
                args.extend(["--model", model.strip()])
            if resume:
                args.append(session_id)
            args.append("-")
        else:
            if enable_skills or enable_connectors:
                system_prompt = system_prompt.replace(
                    "You cannot run tools yourself: return Python code for the bridge to execute.",
                    "You may use available skills and connector tools for supporting work. "
                    "All operations on the live QGIS project MUST use Python returned to the bridge. "
                    "Do not attempt QGIS access from a shell subprocess. "
                    "If tool permission is denied, explain the missing permission to the user. "
                    "Never work around a denied tool using the Python bridge.")
            args = ["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                    "--json-schema", json.dumps(SCHEMA), "--setting-sources", "user",
                    "--settings", '{"disableAllHooks":true}', "--system-prompt", system_prompt,
                    "--tools", "default" if enable_skills or enable_connectors else ""]
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
            self.cancel(self.label + "の応答サイズが上限を超えました")
            return
        try:
            preview = self.stream.feed(chunk)
        except (ValueError, UnicodeError, AttributeError) as exc:
            self.cancel("ストリーム応答を解釈できません: " + str(exc))
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
                raise ValueError(self.label + "が異なるセッションIDを返しました")
            self.reported_session = True
            self.session_opened.emit(session_id)

    def _read_stderr(self):
        self.stderr.extend(bytes(self.process.readAllStandardError()))
        self.stderr = self.stderr[-16000:]

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            detail = self.process.errorString()
            self._release()
            self.failed.emit(self.label + "を起動できません。実行パスとログインを確認してください: " + detail)

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
            self.failed.emit(detail or self.label + "が異常終了しました")
            return
        try:
            self.stream.feed(b"", final=True)
            if self.stream.result is None:
                raise ValueError(self.label + "の応答が完了前に終了しました")
            if self.provider == "codex" and not self.stream.session_id:
                raise ValueError("CodexのセッションIDを取得できませんでした")
            response = parse_response(json.dumps(self.stream.result))
            self._report_session()
        except (ValueError, UnicodeError) as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(response)

    def cancel(self, reason="停止しました"):
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
