"""Only called on the GUI thread: QGIS objects are not thread safe."""
import contextlib
import io
import os
import tempfile
import time
import traceback

from qgis.core import (Qgis, QgsApplication, QgsLayoutExporter, QgsLayoutItemMap, QgsMapLayer,
                       QgsMapRendererParallelJob, QgsMapSettings, QgsPrintLayout,
                       QgsProcessingAlgRunnerTask, QgsProcessingException, QgsProcessingFeedback,
                       QgsProcessingOutputMapLayer, QgsProcessingOutputMultipleLayers,
                       QgsProcessingOutputRasterLayer, QgsProcessingOutputVectorLayer,
                       QgsProcessingUtils, QgsProject, QgsRasterLayer, QgsVectorLayer)
from qgis.PyQt.QtCore import QSize, QSizeF, QTimer
from ..i18n import tr
from .processing_provider import IMAGE_EDGE, pending_images, prepare_image

# The worker thread uses each job's context until the task finishes, even after a stop.
_ACTIVE_JOBS = set()
# Bounds load on remote servers and the size of the results returned to the agent.
MAX_JOBS_PER_RUN = 8


class LimitedOutput(io.StringIO):
    def write(self, text):
        remaining = max(0, 20000 - self.tell())
        super().write(text[:remaining])
        return len(text)


class BackgroundFeedback(QgsProcessingFeedback):
    """Keep the latest progress message for the dock across QGIS 3 and 4."""

    def __init__(self):
        super().__init__()
        self.progress_text = ""

    def setProgressText(self, message):
        self.progress_text = message
        super().setProgressText(message)

    def pushInfo(self, message):
        self.progress_text = message
        super().pushInfo(message)


def describe(value):
    if isinstance(value, QgsMapLayer):
        item = {"layer": value.name(), "id": value.id(), "valid": value.isValid(), "crs": value.crs().authid()}
        if isinstance(value, QgsVectorLayer):
            item["feature_count"] = value.featureCount()
        return item
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [describe(item) for item in value]
    return repr(value)[:500]


class BackgroundProcessing:
    """One Processing algorithm on a QgsTask; QGIS moves result layers back to this thread."""
    images = ()

    def __init__(self, algorithm_id, parameters):
        from processing.tools import dataobjects
        algorithm = QgsApplication.processingRegistry().algorithmById(algorithm_id)
        if algorithm is None:
            raise QgsProcessingException("Algorithm not found: " + algorithm_id)
        if algorithm.flags() & Qgis.ProcessingAlgorithmFlag.NoThreading:
            raise QgsProcessingException(algorithm_id + " cannot run in the background; use processing.run")
        if algorithm_id == "native:filedownloader":
            # It crashes QGIS on a worker thread when a download errors twice (e.g. timeout).
            raise QgsProcessingException("native:filedownloader can crash QGIS in the background; "
                                         "use mapsuke:download_file")
        self.algorithm_id = algorithm_id
        self.feedback = BackgroundFeedback()
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

    @property
    def progress_text(self):
        return self.feedback.progress_text

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
        if self.ok:
            # Processing algorithms can schedule layers without declaring them as outputs.
            # Move these first so output IDs can resolve to their project-owned layers.
            for reference, details in self.context.layersToLoadOnCompletion().items():
                layer = QgsProcessingUtils.mapLayerFromString(
                    reference, self.context, typeHint=details.layerTypeHint)
                if layer is None:
                    self.feedback.reportError("Could not load result layer: " + reference)
                    continue
                target = details.project or QgsProject.instance()
                if target.mapLayer(layer.id()) is None:
                    owned = self.context.temporaryLayerStore().takeMapLayer(layer)
                    details.setOutputLayerName(layer)
                    target.addMapLayer(owned or layer)
                    if details.postProcessor() is not None:
                        details.postProcessor().postProcessLayer(layer, self.context, self.feedback)

        for output in self.outputs:
            value = self.results.get(output.name())
            if isinstance(output, QgsProcessingOutputMultipleLayers) and isinstance(value, (list, tuple)):
                self.results[output.name()] = [self._result_layer(item) for item in value]
            elif isinstance(output, (QgsProcessingOutputMapLayer, QgsProcessingOutputRasterLayer,
                                     QgsProcessingOutputVectorLayer)):
                self.results[output.name()] = self._result_layer(value)
        if self.on_done is not None:
            self.on_done(self)

    def _result_layer(self, value):
        if not self.ok or not isinstance(value, (str, QgsMapLayer)):
            return value
        layer = (value if isinstance(value, QgsMapLayer) else
                 QgsProcessingUtils.mapLayerFromString(value, self.context))
        if layer is None:
            return value
        project = QgsProject.instance()
        if project.mapLayer(layer.id()) is None:
            # A returned layer may have no load-on-completion reservation.
            owned = self.context.temporaryLayerStore().takeMapLayer(layer)
            project.addMapLayer(owned or layer)
        return layer

    def summary(self):
        return {"algorithm": self.algorithm_id, "ok": self.ok,
                "canceled": self.feedback.isCanceled(),
                "results": {key: describe(value) for key, value in self.results.items()},
                "log": self.feedback.textLog()[-12000:]}


