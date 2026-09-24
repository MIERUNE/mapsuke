"""Publish reusable algorithms through QGIS's existing script provider."""
import inspect
import importlib.util
import os
from pathlib import Path
import re
import tempfile

from qgis.core import (QgsApplication, QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingFeatureBasedAlgorithm,
                       QgsProcessingOutputString, QgsProcessingParameterString,
                       QgsProcessingProvider)


class AddTool(QgsProcessingAlgorithm):
    def name(self):
        return "add_tool"

    def displayName(self):
        return "Processingツールを追加・更新"

    def group(self):
        return "ツール管理"

    def groupId(self):
        return "tools"

    def createInstance(self):
        return AddTool()

    def flags(self):
        # The registry and toolbox belong to the GUI thread.
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        return ("QgsProcessingAlgorithmのサブクラスを1つ定義したPythonを登録します。"
                "NAMEは英小文字で始まる英小文字・数字・アンダースコアで、name()と一致させます。"
                "createInstance()、displayName()、initAlgorithm()、processAlgorithm()と"
                "shortHelpString()を実装してください。入力・出力はProcessingパラメータで定義します。"
                "再利用に必要な定義は原則この1ファイルにまとめ、QPT・QMLはXML文字列、"
                "小さな設定は定数や辞書として内蔵します。使い方はshortHelpString()に記述してください。"
                "ファイルパスが必要なAPIには実行時に一時ファイルを作り、利用完了後に削除します。"
                "観測データ・日時・出力先は実行時のパラメータとし、付属ファイルや"
                "生成した別モジュールのimport、sys.pathの変更に依存させないでください。"
                "プロファイルに保存され、script:NAMEですぐ実行でき、再起動後も利用できます。"
                "同じNAMEのツールは元の保存先で更新します。デコレーター形式は対象外です。"
                "登録時にPythonのトップレベルと初期化処理を実行します。そこでデータ操作をせず、"
                "処理本体はprocessAlgorithm()に置いてください。登録成功は処理結果の検証ではありません。"
                "作成・更新後は返されたALGORITHM_IDを実際に実行し、出力を確認してから完了としてください。"
                "一時出力と代表的な入力を使い、失敗したら同じNAMEで修正・更新して再テストします。"
                "取得ツールは実通信も確認し、模擬応答だけで動作確認済みとしないでください。")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString("NAME", "ツールID（例: buffer_and_clip）"))
        self.addParameter(QgsProcessingParameterString("SOURCE", "ツールの定義（Python）", multiLine=True))
        self.addOutput(QgsProcessingOutputString("ALGORITHM_ID", "登録されたツールID"))
        self.addOutput(QgsProcessingOutputString("FILE", "定義の保存先"))

    def processAlgorithm(self, parameters, context, feedback):
        from processing.script import ScriptUtils

        name = self.parameterAsString(parameters, "NAME", context)
        source = self.parameterAsString(parameters, "SOURCE", context)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise QgsProcessingException("NAMEには英小文字で始まる英小文字・数字・アンダースコアを指定してください")
        registry = QgsApplication.processingRegistry()
        provider = registry.providerById("script")
        if provider is None or not provider.isActive():
            raise QgsProcessingException("Processingのスクリプトプロバイダーを有効にしてください")
        algorithm_id = "script:" + name
        existing = registry.algorithmById(algorithm_id)
        existing_source = ScriptUtils.findAlgorithmSource(name) if existing else None
        if existing and not existing_source:
            raise QgsProcessingException("既存ツールの保存先を特定できません: " + algorithm_id)
        path = (Path(existing_source) if existing_source else
                Path(ScriptUtils.defaultScriptsFolder()) / (name + ".py")).resolve()

        try:
            # Match the native script loader's class discovery, so restart loads
            # the same algorithm. A fresh namespace prevents chat-state capture.
            namespace = {"__name__": name, "__file__": str(path)}
            exec(compile(source, str(path), "exec"), namespace, namespace)
            classes = [obj for obj in namespace.values() if inspect.isclass(obj)
                       and issubclass(obj, QgsProcessingAlgorithm)
                       and obj not in (QgsProcessingAlgorithm, QgsProcessingFeatureBasedAlgorithm)]
            if len(classes) != 1:
                raise ValueError("QgsProcessingAlgorithmのサブクラスをちょうど1つ定義してください")
            algorithm = classes[0]()
            # Call Python overrides directly: exceptions crossing Qt/SIP's C++
            # virtual initAlgorithm callback can abort the QGIS process.
            instance = algorithm.createInstance()
            if type(instance) is not type(algorithm):
                raise ValueError("createInstance()は同じアルゴリズムクラスの新しいインスタンスを返す必要があります")
            if instance is algorithm:
                raise ValueError("createInstance()で新しいインスタンスを作成してください")
            if type(algorithm).processAlgorithm is QgsProcessingAlgorithm.processAlgorithm:
                raise ValueError("processAlgorithm()を実装してください")
            instance.initAlgorithm()
            if algorithm.name() != name or instance.name() != name:
                raise ValueError("name()とNAMEが一致していません")
            if not instance.displayName().strip() or not instance.shortHelpString().strip():
                raise ValueError("表示名と用途・入出力を説明するshortHelpString()が必要です")
        except BaseException as exc:
            raise QgsProcessingException("ツール定義を読み込めません: " + str(exc)) from exc

        if feedback.isCanceled():
            raise QgsProcessingException("登録を中止しました")
        # Keep the previous bytes until registration succeeds. Updating in place
        # preserves the algorithm ID and avoids duplicate files in other folders.
        temporary = None
        backup = None
        published = False
        try:
            if path.exists():
                with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".bak", delete=False) as stream:
                    backup = Path(stream.name)
                    stream.write(path.read_bytes())
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(source)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            published = True
            if existing:
                # Same-length edits within one second can otherwise reuse stale
                # Python bytecode when the native provider reloads the file.
                Path(importlib.util.cache_from_source(str(path))).unlink(missing_ok=True)
                provider.refreshAlgorithms()
                if registry.algorithmById(algorithm_id) is None:
                    raise ValueError("Processingへの登録に失敗しました")
            elif not provider.addAlgorithm(algorithm):
                raise ValueError("Processingへの登録に失敗しました")
        except BaseException as exc:
            if published:
                if backup is not None:
                    os.replace(backup, path)
                else:
                    path.unlink()
                Path(importlib.util.cache_from_source(str(path))).unlink(missing_ok=True)
                if existing:
                    provider.refreshAlgorithms()
            raise QgsProcessingException("ツールを保存・登録できません: " + str(exc)) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if backup is not None:
                backup.unlink(missing_ok=True)
        ScriptUtils.scriptsRegistry[name] = str(path)
        provider.algorithmsLoaded.emit()
        feedback.pushInfo("登録しました: " + algorithm_id + "（処理結果は未検証）")
        return {"ALGORITHM_ID": algorithm_id, "FILE": str(path)}


class AgentProcessingProvider(QgsProcessingProvider):
    def id(self):
        return "qgis_agent"

    def name(self):
        return "QGIS Agent"

    def loadAlgorithms(self):
        self.addAlgorithm(AddTool())
