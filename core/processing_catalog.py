"""Compact inventory of every algorithm available in the live QGIS registry."""
from html import unescape
import re


def processing_catalog(registry):
    providers = sorted(registry.providers(), key=lambda p: p.id())
    catalog = {}
    for provider in providers:
        tools = []
        for algorithm in sorted(provider.algorithms(), key=lambda a: a.id()):
            name = " ".join(algorithm.displayName().split())
            algorithm_id = algorithm.id()
            prefix = provider.id() + ":"
            entry = [algorithm_id[len(prefix):] if algorithm_id.startswith(prefix) else algorithm_id, name]
            try:
                help_text = algorithm.shortHelpString() or ""
            except Exception:
                # A broken third-party help method must not block chat requests.
                help_text = ""
            help_text = " ".join(unescape(re.sub(r"<[^>]+>", " ", help_text)).split())
            if help_text:
                # Keep every tool; bound only each description. Local tools need more
                # room because the agent cannot infer their behavior from its training.
                length = 160 if provider.id() in ("script", "mapsuke") else 48
                entry.append(help_text[:length])
            tools.append(entry)
        catalog[provider.id()] = tools
    return catalog
