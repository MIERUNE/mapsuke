---
name: qgis-python-scripting
description: QGIS内で実行するPythonコードやプラグイン・Processingスクリプトを実装、修正するときに使う。特にQGIS 3/4とQt 5/6のAPI差分を扱う。一般的なPythonだけの作業には使わない。
---

# QGIS向けPythonを実装する

対象のQGIS・Qt・PyQtのバージョンを、実行環境の `Qgis.QGIS_VERSION` と `qgis.PyQt.QtCore.QT_VERSION_STR` などから確認する。コードがQGIS 3/4の両方を対象とするなら、両方で使えるAPIを優先する。実際の環境で確かめていない互換性は推測で断定しない。

- Qtクラスは、QGISが公開するモジュールなら `qgis.PyQt` からimportする。`PyQt5` / `PyQt6` の直接importや、別バインディングの混在を避ける。Qt 6でモジュールが移ったクラスもある。たとえば `QAction` はQt 5では `QtWidgets`、Qt 6では `QtGui` に属するため、両対応コードでは実際の環境でimport先を確認し、必要な場合だけ差分を吸収する。`qgis.PyQt` にないモジュールまで存在すると仮定しない。
- 列挙値はQt 5/6で共通のスコープ付き表記を使う。例: `Qt.ItemDataRole.UserRole`、`Qt.CursorShape.WaitCursor`、`QDialog.DialogCode.Accepted`。PyQGISでも `Qgis.MessageLevel.Critical`、`QgsMapLayer.LayerType.VectorLayer` のように明示する。列挙値を整数と決めつけず、数値が必要なAPIでのみ `.value` 等を対象環境で確認する。
- `QDialog` や `QEventLoop` の実行メソッドは `exec()` を使う。PyQt 6では `exec_()` が削除されている。ただし、このプラグインのPythonブリッジはGUIスレッドで動くため、そこで実行する短いコードからダイアログや独自のイベントループを起動しない。
- QtとPyQGISのバージョン依存APIに当たったら、まず対象環境のAPI・ヘルプと例外を確認する。共通APIがない場合だけ、判定と差分を一か所に閉じ込める。QGISのAPI差分はQtのバージョンだけで判定しない。
- QGISオブジェクトの操作はGUIスレッドで行う。Processing処理は適切な `context` と `feedback` を渡し、入出力・CRS・単位を確認する。保存して再利用する依頼では `qgis-save-processing-script` の指針も適用する。

変更後は対象QGISのPython環境でimportと代表的な処理を実行し、返り値や生成物を確認する。両バージョン対応をうたう場合はQGIS 3/Qt 5とQGIS 4/Qt 6の双方で確かめ、片方しか試せなければその範囲を伝える。

未知の差分は [QGISのQt5/Qt6移行ガイド](https://github.com/qgis/QGIS/wiki/Plugin-migration-to-be-compatible-with-Qt5-and-Qt6) と [PyQt 6の差分](https://www.riverbankcomputing.com/static/Docs/PyQt6/pyqt5_differences.html) で確認する。
