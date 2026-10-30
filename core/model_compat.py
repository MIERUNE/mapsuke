"""Inspect the configured CLI before offering pinned model IDs."""
from ..i18n import tr

import json
import re
import shutil
import subprocess  # nosec B404
import threading
from functools import lru_cache
from pathlib import Path


# Claude Code rejects these model IDs before the listed releases.
CLAUDE_MIN_VERSION = {
    "claude-haiku-5-5": (2, 1, 293),
    "claude-sonnet-5-5": (2, 1, 284),
    "claude-opus-5-5": (2, 1, 280),
    "claude-fable-5-1": (2, 1, 257),
    "claude-opus-5": (2, 1, 219),
    "claude-sonnet-5": (2, 1, 197),
    "claude-opus-4-8": (2, 1, 154),
    "claude-opus-4-7": (2, 1, 111),
    "claude-sonnet-4-6": (2, 1, 45),
    "claude-opus-4-6": (2, 1, 32),
    "claude-opus-4-5": (2, 0, 51),
}


def _binary_key(executable):
    path = shutil.which(executable) or executable
    try:
        stat = Path(path).stat()
    except OSError:
        return path, None, None
    return path, stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=16)
def _capabilities(provider, path, modified, size):
    try:
        # Without --bundled, Codex lists the account's catalog, which gains new
        # models without a CLI update. It caches the catalog and falls back to
        # the bundled one when signed out, but a stale cache costs a network fetch.
        args = [path, "--version"] if provider == "claude" else [path, "debug", "models"]
        # The configured CLI is invoked with fixed arguments and no shell.
        result = subprocess.run(args, capture_output=True, text=True,  # nosec B603
                                timeout=2 if provider == "claude" else 10, check=True)
        if provider == "claude":
            match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", result.stdout)
            return tuple(map(int, match.groups())) if match else None
        catalog = json.loads(result.stdout)
        return frozenset(model["slug"] for model in catalog["models"]
                         if model.get("visibility") == "list")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        # A custom or older CLI may not expose a local inventory. Let its own
        # model validation report an error rather than guessing compatibility.
        return None


def unavailable_reason(provider, executable, model):
    """Return a proven CLI-version incompatibility, never a catalog guess."""
    if provider != "claude" or not model:
        return None
    capability = _capabilities(provider, *_binary_key(executable))
    if capability is None:
        return None
    required = CLAUDE_MIN_VERSION.get(model)
    if required and capability < required:
        return (model + tr(" requires Claude Code ") + '.'.join(map(str, required)) +
                tr(" or later (current version: ") + '.'.join(map(str, capability)) + ")")
    return None


_inspected = set()
_pending = set()


def listed_codex_models(executable, on_ready=None):
    """Return local picker suggestions; absence does not prove a model unusable.

    With on_ready, never block: until the CLI has been inspected, return None,
    inspect it on a worker thread, and call on_ready() from that thread.
    """
    key = ("codex",) + _binary_key(executable)
    if on_ready is None or key in _inspected:
        listed = _capabilities(*key)
        _inspected.add(key)
        return listed
    if key not in _pending:
        _pending.add(key)
        threading.Thread(target=lambda: (listed_codex_models(executable), on_ready()), daemon=True).start()
    return None


def hidden_reason(provider, executable, endpoint, model, on_ready=None):
    """Return why the chat picker leaves out a model for this CLI and model service."""
    if provider == "codex" and endpoint == "default" and model:
        listed = listed_codex_models(executable, on_ready)
        if listed is not None and model not in listed:
            return model + tr(" is not in the configured Codex CLI's model list")
    return unavailable_reason(provider, executable, model)
