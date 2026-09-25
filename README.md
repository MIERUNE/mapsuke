# QGIS Agent

QGIS Agent lets you work with your QGIS project through a chat with Claude Code or Codex. It can inspect layers and Processing tools, run generated Python in QGIS, and return the results in the conversation. You can also save reusable tasks as Processing tools.

## Usage

1. Install QGIS 3.44 or later (including QGIS 4) and [Claude Code](https://code.claude.com/docs/en/overview) or the [Codex CLI](https://developers.openai.com/codex/cli).
2. Download the plugin ZIP from [Releases](https://github.com/Kanahiro/qgis-agent/releases). In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP** and select it.
3. Enable QGIS Agent and open it from the Plugins menu or toolbar. Select **New session**, choose Claude or Codex, and follow the login prompt if needed.
4. Enter a request such as “Add a point in Sapporo.” In the default **Ask** mode, review the generated Python and approve it before it runs.

If QGIS cannot find the CLI, set its executable path in QGIS Agent's settings. Generated Python runs with the same permissions as QGIS.
