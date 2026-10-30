"""Inspect the configured CLI before offering pinned model IDs."""
from ..i18n import tr

import json
import re
import shutil
import subprocess  # nosec B404
import threading
from functools import lru_cache
from pathlib import Path

from .models import MODELS, Model


# Claude Code rejects these model IDs before the listed releases.
CLAUDE_MIN_VERSION = {model.id: model.min_cli for model in MODELS.values() if model.min_cli}


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
        # Mapsuke's Fast mode requests service_tier="fast".
        return tuple(Model(model.get("display_name") or model["slug"], model["slug"], model.get("context_window"),
                           None, None, "fast" in (model.get("additional_speed_tiers") or ()))
                     for model in sorted(catalog["models"], key=lambda model: model.get("priority", 0))
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
    """Return the CLI's picker models as Model rows, or None when it cannot list them.

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


def known_models(provider, executable):
    """Map IDs to Model rows without running the CLI; Codex has none until it is listed."""
    if provider != "codex":
        return MODELS
    key = ("codex",) + _binary_key(executable)
    return {model.id: model for model in (_capabilities(*key) if key in _inspected else None) or ()}
