import pytest

from engine.characters.interaction import validate_handoff
from engine.core.models import Project


def handoff_project():
    return {
        "schema_version": "1.6", "id": "exchange", "render": {"frames": 40},
        "scene": {"entities": [
            {"id": "giver", "asset": {"id": "human", "version": 1}, "rigged": True, "pivot": "base", "location": [0, 0, 0]},
            {"id": "receiver", "asset": {"id": "human", "version": 1}, "rigged": True, "pivot": "base", "location": [0, -.8, 0]},
            {"id": "parcel", "primitive": "cube", "scale": [.08, .06, .04]}
        ]},
        "handoff": {
            "prop": "parcel", "initial_owner": "giver",
            "grip": {"name": "parcel-grip", "offset": [0, 0, 0]},
            "receive_grip": {"name": "parcel-receive-grip", "offset": [0, 1, 0]},
            "giver": {"name": "donor-wrist", "actor": "giver", "hand": "right"},
            "receiver": {"name": "recipient-wrist", "actor": "receiver", "hand": "left"},
            "contact": [0, -.4, 1.1], "reach_start": 12, "contact_start": 16,
            "transfer_frame": 18, "contact_end": 20, "release_end": 25
        }
    }


@pytest.mark.parametrize(("key", "invalid", "message"), [
    ("transfer_frame", 16, "ordered"),
    ("initial_owner", "receiver", "initial owner"),
    ("prop", "giver", "static"),
    ("release_end", 100, "render"),
    ("receive_grip", {"name": "parcel-grip"}, "distinct"),
])
def test_project_rejects_unsafe_handoff_state(key, invalid, message):
    value = handoff_project()
    value["handoff"][key] = invalid
    with pytest.raises(ValueError, match=message):
        Project.model_validate(value)


def test_previous_schema_rejects_handoff():
    value = handoff_project() | {"schema_version": "1.5"}
    with pytest.raises(ValueError, match="schema 1.6"):
        Project.model_validate(value)


def test_host_requires_supported_rig_and_finished_motion():
    value = handoff_project()
    value["scene"]["entities"][0]["keyframes"] = [{"frame": 15, "location": [0, .1, 0]}]
    project = Project.model_validate(value)
    asset = {"id": "human", "version": 1, "container": {"profile": "human"},
             "inspection": {"report": {"humanoid_mapping": {
                 f"{side}_{part}": f"{part}_{side}" for side in ("left", "right") for part in ("upper_arm", "forearm", "hand")
             }}}}
    with pytest.raises(ValueError, match="arrive"):
        validate_handoff(project, [asset])
    value["scene"]["entities"][0].pop("keyframes")
    project = Project.model_validate(value)
    validate_handoff(project, [asset])
    asset["container"]["profile"] = "rigged"
    with pytest.raises(ValueError, match="MPFB"):
        validate_handoff(project, [asset])


def test_host_rejects_grip_outside_static_prop_limit():
    value = handoff_project()
    value["handoff"]["receive_grip"]["offset"] = [0, 7, 0]
    with pytest.raises(ValueError, match="0.4 meters"):
        validate_handoff(Project.model_validate(value), [])
