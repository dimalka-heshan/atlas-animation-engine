"""Blender command-line entrypoint for static asset metadata extraction."""
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asset_import import import_asset


def main():
    source, output, *options = sys.argv[sys.argv.index("--") + 1:]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _, report = import_asset(Path(source), "inspection", profile=options[0] if options else "static")
    report["blender_version"] = bpy.app.version_string
    Path(output).write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
