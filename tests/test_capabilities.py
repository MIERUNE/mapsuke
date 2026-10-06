import json
from pathlib import Path
import tempfile
import unittest
from geotaro.core.capabilities import connection_statuses, read_inventory


class InventoryTests(unittest.TestCase):
    def test_local_plugins_and_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / '.claude'
            skill = root / 'skills/personal/SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: sample\ndescription: 日本語の説明\n---\nDo not execute me')
            plugin = root / 'plugins/cache/example/1.0'
            extra = plugin / 'custom/SKILL.md'
            extra.parent.mkdir(parents=True)
            extra.write_text('---\ndescription: plugin skill\n---\nbody')
            (plugin / '.claude-plugin').mkdir()
            (plugin / '.claude-plugin/plugin.json').write_text(json.dumps({'skills': './custom'}))
            (plugin / '.mcp.json').write_text(json.dumps({'mcpServers': {'test': {'command': 'secret-command', 'env': {'KEY': 'SECRET'}}}}))
            (root / 'plugins/installed_plugins.json').write_text(json.dumps({'plugins': {'example@market': [{'installPath': str(plugin), 'scope': 'user'}]}}))
            (root / 'settings.json').write_text(json.dumps({'enabledPlugins': {'example@market': False}}))
            Path(str(root) + '.json').write_text(json.dumps({'mcpServers': {'remote': {'type': 'http', 'url': 'https://SECRET', 'headers': {'Authorization': 'SECRET'}}}}))
            result = read_inventory(root)
            self.assertEqual(len(result['skills']), 2)
            self.assertEqual(len(result['connectors']), 2)
            self.assertIn('Disabled in settings', result['skills'][0]['source'])
            self.assertNotIn('SECRET', json.dumps(result))
            self.assertNotIn('secret-command', json.dumps(result))
            self.assertEqual(result['warnings'], [])

    def test_missing_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(read_inventory(root)['skills'], [])
            (root / 'settings.json').write_text('{broken SECRET')
            result = read_inventory(root)
            self.assertEqual(len(result['warnings']), 1)
            self.assertNotIn('SECRET', str(result))

    def test_cli_status_redaction(self):
        result = connection_statuses('Checking MCP server health...\n'
            'plugin:slack:slack: https://SECRET - ✓ Connected\n'
            'private: command --token SECRET - ✗ Failed to connect\n'
            'login: https://SECRET - ! Needs authentication\n')
        self.assertEqual(result, {'plugin:slack:slack': 'Connected', 'private': 'Connection failed', 'login': 'Authentication required'})
        self.assertNotIn('SECRET', str(result))


class CodexInventoryTests(unittest.TestCase):
    def test_inventory_and_overrides_preserve_existing_settings(self):
        import tomllib
        from unittest.mock import patch
        from geotaro.core.capabilities import read_codex_inventory, codex_capability_args
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / '.codex'
            skill = home / '.agents/skills/example/SKILL.md'
            skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: Example\ndescription: Example skill\n---\nbody')
            root.mkdir()
            config = ('[[skills.config]]\npath = ' + json.dumps(str(skill.parent)) + '\nenabled = false\n'
                      '[mcp_servers."test_server"]\ncommand = "SECRET"\nenabled = false\n'
                      '[mcp_servers."test_server".env]\nTOKEN = "SECRET"\n')
            (root / 'config.toml').write_text(config)
            inventory = read_codex_inventory(root, home)
            self.assertEqual(inventory['warnings'], [])
            self.assertEqual(inventory['skills'][0]['name'], 'Example')
            self.assertFalse(inventory['skills'][0]['enabled'])
            self.assertNotIn('SECRET', json.dumps(inventory))
            with patch('geotaro.core.capabilities.read_codex_inventory', return_value=inventory):
                args = codex_capability_args({'skills': {str(skill): True}, 'connectors': {'test_server': False}})
            parsed = tomllib.loads('\n'.join(args[1::2]))
            self.assertEqual(parsed['skills']['config'], [{'path': str(skill.parent), 'enabled': True}])
            self.assertFalse(parsed['mcp_servers']['test_server']['enabled'])
            self.assertEqual((root / 'config.toml').read_text(), config)
            self.assertEqual(codex_capability_args({}), [])
            (root / 'config.toml').write_text('invalid SECRET')
            inventory = read_codex_inventory(root, home)
            self.assertTrue(inventory['warnings'])
            self.assertNotIn('SECRET', json.dumps(inventory))
            with patch('geotaro.core.capabilities.read_codex_inventory', return_value=inventory):
                with self.assertRaises(ValueError):
                    codex_capability_args({'skills': {str(skill): False}})
