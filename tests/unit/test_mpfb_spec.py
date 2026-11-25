import pytest

from engine.characters.mpfb import HumanSpec


def test_human_generation_spec_is_explicit_and_bounded():
    spec = HumanSpec(id="human-a", seed=1042, age=.65, wardrobe="formal")
    assert spec.age == .65
    with pytest.raises(ValueError):
        HumanSpec(id="human-a", age=float("nan"))
    with pytest.raises(ValueError):
        HumanSpec(id="human-a", hair="../unsafe")
    with pytest.raises(ValueError):
        HumanSpec(id="human-a", unimplemented_feature=True)
