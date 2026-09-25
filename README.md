# QGIS Agent

QGIS Agent lets you work with your QGIS project through a chat with Claude Code or Codex.

## Key ideas

- **No MCP setup:** Connect your agent to QGIS without setting up an MCP server.
- **Your own agent:** Use your existing Claude Code or Codex CLI login and subscription.
- **Python in QGIS:** The agent can run Python with access to QGIS and its Processing tools, so it can handle a wide range of tasks. This code has the same file and network permissions as QGIS; review it and understand the security risks before running it.
- **Processing tools as skills:** The agent discovers the Processing tools available in QGIS and uses them much like an AI agent uses skills.
- **Reusable workflows:** Save routine operations as Processing scripts that remain available from the toolbox and models.

## Usage

1. Install QGIS 3.44 or later (including QGIS 4) and [Claude Code](https://code.claude.com/docs/en/overview) or the [Codex CLI](https://developers.openai.com/codex/cli).
2. Download the plugin ZIP from [Releases](https://github.com/Kanahiro/qgis-agent/releases). In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP** and select it.
3. Enable QGIS Agent and open it from the Plugins menu or toolbar. Select **New session**, choose Claude or Codex, and follow the login prompt if needed.
4. Enter a request such as “Add a point in Sapporo.” In the default **Ask** mode, review the generated Python and approve it before it runs.

If QGIS cannot find the CLI, set its executable path in QGIS Agent's settings.
