"""What Mapsuke knows about models, as Model rows, and the rules built on them.

Claude Code lists no models, so Claude's are a table here. Codex's come from
the configured CLI's catalog, read by codex_models(); model_compat runs the CLI.
"""
from ..i18n import tr

from collections import namedtuple


# context: tokens for the usage ring; None when unknown, so no limit is invented.
# min_cli: Claude Code release that first accepts the ID.
# effort: default reasoning effort; None when the model has no effort setting.
# fast: offers Fast mode.
# Codex rows leave min_cli and effort unset.
Model = namedtuple("Model", "label id context min_cli effort fast")

# Explicit IDs keep the advertised version stable when Claude updates its aliases.
# Verified 2026-10-17: https://code.claude.com/docs/en/model-config
CLAUDE = (
    Model("Claude Opus 5.5", "claude-opus-5-5", 1_000_000, (2, 1, 280), "medium", True),
    Model("Claude Fable 5.1", "claude-fable-5-1", 1_000_000, (2, 1, 257), "high", False),
    Model("Claude Sonnet 5.5", "claude-sonnet-5-5", 1_000_000, (2, 1, 284), "medium", False),
    Model("Claude Haiku 5.5", "claude-haiku-5-5", 1_000_000, (2, 1, 293), "medium", False),
    Model("Claude Sonnet 5", "claude-sonnet-5", 1_000_000, (2, 1, 197), "high", False),
    Model("Claude Opus 4.8", "claude-opus-4-8", 1_000_000, (2, 1, 154), "high", False),
    Model("Claude Opus 4.7", "claude-opus-4-7", 1_000_000, (2, 1, 111), "high", False),
    Model("Claude Opus 4.6", "claude-opus-4-6", 1_000_000, (2, 1, 32), "high", False),
    Model("Claude Sonnet 4.6", "claude-sonnet-4-6", 1_000_000, (2, 1, 45), "high", False),
    Model("Claude Opus 4.5", "claude-opus-4-5", 200_000, (2, 0, 51), "high", False),
    Model("Claude Sonnet 4.5", "claude-sonnet-4-5", 200_000, None, None, False),
    Model("Claude Haiku 4.5", "claude-haiku-4-5-20251001", 200_000, None, None, False),
)
# No longer offered, but chats that saved them still get these checks and limits.
CLAUDE_RETIRED = (
    Model("Claude Opus 5", "claude-opus-5", 1_000_000, (2, 1, 219), "high", True),
)
MODELS = {model.id: model for model in CLAUDE + CLAUDE_RETIRED}

# Picker entries as (label, ID); the empty ID follows the CLI's own default.
CLAUDE_CHOICES = tuple((model.label, model.id) for model in CLAUDE)
DEFAULT_CHOICE = (tr("Default"), "")


def codex_models(catalog):
    """Read `codex debug models` output into the Model rows its picker lists, in its order."""
    # Mapsuke's Fast mode requests service_tier="fast".
    return tuple(Model(entry.get("display_name") or entry["slug"], entry["slug"], entry.get("context_window"),
                       None, None, "fast" in (entry.get("additional_speed_tiers") or ()))
                 for entry in sorted(catalog["models"], key=lambda entry: entry.get("priority", 0))
                 if entry.get("visibility") == "list")


def default_effort(provider, model):
    if provider == "codex":
        return "medium"
    known = MODELS.get(model)
    return (known and known.effort) or "high"


def min_claude_version(model):
    """Return the Claude Code release that first accepts the ID, or None if any release does."""
    known = MODELS.get(model)
    return known and known.min_cli


def has_fast_mode(endpoint, known):
    """Fast mode needs the default service and a model row that offers it."""
    return endpoint == "default" and bool(known and known.fast)


def has_effort(provider, model):
    """Unknown models keep the effort control; the CLI reports what it rejects."""
    return provider == "codex" or model not in MODELS or MODELS[model].effort is not None
