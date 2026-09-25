# QGIS Agent

QGISのチャットからClaude CodeまたはCodexに作業を依頼できるプラグインです。現在のプロジェクトのレイヤーやProcessingツールを参照し、生成したPythonをQGISで実行して結果を会話に返します。よく使う処理はProcessingツールとして保存できます。

## 使い方

1. QGIS 3.44以降（QGIS 4にも対応）と、[Claude Code](https://code.claude.com/docs/en/overview)または[Codex CLI](https://developers.openai.com/codex/cli)を用意します。
2. [Releases](https://github.com/Kanahiro/qgis-agent/releases)からプラグインのZIPをダウンロードし、QGISの「プラグイン → プラグインの管理とインストール → ZIPからインストール」で読み込みます。
3. QGIS Agentを有効にし、メニューまたはツールバーから開きます。「新しいセッション」でClaudeかCodexを選んでください。CLIに未ログインの場合は、画面の案内に従ってログインします。
4. たとえば「札幌に点を追加して」と入力します。既定のAskモードでは、表示されたPythonを確認してから「承認して実行」を押します。

CLIが見つからない場合は、右上の設定で実行ファイルのパスを指定してください。生成されたPythonはQGISと同じ権限で動作します。