class BackgroundPreview:
    """The canvas, a QgsMapSettings or one print layout page as an image for the agent.

    Maps render on worker threads, so QGIS stays responsive and a render that takes too long
    can be canceled. QgsLayoutExporter offers neither: it draws maps on this thread and cannot
    be stopped. A layout is therefore cloned, each map in the clone is rendered on the workers
    and replaced by a raster of the result, and the exporter then draws only those rasters and
    the other items. The layout itself is not touched.
    """
    algorithm_id = "preview_in_background"
    # Seconds after which a render still running is canceled and reported as too heavy.
    TIMEOUT = 120

    def __init__(self, target, iface, page, timeout):
        if not timeout > 0:
            raise ValueError("timeout must be a positive number of seconds")
        self.ok = None
        self.canceled = False
        self.stopped = ""
        self.on_done = None
        self.images = []
        self.log = ""
        self.layout = None
        self.maps = []
        if target is None and iface is not None:
            self.target = "canvas"
            self.settings = [iface.mapCanvas().mapSettings()]
        elif isinstance(target, QgsMapSettings):
            self.target = "map settings"
            self.settings = [target]
        else:
            layout = (QgsProject.instance().layoutManager().layoutByName(target)
                      if isinstance(target, str) else target)
            if not isinstance(layout, QgsPrintLayout):
                raise ValueError("Pass a QgsMapSettings, a print layout or its name, or nothing for the map canvas")
            if not 0 <= page < layout.pageCollection().pageCount():
                raise ValueError(f"The layout has no page {page}")
            self.target = f"layout {layout.name()}, page {page}"
            self.page = page
            # ponytail: the clone loses the atlas preview feature; copy it over if atlas previews matter.
            self.layout = layout.clone()
            sheet = self._inches(self.layout.pageCollection().page(page).rect().size())
            # Sized so the page needs no scaling before it is attached.
            self.dpi = IMAGE_EDGE / max(sheet.width(), sheet.height())
            self.maps = [item for item in self.layout.items()
                         if isinstance(item, QgsLayoutItemMap) and item.page() == page and item.isVisible()]
            self.settings = []
            for item in self.maps:
                size = self._inches(item.rect().size())
                settings = item.mapSettings(
                    item.extent(), QSizeF(size.width() * self.dpi, size.height() * self.dpi), self.dpi, True)
                # Layouts ask for vector output, which this job cannot give and would log a warning about.
                settings.setFlag(Qgis.MapSettingsFlag.ForceVectorOutput, False)
                self.settings.append(settings)
        self.renders = [QgsMapRendererParallelJob(settings) for settings in self.settings]
        self.pending = len(self.renders)
        self.started = time.monotonic()
        self.seconds = 0
        # A render destroyed while active blocks this thread until it stops, so keep it until then.
        _ACTIVE_JOBS.add(self)
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._stop(
            f"Rendering did not finish within {timeout:g} s and was canceled. The map is too heavy to "
            "render as it is: reduce what is drawn (visible layers, geometry detail, labels) and preview again."))
        self.timer.start(int(timeout * 1000))
        for render in self.renders:
            render.finished.connect(self._rendered)
            render.start()
        if not self.renders:
            QTimer.singleShot(0, self._finish)

    def _inches(self, size):
        return self.layout.convertFromLayoutUnits(size, Qgis.LayoutUnit.Inches)

    @property
    def done(self):
        return self.ok is not None

    def progress(self):
        return 0

    @property
    def progress_text(self):
        return tr("Rendering preview")

    def cancel(self):
        self.on_done = None
        self.canceled = True
        self._stop("Canceled")

    def _stop(self, reason):
        if not self.stopped:
            self.stopped = reason
            for render in self.renders:
                render.cancelWithoutBlocking()

    def _rendered(self):
        self.pending -= 1
        if not self.pending:
            # Finishing may drop the last reference to a render, which must outlive its own signal.
            QTimer.singleShot(0, self._finish)

    def _finish(self):
        self.timer.stop()
        _ACTIVE_JOBS.discard(self)
        self.seconds = time.monotonic() - self.started
        self.log = "\n".join(error.layerID + ": " + error.message
                             for render in self.renders for error in render.errors())
        if self.stopped:
            self.log = self.stopped
            self.ok = False
        else:
            try:
                image = self._layout_image() if self.layout is not None else self.renders[0].renderedImage()
                self.images = [prepare_image(image)]
                self.ok = True
            except Exception:
                self.log += "\n" + traceback.format_exc()[-4000:]
                self.ok = False
        self.layout = None
        if self.on_done is not None:
            self.on_done(self)

    def _layout_image(self):
        folder = tempfile.mkdtemp(prefix="preview-", dir=QgsProcessingUtils.tempFolder())
        rasters = []
        for index, (item, render, settings) in enumerate(zip(self.maps, self.renders, self.settings)):
            path = os.path.join(folder, f"map{index}.png")
            if not render.renderedImage().save(path, "PNG"):
                raise RuntimeError("Could not save the rendered map")
            # Georeference the image from its pixel grid, which also covers rotated maps.
            # ponytail: GDAL resamples a rotated map's raster with nearest neighbour, so its text and
            # lines come out slightly jagged; render those at a higher DPI if that ever matters.
            to_map = settings.mapToPixel()
            origin, right, down = (to_map.toMapCoordinates(x, y) for x, y in ((0, 0), (1, 0), (0, 1)))
            transform = (origin.x(), right.x() - origin.x(), down.x() - origin.x(),
                         origin.y(), right.y() - origin.y(), down.y() - origin.y())
            with open(path + ".aux.xml", "w", encoding="utf-8") as stream:
                stream.write("<PAMDataset><GeoTransform>" + ", ".join(repr(value) for value in transform)
                             + "</GeoTransform></PAMDataset>")
            raster = QgsRasterLayer(path, "preview")
            raster.setCrs(settings.destinationCrs())
            if not raster.isValid():
                raise RuntimeError("Could not read the rendered map")
            rasters.append(raster)
            item.setFollowVisibilityPreset(False)
            item.setLayers([raster])
            item.setKeepLayerSet(True)
        image = QgsLayoutExporter(self.layout).renderPageToImage(self.page, QSize(), self.dpi)
        if image.isNull():
            raise RuntimeError("Could not render the layout page")
        return image

    def summary(self):
        return {"algorithm": self.algorithm_id, "ok": self.ok, "canceled": self.canceled,
                "results": {"target": self.target, "seconds": round(self.seconds, 1)}, "log": self.log}


