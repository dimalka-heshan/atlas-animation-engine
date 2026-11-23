"""Expand reusable primitive scatter groups before renderer execution."""
import random

from engine.core.models import Project


def expand_project(project: Project) -> Project:
    """Return a validated scene with seeded, separated XY scatter positions.

    Separation applies to centers inside each group, not mesh collision bounds.
    Reject exhausted placement instead of silently reducing the requested count.
    """
    expanded = project.model_dump(mode="json")
    for group in project.scene.scatter:
        rng = random.Random(f"{project.seed}:{group.id}")
        placed: list[tuple[float, float]] = []
        x0, x1, y0, y1 = group.bounds
        for index in range(group.count):
            for _ in range(1000):
                x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
                if all((x - px) ** 2 + (y - py) ** 2 >= group.min_distance ** 2 for px, py in placed):
                    break
            else:
                raise ValueError(f"Cannot place {group.count} objects in scatter '{group.id}'; enlarge bounds or reduce min_distance")
            placed.append((x, y))
            factor = rng.uniform(*group.scale_range)
            entity = group.prototype.model_dump(mode="json")
            entity.update(id=f"{group.id}_{index}",
                          location=[x, y, group.prototype.location[2] * factor],
                          scale=[v * factor for v in group.prototype.scale],
                          rotation=[*group.prototype.rotation[:2], rng.uniform(0, 360)])
            expanded["scene"]["entities"].append(entity)
    expanded["scene"]["scatter"] = []
    return Project.model_validate(expanded)
