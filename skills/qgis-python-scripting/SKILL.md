---
name: qgis-python-scripting
description: Use when implementing or fixing Python code, plugins, or Processing scripts that run inside QGIS, especially when handling API differences between QGIS 3/4 and Qt 5/6. Do not use for plain Python work unrelated to QGIS.
---

# Implementing Python for QGIS

Check the target QGIS, Qt, and PyQt versions from the runtime, e.g. `Qgis.QGIS_VERSION` and `qgis.PyQt.QtCore.QT_VERSION_STR`. If the code targets both QGIS 3 and 4, prefer APIs available in both. Do not assert compatibility you have not verified in an actual environment.

- Import Qt classes from `qgis.PyQt` for modules QGIS exposes. Avoid importing `PyQt5` / `PyQt6` directly or mixing bindings. Some classes moved modules in Qt 6; for example, `QAction` is in `QtWidgets` in Qt 5 but in `QtGui` in Qt 6. In code targeting both, check the import location in the actual environment and bridge the difference only where necessary. Do not assume modules exist that `qgis.PyQt` does not provide.
- Use scoped enum names that work in both Qt 5 and 6, e.g. `Qt.ItemDataRole.UserRole`, `Qt.CursorShape.WaitCursor`, `QDialog.DialogCode.Accepted`. Be explicit in PyQGIS too, e.g. `Qgis.MessageLevel.Critical`, `QgsMapLayer.LayerType.VectorLayer`. Do not assume enum values are integers; check `.value` and similar in the target environment only for APIs that require a number.
- Use `exec()` to run `QDialog` and `QEventLoop`; `exec_()` was removed in PyQt 6. However, this plugin's Python bridge runs on the GUI thread, so do not launch dialogs or custom event loops from short snippets executed there.
- When you hit version-dependent Qt or PyQGIS APIs, first check the target environment's API, help, and exceptions. Only when no common API exists, confine the detection and differences to one place. Do not decide QGIS API differences based on the Qt version alone.
- Manipulate QGIS objects on the GUI thread. Pass appropriate `context` and `feedback` to Processing calls, and check inputs, outputs, CRS, and units. For requests to save work for reuse, also apply the `qgis-save-processing-script` guidelines.

After making changes, run imports and representative operations in the target QGIS Python environment and check the return values and outputs. If you claim support for both versions, verify on both QGIS 3/Qt 5 and QGIS 4/Qt 6; if you can test only one, state that scope.

Check unknown differences in the [QGIS Qt5/Qt6 migration guide](https://github.com/qgis/QGIS/wiki/Plugin-migration-to-be-compatible-with-Qt5-and-Qt6) and [Differences between PyQt 5 and PyQt 6](https://www.riverbankcomputing.com/static/Docs/PyQt6/pyqt5_differences.html).
