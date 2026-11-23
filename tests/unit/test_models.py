import copy
import pytest
from pydantic import ValidationError
from engine.core.models import Project
from engine.worlds.placement import expand_project


def config():
    return {"schema_version": "1.0", "id": "test", "scene": {
        "entities": [{"id": "hero", "primitive": "cube"}],
        "camera": {"target_entity": "hero"}}}


def test_defaults_and_roundtrip():
    project = Project.model_validate(config())
    assert project.render.fps == 24
    assert project.render.frames == 48
    assert Project.model_validate_json(project.model_dump_json()) == project


@pytest.mark.parametrize("change", [
    {"schema_version": "2.0"}, {"id": "../escape"}, {"unknown": True},
    {"render": {"width": 321}}, {"render": {"frames": 0}},
    {"render": {"fps": True}}, {"seed": -1},
])
def test_invalid_project(change):
    value = config() | change
    with pytest.raises(ValidationError):
        Project.model_validate(value)


@pytest.mark.parametrize("entity", [
    {"id": "hero", "primitive": "script"},
    {"id": "hero", "scale": [1, 0, 1]},
    {"id": "hero", "location": [float("nan"), 0, 0]},
    {"id": "hero", "keyframes": [{"frame": 49, "location": [0, 0, 0]}]},
    {"id": "hero", "keyframes": [{"frame": 2}, {"frame": 1}]},
    {"id": "hero", "keyframes": [{"frame": 1}, {"frame": 1}]},
])
def test_invalid_entities(entity):
    value = config()
    value["scene"]["entities"] = [entity]
    with pytest.raises(ValidationError):
        Project.model_validate(value)


def test_references_and_duplicate_ids():
    value = config()
    value["scene"]["camera"]["target_entity"] = "missing"
    with pytest.raises(ValidationError, match="target"):
        Project.model_validate(value)
    value = config()
    value["scene"]["entities"] *= 2
    with pytest.raises(ValidationError, match="unique"):
        Project.model_validate(value)


def test_scatter_is_deterministic_without_mutating_source():
    value = config()
    value["scene"]["scatter"] = [{"id": "rocks", "count": 6,
        "prototype": {"id": "rock", "primitive": "ico_sphere"},
        "bounds": [-4, 4, -4, 4], "min_distance": 1.0}]
    project = Project.model_validate(value)
    before = copy.deepcopy(project)
    a, b = expand_project(project), expand_project(project)
    assert a == b
    assert project == before
    assert len(a.scene.entities) == 7
    positions = [e.location for e in a.scene.entities[1:]]
    assert len(set(positions)) == 6
    for i, p in enumerate(positions):
        for q in positions[i + 1:]:
            assert (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= 1
    assert expand_project(project.model_copy(update={"seed": 99})) != a


def test_impossible_scatter_fails():
    value = config()
    value["scene"]["scatter"] = [{"id": "rocks", "count": 10,
        "prototype": {"id": "rock"}, "bounds": [0, 1, 0, 1], "min_distance": 5}]
    with pytest.raises(ValueError, match="place"):
        expand_project(Project.model_validate(value))


@pytest.mark.parametrize("change", [
    {"camera": {"location": [1, 0, 0], "target": [0, 0, 0],
                "keyframes": [{"frame": 20, "location": [0, 0, 0]}]}},
    {"lights": [{"id": "bad", "kind": "AREA", "location": [0, 0, 0], "target": [0, 0, 0]}]},
    {"lights": [{"id": "bad", "kind": "SUN", "location": [0, 0, 0], "target": [0, 0, 0]}]},
])
def test_undefined_aim_rejected(change):
    value = config()
    value["scene"].update(change)
    with pytest.raises(ValidationError, match="target"):
        Project.model_validate(value)


def test_point_light_target_is_not_used():
    value = config()
    value["scene"]["lights"] = [{"id": "point", "kind": "POINT", "location": [0, 0, 0], "target": [0, 0, 0]}]
    Project.model_validate(value)


def test_extreme_scatter_number_returns_validation_error():
    value = config()
    value["scene"]["scatter"] = [{"id": "huge", "count": 2,
        "prototype": {"id": "rock"}, "min_distance": 1e200}]
    with pytest.raises(ValueError):
        expand_project(Project.model_validate(value))
