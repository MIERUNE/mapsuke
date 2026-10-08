"""Static facts about this QGIS installation, sent once with a session's first request.

Installations differ (OSGeo4W, macOS app, distro builds, QGIS 3/4), so the agent cannot
infer them, yet they do not change while QGIS runs."""
import importlib.metadata
import platform
import re

from .processing_catalog import processing_catalog


def python_packages():
    # A duplicate project keeps the first, importable one; names compare after PEP 503
    # normalization (foo_bar and Foo.Bar are one project).
    packages = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            packages.setdefault(re.sub(r"[-_.]+", "-", name).lower(), f"{name} {dist.version}")
    return sorted(packages.values(), key=str.lower)


def environment():
    from osgeo import gdal
    from qgis.core import Qgis, QgsApplication, QgsProjUtils
    from qgis.PyQt.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
    return {
        "versions": {
            "qgis": Qgis.QGIS_VERSION, "qt": QT_VERSION_STR, "pyqt": PYQT_VERSION_STR,
            "python": platform.python_version(), "os": platform.platform(),
            "gdal": gdal.VersionInfo("RELEASE_NAME"), "geos": Qgis.geosVersion(),
            "proj": f"{QgsProjUtils.projVersionMajor()}.{QgsProjUtils.projVersionMinor()}",
        },
        "python_packages": python_packages(),
        "processing_catalog": processing_catalog(QgsApplication.processingRegistry()),
    }
