---
name: mapsuke-python-scripting
description: Implement or fix Python for Mapsuke operations and reusable Processing tools, using the QGIS and Qt APIs available in the live session. Use only in a Mapsuke session when writing or debugging code for its Python bridge or tools, including QGIS 3/4 and Qt 5/6 API differences. The user need not mention Python, Mapsuke, or QGIS. Do not use for general Python or standalone plugin development outside Mapsuke.
---

# Implementing Python for Mapsuke

For tools intended to run on both QGIS 3 and 4, prefer APIs available in both. Confine necessary version-specific branches to one place.

- Import Qt classes from `qgis.PyQt` for modules QGIS exposes. Avoid importing `PyQt5` / `PyQt6` directly or mixing bindings. Some classes moved modules in Qt 6; for example, `QAction` is in `QtWidgets` in Qt 5 but in `QtGui` in Qt 6. In code targeting both, check the import location in the actual environment and bridge the difference only where necessary. Do not assume modules exist that `qgis.PyQt` does not provide.
- Use scoped enum names that work in both Qt 5 and 6, e.g. `Qt.ItemDataRole.UserRole`, `Qt.CursorShape.WaitCursor`, `QDialog.DialogCode.Accepted`. Be explicit in PyQGIS too, e.g. `Qgis.MessageLevel.Critical`, `QgsMapLayer.LayerType.VectorLayer`. Do not assume enum values are integers; check `.value` and similar in the target environment only for APIs that require a number.
- When you hit version-dependent Qt or PyQGIS APIs, first check the target environment's API, help, and exceptions. Add version-specific handling only when no common API exists. Do not decide QGIS API differences based on the Qt version alone.
- Before calling 3D APIs such as `iface.createNewMapCanvas3D()` or `iface.mapCanvases3D()`, run `import qgis._3d`. Their return type `Qgs3DMapCanvas` lives in that module, and if it has not been imported the binding crashes QGIS instead of raising an exception.
- Never chain a call onto a pointer borrowed from a temporary, e.g. `renderer.ranges()[i].symbol().clone()` or `renderer.categories()[i].symbol()`. `ranges()` / `categories()` return copies; the copy is freed right after `.symbol()` returns, and its symbol goes with it, so the next call dereferences freed memory and crashes QGIS. Bind the owner to a variable first: `for i, rng in enumerate(renderer.ranges()): sym = rng.symbol().clone()`.
- Some bundled pandas builds (e.g. pandas 3.0.3 with numpy 2.5 in QGIS 4.2 for macOS) crash or hang QGIS when converting to datetime64: `pd.to_datetime`, or a DataFrame/GeoDataFrame built from `datetime` values. Keep dates as ISO strings (`'2026-10-15'`) in pandas/geopandas, or write features with PyQGIS instead.

Claim compatibility with both QGIS 3/Qt 5 and QGIS 4/Qt 6 only after verifying imports and representative operations on both; otherwise state the environment actually tested.

Check unknown differences in the [QGIS Qt5/Qt6 migration guide](https://github.com/qgis/QGIS/wiki/Plugin-migration-to-be-compatible-with-Qt5-and-Qt6) and [Differences between PyQt 5 and PyQt 6](https://www.riverbankcomputing.com/static/Docs/PyQt6/pyqt5_differences.html).
