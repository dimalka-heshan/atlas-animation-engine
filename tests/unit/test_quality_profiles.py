import pytest

from engine.core.models import Project
from engine.core.quality import enforce_geometry_budget


def test_quality_sets_defaults_and_preserves_explicit_render_overrides():
    project = Project.model_validate({"schema_version": "1.4", "id": "shot", "scene": {},
                                      "quality": {"profile": "cinematic"}, "render": {"width": 960, "samples": 32}})
    assert project.render.model_dump(include={"engine", "width", "height", "samples"}) == {
        "engine": "cycles", "width": 960, "height": 1080, "samples": 32,
    }
    assert project.quality.look == "AgX - Medium High Contrast"
    assert Project.model_validate(project.model_dump()) == project


@pytest.mark.parametrize("profile", ["authoring", ["preview"], {"name": "preview"}])
def test_invalid_profile_raises_validation_error(profile):
    with pytest.raises(ValueError, match="quality.profile"):
        Project.model_validate({"schema_version": "1.4", "id": "shot", "scene": {}, "quality": {"profile": profile}})


def test_quality_settings_require_new_schema():
    with pytest.raises(ValueError, match="require schema 1.4"):
        Project.model_validate({"schema_version": "1.3", "id": "shot", "scene": {}, "quality": {"profile": "preview"}})


def test_budget_counts_instances_and_checks_packed_texture_dimensions():
    reference = {"id": "scan", "version": 1}
    project = Project.model_validate({"schema_version": "1.4", "id": "shot",
        "quality": {"profile": "preview", "max_asset_polygons": 1000, "max_texture_size": 1024},
        "scene": {"entities": [{"id": name, "asset": reference} for name in ("one", "two")]}})
    report = {"polygon_count": 600, "textures": [{"size": [1024, 512]}]}
    entries = [reference | {"inspection": {"report": report}}]
    with pytest.raises(ValueError, match="1200 imported polygons"):
        enforce_geometry_budget(project, entries)
    report["polygon_count"] = 400
    enforce_geometry_budget(project, entries)
    report["textures"][0]["size"] = [1024, 2048]
    with pytest.raises(ValueError, match="texture resolution budget"):
        enforce_geometry_budget(project, entries)
