"""UI translations selected from QGIS's interface locale.

The existing Japanese strings remain stable keys because older sessions persist
some of them as role and notice identifiers. English is the fallback language.
"""
import locale


EN = {
    "デフォルト（Claude Codeの設定）": "Default (Claude Code settings)",
    "デフォルト（Codexの設定）": "Default (Codex settings)",
    "新しいセッション": "New session",
    "新しいセッションを開始しました。": "Started a new session.",
    "セッションを復元しました。Python変数はリセットされ、過去のコードは再実行していません。現在のQGISプロジェクトを参照します。": "Session restored. Python variables were reset and past code was not rerun. The current QGIS project is used.",
    "セッションを切り替え（自動保存）": "Switch sessions (autosaved)",
    "一覧…": "All…", "設定": "Settings", "準備完了": "Ready", "応答待ち": "Waiting for response",
    "QGISでやりたいことを入力…\nEnterで送信 · Shift+Enterで改行": "Describe what you want to do in QGIS…\nEnter to send · Shift+Enter for a new line",
    "承認モード": "Approval mode", "モデル": "Model", "このセッションのモデル": "Model for this session",
    "Ask: 毎回確認 / Auto: AIがリスクを判断 / Full auto: 確認なしで実行": "Ask: confirm each run / Auto: AI assesses risk / Full auto: run without confirmation",
    "次の応答で使う推論の強さ。段階の意味と対応範囲はモデル・CLIごとに異なります。": "Reasoning effort for the next response. Levels and availability vary by model and CLI.",
    "次の応答から高速モードを使います。利用可能なモデルとアカウントが必要です。": "Use fast mode for the next response. Requires a supported model and account.",
    "次の応答から高速モードを使います。追加の利用料金やクレジットが必要です。": "Use fast mode for the next response. Additional charges or credits may apply.",
    "選択中のモデルでは Fast mode を指定できません。": "Fast mode is unavailable for the selected model.",
    "承認して実行": "Approve and run", "今後は自動承認": "Always approve", "送信 ↑": "Send ↑", "停止": "Stop",
    "承認して実行し、以降はFull auto（確認なしで実行）に切り替えます": "Approve and run, then switch to Full auto without further confirmation",
    "コンテキスト使用率": "Context usage", "Pythonコード": "Python code", "あなた": "You",
    "思考の要約\n": "Reasoning summary\n", "が応答しています…": " is responding…",
    "の応答を待っています…": " is responding…", "が回答を待っています": " is waiting for your answer",
    "Pythonを実行中…": "Running Python…", "に実行結果を返します…": " is receiving execution results…",
    "へのログインが必要です": " sign-in required", "ブラウザでログインしてください…": "Sign in in your browser…",
    "ログインできませんでした": "Sign-in failed", "ログインしました": "Signed in",
    "ログインできませんでした: ": "Sign-in failed: ", "にログインしました。メッセージを再送信します。": " signed in. Resending your message.",
    "の実行パスを入力してください": " executable path is required", "。モデルを変更するか、CLIを更新してください。": ". Choose another model or update the CLI.",
    "エラー": "Error", "保存エラー": "Save error", "読込エラー": "Load error", "エラー / 停止": "Error / stopped",
    "会話が上限に達しました。新しいセッションを開始してください": "Conversation limit reached. Start a new session.",
    "セッション状態を保存できませんでした": "Could not save the session state",
    "保存に失敗したためコードを実行しませんでした": "Code was not run because the session could not be saved",
    "実行の確認": "Confirm execution", "実行の承認待ち": "Waiting for execution approval",
    "Askモードのため実行前に確認します。": "Ask mode requires confirmation before running.",
    "AIのリスク評価がないため、実行前に確認します。": "No AI risk assessment was provided, so confirmation is required.",
    "\n承認して実行・今後は自動承認・停止のいずれかを選んでください。": "\nChoose Approve and run, Always approve, or Stop.",
    "承認モードをFull autoに切り替えました。以降のPythonは確認なしで実行します。": "Switched to Full auto. Future Python code will run without confirmation.",
    "実行成功": "Run succeeded", "実行エラー": "Run error", "（出力なし）": "(No output)",
    "実行結果を保存できなかったため停止しました": "Stopped because execution results could not be saved",
    " · 応答中断（未実行）": " · Response interrupted (not run)",
    "停止しました。未実行のコードは実行していません。": "Stopped. Pending code was not run.",
    "利用不可: ": "Unavailable: ", "以前の設定: ": "Previous setting: ",
    " 前回の処理は途中で終了しています。変更が部分的に適用されている可能性があります。": " The previous operation ended early; some changes may have been applied.",
    "セッションを保存できませんでした": "Could not save the session",
    "Autoでは、AIがリスクを評価し、確認不要と判断したPythonコードを自動実行します。AIの判断は誤ることがあります。": "In Auto mode, the AI runs Python code it considers safe without asking. Its assessment may be wrong.",
    "Full autoでは、生成したPythonコードを実行前の確認なしで実行します。": "In Full auto mode, generated Python code runs without prior confirmation.",
    "自動実行のリスクへの同意": "Consent to automatic execution",
    "\n\nコードはQGISと同じ権限で動作し、ファイルの変更・削除や外部へのデータ送信が可能です。変更を自動で元に戻すことはできません。\n\nリスクを理解し、このモードを有効にすることに同意しますか？": "\n\nCode runs with QGIS's permissions and can change or delete files or send data externally. Changes cannot be automatically undone.\n\nDo you understand these risks and agree to enable this mode?",
    "セッション一覧": "Sessions", "タイトルで検索": "Search by title", "さらに表示": "Show more",
    "開く": "Open", "削除": "Delete", "セッションを削除": "Delete session", "削除エラー": "Delete error",
    "このセッションを一覧から削除しますか？QGISのレイヤーとエージェント側の履歴は残ります。": "Delete this session from the list? QGIS layers and the agent's history will remain.",
    "ブラウザに表示されたコードを貼り付け": "Paste the code shown in your browser", "コードを送信": "Submit code",
    "キャンセル": "Cancel", " · ログインが必要です": " · Sign-in required", "にログイン": " sign in",
    "のアカウントでログインしてください。ログインが完了すると、止まったメッセージを自動で再送信します。": " account. When sign-in is complete, the interrupted message will be resent automatically.",
    "開いたページでログインし、表示されたコードを貼り付けてください。": "Sign in on the opened page and paste the displayed code.",
    "コードを確認しています…": "Checking code…", "ブラウザでログインしてください。完了するとこの画面に戻ります。": "Sign in in your browser. Return here when finished.",
    "ブラウザが開かない場合は <a href=\"{0}\">こちらを開いてください</a>": "If the browser does not open, <a href=\"{0}\">open this link</a>",
    "入力欄から自由に回答することもできます。": "You can also answer freely in the input field.",
    "入力欄から回答してください。": "Answer in the input field.",
    "QGIS Agent の設定": "QGIS Agent settings", "一般": "General", "参照…": "Browse…",
    "実行ファイル": "Executable", "Claude Code実行ファイル": "Claude Code executable",
    "Codex実行ファイル": "Codex executable", "のログイン情報を使用します。\n": " credentials are used.\n",
    "ターミナルで codex login を実行してください。": "Run codex login in a terminal.",
    "ターミナルで claude を実行してください。": "Run claude in a terminal.",
    " token · 上限不明": " tokens · limit unknown", " token · 割合不明": " tokens · percentage unknown",
    "スキル": "Skills", "コネクタ": "Connectors", "接続確認": "Check connections",
    "再読み込み": "Refresh", "名前": "Name", "説明": "Description", "読み込み元": "Source",
    "このチャット": "This chat", "接続状態": "Connection status", "種類": "Type", "登録元": "Registered by",
    "このセッション": "This session", "このセッションで": "Use ", "を使用する": " in this session",
    "OKで適用し、次の送信から反映します。読み込み対象はClaude Code側の設定に従います。\nツール実行はClaude側で許可済みの操作に限ります。追加の許可はターミナルの /permissions で設定できます。": "Click OK to apply from the next message. Items loaded follow Claude Code settings.\nOnly tools already permitted by Claude may run. Set additional permissions with /permissions in a terminal.",
    "対象：個人スキル・登録済みプラグイン。組み込み・クラウド同期・プロジェクト直下のスキルは対象外。": "Includes personal skills and registered plugins. Built-in, cloud-synced, and project skills are excluded.",
    "対象：個人・プラグインのMCP。接続確認には現在のClaude実行パスを使います。\n提供ツール：未取得（CLIの一覧機能では取得できません）。": "Includes personal and plugin MCP servers. Connection checks use the configured Claude executable.\nProvided tools: unavailable from the CLI listing.",
    " スキル": " skills", " コネクタ · 接続未確認": " connectors · not checked",
    " · 一部読込失敗（詳細はホバー）": " · some items could not be loaded (hover for details)",
    "使用しない": "Disable", "使用する": "Enable", "読み込み許可": "Allowed to load",
    "Claude側で無効": "Disabled in Claude", "対象外（別スコープ）": "Outside this scope",
    "一般タブでClaudeの実行パスを指定してください": "Set the Claude executable in the General tab",
    "接続を確認しています…": "Checking connections…", "接続確認完了": "Connection check complete",
    "接続確認に失敗しました": "Connection check failed", "接続確認がタイムアウトしました": "Connection check timed out",
    " · コネクタなし、またはCLI出力形式が未対応": " · no connectors or unsupported CLI output",
    "接続確認の出力が上限を超えました": "Connection check output exceeded the limit",
    "Claudeを起動できません。実行パスを確認してください": "Could not start Claude. Check its executable path",
    "未確認": "Not checked", "このセッションでの使用設定です。OKで保存し、次の送信から反映します。\n「CLIの設定に従う」はCodex側の設定を使用します。": "These settings apply to this session. Click OK to save; changes take effect with the next message.\nFollow CLI settings uses Codex's configuration.",
    "CLIの設定に従う": "Follow CLI settings", "保存済みの設定（現在の一覧にはありません）": "Saved setting (not in the current list)",
    "この名前のMCPはCodex CLI側で設定してください": "Configure this MCP name in Codex CLI",
    "対象：個人のローカルスキルとconfig.tomlのMCP。プラグイン・クラウドの項目はCLI側で管理します。\n": "Includes local personal skills and MCP servers in config.toml. Manage plugin and cloud items in the CLI.\n",
    " · 無効設定": " · disabled", "有効設定": "Enabled in settings", "有効設定未確認": "Enabled; not checked",
    "無効設定": "Disabled in settings", "個人": "Personal", "不明": "Unknown", "説明なし": "No description",
    "認証が必要": "Authentication required", "接続失敗": "Connection failed", "承認待ち": "Awaiting approval",
    "接続済み": "Connected", "無効": "Disabled",
    "プラグイン登録情報の形式が未対応です": "Unsupported plugin registry format",
    "メタデータを解析できませんでした": "Could not parse metadata",
    "Codex設定を読み取れませんでした（Python 3.11未満ではtomliが必要です）": "Could not read Codex settings (tomli is required before Python 3.11)",
    "Codexのスキル設定を安全に読み込めないため、設定を適用できません": "Cannot apply settings because Codex skill settings could not be read safely",
    "このMCP名はCLIの個別上書きに対応していません: ": "This MCP name does not support a CLI override: ",
    "読み取れないスキルがあります": "Some skills could not be read",
    ": 読み取れませんでした": ": could not be read", ": インストール先が見つかりません": ": install location not found",
    ": プラグイン登録形式が未対応です": ": unsupported plugin registry format",
    "ログインを中止しました": "Sign-in canceled", "ログインが10分以内に完了しませんでした": "Sign-in did not finish within 10 minutes",
    "ログインを開始できません。実行パスを確認してください: ": "Could not start sign-in. Check the executable path: ",
    "ログインに失敗しました": "Sign-in failed",
    "セッションが見つかりません": "Session not found", "未対応のセッション形式です": "Unsupported session format",
    "セッションの履歴を読み取れません": "Could not read session history",
    "セッション設定の形式が不正です": "Invalid session settings format",
    "セッション継続状態が不正です": "Invalid session resume state",
    "未対応のエージェントです": "Unsupported agent", "エージェントのセッションIDが不正です": "Invalid agent session ID",
    "Codexのスキル・コネクタ設定の形式が不正です": "Invalid Codex skill or connector settings",
    "スキル・コネクタ設定の形式が不正です": "Invalid skill or connector settings",
    "セッション継続位置が不正です": "Invalid session resume position",
    "保存メッセージの形式が不正です": "Invalid saved message format",
    "保存履歴の形式が不正です": "Invalid saved history format",
    " には Claude Code ": " requires Claude Code ", " 以上が必要です（現在 ": " or later (current version: ",
    "既に応答待ちです": "Already waiting for a response", "の応答が5分以内に完了しませんでした": " response did not finish within 5 minutes",
    "の応答サイズが上限を超えました": " response exceeded the size limit",
    "ストリーム応答を解釈できません: ": "Could not parse streamed response: ",
    "が異なるセッションIDを返しました": " returned a different session ID",
    "を起動できません。実行パスとログインを確認してください: ": " could not start. Check its executable path and sign-in: ",
    "が異常終了しました": " exited unexpectedly", "の応答が完了前に終了しました": " response ended before completion",
    "CodexのセッションIDを取得できませんでした": "Could not obtain the Codex session ID", "停止しました": "Stopped",
    "CLI応答がオブジェクトではありません": "CLI response is not an object",
    "応答にはmessageとcodeが必要です": "Response requires message and code",
    "応答に未知のフィールドがあります": "Response contains unknown fields",
    "message、code、title、approval_reason、questionは文字列である必要があります": "message, code, title, approval_reason, and question must be strings",
    "choicesは空でない文字列の配列である必要があります": "choices must be an array of nonempty strings",
    "choicesは5件までです": "choices is limited to five items",
    "質問する場合はcodeを空にする必要があります": "code must be empty when asking a question",
    "choicesにはquestionが必要です": "choices requires question",
    "承認判断にはbooleanのrequires_approvalとapproval_reasonが必要です": "Approval decisions require boolean requires_approval and approval_reason",
    "確認が必要な場合は承認理由が必要です": "An approval reason is required when confirmation is needed",
    "エージェントのJSON応答を解釈できません: ": "Could not parse the agent's JSON response: ",
    "Codexの推論要約が不正です": "Invalid Codex reasoning summary",
    "Codexの応答テキストが不正です": "Invalid Codex response text",
    "Codexの処理に失敗しました": "Codex operation failed",
    "Processingツールを追加・更新": "Add or update Processing tool", "ツール管理": "Tool management",
    "ツールID（例: buffer_and_clip）": "Tool ID (e.g. buffer_and_clip)",
    "ツールの定義（Python）": "Tool definition (Python)",
    "登録されたツールID": "Registered tool ID", "定義の保存先": "Definition file",
    "NAMEには英小文字で始まる英小文字・数字・アンダースコアを指定してください": "NAME must start with a lowercase letter and contain only lowercase letters, digits, or underscores",
    "Processingのスクリプトプロバイダーを有効にしてください": "Enable the Processing script provider",
    "既存ツールの保存先を特定できません: ": "Could not locate the existing tool: ",
    "QgsProcessingAlgorithmのサブクラスをちょうど1つ定義してください": "Define exactly one QgsProcessingAlgorithm subclass",
    "createInstance()は同じアルゴリズムクラスの新しいインスタンスを返す必要があります": "createInstance() must return a new instance of the same algorithm class",
    "createInstance()で新しいインスタンスを作成してください": "createInstance() must create a new instance",
    "processAlgorithm()を実装してください": "Implement processAlgorithm()",
    "name()とNAMEが一致していません": "name() does not match NAME",
    "表示名と用途・入出力を説明するshortHelpString()が必要です": "Provide a display name and a shortHelpString() describing purpose, inputs, and outputs",
    "ツール定義を読み込めません: ": "Could not load tool definition: ",
    "登録を中止しました": "Registration canceled",
    "Processingへの登録に失敗しました": "Could not register with Processing",
    "ツールを保存・登録できません: ": "Could not save or register tool: ",
    "登録しました: ": "Registered: ", "（処理結果は未検証）": " (processing result not verified)",
}

