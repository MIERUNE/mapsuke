# Qtaro

Qtaro lets you work with your QGIS project through a chat with Claude Code or Codex.

## Key ideas

- **No MCP setup:** Connect your agent to QGIS without setting up an MCP server.
- **Your own agent:** Use your existing Claude Code or Codex CLI login and subscription, or an Anthropic or OpenAI API key.
- **Python in QGIS:** The agent can run Python with access to QGIS and its Processing tools, so it can handle a wide range of tasks. This code has the same file and network permissions as QGIS; review it and understand the security risks before running it.
- **Processing tools as skills:** The agent discovers the Processing tools available in QGIS and uses them much like an AI agent uses skills.
- **Reusable workflows:** Save routine operations as Processing scripts that remain available from the toolbox and models.

## Usage

1. Install QGIS 3.44 or later (including QGIS 4) and [Claude Code](https://code.claude.com/docs/en/overview) or the [Codex CLI](https://developers.openai.com/codex/cli).
2. Install the Qtaro plugin in QGIS.
3. Enable Qtaro and open it from the Plugins menu or toolbar. Select **New session**, choose Claude or Codex, and follow the login prompt if needed.
4. Enter a request such as “Add a point in Sapporo.” In the default **Ask** mode, review the generated Python and approve it before it runs.

If QGIS cannot find the CLI, set its executable path in Qtaro's settings.

On first enable, Qtaro asks whether to copy its bundled QGIS skills into the installed CLIs' skills folders. It does not ask again or copy skills on later starts. Use **Settings → General → Sync built-in skills** to copy them later or replace existing bundled skills; syncing overwrites local edits to those skills.

In **Settings → Claude → Skills**, each personal skill can follow Claude Code's setting or be enabled or disabled for this chat. Changes take effect with the next message and do not edit Claude Code's settings files. Claude plugin skills are listed for reference; manage their availability through Claude Code's plugin settings.

To use an API key instead of a subscription, open Qtaro's settings, choose **Default** under **Model service**, then **API key** under **Authentication** for Claude or Codex, and enter the key. Usage is billed to that key. Qtaro stores it encrypted in the QGIS authentication database, so QGIS may ask for its master password, and passes it only to that CLI (as `ANTHROPIC_API_KEY` or `CODEX_API_KEY`).

### Other model services

In **Settings → Claude** or **Settings → Codex**, choose a **Model service** first. **Authentication** then shows the method available for that service: CLI sign-in or API key for Default, API key for Custom endpoint, and AWS credentials for Bedrock.

- **Custom endpoint:** Enter a base URL and an API key, then enter the service's exact **Custom model ID**. Qtaro sends the key only to that provider's CLI. Each provider has one saved API key shared between Default and Custom endpoint, so replace it when switching services. The Claude endpoint must support the Anthropic API used by Claude Code; the Codex endpoint must support the OpenAI Responses API. A URL alone does not make another protocol compatible.
- **Amazon Bedrock:** Choose Bedrock for Claude, or Bedrock Runtime or Mantle for Codex. Configure AWS credentials or a Bedrock API key and a Region in the environment QGIS inherits, or use a standard AWS profile. Enter the Bedrock model ID or inference profile ID as the custom model ID, then select it in the chat model picker. Bedrock requests are billed through AWS.

The connection setting is separate for Claude and Codex. Changing it starts a fresh native CLI conversation for the current chat and resends its saved history. Credentials and model access must already be configured with the selected service. The **Default** setting keeps the normal CLI connection.
