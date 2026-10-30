"""Every Claude model ID Mapsuke offers, and what it needs to know about each.

Codex models are not listed here: they come from the configured CLI's catalog
(see model_compat.listed_codex_models), as the same Model rows.
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
DEFAULT_CHOICE = (tr("Default"), "")
MODEL_CHOICES = tuple((model.label, model.id) for model in CLAUDE) + (DEFAULT_CHOICE,)


def default_effort(provider, model):
    if provider == "codex":
        return "medium"
    known = MODELS.get(model)
    return (known and known.effort) or "high"


def has_effort(provider, model):
    """Unknown models keep the effort control; the CLI reports what it rejects."""
    return provider == "codex" or model not in MODELS or MODELS[model].effort is not None
