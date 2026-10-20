"""Publish reusable algorithms through QGIS's existing script provider."""
from ..i18n import tr
import inspect
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

from qgis.core import (Qgis, QgsApplication, QgsMapLayer, QgsNetworkAccessManager,
                       QgsProcessingAlgorithm, QgsProcessingException,
                       QgsProcessingFeatureBasedAlgorithm, QgsProcessingOutputNumber,
                       QgsProcessingOutputString, QgsProcessingParameterFile,
                       QgsProcessingParameterFileDestination, QgsProcessingParameterString,
                       QgsProcessingProvider, QgsProcessingUtils, QgsProject, QgsVectorLayer,
                       QgsWkbTypes)
from qgis.PyQt.QtCore import QEventLoop, Qt, QUrl
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

LAYER_LIMIT = 100
FIELD_LIMIT = 100
IMAGE_LIMIT = 4
IMAGE_EDGE = 1568
IMAGE_BYTES = 2_000_000
# Images view_image prepared for the agent's next request; the bridge drains it per code block.
pending_images = []


def prepare_image(source):
    """Copy an image scaled and compressed for an agent request; raises QgsProcessingException."""
    image = QImage(str(source))
    if image.isNull():
        raise QgsProcessingException(tr("Could not read the image"))
    if max(image.width(), image.height()) > IMAGE_EDGE:
        image = image.scaled(IMAGE_EDGE, IMAGE_EDGE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    handle, path = tempfile.mkstemp(prefix="agent-view-", suffix=".png", dir=QgsProcessingUtils.tempFolder())
    os.close(handle)
    if not image.save(path, "PNG"):
        raise QgsProcessingException(tr("Could not save the image"))
    if os.path.getsize(path) > IMAGE_BYTES:
        # Photos and imagery compress poorly as PNG; flatten transparency onto white for JPEG.
        flat = QImage(image.size(), QImage.Format.Format_RGB32)
        flat.fill(QColor("white"))
        painter = QPainter(flat)
        painter.drawImage(0, 0, image)
        painter.end()
        os.remove(path)
        path = path[:-4] + ".jpg"
        if not flat.save(path, "JPEG", 90):
            raise QgsProcessingException(tr("Could not save the image"))
    return path


def describe_layer(layer, visible):
    item = {"id": layer.id(), "name": layer.name(), "type": QgsMapLayer.LayerType(layer.type()).name,
            "provider": layer.providerType(), "source": layer.publicSource()[:500],
            "crs": layer.crs().authid(), "valid": layer.isValid(), "visible": visible}
    if isinstance(layer, QgsVectorLayer):
        fields = list(layer.fields())
        item.update(geometry_type=QgsWkbTypes.displayString(layer.wkbType()),
                    feature_count=layer.featureCount(), selected_count=layer.selectedFeatureCount(),
                    fields=[{"name": f.name(), "type": f.typeName()} for f in fields[:FIELD_LIMIT]],
                    field_count=len(fields))
    return item


def project_state(project):
    """Layers in Layers panel order (top first); layers outside the tree follow."""
    from qgis.utils import iface
    nodes = project.layerTreeRoot().findLayers()
    listed = [(node.layer(), node.isVisible()) for node in nodes if node.layer() is not None]
    ids = {layer.id() for layer, _ in listed}
    listed += [(layer, False) for layer in project.mapLayers().values() if layer.id() not in ids]
    state = {"project_path": project.fileName() or None,
             "project_crs": project.crs().authid(), "active_layer_id": None,
             "layers": [describe_layer(layer, visible) for layer, visible in listed[:LAYER_LIMIT]],
             "layer_count": len(listed), "layer_limit": LAYER_LIMIT}
    if iface is not None:
        active = iface.activeLayer()
        canvas = iface.mapCanvas()
        extent = canvas.extent()
        state["active_layer_id"] = active.id() if active else None
        state["canvas"] = {"crs": canvas.mapSettings().destinationCrs().authid(),
                           "extent": [extent.xMinimum(), extent.yMinimum(),
                                      extent.xMaximum(), extent.yMaximum()],
                           "scale": canvas.scale()}
    return state


class ProjectState(QgsProcessingAlgorithm):
    def name(self):
        return "project_state"

    def displayName(self):
        return tr("Get project state")

    def group(self):
        return tr("Project")

    def groupId(self):
        return "project"

    def createInstance(self):
        return ProjectState()

    def flags(self):
        # The project, layer tree and canvas belong to the GUI thread.
        return super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading

    def shortHelpString(self):
        return (tr("Return the current project state as JSON in STATE: project path and CRS, active layer, "
                   "map canvas extent and scale, and up to 100 layers in Layers panel order with ID, name, "
                   "type, provider, source, CRS, validity and visibility. Vector layers also include "
                   "geometry type, feature and selection counts, and up to 100 fields."))

    def initAlgorithm(self, config=None):
        self.addOutput(QgsProcessingOutputString("STATE", tr("Project state (JSON)")))

    def processAlgorithm(self, parameters, context, feedback):
        state = project_state(context.project() or QgsProject.instance())
        return {"STATE": json.dumps(state, ensure_ascii=False)}


class ViewImage(QgsProcessingAlgorithm):
    def name(self):
        return "view_image"

    def displayName(self):
        return tr("Show image to the agent")

    def group(self):
        return tr("Project")

    def groupId(self):
        return "project"

    def createInstance(self):
        return ViewImage()

    def flags(self):
        # The queue is read by the bridge on the GUI thread.
        return super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading

    def shortHelpString(self):
        return (tr("Attach a PNG or JPEG image to the agent's next request so it can see it, e.g. the canvas "
                   "saved with iface.mapCanvas().saveAsImage(path), a layout page exported with "
                   "QgsLayoutExporter.exportToImage, or a chart. Images are scaled to at most 1568 px on the "
                   "long edge. Up to 4 images per code block. Only takes effect when run from the agent's "
                   "Python bridge. IMAGE returns the attached copy."))

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile("INPUT", tr("Image (PNG or JPEG)"),
                                                     fileFilter="Images (*.png *.jpg *.jpeg)"))
        self.addOutput(QgsProcessingOutputString("IMAGE", tr("Attached image")))

    def processAlgorithm(self, parameters, context, feedback):
        if len(pending_images) >= IMAGE_LIMIT:
            raise QgsProcessingException(tr("Up to 4 images can be attached per code block"))
        path = prepare_image(self.parameterAsFile(parameters, "INPUT", context))
        pending_images.append(path)
        return {"IMAGE": path}


