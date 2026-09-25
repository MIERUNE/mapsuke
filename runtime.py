"""Only called on the GUI thread: QGIS objects are not thread safe."""
import contextlib
import io
import traceback

from qgis.core import (Qgis, QgsApplication, QgsMapLayer, QgsProcessingAlgRunnerTask,
                       QgsProcessingException, QgsProcessingFeedback, QgsProcessingOutputMapLayer,
                       QgsProcessingOutputRasterLayer, QgsProcessingOutputVectorLayer, QgsProject,
                       QgsVectorLayer)

# The worker thread uses each job's context until the task finishes, even after a stop.
_ACTIVE_JOBS = set()


class LimitedOutput(io.StringIO):
    def write(self, text):
        remaining = max(0, 20000 - self.tell())
        super().write(text[:remaining])
        return len(text)


def describe(value):
    if isinstance(value, QgsMapLayer):
        item = {"layer": value.name(), "valid": value.isValid(), "crs": value.crs().authid()}
        if isinstance(value, QgsVectorLayer):
            item["feature_count"] = value.featureCount()
        return item
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)[:500]


class BackgroundProcessing:
    """One Processing algorithm on a QgsTask; QGIS moves result layers back to this thread."""

    def __init__(self, algorithm_id, parameters):
        from processing.tools import dataobjects
        algorithm = QgsApplication.processingRegistry().algorithmById(algorithm_id)
        if algorithm is None:
            raise QgsProcessingException("Algorithm not found: " + algorithm_id)
        if algorithm.flags() & Qgis.ProcessingAlgorithmFlag.NoThreading:
            raise QgsProcessingException(algorithm_id + " cannot run in the background; use processing.run")
        self.algorithm_id = algorithm_id
        self.feedback = QgsProcessingFeedback()
        self.context = dataobjects.createContext(self.feedback)
        valid, message = algorithm.checkParameterValues(parameters, self.context)
        if not valid:
            raise QgsProcessingException(message)
        self.outputs = algorithm.outputDefinitions()
        self.ok = None
        self.results = {}
        self.on_done = None
        self.task = QgsProcessingAlgRunnerTask(algorithm, parameters, self.context, self.feedback)
        self.task.executed.connect(self._executed)
        _ACTIVE_JOBS.add(self)
        QgsApplication.taskManager().addTask(self.task)

    @property
    def done(self):
        return self.ok is not None

    def progress(self):
        return self.feedback.progress()

    def cancel(self):
        self.on_done = None
        self.feedback.cancel()
        if self.task is not None:
            self.task.cancel()

    def _executed(self, ok, results):
        # The task manager deletes the task after this signal.
        self.task = None
        _ACTIVE_JOBS.discard(self)
        self.ok = bool(ok) and not self.feedback.isCanceled()
        self.results = dict(results or {})
        for output in self.outputs:
            value = self.results.get(output.name())
            if isinstance(output, (QgsProcessingOutputMapLayer, QgsProcessingOutputRasterLayer,
                                   QgsProcessingOutputVectorLayer)) and isinstance(value, str):
                layer = self.context.takeResultLayer(value)
                if layer is not None:
                    self.results[output.name()] = layer
        if self.on_done is not None:
            self.on_done(self)

    def summary(self):
        return {"algorithm": self.algorithm_id, "ok": self.ok,
                "canceled": self.feedback.isCanceled(),
                "results": {key: describe(value) for key, value in self.results.items()},
                "log": self.feedback.textLog()[-12000:]}


class QgisRuntime:
    def __init__(self, iface):
        import processing
        import qgis
        self.iface = iface
        self.namespace = {"__name__": "__qgis_agent__", "iface": iface,
                          "project": QgsProject.instance(), "processing": processing,
                          "qgis": qgis,
                          "run_processing_in_background": self.run_processing_in_background}
        self.job = None

    def run_processing_in_background(self, algorithm_id, parameters):
        """Start after the current code; the bridge reports the job when it finishes."""
        if self.job is not None:
            raise RuntimeError("Only one background Processing run per code execution")
        self.job = BackgroundProcessing(algorithm_id, parameters)
        return self.job

    def take_job(self):
        job, self.job = self.job, None
        return job

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
