"""Present CLI token counts without inventing limits for unknown models."""
try:
    from .i18n import tr
except ImportError:  # Standalone unit tests
    from i18n import tr

# These limits are model specifications, not a quota or a record of total spend.
CONTEXT_WINDOWS = {
    'claude-opus-5-5': 1_000_000,
    'claude-fable-5-1': 1_000_000,
    'claude-opus-5': 1_000_000,
    'claude-sonnet-5': 1_000_000,
    'claude-haiku-4-5-20251001': 200_000,
    'gpt-6-astra': 1_050_000,
    'gpt-5.6-sol': 1_050_000,
    'gpt-5.6-terra': 1_050_000,
    'gpt-5.6-luna': 1_050_000,
    'gpt-5.5': 1_050_000,
}


def context_meter(usage, selected_model):
    """Return compact tooltip text and a 0–1000 ring value."""
    if (not isinstance(usage, dict) or type(usage.get('tokens')) is not int or
            usage['tokens'] <= 0):
        return '0', 0
    tokens = usage['tokens']
    model = usage.get('model') or selected_model
    if not isinstance(model, str):
        return '0', 0
    if selected_model and model != selected_model and not model.startswith(selected_model + '-'):
        return '0', 0
    window = CONTEXT_WINDOWS.get(model) or (CONTEXT_WINDOWS.get(selected_model)
                                             if model.startswith(selected_model + '-') else None)
    if not window:
        return f'{tokens:,}' + tr(' tokens · limit unknown'), None
    if tokens > window:
        return f'{tokens:,}' + tr(' tokens · percentage unknown'), None
    return f'{tokens / window:.1%} · {tokens:,} / {window:,} token', round(tokens * 1000 / window)
