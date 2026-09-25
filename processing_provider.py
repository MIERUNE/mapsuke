"""Publish reusable algorithms through QGIS's existing script provider."""
from .i18n import tr
import inspect
import importlib.util
import os
from pathlib import Path
import re
import tempfile

from qgis.core import (Qgis, QgsApplication, QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingFeatureBasedAlgorithm,
                       QgsProcessingOutputString, QgsProcessingParameterString,
                       QgsProcessingProvider)


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
