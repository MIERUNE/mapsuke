"""UI translations selected from QGIS's interface locale.

English strings are the source text and the fallback. Japanese is provided by JA.
Sessions saved by earlier versions may persist Japanese role labels and notices;
from_legacy() maps them back to the English source text.
"""
import locale


JA = {
    "Default (Claude Code settings)": "デフォルト（Claude Codeの設定）",
    "Default (Codex settings)": "デフォルト（Codexの設定）",
    "New session": "新しいセッション",
    "Started a new session.": "新しいセッションを開始しました。",
    "Session restored. Work continues on the current QGIS project.": "セッションを復元しました。現在のQGISプロジェクトで作業を続けます。",
    "Switch sessions (autosaved)": "セッションを切り替え（自動保存）",
    "All…": "一覧…",
    "Settings": "設定",
    "Ready": "準備完了",
    "Waiting for response": "応答待ち",
    "Describe what you want to do in QGIS…\nEnter to send · Shift+Enter for a new line": "QGISでやりたいことを入力…\nEnterで送信 · Shift+Enterで改行",
    "Approval mode": "承認モード",
    "Model": "モデル",
    "Model for this session": "このセッションのモデル",
    "Ask: confirm each run / Auto: AI assesses risk / Full auto: run without confirmation": "Ask: 毎回確認 / Auto: AIがリスクを判断 / Full auto: 確認なしで実行",
    "Reasoning effort for the next response. Levels and availability vary by model and CLI.": "次の応答で使う推論の強さ。段階の意味と対応範囲はモデル・CLIごとに異なります。",
    "Use fast mode for the next response. Requires a supported model and account.": "次の応答から高速モードを使います。利用可能なモデルとアカウントが必要です。",
    "Use fast mode for the next response. Additional charges or credits may apply.": "次の応答から高速モードを使います。追加の利用料金やクレジットが必要です。",
    "Fast mode is unavailable for the selected model.": "選択中のモデルでは Fast mode を指定できません。",
    "Approve and run": "承認して実行",
    "Always approve": "今後は自動承認",
    "Send ↑": "送信 ↑",
    "Stop": "停止",
    "Approve and run, then switch to Full auto without further confirmation": "承認して実行し、以降はFull auto（確認なしで実行）に切り替えます",
    "Context usage": "コンテキスト使用率",
    "Python code": "Pythonコード",
    "You": "あなた",
    "Reasoning summary\n": "思考の要約\n",
    " is responding…": "が応答しています…",
    " is waiting for your answer": "が回答を待っています",
    "Running Python…": "Pythonを実行中…",
    " is receiving execution results…": "に実行結果を返します…",
    " sign-in required": "へのログインが必要です",
    "Sign in in your browser…": "ブラウザでログインしてください…",
    "Sign-in failed": "ログインに失敗しました",
    "Signed in": "ログインしました",
    "Sign-in failed: ": "ログインできませんでした: ",
    " signed in. Resending your message.": "にログインしました。メッセージを再送信します。",
    " executable path is required": "の実行パスを入力してください",
    ". Choose another model or update the CLI.": "。モデルを変更するか、CLIを更新してください。",
    "Error": "エラー",
    "Save error": "保存エラー",
    "Load error": "読込エラー",
    "Error / stopped": "エラー / 停止",
    "Conversation limit reached. Start a new session.": "会話が上限に達しました。新しいセッションを開始してください",
    "Could not save the session state": "セッション状態を保存できませんでした",
    "Code was not run because the session could not be saved": "保存に失敗したためコードを実行しませんでした",
    "Confirm execution": "実行の確認",
    "Waiting for execution approval": "実行の承認待ち",
    "Ask mode requires confirmation before running.": "Askモードのため実行前に確認します。",
    "No AI risk assessment was provided, so confirmation is required.": "AIのリスク評価がないため、実行前に確認します。",
    "\nChoose Approve and run, Always approve, or Stop.": "\n承認して実行・今後は自動承認・停止のいずれかを選んでください。",
    "Switched to Full auto. Future Python code will run without confirmation.": "承認モードをFull autoに切り替えました。以降のPythonは確認なしで実行します。",
    "Run succeeded": "実行成功",
    "Run error": "実行エラー",
    "Background run succeeded": "バックグラウンド処理成功",
    "Background run canceled": "バックグラウンド処理中止",
    "Background run error": "バックグラウンド処理エラー",
    "Running Processing in the background… ": "Processingをバックグラウンドで実行中… ",
    "Stopped. The background Processing run was canceled.": "停止しました。バックグラウンドのProcessingを中止しました。",
    "(No output)": "（出力なし）",
    "Stopped because execution results could not be saved": "実行結果を保存できなかったため停止しました",
    "Stopped. Pending code was not run.": "停止しました。未実行のコードは実行していません。",
    "Unavailable: ": "利用不可: ",
    "Previous setting: ": "以前の設定: ",
    " The previous operation ended early; some changes may have been applied.": " 前回の処理は途中で終了しています。変更が部分的に適用されている可能性があります。",
    "Could not save the session": "セッションを保存できませんでした",
    "In Auto mode, the AI runs Python code it considers safe without asking. Its assessment may be wrong.": "Autoでは、AIがリスクを評価し、確認不要と判断したPythonコードを自動実行します。AIの判断は誤ることがあります。",
    "In Full auto mode, generated Python code runs without prior confirmation.": "Full autoでは、生成したPythonコードを実行前の確認なしで実行します。",
    "Consent to automatic execution": "自動実行のリスクへの同意",
    "\n\nCode runs with QGIS's permissions and can change or delete files or send data externally. Changes cannot be automatically undone.\n\nDo you understand these risks and agree to enable this mode?": "\n\nコードはQGISと同じ権限で動作し、ファイルの変更・削除や外部へのデータ送信が可能です。変更を自動で元に戻すことはできません。\n\nリスクを理解し、このモードを有効にすることに同意しますか？",
    "Sessions": "セッション一覧",
    "Search by title": "タイトルで検索",
    "Show more": "さらに表示",
    "Open": "開く",
    "Delete": "削除",
    "Delete session": "セッションを削除",
    "Delete error": "削除エラー",
    "Delete this session from the list? QGIS layers and the agent's history will remain.": "このセッションを一覧から削除しますか？QGISのレイヤーとエージェント側の履歴は残ります。",
    "Paste the code shown in your browser": "ブラウザに表示されたコードを貼り付け",
    "Submit code": "コードを送信",
    "Cancel": "キャンセル",
    " · Sign-in required": " · ログインが必要です",
    " sign in": "にログイン",
    " account. When sign-in is complete, the interrupted message will be resent automatically.": "のアカウントでログインしてください。ログインが完了すると、止まったメッセージを自動で再送信します。",
    "Sign in on the opened page and paste the displayed code.": "開いたページでログインし、表示されたコードを貼り付けてください。",
    "Checking code…": "コードを確認しています…",
    "Sign in in your browser. Return here when finished.": "ブラウザでログインしてください。完了するとこの画面に戻ります。",
    "If the browser does not open, <a href=\"{0}\">open this link</a>": "ブラウザが開かない場合は <a href=\"{0}\">こちらを開いてください</a>",
    "You can also answer freely in the input field.": "入力欄から自由に回答することもできます。",
    "Answer in the input field.": "入力欄から回答してください。",
    "Choose location…": "保存先を選択…",
    "Choose folder…": "フォルダを選択…",
    "All files (*)": "すべてのファイル (*)",
    "QGIS Agent settings": "QGIS Agent の設定",
    "General": "一般",
    "Browse…": "参照…",
    "Executable": "実行ファイル",
    "Claude Code executable": "Claude Code実行ファイル",
    "Codex executable": "Codex実行ファイル",
    " credentials are used.\n": "のログイン情報を使用します。\n",
    "Run codex login in a terminal.": "ターミナルで codex login を実行してください。",
    "Run claude in a terminal.": "ターミナルで claude を実行してください。",
    " tokens · limit unknown": " token · 上限不明",
    " tokens · percentage unknown": " token · 割合不明",
    "Skills": "スキル",
    "Connectors": "コネクタ",
    "Check connections": "接続確認",
    "Refresh": "再読み込み",
    "Name": "名前",
    "Description": "説明",
    "Source": "読み込み元",
    "This chat": "このチャット",
    "Connection status": "接続状態",
    "Type": "種類",
    "Registered by": "登録元",
    "This session": "このセッション",
    "Use ": "このセッションで",
    " in this session": "を使用する",
    "Click OK to apply from the next message. Items loaded follow Claude Code settings.\nOnly tools already permitted by Claude may run. Set additional permissions with /permissions in a terminal.": "OKで適用し、次の送信から反映します。読み込み対象はClaude Code側の設定に従います。\nツール実行はClaude側で許可済みの操作に限ります。追加の許可はターミナルの /permissions で設定できます。",
    "Includes personal skills and registered plugins. Built-in, cloud-synced, and project skills are excluded.": "対象：個人スキル・登録済みプラグイン。組み込み・クラウド同期・プロジェクト直下のスキルは対象外。",
    "Includes personal and plugin MCP servers. Connection checks use the configured Claude executable.\nProvided tools: unavailable from the CLI listing.": "対象：個人・プラグインのMCP。接続確認には現在のClaude実行パスを使います。\n提供ツール：未取得（CLIの一覧機能では取得できません）。",
    " skills": " スキル",
    " connectors · not checked": " コネクタ · 接続未確認",
    " · some items could not be loaded (hover for details)": " · 一部読込失敗（詳細はホバー）",
    "Disable": "使用しない",
    "Enable": "使用する",
    "Allowed to load": "読み込み許可",
    "Disabled in Claude": "Claude側で無効",
    "Outside this scope": "対象外（別スコープ）",
    "Set the Claude executable in the General tab": "一般タブでClaudeの実行パスを指定してください",
    "Checking connections…": "接続を確認しています…",
    "Connection check complete": "接続確認完了",
    "Connection check failed": "接続確認に失敗しました",
    "Connection check timed out": "接続確認がタイムアウトしました",
    " · no connectors or unsupported CLI output": " · コネクタなし、またはCLI出力形式が未対応",
    "Connection check output exceeded the limit": "接続確認の出力が上限を超えました",
    "Could not start Claude. Check its executable path": "Claudeを起動できません。実行パスを確認してください",
    "Not checked": "未確認",
    "These settings apply to this session. Click OK to save; changes take effect with the next message.\nFollow CLI settings uses Codex's configuration.": "このセッションでの使用設定です。OKで保存し、次の送信から反映します。\n「CLIの設定に従う」はCodex側の設定を使用します。",
    "Follow CLI settings": "CLIの設定に従う",
    "Saved setting (not in the current list)": "保存済みの設定（現在の一覧にはありません）",
    "Configure this MCP name in Codex CLI": "この名前のMCPはCodex CLI側で設定してください",
    "Includes local personal skills and MCP servers in config.toml. Manage plugin and cloud items in the CLI.\n": "対象：個人のローカルスキルとconfig.tomlのMCP。プラグイン・クラウドの項目はCLI側で管理します。\n",
    " · disabled": " · 無効設定",
    "Enabled in settings": "有効設定",
    "Enabled; not checked": "有効設定未確認",
    "Disabled in settings": "無効設定",
    "Personal": "個人",
    "Unknown": "不明",
    "No description": "説明なし",
    "Authentication required": "認証が必要",
    "Connection failed": "接続失敗",
    "Awaiting approval": "承認待ち",
    "Connected": "接続済み",
    "Disabled": "無効",
    "Unsupported plugin registry format": "プラグイン登録情報の形式が未対応です",
    "Could not parse metadata": "メタデータを解析できませんでした",
    "Could not read Codex settings (tomli is required before Python 3.11)": "Codex設定を読み取れませんでした（Python 3.11未満ではtomliが必要です）",
    "Cannot apply settings because Codex skill settings could not be read safely": "Codexのスキル設定を安全に読み込めないため、設定を適用できません",
    "This MCP name does not support a CLI override: ": "このMCP名はCLIの個別上書きに対応していません: ",
    "Some skills could not be read": "読み取れないスキルがあります",
    ": could not be read": ": 読み取れませんでした",
    ": install location not found": ": インストール先が見つかりません",
    ": unsupported plugin registry format": ": プラグイン登録形式が未対応です",
    "Sign-in canceled": "ログインを中止しました",
    "Sign-in did not finish within 10 minutes": "ログインが10分以内に完了しませんでした",
    "Could not start sign-in. Check the executable path: ": "ログインを開始できません。実行パスを確認してください: ",
    "Session not found": "セッションが見つかりません",
    "Unsupported session format": "未対応のセッション形式です",
    "Could not read session history": "セッションの履歴を読み取れません",
    "Invalid session settings format": "セッション設定の形式が不正です",
    "Invalid session resume state": "セッション継続状態が不正です",
    "Unsupported agent": "未対応のエージェントです",
    "Invalid agent session ID": "エージェントのセッションIDが不正です",
    "Invalid Codex skill or connector settings": "Codexのスキル・コネクタ設定の形式が不正です",
    "Invalid skill or connector settings": "スキル・コネクタ設定の形式が不正です",
    "Invalid session resume position": "セッション継続位置が不正です",
    "Invalid saved message format": "保存メッセージの形式が不正です",
    "Invalid saved history format": "保存履歴の形式が不正です",
    " requires Claude Code ": " には Claude Code ",
    " or later (current version: ": " 以上が必要です（現在 ",
    "Already waiting for a response": "既に応答待ちです",
    " response did not finish within 5 minutes": "の応答が5分以内に完了しませんでした",
    " response exceeded the size limit": "の応答サイズが上限を超えました",
    "Could not parse streamed response: ": "ストリーム応答を解釈できません: ",
    " returned a different session ID": "が異なるセッションIDを返しました",
    " could not start. Check its executable path and sign-in: ": "を起動できません。実行パスとログインを確認してください: ",
    " exited unexpectedly": "が異常終了しました",
    " response ended before completion": "の応答が完了前に終了しました",
    "Could not obtain the Codex session ID": "CodexのセッションIDを取得できませんでした",
    "Stopped": "停止しました",
    "CLI response is not an object": "CLI応答がオブジェクトではありません",
    "Response requires message and code": "応答にはmessageとcodeが必要です",
    "Response contains unknown fields": "応答に未知のフィールドがあります",
    "message, code, title, approval_reason, question, path_request, path_suggestion, and suggestion must be strings": "message、code、title、approval_reason、question、path_request、path_suggestion、suggestionは文字列である必要があります",
    "suggestion requires empty code and question": "suggestionはcodeとquestionが空の場合のみ指定できます",
    "path_request must be empty, file, or directory": "path_requestは空文字、file、directoryのいずれかである必要があります",
    "path_request requires question": "path_requestにはquestionが必要です",
    "choices must be an array of nonempty strings": "choicesは空でない文字列の配列である必要があります",
    "choices is limited to five items": "choicesは5件までです",
    "code must be empty when asking a question": "質問する場合はcodeを空にする必要があります",
    "choices requires question": "choicesにはquestionが必要です",
    "Approval decisions require boolean requires_approval and approval_reason": "承認判断にはbooleanのrequires_approvalとapproval_reasonが必要です",
    "An approval reason is required when confirmation is needed": "確認が必要な場合は承認理由が必要です",
    "Could not parse the agent's JSON response: ": "エージェントのJSON応答を解釈できません: ",
    "Invalid Codex reasoning summary": "Codexの推論要約が不正です",
    "Invalid Codex response text": "Codexの応答テキストが不正です",
    "Codex operation failed": "Codexの処理に失敗しました",
    "Add or update Processing tool": "Processingツールを追加・更新",
    "Tool management": "ツール管理",
    "Tool ID (e.g. buffer_and_clip)": "ツールID（例: buffer_and_clip）",
    "Tool definition (Python)": "ツールの定義（Python）",
    "Registered tool ID": "登録されたツールID",
    "Definition file": "定義の保存先",
    "Get project state": "プロジェクトの状態を取得",
    "Project": "プロジェクト",
    "Project state (JSON)": "プロジェクトの状態（JSON）",
    "Return the current project state as JSON in STATE: project path and CRS, active layer, map canvas extent and scale, and up to 100 layers in Layers panel order with ID, name, type, provider, source, CRS, validity and visibility. Vector layers also include geometry type, feature and selection counts, and up to 100 fields.": "現在のプロジェクトの状態をSTATEにJSONで返します。プロジェクトのパスとCRS、アクティブレイヤ、マップキャンバスの範囲と縮尺、レイヤパネル順で最大100件のレイヤ（ID、名前、種類、プロバイダ、ソース、CRS、有効性、表示状態）を含みます。ベクタレイヤにはジオメトリタイプ、地物数と選択数、最大100件のフィールドも含みます。",
    "NAME must start with a lowercase letter and contain only lowercase letters, digits, or underscores": "NAMEには英小文字で始まる英小文字・数字・アンダースコアを指定してください",
    "Enable the Processing script provider": "Processingのスクリプトプロバイダーを有効にしてください",
    "Could not locate the existing tool: ": "既存ツールの保存先を特定できません: ",
    "Define exactly one QgsProcessingAlgorithm subclass": "QgsProcessingAlgorithmのサブクラスをちょうど1つ定義してください",
    "createInstance() must return a new instance of the same algorithm class": "createInstance()は同じアルゴリズムクラスの新しいインスタンスを返す必要があります",
    "createInstance() must create a new instance": "createInstance()で新しいインスタンスを作成してください",
    "Implement processAlgorithm()": "processAlgorithm()を実装してください",
    "name() does not match NAME": "name()とNAMEが一致していません",
    "Provide a display name and a shortHelpString() describing purpose, inputs, and outputs": "表示名と用途・入出力を説明するshortHelpString()が必要です",
    "Could not load tool definition: ": "ツール定義を読み込めません: ",
    "Registration canceled": "登録を中止しました",
    "Could not register with Processing": "Processingへの登録に失敗しました",
    "Could not save or register tool: ": "ツールを保存・登録できません: ",
    "Registered: ": "登録しました: ",
    " (processing result not verified)": "（処理結果は未検証）",
    " is working…": "の応答を待っています…",
    "Response interrupted (not run)": "応答中断（未実行）",
}

# The Processing help is one Qt-facing message, assembled from adjacent literals.
JA[(
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
)] = "".join((
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
))


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
    return JA.get(source, source) if is_japanese() else source


def tr_label(label):
    """Translate each " · "-separated part, leaving names such as Claude or QGIS intact."""
    return " · ".join(tr(part) for part in label.split(" · "))


def tr_inventory(source):
    """Translate fixed inventory labels while leaving names and paths intact."""
    if not is_japanese():
        return source
    for suffix in (
        ": could not be read", ": unsupported plugin registry format",
        ": install location not found",
    ):
        if source.endswith(suffix):
            return source[:-len(suffix)] + JA[suffix]
    return tr_label(source)


LEGACY = {japanese: english for english, japanese in JA.items()}


def from_legacy(label):
    """Map a label persisted in Japanese by earlier versions to its English source."""
    return " · ".join(LEGACY.get(part, part) for part in label.split(" · "))
