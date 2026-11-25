import pytest

from engine.adapters.blender.walk_contact import stance_targets
from engine.core.models import Project
from tests.unit.test_locomotion import BAKES, actor, movement, project
from engine.characters.locomotion import compile_movement


def test_stance_targets_lock_to_center_without_moving_vertical_path():
    samples = [(frame, (.04 * frame, 0, .10 + frame * .01), frame in range(2, 7)) for frame in range(1, 9)]
    keys = stance_targets(samples)
    assert keys[1][1] == keys[7][1] == 0
    assert keys[4] == ((.16, 0, .14), 1)
    assert keys[2][0][2] == pytest.approx(.12)
    assert keys[2][1] == .5


def test_stance_targets_skip_singletons_and_bound_horizontal_correction():
    samples = [(frame, (float(frame), 0, .1), frame not in {2, 6}) for frame in range(1, 7)]
    keys = stance_targets(samples)
    assert keys[1][1] == 0
    assert keys[3][0][0] == pytest.approx(3.12)
    assert keys[5][0][0] == pytest.approx(4.88)


def test_walk_lock_is_compiled_and_rejected_in_previous_schema():
    action = movement("hero", [0, -1.8, 0], foot_lock=True)
    configured = project([actor("hero", 0, 0)], [action], schema_version="1.6")
    compiled, _ = compile_movement(configured, BAKES)
    assert compiled.scene.entities[0].clips[1].foot_lock
    with pytest.raises(ValueError, match="schema 1.6"):
        Project.model_validate(configured.model_dump() | {"schema_version": "1.5"})
