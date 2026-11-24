import pytest

from engine.core.models import EnvironmentCollection, Project, RiggedEntity
from engine.worlds.placement import expand_project


def project():
    return {"schema_version": "1.3", "id": "rig-test", "scene": {"entities": [
        {"id": "actor", "asset": {"id": "hero", "version": 1}, "rigged": True,
         "clips": [{"name": "Idle", "start_frame": 1, "frame_count": 12}]}]}}


def test_rigged_clip_survives_save_and_expansion():
    saved = Project.model_validate(project()).model_dump_json()
    entity = expand_project(Project.model_validate_json(saved)).scene.entities[0]
    assert isinstance(entity, RiggedEntity)
    assert entity.clips[0].name == "Idle"


@pytest.mark.parametrize("start,count", [(12, 2), (48, 2)])
def test_rigged_timeline_rejects_overlap_and_overrun(start, count):
    data = project()
    data["scene"]["entities"][0]["clips"].append({"name": "Walk", "start_frame": start, "frame_count": count})
    with pytest.raises(ValueError, match="nonoverlapping"):
        Project.model_validate(data)


def test_legacy_project_rejects_rigged_features():
    data = project() | {"schema_version": "1.2"}
    with pytest.raises(ValueError, match="1.3"):
        Project.model_validate(data)


def test_collection_reuses_pins_and_rejects_id_collisions():
    item = {"id": "tree", "asset": {"id": "oak", "version": 3}}
    collection = EnvironmentCollection(id="grove", entities=[item])
    original = Project.model_validate(project())
    merged = collection.apply(original)
    assert merged.scene.entities[1].asset.version == 3
    assert len(original.scene.entities) == 1
    with pytest.raises(ValueError, match="unique"):
        collection.apply(merged)
