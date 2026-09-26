"""Build an installable QGIS plugin ZIP from release files only."""

from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "qtaro"


def main(tag):
    version = tag.removeprefix("v")
    if not re.fullmatch(r"\d+(?:\.\d+)+(?:[-.][A-Za-z0-9]+)*", version):
        raise SystemExit(f"Invalid release tag: {tag!r}")

    source_metadata = (ROOT / "metadata.txt").read_text(encoding="utf-8")
    metadata, count = re.subn(r"(?m)^version[ \t]*=.*$", f"version={version}", source_metadata)
    if count != 1:
        raise SystemExit("metadata.txt must contain exactly one version entry")

    files = sorted(ROOT.glob("*.py"))
    files += sorted((ROOT / "skills").glob("*/SKILL.md"))
    files += [ROOT / "README.md", ROOT / "LICENSE"]
    output = ROOT / "dist" / f"{PLUGIN_ID}-{version}.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"{PLUGIN_ID}/{path.relative_to(ROOT).as_posix()}")
        archive.writestr(f"{PLUGIN_ID}/metadata.txt", metadata)
    print(output)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/package_plugin.py [v]X.Y.Z")
    main(sys.argv[1])