class DownloadFile(QgsProcessingAlgorithm):
    """Stream a download to disk on the Processing worker with QGIS network settings.

    native:filedownloader can crash QGIS on a worker thread: its signal lambdas capture
    stack locals and are queued to the main thread, so a second error after a timeout
    writes to a finished call frame.
    """

    def name(self):
        return "download_file"

    def displayName(self):
        return tr("Download file")

    def group(self):
        return tr("Files")

    def groupId(self):
        return "files"

    def createInstance(self):
        return DownloadFile()

    def shortHelpString(self):
        return tr("Download an HTTP or HTTPS URL to OUTPUT using QGIS's network settings (proxy, "
                  "authentication, timeout). With DATA, sends a form-encoded POST; otherwise GET. "
                  "Run with run_processing_in_background to keep QGIS responsive. Reports progress "
                  "and supports cancellation. OUTPUT is replaced only after a complete download.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString("URL", tr("HTTP or HTTPS URL")))
        self.addParameter(QgsProcessingParameterString("DATA", tr("POST data"), optional=True, multiLine=True))
        self.addParameter(QgsProcessingParameterFileDestination("OUTPUT", tr("Destination file")))
        self.addOutput(QgsProcessingOutputNumber("BYTES", tr("Downloaded bytes")))

    def processAlgorithm(self, parameters, context, feedback):
        url = QUrl(self.parameterAsString(parameters, "URL", context).strip())
        if url.scheme().lower() not in ("http", "https") or not url.host():
            raise QgsProcessingException(tr("Enter a valid HTTP or HTTPS URL"))
        data = self.parameterAsString(parameters, "DATA", context)
        destination = Path(self.parameterAsFileOutput(parameters, "OUTPUT", context))
        if not destination.parent.is_dir():
            raise QgsProcessingException(tr("Destination folder does not exist"))

        request = QNetworkRequest(url)
        if data:
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/x-www-form-urlencoded")
        temporary = None
        reply = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix="." + destination.name + ".",
                                             suffix=".part", delete=False) as stream:
                temporary = Path(stream.name)
                # The manager, reply and loop belong to this worker thread, so reply signals
                # are delivered directly here; cancel is queued here from the GUI thread.
                network = QgsNetworkAccessManager.instance()
                reply = network.post(request, data.encode("utf-8")) if data else network.get(request)
                loop = QEventLoop()
                reply.readyRead.connect(lambda: stream.write(reply.readAll().data()))
                reply.downloadProgress.connect(
                    lambda received, total: feedback.setProgress(100 * received / total) if total > 0 else None)
                reply.finished.connect(loop.quit)
                feedback.canceled.connect(reply.abort)
                if not reply.isFinished():
                    loop.exec()
                stream.write(reply.readAll().data())
            if feedback.isCanceled():
                raise QgsProcessingException(tr("Download canceled"))
            # HTTP errors, unsafe redirects and QGIS network timeouts all end here.
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise QgsProcessingException(tr("Download failed: ") + reply.errorString())
            downloaded = temporary.stat().st_size
            os.replace(temporary, destination)
            temporary = None
        except OSError as exc:
            raise QgsProcessingException(tr("Could not save the file: ") + str(exc)) from exc
        finally:
            if reply is not None:
                reply.deleteLater()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        feedback.setProgress(100)
        return {"OUTPUT": str(destination), "BYTES": downloaded}


