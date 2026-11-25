"""Deterministic planar movement through explicitly defined scene bounds."""

import heapq
import math
from fractions import Fraction


Point = tuple[float, float]
Rectangle = tuple[float, float, float, float]
MAX_OBSTACLES = 64


def plan_route(
    start: Point,
    destination: Point,
    bounds: Rectangle,
    obstacles: list[Rectangle],
    clearance: float = 0.0,
) -> list[Point]:
    """Return a visibility-graph route between the exact endpoints.

    Clearance insets the walkable bounds and expands the closed obstacles.
    Raises ValueError for invalid geometry, blocked endpoints or no route.
    """
    start = _point(start, "Start")
    destination = _point(destination, "Destination")
    clearance, = _finite_values((clearance,), 1, "Clearance")
    if clearance < 0:
        raise ValueError("Clearance must be nonnegative")
    if len(obstacles) > MAX_OBSTACLES:
        raise ValueError(f"At most {MAX_OBSTACLES} obstacles are supported")

    left, bottom, right, top = _rectangle(bounds, "Walkable bounds")
    area = (left + clearance, bottom + clearance, right - clearance, top - clearance)
    left, bottom, right, top = area
    if not (left <= right and bottom <= top):
        raise ValueError("Clearance leaves no walkable area")
    blocked = _blocked_rectangles(obstacles, area, clearance)
    for point, label in ((start, "Start"), (destination, "Destination")):
        if not _contains(area, point):
            raise ValueError(f"{label} is outside the walkable area after applying clearance")
        if any(_contains(box, point) for box in blocked):
            raise ValueError(f"{label} is blocked by an obstacle")

    if start == destination:
        return [start]
    if _visible(start, destination, blocked):
        return [start, destination]

    scale = math.hypot(right - left, top - bottom)
    # Step into free space by the smallest representable amount so even a
    # narrow passage remains available to the graph.
    candidates = set()
    for x0, y0, x1, y1 in blocked:
        for x, toward_x in ((x0, -math.inf), (x1, math.inf)):
            for y, toward_y in ((y0, -math.inf), (y1, math.inf)):
                corner = (math.nextafter(x, toward_x), math.nextafter(y, toward_y))
                if _contains(area, corner) and not any(_contains(box, corner) for box in blocked):
                    candidates.add(corner)
    candidates.difference_update((start, destination))
    return _shortest_route([start, destination, *sorted(candidates)], blocked, scale)


def approach_position(start: Point, target: Point, distance: float) -> Point:
    """Choose a stopping point on the start side of the target at a positive distance."""
    start_x, start_y = _point(start, "Start")
    target_x, target_y = _point(target, "Target")
    distance, = _finite_values((distance,), 1, "Approach distance")
    if distance <= 0:
        raise ValueError("Approach distance must be positive")
    offset_x, offset_y = start_x - target_x, start_y - target_y
    separation = math.hypot(offset_x, offset_y)
    if separation == 0:
        raise ValueError("Cannot approach from coincident actor locations")
    if not math.isfinite(separation):
        raise ValueError("Approach locations must have finite separation")
    position = _point(
        (target_x + distance * (offset_x / separation), target_y + distance * (offset_y / separation)),
        "Approach position",
    )
    if position == (target_x, target_y):
        raise ValueError("Approach distance is too small for the target coordinates")
    return position


def plan_approach(start: Point, target: Point, distance: float, bounds: Rectangle,
                  obstacles: list[Rectangle], clearance: float, actor_separation: float) -> list[Point]:
    """Prefer the near side and try alternate stops at the same distance."""
    if math.dist(start, target) <= distance:
        return plan_route(start, start, bounds, obstacles, clearance)
    preferred = approach_position(start, target, distance)
    heading = math.atan2(preferred[1] - target[1], preferred[0] - target[0])
    stops = [preferred]
    for step in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6):
        angle = heading + step * math.pi / 6
        stops.append((target[0] + distance * math.cos(angle), target[1] + distance * math.sin(angle)))
    for stop in stops:
        try:
            path = plan_route(start, stop, bounds, obstacles, clearance)
        except ValueError as error:
            if str(error).startswith("Destination"):
                continue
            raise
        if all(not segments_conflict(a, b, target, target, actor_separation) for a, b in zip(path, path[1:])):
            return path
    raise ValueError("No sampled approach stop is reachable at the requested distance")


