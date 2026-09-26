"""One conversation with an agent CLI and the live QGIS runtime, independent of widgets.

Front ends render ``messages`` and react to signals; persistence, CLI turns, approval
decisions and Python execution all happen here, so a GUI dock and a future headless
front end share the same behavior.
"""
from .i18n import JA, from_legacy, tr
from pathlib import Path
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QObject, QSettings, QTimer, pyqtSignal
from .agent import AgentProcess, default_executable, default_codex_executable
from .protocol import build_prompt
from .processing_catalog import processing_catalog
from .runtime import QgisRuntime
from .sessions import SessionStore
from .model_compat import unavailable_reason
import json
import os
import re


# Explicit IDs keep the advertised version stable when Claude updates its aliases.
MODEL_CHOICES = (
    ("Claude Opus 5.5", "claude-opus-5-5"),
    ("Claude Fable 5.1", "claude-fable-5-1"),
    ("Claude Sonnet 5", "claude-sonnet-5"),
    ("Claude Haiku 4.5", "claude-haiku-4-5-20251001"),
    (tr("Default (Claude Code settings)"), ""),
)
CODEX_MODELS = (
    ("GPT-6 Astra", "gpt-6-astra"),
    ("GPT-5.6 Sol", "gpt-5.6-sol"),
    ("GPT-5.6 Terra", "gpt-5.6-terra"),
    ("GPT-5.6 Luna", "gpt-5.6-luna"),
    ("GPT-5.5", "gpt-5.5"),
    (tr("Default (Codex settings)"), ""),
)
LEGACY_MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5",
                 "haiku": "claude-haiku-4-5-20251001"}
RESTORE_NOTICE = "Session restored. Work continues on the current QGIS project."
NEW_SESSION_NOTICE = "Started a new session."
# Saved sessions may contain earlier or Japanese wordings of this UI-only notice.
RESTORE_NOTICES = (RESTORE_NOTICE, JA[RESTORE_NOTICE],
                   "Session restored. Python variables were reset",
                   "セッションを復元しました。Python変数はリセット")
NEW_SESSION_NOTICES = (NEW_SESSION_NOTICE, JA[NEW_SESSION_NOTICE])


def default_effort(provider, model):
    return "medium" if provider == "codex" or model == "claude-opus-5-5" else "high"


def default_session_path():
    return Path(QgsApplication.qgisSettingsDirPath()) / "qtaro/sessions.sqlite3"


def migrate_legacy_settings(move_sessions=True):
    """Carry settings and saved sessions over from the plugin's former name, QGIS Agent."""
    settings = QSettings()
    settings.beginGroup("qgis-agent")
    legacy = {key: settings.value(key) for key in settings.allKeys()}
    settings.remove("")
    settings.endGroup()
    for key, value in legacy.items():
        if not settings.contains("qtaro/" + key):
            settings.setValue("qtaro/" + key, value)
    old, new = Path(QgsApplication.qgisSettingsDirPath()) / "qgis-agent", default_session_path().parent
    if move_sessions and old.is_dir() and not new.exists():
        old.rename(new)
        # Claude Code files sessions under its working directory, so move them to keep resuming.
        projects = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser() / "projects"
        slug = lambda path: re.sub(r"[^A-Za-z0-9]", "-", str(path / "claude-workspace"))
        if (projects / slug(old)).is_dir() and not (projects / slug(new)).exists():
            (projects / slug(old)).rename(projects / slug(new))


def new_message(role, text, code=""):
    """A saved transcript entry; question fields stay empty unless the agent asked."""
    return {"role": role, "text": text, "code": code, "question": "", "choices": [],
            "path_request": "", "path_suggestion": "", "suggestion": ""}


