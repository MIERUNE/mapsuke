"""Present CLI token counts without inventing limits for unknown models."""
from ..i18n import tr

# These limits are model specifications, not a quota or a record of total spend.


def context_meter(usage, selected_model, models):
    """Return compact tooltip text and a 0–1000 ring value; models maps IDs to Model rows."""
    if (not isinstance(usage, dict) or type(usage.get('tokens')) is not int or
            usage['tokens'] <= 0):
        return '0', 0
    tokens = usage['tokens']
    model = usage.get('model') or selected_model
    if not isinstance(model, str):
        return '0', 0
    if selected_model and model != selected_model and not model.startswith(selected_model + '-'):
        return '0', 0
    known = models.get(model) or (models.get(selected_model) if model.startswith(selected_model + '-') else None)
    window = known and known.context
    if not window:
        return f'{tokens:,}' + tr(' tokens · limit unknown'), None
    if tokens > window:
        return f'{tokens:,}' + tr(' tokens · percentage unknown'), None
    return f'{tokens / window:.1%} · {tokens:,} / {window:,} token', round(tokens * 1000 / window)