# The Processing help is one Qt-facing message, assembled from adjacent literals.
EN["".join((
    "QgsProcessingAlgorithmのサブクラスを1つ定義したPythonを登録します。",
    "NAMEは英小文字で始まる英小文字・数字・アンダースコアで、name()と一致させます。",
    "createInstance()、displayName()、initAlgorithm()、processAlgorithm()と",
    "shortHelpString()を実装してください。入力・出力はProcessingパラメータで定義します。",
    "再利用に必要な定義は原則この1ファイルにまとめ、QPT・QMLはXML文字列、",
    "小さな設定は定数や辞書として内蔵します。使い方はshortHelpString()に記述してください。",
    "ファイルパスが必要なAPIには実行時に一時ファイルを作り、利用完了後に削除します。",
    "観測データ・日時・出力先は実行時のパラメータとし、付属ファイルや",
    "生成した別モジュールのimport、sys.pathの変更に依存させないでください。",
    "プロファイルに保存され、script:NAMEですぐ実行でき、再起動後も利用できます。",
    "同じNAMEのツールは元の保存先で更新します。デコレーター形式は対象外です。",
    "登録時にPythonのトップレベルと初期化処理を実行します。そこでデータ操作をせず、",
    "処理本体はprocessAlgorithm()に置いてください。登録成功は処理結果の検証ではありません。",
    "作成・更新後は返されたALGORITHM_IDを実際に実行し、出力を確認してから完了としてください。",
    "一時出力と代表的な入力を使い、失敗したら同じNAMEで修正・更新して再テストします。",
    "取得ツールは実通信も確認し、模擬応答だけで動作確認済みとしないでください。",
))] = (
    "Register Python defining exactly one QgsProcessingAlgorithm subclass. "
    "NAME must start with a lowercase letter, contain lowercase letters, digits or underscores, and match name(). "
    "Implement createInstance(), displayName(), initAlgorithm(), processAlgorithm(), and shortHelpString(). "
    "Define inputs and outputs with Processing parameters. Keep reusable definitions in this single file where possible; "
    "embed QPT and QML as XML strings and small settings as constants or dictionaries. Describe usage in shortHelpString(). "
    "For APIs requiring file paths, create temporary files at runtime and remove them afterward. "
    "Make observations, dates, and outputs runtime parameters; do not depend on bundled files, generated modules, or sys.path changes. "
    "The tool is saved in the QGIS profile as script:NAME and remains available after restart. An existing NAME is updated "
    "at its original location. Decorator-style scripts are unsupported. Registration executes top-level and initialization code, "
    "so keep data operations in processAlgorithm(). Registration alone does not verify the result. After creating or updating, "
    "run the returned ALGORITHM_ID and inspect its output. Use representative inputs and temporary output; fix and retest with "
    "the same NAME if needed. Test real connections for retrieval tools; a mock response alone is insufficient."
)


def is_japanese():
    try:
        from qgis.PyQt.QtCore import QLocale, QSettings
    except ImportError:
        return (locale.getlocale()[0] or "").lower().startswith("ja")
    settings = QSettings()
    if settings.value("locale/overrideFlag", False, type=bool):
        selected = settings.value("locale/userLocale", "")
        if selected:
            return selected.lower().startswith("ja")
    try:
        from qgis.core import QgsApplication
        application = QgsApplication.instance()
        if application:
            return application.locale().lower().startswith("ja")
    except (ImportError, AttributeError):
        pass
    return QLocale.system().name().lower().startswith("ja")


def tr(source):
    return source if is_japanese() else EN.get(source, source)


def tr_inventory(source):
    """Translate fixed inventory labels while leaving names and paths intact."""
    if is_japanese():
        return source
    for suffix in (
        ": 読み取れませんでした", ": プラグイン登録形式が未対応です",
        ": インストール先が見つかりません",
    ):
        if source.endswith(suffix):
            return source[:-len(suffix)] + EN[suffix]
    return " · ".join(EN.get(part, part) for part in source.split(" · "))
