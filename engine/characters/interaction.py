"""Validate handoff state and rig preconditions before starting Blender."""
from math import dist, hypot

from engine.core.models import Project


def validate_handoff(project: Project, assets: list[dict]) -> None:
    event = project.handoff
    if event is None:
        return
    entities = {entity.id: entity for entity in project.scene.entities}
    prop = entities[event.prop]
    for grip in (event.grip, event.receive_grip):
        if hypot(*(scale * position for scale, position in zip(prop.scale, grip.offset))) > .4:
            raise ValueError(f"Prop anchor {grip.name} exceeds 0.4 meters from the object origin")
    pinned = {(entry["id"], entry["version"]): entry for entry in assets}
    for anchor in (event.giver, event.receiver):
        actor = entities[anchor.actor]
        if actor.keyframes and actor.keyframes[-1].frame > event.reach_start:
            raise ValueError(f"Actor {actor.id} must arrive before starting the handoff reach")
        if actor.scale != (1, 1, 1) or actor.normalize != "none" or actor.pivot != "base":
            raise ValueError("MPFB handoff requires meter-scale base-pivot actors")
        entry = pinned[(actor.asset.id, actor.asset.version)]
        roles = entry["inspection"]["report"]["humanoid_mapping"]
        if entry["container"].get("profile") != "human" or any(
                f"{anchor.hand}_{role}" not in roles for role in ("upper_arm", "forearm", "hand")):
            raise ValueError(f"Actor {actor.id} lacks an inspected MPFB handoff arm")
        root = next((key.location for key in reversed(actor.keyframes) if key.location is not None), actor.location)
        if dist(root[:2], event.contact[:2]) > 1 or not 0.5 <= event.contact[2] - root[2] <= 1.7:
            raise ValueError(f"Contact is outside the handoff zone of actor {actor.id}")