class AddTool(QgsProcessingAlgorithm):
    def name(self):
        return "add_tool"

    def displayName(self):
        return tr("Add or update Processing tool")

    def group(self):
        return tr("Tool management")

    def groupId(self):
        return "tools"

    def createInstance(self):
        return AddTool()

    def flags(self):
        # The registry and toolbox belong to the GUI thread.
        return super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading

    def shortHelpString(self):
        return (tr("Register a reusable single-file Processing tool as script:NAME in the QGIS profile, available immediately and after restart. "
                "NAME must start with a lowercase letter, contain only lowercase letters, digits or underscores, and match name(). "
                "Supply SOURCE defining exactly one QgsProcessingAlgorithm subclass implementing name(), createInstance(), displayName(), initAlgorithm(), processAlgorithm(), and shortHelpString(). Decorator-style scripts are unsupported. "
                "Use the same NAME to update an existing tool at its original location. "
                "Declare inputs and outputs with Processing parameters. Expose layers, extents, observations, dates, adjustable conditions, and output destinations as inputs; specify units, CRS, and selection handling. Do not depend on chat variables, fixed layer IDs, or iface. "
                "Keep helpers, QPT/QML XML strings, and small settings in this file; do not depend on adjacent files, generated modules, or sys.path changes. If an API needs a file path, create a temporary file at runtime and clean it up on success or failure. "
                "Put data and network operations in processAlgorithm(), never at the top level or during initialization, which registration executes. Pass context and feedback to nested Processing calls, report progress, handle cancellation, and return the declared outputs. "
                "Processing may run processAlgorithm() on a worker thread. Use parameter-derived feature sources and sinks for data processing; do not access GUI or main-thread-owned project or layer objects from that thread. If the tool must manipulate the live project, layouts, or other main-thread-owned objects, implement flags() returning super().flags() | Qgis.ProcessingAlgorithmFlag.NoThreading so Processing runs it on the main thread. "
                "Describe purpose, assumptions, inputs, outputs, units, and usage in shortHelpString(). "
                "Registration alone does not verify behavior. Run the returned ALGORITHM_ID with representative inputs and temporary outputs; inspect results, including loading and styling where relevant. Test main modes and representative invalid inputs without destructive tests. For retrieval tools, verify permitted real connections rather than mocks alone; do not silently substitute unavailable data. Fix and retest under the same NAME if needed. "
                "Report the tool name, ALGORITHM_ID, FILE, toolbox location, and verified inputs and results, identifying blockers and unverified behavior."))

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterString("NAME", tr("Tool ID (e.g. buffer_and_clip)")))
        self.addParameter(QgsProcessingParameterString("SOURCE", tr("Tool definition (Python)"), multiLine=True))
        self.addOutput(QgsProcessingOutputString("ALGORITHM_ID", tr("Registered tool ID")))
        self.addOutput(QgsProcessingOutputString("FILE", tr("Definition file")))

    def processAlgorithm(self, parameters, context, feedback):
        from processing.script import ScriptUtils

        name = self.parameterAsString(parameters, "NAME", context)
        source = self.parameterAsString(parameters, "SOURCE", context)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise QgsProcessingException(tr("NAME must start with a lowercase letter and contain only lowercase letters, digits, or underscores"))
        registry = QgsApplication.processingRegistry()
        provider = registry.providerById("script")
        if provider is None or not provider.isActive():
            raise QgsProcessingException(tr("Enable the Processing script provider"))
        algorithm_id = "script:" + name
        existing = registry.algorithmById(algorithm_id)
        existing_source = ScriptUtils.findAlgorithmSource(name) if existing else None
        if existing and not existing_source:
            raise QgsProcessingException(tr("Could not locate the existing tool: ") + algorithm_id)
        path = (Path(existing_source) if existing_source else
                Path(ScriptUtils.defaultScriptsFolder()) / (name + ".py")).resolve()

        try:
            # Match the native script loader's class discovery, so restart loads
            # the same algorithm. A fresh namespace prevents chat-state capture.
            namespace = {"__name__": name, "__file__": str(path)}
            exec(compile(source, str(path), "exec"), namespace, namespace)  # nosec B102
            classes = [obj for obj in namespace.values() if inspect.isclass(obj)
                       and issubclass(obj, QgsProcessingAlgorithm)
                       and obj not in (QgsProcessingAlgorithm, QgsProcessingFeatureBasedAlgorithm)]
            if len(classes) != 1:
                raise ValueError(tr("Define exactly one QgsProcessingAlgorithm subclass"))
            algorithm = classes[0]()
            # Call Python overrides directly: exceptions crossing Qt/SIP's C++
            # virtual initAlgorithm callback can abort the QGIS process.
            instance = algorithm.createInstance()
            if type(instance) is not type(algorithm):
                raise ValueError(tr("createInstance() must return a new instance of the same algorithm class"))
            if instance is algorithm:
                raise ValueError(tr("createInstance() must create a new instance"))
            if type(algorithm).processAlgorithm is QgsProcessingAlgorithm.processAlgorithm:
                raise ValueError(tr("Implement processAlgorithm()"))
            instance.initAlgorithm()
            if algorithm.name() != name or instance.name() != name:
                raise ValueError(tr("name() does not match NAME"))
            if not instance.displayName().strip() or not instance.shortHelpString().strip():
                raise ValueError(tr("Provide a display name and a shortHelpString() describing purpose, inputs, and outputs"))
        except BaseException as exc:
            raise QgsProcessingException(tr("Could not load tool definition: ") + str(exc)) from exc

        if feedback.isCanceled():
            raise QgsProcessingException(tr("Registration canceled"))
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
                    raise ValueError(tr("Could not register with Processing"))
            elif not provider.addAlgorithm(algorithm):
                raise ValueError(tr("Could not register with Processing"))
        except BaseException as exc:
            if published:
                if backup is not None:
                    os.replace(backup, path)
                else:
                    path.unlink()
                Path(importlib.util.cache_from_source(str(path))).unlink(missing_ok=True)
                if existing:
                    provider.refreshAlgorithms()
            raise QgsProcessingException(tr("Could not save or register tool: ") + str(exc)) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if backup is not None:
                backup.unlink(missing_ok=True)
        ScriptUtils.scriptsRegistry[name] = str(path)
        provider.algorithmsLoaded.emit()
        feedback.pushInfo(tr("Registered: ") + algorithm_id + tr(" (processing result not verified)"))
        return {"ALGORITHM_ID": algorithm_id, "FILE": str(path)}


class AgentProcessingProvider(QgsProcessingProvider):
    def id(self):
        return "mapsuke"

    def name(self):
        return "Mapsuke"

    def loadAlgorithms(self):
        self.addAlgorithm(AddTool())
        self.addAlgorithm(DownloadFile())
        self.addAlgorithm(ProjectState())
        self.addAlgorithm(ViewImage())
