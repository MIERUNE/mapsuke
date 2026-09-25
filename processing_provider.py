"""Publish reusable algorithms through QGIS's existing script provider."""
from .i18n import tr
import inspect
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

from qgis.core import (Qgis, QgsApplication, QgsMapLayer, QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingFeatureBasedAlgorithm,
                       QgsProcessingOutputString, QgsProcessingParameterString,
                       QgsProcessingProvider, QgsProject, QgsVectorLayer, QgsWkbTypes)

LAYER_LIMIT = 100
FIELD_LIMIT = 100


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
    state = {"qgis_version": Qgis.QGIS_VERSION, "project_path": project.fileName() or None,
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
        return (tr("Register Python defining exactly one QgsProcessingAlgorithm subclass. "
                "NAME must start with a lowercase letter, contain lowercase letters, digits or underscores, and match name(). "
                "Implement createInstance(), displayName(), initAlgorithm(), processAlgorithm(), and shortHelpString(). "
                "Define inputs and outputs with Processing parameters. "
                "Keep reusable definitions in this single file where possible; embed QPT and QML as XML strings and small settings as constants or dictionaries. "
                "Describe usage in shortHelpString(). "
                "For APIs requiring file paths, create temporary files at runtime and remove them afterward. "
                "Make observations, dates, and outputs runtime parameters; do not depend on bundled files, generated modules, or sys.path changes. "
                "The tool is saved in the QGIS profile as script:NAME and remains available after restart. "
                "An existing NAME is updated at its original location. Decorator-style scripts are unsupported. "
                "Registration executes top-level and initialization code, so keep data operations in processAlgorithm(). "
                "Registration alone does not verify the result. "
                "After creating or updating, run the returned ALGORITHM_ID and inspect its output. "
                "Use representative inputs and temporary output; fix and retest with the same NAME if needed. "
                "Test real connections for retrieval tools; a mock response alone is insufficient."))

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
        return "qgis_agent"

    def name(self):
        return "QGIS Agent"

    def loadAlgorithms(self):
        self.addAlgorithm(AddTool())
        self.addAlgorithm(ProjectState())
