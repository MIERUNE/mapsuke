"""Read Claude's local inventory without executing skills or exposing MCP secrets."""
import json
import os
import re
from pathlib import Path


def read_inventory(config_dir=None):
    root = Path(config_dir or os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")).expanduser()
    skills, connectors, warnings = [], [], []

    def read_json(path):
        try:
            with path.open(encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            warnings.append(str(path) + ": 読み取れませんでした")
            return {}

    def scan_skills(directory, source, prefix=""):
        if not directory.is_dir():
            return
        paths = [directory / "SKILL.md"] if (directory / "SKILL.md").is_file() else sorted(directory.glob("*/SKILL.md"))
        for path in paths:
            if path.parent.name.lower() == "synced":
                continue
            try:
                with path.open(encoding="utf-8") as stream:
                    text = stream.read(32768)
                metadata = skill_metadata(text)
                skills.append({"name": prefix + str(metadata.get("name") or path.parent.name),
                               "description": str(metadata.get("description") or "説明なし"),
                               "source": source, "path": str(path)})
            except (OSError, UnicodeError):
                warnings.append(str(path) + ": 読み取れませんでした")

    def add_servers(data, source, path, prefix=""):
        servers = data.get("mcpServers", data)
        if not isinstance(servers, dict):
            return
        for name, config in servers.items():
            if not isinstance(config, dict):
                continue
            transport = config.get("type") or ("stdio" if "command" in config else "http" if "url" in config else "不明")
            if transport not in ("stdio", "http", "sse"):
                transport = "不明"
            connectors.append({"name": prefix + name, "transport": transport,
                               "source": source, "path": str(path), "status": "未確認"})

    scan_skills(root / "skills", "個人")
    settings = read_json(root / "settings.json")
    registry = read_json(root / "plugins/installed_plugins.json").get("plugins", {})
    if not isinstance(registry, dict):
        warnings.append("プラグイン登録情報の形式が未対応です")
        registry = {}
    enabled = settings.get("enabledPlugins", {})
    if not isinstance(enabled, dict):
        enabled = {}
    for plugin, installations in registry.items():
        if not isinstance(installations, list):
            warnings.append(plugin + ": プラグイン登録形式が未対応です")
            continue
        for installation in installations:
            if not isinstance(installation, dict) or not isinstance(installation.get("installPath"), str):
                continue
            path = Path(installation["installPath"])
            scope = installation.get("scope", "不明")
            state = "有効設定" if enabled.get(plugin) is True else "無効設定" if enabled.get(plugin) is False else "有効設定未確認"
            source = plugin + " · " + str(scope) + " · " + state
            if not path.is_dir():
                warnings.append(plugin + ": インストール先が見つかりません")
                continue
            name = plugin.split("@", 1)[0]
            scan_skills(path / "skills", source, name + ":")
            manifest = read_json(path / ".claude-plugin/plugin.json")
            extra_skills = manifest.get("skills", [])
            if isinstance(extra_skills, str):
                extra_skills = [extra_skills]
            if isinstance(extra_skills, list):
                for relative in extra_skills:
                    if isinstance(relative, str) and relative not in ("./skills", "skills"):
                        scan_skills(path / relative, source, name + ":")
            default_mcp = path / ".mcp.json"
            add_servers(read_json(default_mcp), source, default_mcp, "plugin:" + name + ":")
            extra = manifest.get("mcpServers")
            if isinstance(extra, dict):
                add_servers(extra, source, path / ".claude-plugin/plugin.json", "plugin:" + name + ":")
            else:
                for relative in ([extra] if isinstance(extra, str) else extra if isinstance(extra, list) else []):
                    if isinstance(relative, str) and relative not in ("./.mcp.json", ".mcp.json"):
                        add_servers(read_json(path / relative), source, path / relative, "plugin:" + name + ":")
    # Claude stores user MCP configuration next to its configuration directory.
    user_config = Path(str(root) + ".json")
    add_servers({"mcpServers": read_json(user_config).get("mcpServers", {})}, "個人", user_config)
    def unique(rows):
        return sorted({(r["name"], r["path"], r["source"]): r for r in rows}.values(), key=lambda r: r["name"].casefold())
    return {"skills": unique(skills), "connectors": unique(connectors), "warnings": warnings}


def skill_metadata(text):
    if not text.startswith("---\n"):
        return {}
    header = text.split("\n---", 1)[0][4:]
    try:
        import yaml
        data = yaml.safe_load(header)
        return data if isinstance(data, dict) else {}
    except ImportError:
        # Keep inventory usable in QGIS distributions without PyYAML.
        result = {}
        for key in ("name", "description"):
            match = re.search(r"^" + key + r":\s*(.*)(?:\n((?:[ \t]+.*\n?)*))?", header, re.M)
            if match:
                value = match.group(1).strip()
                if value in ("|", ">", "|-", ">-"):
                    value = " ".join((match.group(2) or "").split())
                result[key] = value.strip("\"'")
        return result
    except Exception:
        return {"description": "メタデータを解析できませんでした"}


def connection_statuses(output):
    """Whitelist health states only: CLI output may contain tokens in URLs/args."""
    statuses = {}
    output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
    for line in output.splitlines():
        match = re.match(r"^([^\s]+):\s+.*? - (.+)$", line)
        if not match:
            continue
        name, state = match.groups()
        if "Needs authentication" in state:
            statuses[name] = "認証が必要"
        elif "Failed to connect" in state:
            statuses[name] = "接続失敗"
        elif "Pending approval" in state:
            statuses[name] = "承認待ち"
        elif "Connected" in state:
            statuses[name] = "接続済み"
        elif "Disabled" in state:
            statuses[name] = "無効"
    return statuses


def read_codex_inventory(config_dir=None, home=None):
    """Read user-defined Codex skills/MCP metadata, never credentials or commands."""
    home = Path(home or Path.home())
    root = Path(config_dir or os.environ.get('CODEX_HOME', home / '.codex'))
    result = {'skills': [], 'connectors': [], 'warnings': [], 'skill_config': []}
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        path = root / 'config.toml'
        config = tomllib.loads(path.read_text()) if path.exists() else {}
        configured = config.get('skills', {}).get('config', [])
        result['skill_config'] = [{'path': row['path'], 'enabled': row.get('enabled', True)} for row in configured]
        paths = set()
        for directory in (home / '.agents/skills', root / 'skills'):
            paths.update(directory.glob('*/SKILL.md'))
            paths.update((directory / '.system').glob('*/SKILL.md'))
        paths.update(Path(row['path']) for row in configured)
        states = {str(Path(row['path'])): row.get('enabled', True) for row in configured}
        for path in sorted(paths):
            if path.is_dir():
                path = path / 'SKILL.md'
            try:
                metadata = skill_metadata(path.read_text()[:32768])
                result['skills'].append({'id': str(path), 'name': str(metadata.get('name') or path.parent.name),
                                         'description': str(metadata.get('description') or ''),
                                         'enabled': states.get(str(path), states.get(str(path.parent), True))})
            except (OSError, UnicodeError):
                result['warnings'].append('読み取れないスキルがあります')
        for name, server in sorted(config.get('mcp_servers', {}).items()):
            result['connectors'].append({'id': name, 'name': name,
                                         'description': 'MCP', 'enabled': server.get('enabled', True)})
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        result['warnings'].append('Codex設定を読み取れませんでした（Python 3.11未満ではtomliが必要です）')
    return result


def codex_capability_args(overrides):
    """Translate only explicit session choices into CLI overrides."""
    args = []
    skills = overrides.get('skills', {})
    if skills:
        # skills.config is an array: preserve user entries when replacing it.
        inventory = read_codex_inventory()
        if inventory['warnings']:
            raise ValueError('Codexのスキル設定を安全に読み込めないため、設定を適用できません')
        states = {row['path']: row['enabled'] for row in inventory['skill_config']}
        for path, enabled in skills.items():
            directory = str(Path(path).parent)
            if directory in states:
                states[directory] = enabled
            else:
                states[path] = enabled
        entries = ', '.join('{path = ' + json.dumps(path, ensure_ascii=False) + ', enabled = ' + str(enabled).lower() + '}'
                            for path, enabled in states.items())
        args += ['-c', 'skills.config=[' + entries + ']']
    for name, enabled in overrides.get('connectors', {}).items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('このMCP名はCLIの個別上書きに対応していません: ' + name)
        args += ['-c', 'mcp_servers.' + name + '.enabled=' + str(enabled).lower()]
    return args
