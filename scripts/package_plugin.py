"""Build an installable QGIS plugin ZIP from release files only."""

import configparser
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "qgis-agent"


def main(tag):
    metadata = configparser.ConfigParser()
    metadata.read(ROOT / "metadata.txt", encoding="utf-8")
    version = metadata["general"]["version"]
    if tag != f"v{version}":
        raise SystemExit(f"Tag {tag!r} does not match metadata version v{version}")

    files = sorted(ROOT.glob("*.py"))
    files += sorted((ROOT / "skills").glob("*/SKILL.md"))
    files += [ROOT / "metadata.txt", ROOT / "README.md", ROOT / "LICENSE"]
    output = ROOT / "dist" / f"{PLUGIN_ID}-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"{PLUGIN_ID}/{path.relative_to(ROOT).as_posix()}")
    print(output)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/package_plugin.py vX.Y.Z")
    main(sys.argv[1])
