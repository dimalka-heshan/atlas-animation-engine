from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.assets.registry import file_hash
from engine.characters.motion import load_motion, resolve_motions, snapshot_motions, store_motion
from engine.core.models import MotionPin


def test_immutable_motion_pin_verifies_payload_and_alias(tmp_path):
    content = {"profile": "atlas-motion-1", "source": {"clip": "Walk"}, "target": {"skeleton_sha256": "1" * 64},
               "bake": {"fps": 30, "bones": ["hips"], "pelvis": "hips", "frames": [[[1, 0, 0, 0], [0, 0, 0]],
                 [[1, 0, 0, 0], [0, 0, 0]]], "metrics": {}}}
    pin = store_motion(tmp_path, "walking", content)
    record, blob = load_motion(tmp_path, pin)
    assert record == content
    assert file_hash(blob) == pin["sha256"]
    assert store_motion(tmp_path, "walking", content) == pin
    with pytest.raises(ValueError, match="missing"):
        load_motion(tmp_path, pin | {"id": "unknown"})
    Path(blob).write_text("changed")
    with pytest.raises(ValueError, match="hash"):
        load_motion(tmp_path, pin)


def test_snapshot_retains_both_aliases_and_copies_shared_blob_once(tmp_path):
    content = {"profile": "atlas-motion-1", "source": {"clip": "Walk"}, "target": {}, "category": "walk",
               "bake": {"fps": 30, "frames": [[], []], "metrics": {}}}
    cache = tmp_path / "cache"
    first, second = [store_motion(cache, name, content) for name in ("walk", "walk-copy")]
    project = SimpleNamespace(actions=[SimpleNamespace(motion=MotionPin(**pin)) for pin in (first, second)],
                              scene=SimpleNamespace(entities=[]))
    job = tmp_path / "job"
    job.mkdir()
    snapshots = snapshot_motions(resolve_motions(project, cache), job)
    assert [entry["motion"] for entry in snapshots] == [first, second]
    assert len(list((job / "motions").iterdir())) == 1