def segments_conflict(
    start_a: Point, end_a: Point, start_b: Point, end_b: Point, clearance: float,
) -> bool:
    """Check combined personal-space clearance over a shared time interval."""
    start_a = _point(start_a, "First segment start")
    end_a = _point(end_a, "First segment end")
    start_b = _point(start_b, "Second segment start")
    end_b = _point(end_b, "Second segment end")
    clearance, = _finite_values((clearance,), 1, "Combined clearance")
    if clearance < 0:
        raise ValueError("Combined clearance must be nonnegative")

    # In relative coordinates, the minimum separation is the distance from
    # the origin to a single segment. Use exact squared distances for contact.
    x0, y0 = (Fraction(a) - Fraction(b) for a, b in zip(start_a, start_b))
    x1, y1 = (Fraction(a) - Fraction(b) for a, b in zip(end_a, end_b))
    dx, dy = x1 - x0, y1 - y0
    length_squared = dx * dx + dy * dy
    projection = -(x0 * dx + y0 * dy)
    clearance_squared = Fraction(clearance) ** 2
    if projection <= 0:
        return x0 * x0 + y0 * y0 <= clearance_squared
    if projection >= length_squared:
        return x1 * x1 + y1 * y1 <= clearance_squared
    cross = x0 * dy - y0 * dx
    return cross * cross <= clearance_squared * length_squared


def _finite_values(values: tuple, size: int, label: str) -> tuple[float, ...]:
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{label} must contain {size} finite numbers") from error
    if len(result) != size or not all(map(math.isfinite, result)):
        raise ValueError(f"{label} must contain {size} finite numbers")
    return result


def _point(values: Point, label: str) -> Point:
    x, y = _finite_values(values, 2, label)
    return x, y


def _rectangle(values: Rectangle, label: str) -> Rectangle:
    left, bottom, right, top = _finite_values(values, 4, label)
    if not (left < right and bottom < top) or not math.isfinite(math.hypot(right - left, top - bottom)):
        raise ValueError(f"{label} must have positive finite width and height")
    return left, bottom, right, top


def _blocked_rectangles(obstacles: list[Rectangle], area: Rectangle, clearance: float) -> list[Rectangle]:
    bounds_left, bounds_bottom, bounds_right, bounds_top = area
    blocked = set()
    for index, obstacle in enumerate(obstacles, start=1):
        left, bottom, right, top = _rectangle(obstacle, f"Obstacle {index}")
        # Clipping after expansion also keeps segment arithmetic inside the
        # finite walkable span when obstacles extend beyond the scene bounds.
        x0 = max(bounds_left, left - clearance)
        y0 = max(bounds_bottom, bottom - clearance)
        x1 = min(bounds_right, right + clearance)
        y1 = min(bounds_top, top + clearance)
        if x0 <= x1 and y0 <= y1:
            blocked.add((x0, y0, x1, y1))
    return sorted(blocked)


def _contains(box: Rectangle, point: Point) -> bool:
    left, bottom, right, top = box
    x, y = point
    return left <= x <= right and bottom <= y <= top


def _visible(start: Point, end: Point, obstacles: list[Rectangle]) -> bool:
    return not any(_intersects(start, end, box) for box in obstacles)


def _intersects(start: Point, end: Point, box: Rectangle) -> bool:
    entry, exit = 0.0, 1.0
    slabs = []
    for a, b, low, high in zip(start, end, box[:2], box[2:]):
        if max(a, b) < low or min(a, b) > high:
            return False
        if a == b:
            continue
        # Intersect the parameter intervals where the segment lies in each
        # coordinate slab. Equal entry and exit is closed-boundary contact.
        if a > b:
            low, high = high, low
        entry = max(entry, (low - a) / (b - a))
        exit = min(exit, (high - a) / (b - a))
        slabs.append((a, b, low, high))
    if abs(entry - exit) > 8 * math.ulp(1.0):
        return entry < exit

    # Near a corner, rounding in the parameter intervals can hide a collision
    # or close a valid passage. Compare the float inputs as exact ratios there.
    intervals = [(Fraction(0), Fraction(1))]
    for slab in slabs:
        a, b, low, high = map(Fraction, slab)
        intervals.append(((low - a) / (b - a), (high - a) / (b - a)))
    return max(low for low, _ in intervals) <= min(high for _, high in intervals)


def _shortest_route(points: list[Point], blocked: list[Rectangle], scale: float) -> list[Point]:
    destination = points[1]
    distances = {0: 0.0}
    previous = {}
    visited = set()
    queue = [(math.dist(points[0], destination) / scale, 0.0, 0)]
    while queue:
        _, distance, index = heapq.heappop(queue)
        if index in visited:
            continue
        if index == 1:
            route = [destination]
            while index:
                index = previous[index]
                route.append(points[index])
            return route[::-1]
        visited.add(index)
        start = points[index]
        for next_index, end in enumerate(points):
            if next_index in visited:
                continue
            next_distance = distance + math.dist(start, end) / scale
            if next_distance >= distances.get(next_index, math.inf) or not _visible(start, end, blocked):
                continue
            distances[next_index] = next_distance
            previous[next_index] = index
            priority = next_distance + math.dist(end, destination) / scale
            heapq.heappush(queue, (priority, next_distance, next_index))
    raise ValueError("Destination is unreachable within the walkable area")