class QgisRuntime:
    def __init__(self, iface=None):
        """iface is None without the QGIS desktop; code then sees iface = None."""
        import processing
        import qgis
        self.iface = iface
        self.processing = processing
        self.qgis = qgis
        self.jobs = []

    def namespace(self):
        """Each run starts fresh; state lives in the QGIS project, not in Python variables."""
        return {"__name__": "__mapsuke__", "iface": self.iface,
                "project": QgsProject.instance(), "processing": self.processing,
                "qgis": self.qgis,
                "run_processing_in_background": self.run_processing_in_background,
                "preview_in_background": self.preview_in_background}

    def run_processing_in_background(self, algorithm_id, parameters):
        """Start now; the bridge reports each job and resumes the agent once all have finished."""
        return self._start(lambda: BackgroundProcessing(algorithm_id, parameters))

    def preview_in_background(self, target=None, page=0, timeout=BackgroundPreview.TIMEOUT):
        """Render the canvas, a QgsMapSettings, or a print layout (object or name) for the agent to see."""
        return self._start(lambda: BackgroundPreview(target, self.iface, page, timeout))

    def _start(self, create):
        if len(self.jobs) >= MAX_JOBS_PER_RUN:
            raise RuntimeError(f"At most {MAX_JOBS_PER_RUN} background runs per code execution")
        job = create()
        self.jobs.append(job)
        return job

    def take_jobs(self):
        jobs, self.jobs = self.jobs, []
        return jobs

    def execute(self, code):
        output = LimitedOutput()
        error = None
        # Only images requested by this block are attached, not ones queued from the toolbox.
        pending_images.clear()
        try:
            compiled = compile(code, "<mapsuke>", "exec")
            namespace = self.namespace()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                # Executing the reviewed agent code in QGIS is this module's contract.
                exec(compiled, namespace, namespace)  # nosec B102
        except BaseException:
            # Even SystemExit must not close the host application.
            error = traceback.format_exc()[-12000:]
        finally:
            self.refresh_canvas()
        result = {"ok": error is None, "output": output.getvalue(), "error": error,
                  "output_limit": 20000}
        if pending_images:
            result["attached_images"] = list(pending_images)
            pending_images.clear()
        return result

    def refresh_canvas(self):
        if self.iface is not None:
            self.iface.mapCanvas().refresh()
