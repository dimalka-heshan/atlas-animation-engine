import json
import subprocess
import sys
from pathlib import Path


def cli(*args):
    return subprocess.run([sys.executable, "-m", "apps.cli", *args], capture_output=True, text=True)


def test_cli_schema():
    result = cli("schema")
    assert result.returncode == 0, result.stderr
    assert "1.0" in json.loads(result.stdout)["properties"]["schema_version"]["enum"]


def test_invalid_cli_input(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"id":"bad", "scene":{"camera":{"target_entity":"missing"}}}')
    result = cli("validate", str(path))
    assert result.returncode == 2
    assert "target" in result.stderr
    assert "Traceback" not in result.stderr


def test_examples_are_valid():
    from engine.core.models import Project
    from engine.assets.resolution import project_asset_references
    examples = list(Path("examples").glob("*.json"))
    assert len(examples) >= 3
    for path in examples:
        project = Project.model_validate_json(path.read_text())
        if project_asset_references(project) or project.audio:
            # Media examples require initialized libraries; real resolution/rendering
            # is covered by integration tests rather than a developer's local library.
            continue
        result = cli("validate", str(path))
        assert result.returncode == 0, result.stderr


def test_missing_project_is_actionable():
    result = cli("validate", "missing-project.json")
    assert result.returncode == 2
    assert "missing-project.json" in result.stderr


def test_listing_missing_history_does_not_create_files(tmp_path):
    output = tmp_path / "never-created"
    result = cli("jobs", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert not output.exists()