class AgentSession(QObject):
    # Transcript entries, by index into messages.
    message_added = pyqtSignal(int)
    message_changed = pyqtSignal(int)
    question_asked = pyqtSignal(int)
    approval_requested = pyqtSignal(int)
    # Transient information that is shown but never saved.
    notice = pyqtSignal(str)
    reasoning = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    # Turn lifecycle.
    submitted = pyqtSignal(str)
    turn_started = pyqtSignal()
    busy_changed = pyqtSignal(bool)
    # The turn ended or is waiting on the user (answer or approval); carries a short summary.
    attention_needed = pyqtSignal(str)
    waiting_changed = pyqtSignal(bool)
    login_required = pyqtSignal(str)
    usage_changed = pyqtSignal()
    saved = pyqtSignal()
    # Another session was loaded or started; rebuild the transcript from messages.
    reset = pyqtSignal()
    # Settings or the session list changed.
    changed = pyqtSignal()

    def __init__(self, parent=None, iface=None, session_path=None):
        super().__init__(parent)
        self.runtime = QgisRuntime(iface)
        session_path = Path(session_path or default_session_path())
        self.agent = AgentProcess(self, workdir=session_path.parent / "claude-workspace")
        self.agent.session_opened.connect(self.on_session_opened)
        self.agent.completed.connect(self.on_response)
        self.agent.usage_updated.connect(self.on_usage_updated)
        self.agent.failed.connect(self.on_failure)
        self.agent.progress.connect(self.on_progress)
        self.agent.login_required.connect(self.on_login_required)
        settings = QSettings()
        self.options = {"executable": settings.value("qtaro/executable", default_executable()),
                        "approval_mode": settings.value("qtaro/approval_mode", "ask")}
        if self.options["approval_mode"] not in ("ask", "auto", "full_auto"):
            self.options["approval_mode"] = "ask"
        # Previously saved automatic modes have not necessarily received informed consent.
        if (self.options["approval_mode"] != "ask" and
                settings.value("qtaro/consented_approval_mode", "") != self.options["approval_mode"]):
            self.options["approval_mode"] = "ask"
        settings.setValue("qtaro/approval_mode", self.options["approval_mode"])
        self.options["provider"] = "claude"
        self.options["codex_capabilities"] = json.loads(settings.value("qtaro/codex_capabilities", "{}"))
        self.options["codex_executable"] = settings.value("qtaro/codex_executable", default_codex_executable())
        self.options["model"] = settings.value("qtaro/model", "")
        self.options["effort"] = settings.value("qtaro/claude_effort", "") or default_effort("claude", self.options["model"])
        self.options["fast_mode"] = settings.value("qtaro/claude_fast_mode", False, type=bool)
        # Bundled QGIS skills load through the CLI, so skills default to on.
        self.options["enable_skills"] = settings.value("qtaro/enable_skills", True, type=bool)
        self.options["enable_connectors"] = settings.value("qtaro/enable_connectors", False, type=bool)
        self.options["custom_prompt"] = settings.value("qtaro/custom_prompt", "")
        self.options["notifications"] = settings.value("qtaro/notifications", True, type=bool)
        self.session_id = None
        self.session_title = ""
        self.context_usage = None
        self.store = SessionStore(session_path)
        self.agent_started = False
        self.native_session_id = None
        self.sent_history = 0
        self.request_history_end = 0
        self.history = []
        self.messages = []
        self.draft = ""
        self.streaming_index = None
        self.pending_code = None
        self.job = None
        self.running = False
        self.continuation = QTimer(self)
        self.continuation.setSingleShot(True)
        self.continuation.timeout.connect(self.request)

    def restore(self):
        """Open the last selected session, or persist a fresh one on first use."""
        last = QSettings().value("qtaro/last_session", "")
        initial = last if last and self.store.exists(last) else self.store.latest_id()
        if initial:
            self.load(initial)
        else:
            self.save()

    @property
    def agent_label(self):
        return "Codex" if self.options["provider"] == "codex" else "Claude"

    @property
    def listed_title(self):
        title = self.session_title or next((item["content"][:50].replace("\n", " ") for item in self.history
                                            if item["role"] == "user"), tr("New session"))
        return "[" + self.agent_label + "] " + title

    def log(self, role, text, code=""):
        self.messages.append(new_message(role, text, code))
        index = len(self.messages) - 1
        self.message_added.emit(index)
        return index

    def set_status(self, text):
        self.status_changed.emit(text)

    def set_running(self, busy):
        self.running = busy
        if not busy:
            self.waiting_changed.emit(False)
        self.busy_changed.emit(busy)

    # Settings

    def normalize_model(self):
        if self.options["provider"] == "claude":
            self.options["model"] = LEGACY_MODELS.get(self.options["model"], self.options["model"])

    def fast_mode_available(self):
        model = self.options["model"]
        return (model.startswith("claude-opus-5") if self.options["provider"] == "claude"
                else model in {item[1] for item in CODEX_MODELS if item[1]})

    def effort_available(self):
        return (self.options["provider"] == "codex" or
                not self.options["model"].startswith("claude-haiku"))

    def set_model(self, model):
        if self.running:
            return
        followed_default = self.options["effort"] == default_effort(self.options["provider"], self.options["model"])
        self.options["model"] = model
        QSettings().setValue("qtaro/" + ("codex_model" if self.options["provider"] == "codex" else "model"), model)
        if followed_default:
            self.options["effort"] = default_effort(self.options["provider"], model)
            QSettings().setValue("qtaro/" + self.options["provider"] + "_effort", self.options["effort"])
        if not self.fast_mode_available():
            self.options["fast_mode"] = False
        self.save()
        self.changed.emit()

    def set_effort(self, effort):
        if self.running:
            return
        self.options["effort"] = effort
        QSettings().setValue("qtaro/" + self.options["provider"] + "_effort", effort)
        self.save()

    def set_fast_mode(self, enabled):
        if self.running or not self.fast_mode_available():
            return
        self.options["fast_mode"] = enabled
        QSettings().setValue("qtaro/" + self.options["provider"] + "_fast_mode", enabled)
        self.save()

    def set_approval_mode(self, mode, record_consent=True):
        """The caller obtains informed consent before passing an automatic mode."""
        self.options["approval_mode"] = mode
        settings = QSettings()
        settings.setValue("qtaro/approval_mode", mode)
        if record_consent:
            settings.setValue("qtaro/consented_approval_mode", mode if mode != "ask" else "")

    def update_settings(self, values):
        self.options.update(values)
        for key, value in values.items():
            QSettings().setValue("qtaro/" + key, json.dumps(value) if key == "codex_capabilities" else value)
        self.save()
        self.changed.emit()

    # Turns

    def submit(self, message):
        """Send a user message; returns False when it was not accepted."""
        message = message.strip()
        if not message or self.running:
            return False
        executable_key = "codex_executable" if self.options["provider"] == "codex" else "executable"
        if not self.options[executable_key]:
            self.log("Error", self.agent_label + tr(" executable path is required"))
            return False
        issue = unavailable_reason(self.options["provider"], self.options[executable_key],
                                   self.options["model"])
        if issue:
            self.log("Error", issue + tr(". Choose another model or update the CLI."))
            return False
        self.submitted.emit(message)
        self.history.append({"role": "user", "content": message})
        self.log("You", message)
        self.set_running(True)
        if not self.save():
            self.set_running(False)
            return False
        self.changed.emit()
        self.request()
        return True

    def resume(self):
        """Resend the pending conversation, e.g. after signing in."""
        if self.running or not self.history:
            return
        self.set_running(True)
        self.request()

    def request(self):
        if not self.running:
            return
        self.streaming_index = None
        self.turn_started.emit()
        self.set_status(self.agent_label + tr(" is working…"))
        self.waiting_changed.emit(True)
        try:
            delta = self.history[self.sent_history:] if self.agent_started else self.history
            if self.agent_started:
                delta = [entry for entry in delta if entry["role"] != "assistant"]
            catalog = processing_catalog(QgsApplication.processingRegistry()) if not self.agent_started else None
            prompt = build_prompt(delta, catalog, generate_title=
                                  not self.session_title and not any(item["role"] == "assistant" for item in self.history),
                                  approval_mode=self.options["approval_mode"])
            images = [path for entry in delta if entry["role"] == "bridge" and isinstance(entry["content"], dict)
                      for path in entry["content"].get("attached_images", []) if Path(path).is_file()]
            self.request_history_end = len(self.history)
            if len(prompt.encode("utf-8")) > 500000:
                raise ValueError(tr("Conversation limit reached. Start a new session."))
            executable_key = "codex_executable" if self.options["provider"] == "codex" else "executable"
            self.agent.request(self.options[executable_key], prompt, self.options["model"],
                               self.native_session_id or self.session_id, resume=self.agent_started,
                               provider=self.options["provider"],
                               enable_skills=self.options["enable_skills"],
                               enable_connectors=self.options["enable_connectors"],
                               codex_capabilities=self.options["codex_capabilities"],
                               effort=self.options["effort"] if self.effort_available() else "",
                               fast_mode=self.options["fast_mode"] and self.fast_mode_available(),
                               custom_prompt=self.options["custom_prompt"], images=images)
        except Exception as exc:
            self.on_failure(str(exc))

    def on_session_opened(self, session_id):
        # An init event means the CLI owns this session, including interrupted turns.
        self.agent_started = True
        self.native_session_id = session_id
        self.sent_history = self.request_history_end
        if not self.save():
            self.agent.cancel(tr("Could not save the session state"))

    def on_progress(self, preview):
        if not self.running or not any(preview.values()):
            return
        if preview.get("reasoning", ""):
            self.reasoning.emit(preview["reasoning"])
        if preview.get("message") or preview.get("code"):
            if self.streaming_index is None:
                self.streaming_index = self.log(self.agent_label, "")
            self.messages[self.streaming_index].update(text=preview["message"], code=preview["code"])
            self.message_changed.emit(self.streaming_index)
            self.waiting_changed.emit(False)
            self.set_status(self.agent_label + tr(" is responding…"))

    def on_response(self, response):
        if not self.running:
            return
        self.waiting_changed.emit(False)
        if not self.agent_started:
            self.on_session_opened(self.session_id)
        if not self.session_title and not any(item["role"] == "assistant" for item in self.history):
            self.session_title = " ".join(response.get("title", "").split())[:50]
        self.history.append({"role": "assistant", "content": response})
        index = self.log(self.agent_label, "") if self.streaming_index is None else self.streaming_index
        self.streaming_index = None
        self.messages[index].update(text=response["message"], code=response["code"])
        self.message_changed.emit(index)
        if not response["code"].strip():
            self.set_running(False)
            summary = response["message"]
            if response.get("question", "").strip():
                self.messages[index].update(
                    question=response["question"].strip(), choices=list(response.get("choices", [])),
                    path_request=response.get("path_request", ""),
                    path_suggestion=response.get("path_suggestion", ""))
                self.question_asked.emit(index)
                self.set_status(self.agent_label + tr(" is waiting for your answer"))
                summary = response["question"].strip()
            elif response.get("suggestion", "").strip():
                self.messages[index]["suggestion"] = response["suggestion"].strip()
                self.question_asked.emit(index)
            self.save()
            self.attention_needed.emit(summary)
            return
        self.pending_code = response["code"]
        if not self.save():
            self.on_failure(tr("Code was not run because the session could not be saved"))
            return
        mode = self.options["approval_mode"]
        needs_approval = mode == "ask" or (mode == "auto" and response.get("requires_approval", True))
        if not needs_approval:
            self.execute()
            return
        self.approval_requested.emit(index)
        reason = response.get("approval_reason", "").strip()
        if not reason:
            reason = tr("Ask mode requires confirmation before running.") if mode == "ask" else tr("No AI risk assessment was provided, so confirmation is required.")
        self.log("Confirm execution", reason + tr("\nChoose Approve and run, Always approve, or Stop."))
        self.set_status(tr("Waiting for execution approval"))
        self.save()
        self.attention_needed.emit(tr("Waiting for execution approval") + ": " + reason)

    def execute(self):
        """Run the pending code; the front end calls this once the user approves."""
        if self.pending_code is None or not self.running:
            return
        self.waiting_changed.emit(False)
        code, self.pending_code = self.pending_code, None
        self.set_status(tr("Running Python…"))
        result = self.runtime.execute(code)
        job = self.runtime.take_job()
        self.history.append({"role": "bridge", "content": result})
        attached = "".join(tr("Image shown to the agent: ") + path + "\n"
                           for path in result.get("attached_images", []))
        self.log("QGIS · " + ("Run succeeded" if result["ok"] else "Run error"),
                 result["output"] + (result["error"] or "") + attached or tr("(No output)"))
        if job is None:
            self.continue_after_execution()
        elif not self.save():
            job.cancel()
            self.on_failure(tr("Stopped because execution results could not be saved"))
        else:
            self.job = job
            job.on_done = self.on_job_done
            self.waiting_changed.emit(True)

    def on_job_done(self, job):
        if job is not self.job or not self.running:
            return
        self.job = None
        self.waiting_changed.emit(False)
        summary = job.summary()
        self.history.append({"role": "bridge", "content": {"background_processing": summary}})
        status = ("Background run succeeded" if summary["ok"] else
                  "Background run canceled" if summary["canceled"] else "Background run error")
        self.log("QGIS · " + status, job.algorithm_id + "\n" +
                 json.dumps(summary["results"], ensure_ascii=False, indent=1) +
                 ("\n" + summary["log"] if summary["log"] else ""))
        self.runtime.refresh_canvas()
        self.continue_after_execution()

    def continue_after_execution(self):
        self.set_status(self.agent_label + tr(" is receiving execution results…"))
        # Yield to Qt so the canvas refresh and stop requests can be processed.
        if self.save():
            self.continuation.start(0)
        else:
            self.on_failure(tr("Stopped because execution results could not be saved"))

    def on_failure(self, message, show=True):
        self.continuation.stop()
        self.waiting_changed.emit(False)
        self.pending_code = None
        self.history.append({"role": "bridge", "content": "Interaction stopped: " + message})
        if self.streaming_index is not None:
            index, self.streaming_index = self.streaming_index, None
            self.messages[index]["role"] = self.agent_label + " · Response interrupted (not run)"
            self.message_changed.emit(index)
        if show:
            self.log("Error / stopped", message)
        self.set_running(False)
        self.save()

    def on_login_required(self, detail):
        self.on_failure(detail, show=False)
        self.login_required.emit(detail)

    def on_usage_updated(self, usage):
        self.context_usage = usage
        self.usage_changed.emit()

    def cancel(self):
        self.continuation.stop()
        if self.job is not None:
            self.job.cancel()
            self.job = None
            self.on_failure(tr("Stopped. The background Processing run was canceled."))
        elif self.agent.process is not None:
            self.agent.cancel()
        else:
            self.on_failure(tr("Stopped. Pending code was not run."))

    # Persistence

    def save(self):
        self.normalize_model()
        payload = {"version": 1, "title": self.session_title, "history": self.history, "model": self.options["model"],
                   "effort": self.options["effort"], "fast_mode": self.options["fast_mode"],
                   "draft": self.draft, "interrupted": self.running,
                   "agent_started": self.agent_started, "sent_history": self.sent_history,
                   "provider": self.options["provider"], "native_session_id": self.native_session_id,
                   "context_usage": self.context_usage,
                   "codex_capabilities": self.options["codex_capabilities"],
                   "enable_skills": self.options["enable_skills"],
                   "enable_connectors": self.options["enable_connectors"],
                   "messages": [dict(message) for index, message in enumerate(self.messages)
                                if index != self.streaming_index]}
        try:
            self.session_id = self.store.save(self.session_id, self.listed_title, payload)
            QSettings().setValue("qtaro/last_session", self.session_id)
            self.saved.emit()
            return True
        except Exception as exc:
            self.log("Save error", str(exc))
            self.set_status(tr("Could not save the session"))
            return False

    def load(self, session_id):
        try:
            payload = self.store.load(session_id)
        except Exception as exc:
            self.log("Load error", str(exc))
            return False
        self.session_id = session_id
        self.session_title = payload.get("title", "")
        self.context_usage = payload.get("context_usage")
        # Earlier versions persisted this UI-only notice; remove it without changing
        # the cursor that tracks which history entries were sent to the CLI.
        old_history = payload["history"]
        self.sent_history = payload.get("sent_history", 0)
        self.sent_history -= sum(
            entry.get("role") == "bridge" and
            isinstance(entry.get("content"), str) and entry["content"].startswith(RESTORE_NOTICES)
            for entry in old_history[:self.sent_history])
        self.history = [entry for entry in old_history if not (
            entry.get("role") == "bridge" and isinstance(entry.get("content"), str) and
            entry["content"].startswith(RESTORE_NOTICES))]
        self.options["provider"] = payload.get("provider", "claude")
        self.options["codex_capabilities"] = payload.get("codex_capabilities", {})
        self.agent_started = payload.get("agent_started", payload.get("claude_started", False))
        self.native_session_id = payload.get("native_session_id") or (session_id if self.agent_started else None)
        self.options["model"] = payload.get("model", "")
        self.options["effort"] = payload.get("effort") or default_effort(self.options["provider"], self.options["model"])
        self.options["fast_mode"] = payload.get("fast_mode", False)
        for key in ("enable_skills", "enable_connectors"):
            self.options[key] = payload.get(key, False)
        self.draft = payload.get("draft", "")
        self.pending_code = None
        self.streaming_index = None
        self.runtime = QgisRuntime(self.runtime.iface)
        self.messages = []
        for message in payload["messages"]:
            if message["role"] == "QGIS" and (
                    message["text"].startswith(RESTORE_NOTICES) or
                    message["text"] in NEW_SESSION_NOTICES):
                continue
            entry = new_message(from_legacy(message["role"]), message["text"], message["code"])
            if message.get("question"):
                entry.update(question=message["question"], choices=list(message.get("choices", [])),
                             path_request=message.get("path_request", ""),
                             path_suggestion=message.get("path_suggestion", ""))
            elif message.get("suggestion"):
                entry["suggestion"] = message["suggestion"]
            self.messages.append(entry)
        self.reset.emit()
        if self.history:
            note = tr(RESTORE_NOTICE)
            if payload.get("interrupted"):
                note += tr(" The previous operation ended early; some changes may have been applied.")
            self.notice.emit(note)
        self.save()
        self.changed.emit()
        return True

    def open_question_index(self):
        """The latest agent question or suggestion that can still be answered, if any."""
        for index in range(len(self.messages) - 1, -1, -1):
            message = self.messages[index]
            if message["role"] in ("You", self.agent_label):
                return index if message["role"] == self.agent_label and (
                    message["question"] or message["suggestion"]) else None
        return None

    def switch_to(self, session_id):
        if self.running or not session_id or session_id == self.session_id:
            return
        if self.save():
            self.load(session_id)

    def new_chat(self, provider=None):
        """Start a session; an untouched one is reused, switching its provider if asked."""
        if self.running:
            return
        provider = provider or self.options["provider"]
        if not self.history and not self.agent_started and not self.draft.strip():
            if provider != self.options["provider"]:
                previous = {key: self.options[key] for key in ("provider", "model", "effort", "fast_mode")}
                self.options["provider"] = provider
                self.options["model"] = QSettings().value("qtaro/" + ("codex_model" if provider == "codex" else "model"), "")
                self.options["effort"] = (QSettings().value("qtaro/" + provider + "_effort", "")
                                          or default_effort(provider, self.options["model"]))
                self.options["fast_mode"] = QSettings().value("qtaro/" + provider + "_fast_mode", False, type=bool)
                if not self.save():
                    self.options.update(previous)
                self.changed.emit()
            return
        if self.save():
            self.start(provider)

    def start(self, provider=None):
        self.options["codex_capabilities"] = json.loads(QSettings().value("qtaro/codex_capabilities", "{}"))
        if provider is not None:
            self.options["provider"] = provider
        self.agent_started = False
        self.native_session_id = None
        self.sent_history = 0
        self.session_id = None
        self.session_title = ""
        self.context_usage = None
        self.history = []
        self.messages = []
        self.draft = ""
        self.pending_code = None
        self.streaming_index = None
        self.runtime = QgisRuntime(self.runtime.iface)
        self.options["model"] = QSettings().value("qtaro/" + ("codex_model" if self.options["provider"] == "codex" else "model"), "")
        self.options["effort"] = (QSettings().value("qtaro/" + self.options["provider"] + "_effort", "")
                                  or default_effort(self.options["provider"], self.options["model"]))
        self.options["fast_mode"] = QSettings().value("qtaro/" + self.options["provider"] + "_fast_mode", False, type=bool)
        self.options["enable_skills"] = QSettings().value("qtaro/enable_skills", True, type=bool)
        self.options["enable_connectors"] = QSettings().value("qtaro/enable_connectors", False, type=bool)
        self.reset.emit()
        self.notice.emit(tr(NEW_SESSION_NOTICE))
        self.save()
        self.changed.emit()

    def shutdown(self):
        self.continuation.stop()
        if self.running:
            self.cancel()
        self.save()
        self.agent.close()
        self.store.close()
