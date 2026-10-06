"""Load the plugin root as the `geotaro` package so relative imports resolve as they do in QGIS."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if "geotaro" not in sys.modules:
    spec = importlib.util.spec_from_file_location("geotaro", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    sys.modules[spec.name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sys.modules[spec.name])
