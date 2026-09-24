"""Run the CLIs' own browser login so users never need a terminal or an API key."""
import os
import re

from qgis.PyQt.QtCore import QObject, QProcess, QTimer, pyqtSignal
from .agent import cli_environment

LOGIN_ARGS = {"claude": ["auth", "login", "--claudeai"], "codex": ["login"]}
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
URL = re.compile(r"https://[^\s\x1b]+")


class LoginProcess(QObject):
    """Both CLIs open the browser and finish via a localhost callback; Claude also accepts a pasted code."""
    url_found = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, parent):
        super().__init__(parent)
        self.process = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.cancel("ログインが10分以内に完了しませんでした"))

    def start(self, provider, executable):
        if self.process is not None:
            return
        self.output = ""
        self.url = None
        process = QProcess(self)
        self.process = process
        process.setProcessEnvironment(cli_environment())
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read)
        process.errorOccurred.connect(self._error)
        process.finished.connect(self._finished)
        self.timer.start(600000)
        process.start(os.path.expanduser(executable), LOGIN_ARGS[provider])

    def submit_code(self, code):
        if self.process is not None and code.strip():
            self.process.write((code.strip() + "\n").encode("utf-8"))

    def _read(self):
        self.output += bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.output = ANSI.sub("", self.output)[-16000:]
        match = URL.search(self.output)
        if match and self.url is None:
            self.url = match.group(0)
            self.url_found.emit(self.url)

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            detail = self.process.errorString()
            self._release()
            self.finished.emit(False, "ログインを開始できません。実行パスを確認してください: " + detail)

    def _finished(self, exit_code, exit_status):
        if self.process is None:
            return
        self._read()
        self._release()
        ok = exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        self.finished.emit(ok, "" if ok else self.output.strip()[-2000:] or "ログインに失敗しました")

    def _release(self):
        self.timer.stop()
        process, self.process = self.process, None
        process.deleteLater()

    def cancel(self, reason="ログインを中止しました"):
        if self.process is None:
            return
        process = self.process
        process.blockSignals(True)
        process.kill()
        process.waitForFinished(1000)
        self._release()
        self.finished.emit(False, reason)
