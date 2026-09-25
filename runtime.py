"""Only called on the GUI thread: QGIS objects are not thread safe."""
import contextlib
import io
import traceback

from qgis.core import Qgis, QgsProject, QgsVectorLayer


class LimitedOutput(io.StringIO):
    def write(self, text):
        remaining = max(0, 20000 - self.tell())
        super().write(text[:remaining])
        return len(text)


class QgisRuntime:
    def __init__(self, iface):
        import processing
        import qgis
        self.iface = iface
        self.namespace = {"__name__": "__qgis_agent__", "iface": iface,
                          "project": QgsProject.instance(), "processing": processing,
                          "qgis": qgis}

    def context(self, catalog=None):
        project = QgsProject.instance()
        layers = []
        for layer in list(project.mapLayers().values())[:100]:
            item = {"id": layer.id(), "name": layer.name(), "crs": layer.crs().authid(),
                    "valid": layer.isValid(), "type": int(layer.type())}
            if isinstance(layer, QgsVectorLayer):
                item["fields"] = [{"name": f.name(), "type": f.typeName()} for f in list(layer.fields())[:100]]
                item["selected_count"] = layer.selectedFeatureCount()
            layers.append(item)
        active = self.iface.activeLayer()
        context = {"qgis_version": Qgis.QGIS_VERSION, "project_crs": project.crs().authid(),
                   "active_layer_id": active.id() if active else None, "layers": layers,
                   "layer_count": len(project.mapLayers()), "layer_limit": 100}
        if catalog is not None:
            context["processing_catalog"] = catalog
        return context

    def execute(self, code):
        output = LimitedOutput()
        error = None
        try:
            compiled = compile(code, "<qgis-agent>", "exec")
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                # Executing the reviewed agent code in QGIS is this module's contract.
                exec(compiled, self.namespace, self.namespace)  # nosec B102
        except BaseException:
            # Even SystemExit must not close the host application.
            error = traceback.format_exc()[-12000:]
        finally:
            self.iface.mapCanvas().refresh()
        return {"ok": error is None, "output": output.getvalue(), "error": error,
                "output_limit": 20000}
