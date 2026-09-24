"""Inspect the configured CLI before offering pinned model IDs."""

import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


# Claude Code rejects these model IDs before the listed releases.
CLAUDE_MIN_VERSION = {
    "claude-opus-5-5": (2, 1, 280),
    "claude-fable-5-1": (2, 1, 257),
    "claude-opus-5": (2, 1, 219),
    "claude-sonnet-5": (2, 1, 197),
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
        args = ([path, "--version"] if provider == "claude" else
                [path, "debug", "models", "--bundled"])
        result = subprocess.run(args, capture_output=True, text=True, timeout=2, check=True)
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
        return (f"{model} には Claude Code {'.'.join(map(str, required))} 以上が必要です"
                f"（現在 {'.'.join(map(str, capability))}）")
    return None


def listed_codex_models(executable):
    """Return local picker suggestions; absence does not prove a model unusable."""
    return _capabilities("codex", *_binary_key(executable))
