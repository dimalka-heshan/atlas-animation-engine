import pytest
from pydantic import ValidationError

from engine.core.models import Project


def asset_project():
    return {"schema_version": "1.1", "id": "asset-scene", "scene": {
        "entities": [{"id": "hero", "asset": {"id": "prop", "version": 1},
                      "normalize": "unit", "pivot": "base"}],
        "camera": {"target_entity": "hero"}}}


def test_asset_references_are_pinned_and_portable():
    project = Project.model_validate(asset_project())
    assert project.scene.entities[0].asset.id == "prop"
    assert project.scene.entities[0].asset.version == 1
    assert Project.model_validate_json(project.model_dump_json()) == project


@pytest.mark.parametrize("change", [{"asset": {"id": "prop"}},
    {"asset": {"id": "../escape", "version": 1}}, {"asset": {"id": "prop", "version": 0}},
    {"primitive": "cube"}, {"material": {"color": [1, 0, 0]}}, {"normalize": "unknown"},
    {"path": "C:/unapproved.glb"}])
def test_invalid_or_ambiguous_asset_entities(change):
    value = asset_project()
    value["scene"]["entities"][0].update(change)
    with pytest.raises(ValidationError):
        Project.model_validate(value)


def test_asset_fields_require_new_schema_version():
    value = asset_project()
    value["schema_version"] = "1.0"
    with pytest.raises(ValidationError, match="1.1"):
        Project.model_validate(value)


def test_old_primitive_projects_remain_valid():
    project = Project.model_validate({"schema_version": "1.0", "id": "old", "scene": {"entities": [{"id": "cube"}]}})
    assert project.scene.entities[0].primitive == "cube"


def test_missing_library_rejected_without_launching_renderer(tmp_path):
    import json
    from engine.rendering.pipeline import render_project
    project = Project.model_validate(asset_project())
    with pytest.raises(ValueError, match="library does not exist"):
        render_project(project, tmp_path / "output", asset_library=tmp_path / "missing")
    job = next((tmp_path / "output").glob("*/manifest.json"))
    assert json.loads(job.read_text())["status"] == "failed"
    assert not (job.parent / "blender.log").exists()
