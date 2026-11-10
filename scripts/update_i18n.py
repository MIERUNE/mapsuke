"""Sync every translation dictionary in i18n.py with the English source text used in the code.

Source text is every string literal passed to tr().
The dictionaries are the ones listed in LANGUAGES (JA, TR, ...). In each of them, entries whose
key is no longer used are removed, and new source text is added with an empty translation for
a person to fill in. Run with --check to only report differences.
"""

import ast
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "i18n.py"


def source_files():
    return [*sorted(ROOT.glob("*.py")), *sorted((ROOT / "core").glob("*.py")), *sorted((ROOT / "ui").glob("*.py"))]


def used_keys():
    """Return source text in order of first appearance."""
    keys = {}
    for path in source_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                keys.setdefault(node.args[0].value, f"{path.relative_to(ROOT)}:{node.lineno}")
    return keys


def table_names(tree):
    """Names of the dictionaries in LANGUAGES, in order."""
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "LANGUAGES"):
            return [value.id for value in node.value.values]
    raise SystemExit("i18n.py must define LANGUAGES = {prefix: DICTIONARY, ...}")


def string_constants(tree):
    """Module-level NAME = "text" assignments, which a long key may be spelled through."""
    return {node.targets[0].id: node.value.value for node in tree.body
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)}


def table_entries(tree, name):
    """Yield (key, first line, last line) for dict entries and separate NAME[...] = ... statements."""
    constants = string_constants(tree)

    def key_of(node):
        return constants[node.id] if isinstance(node, ast.Name) else node.value

    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name):
            yield from ((key.value, key.lineno, value.end_lineno) for key, value in zip(node.value.keys, node.value.values))
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript)
                and isinstance(node.targets[0].value, ast.Name) and node.targets[0].value.id == name):
            yield key_of(node.targets[0].slice), node.lineno, node.end_lineno


def sync_table(name, check, used):
    """Sync one dictionary; return True if a --check run found differences."""
    text = I18N.read_text(encoding="utf-8")
    tree = ast.parse(text)
    table = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name)
    entries = list(table_entries(tree, name))
    existing = {key for key, _, _ in entries}
    stale = [(key, first, last) for key, first, last in entries if key not in used]
    added = [key for key in used if key not in existing]
    for key, _, _ in stale:
        print(f"{name} remove:", json.dumps(key, ensure_ascii=False))
    for key in added:
        print(f"{name} add:   ", json.dumps(key, ensure_ascii=False), "(" + used[key] + ")")
    if check or not (stale or added):
        return check and bool(stale or added)

    lines = text.splitlines(keepends=True)
    # The dict's closing brace is on its own line; new entries go right above it.
    closing = table.end_lineno - 1
    for key, first, last in sorted(stale, key=lambda entry: entry[1], reverse=True):
        if first > table.end_lineno:
            # A separate NAME[...] statement also takes its leading comment and blank line.
            while first > 1 and lines[first - 2].lstrip().startswith("#"):
                first -= 1
            if first > 1 and not lines[first - 2].strip():
                first -= 1
        else:
            closing -= last - first + 1
        del lines[first - 1:last]
    lines[closing:closing] = [f"    {json.dumps(key, ensure_ascii=False)}: \"\",\n" for key in added]
    I18N.write_text("".join(lines), encoding="utf-8")
    if added:
        print(f"Fill in the {len(added)} empty {name} translation(s) in i18n.py.")
    return False


def main(check):
    used = used_keys()
    differs = False
    # Each dictionary is rewritten and re-parsed in turn, so line numbers stay valid.
    for name in table_names(ast.parse(I18N.read_text(encoding="utf-8"))):
        differs |= sync_table(name, check, used)
    return 1 if differs else 0


if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--check"]):
        raise SystemExit("Usage: python3 scripts/update_i18n.py [--check]")
    sys.exit(main(sys.argv[1:] == ["--check"]))
