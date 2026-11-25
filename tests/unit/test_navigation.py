import math

import pytest

from engine.characters.navigation import approach_position, plan_route, segments_conflict


BOUNDS = (0, 0, 10, 10)


def test_clear_route_keeps_exact_endpoints_and_skips_unneeded_turns():
    start, destination = (0.25, 3.5), (9.75, 3.5)
    assert plan_route(start, destination, BOUNDS, [(4, 4, 6, 6)]) == [start, destination]


def test_route_detours_around_obstacles_with_clearance_and_stable_ordering():
    start, destination = (1, 5), (9, 5)
    obstacles = [(4, 4, 6, 6), (4, 8, 6, 9)]
    route = plan_route(start, destination, BOUNDS, obstacles, clearance=0.5)

    assert route == plan_route(start, destination, BOUNDS, obstacles[::-1], clearance=0.5)
    assert route[0] == start and route[-1] == destination
    assert len(route) == 4
    assert all(0.5 <= x <= 9.5 and 0.5 <= y <= 9.5 for x, y in route)
    for x in (3.5, 4, 5, 6, 6.5):
        preceding, following = next((a, b) for a, b in zip(route, route[1:]) if a[0] <= x <= b[0])
        y = preceding[1] + (following[1] - preceding[1]) * (x - preceding[0]) / (following[0] - preceding[0])
        assert y < 3.5 or 6.5 < y < 7.5


def test_route_avoids_a_closed_obstacle_corner_on_the_direct_segment():
    start, destination = (1, 7), (7, 1)
    route = plan_route(start, destination, BOUNDS, [(4, 4, 6, 6)])

    assert len(route) == 3
    assert sum(route[1]) < 8


def test_destination_inside_obstacle_clearance_is_blocked():
    with pytest.raises(ValueError, match="Destination.*blocked"):
        plan_route((1, 5), (3.8, 5), BOUNDS, [(4, 4, 6, 6)], clearance=0.5)


def test_start_on_closed_obstacle_edge_is_blocked():
    with pytest.raises(ValueError, match="Start.*blocked"):
        plan_route((4, 5), (1, 5), BOUNDS, [(4, 4, 6, 6)])


def test_clearance_required_at_walkable_boundary():
    with pytest.raises(ValueError, match="Destination.*walkable"):
        plan_route((1, 5), (9.75, 5), BOUNDS, [], clearance=0.5)


def test_route_cannot_pass_diagonally_between_touching_corners():
    obstacles = [(0, 5, 5, 10), (5, 0, 10, 5)]
    with pytest.raises(ValueError, match="unreachable"):
        plan_route((2, 2), (8, 8), BOUNDS, obstacles)


def test_route_cannot_pass_through_full_width_obstacle():
    with pytest.raises(ValueError, match="unreachable"):
        plan_route((2, 5), (8, 5), BOUNDS, [(4, -1, 6, 11)])


def test_route_can_use_a_representable_passage_between_obstacles():
    start, destination = (1, 3), (9, 7)
    lower_top = math.nextafter(5, -math.inf)
    upper_bottom = math.nextafter(5, math.inf)
    route = plan_route(start, destination, BOUNDS, [(4, 0, 6, lower_top), (4, upper_bottom, 6, 10)])

    assert route[0] == start and route[-1] == destination
    assert len(route) == 4
    assert [point[1] for point in route[1:-1]] == [5, 5]


def test_route_stays_at_its_valid_current_location():
    assert plan_route((2, 5), (2, 5), BOUNDS, []) == [(2, 5)]


@pytest.mark.parametrize(
    "start,bounds,obstacles,clearance",
    [
        ((math.nan, 5), BOUNDS, [], 0),
        ((1, 5), (0, 0, math.inf, 10), [], 0),
        ((1, 5), (0, 0, 0, 10), [], 0),
        ((1, 5), BOUNDS, [(2, 2, 1, 3)], 0),
        ((1, 5), BOUNDS, [(2, 2, 2)], 0),
        ((1, 5), BOUNDS, [], -1),
        ((1, 5), BOUNDS, [], math.nan),
        ((1, 5), BOUNDS, [], 5.5),
    ],
)
def test_nonfinite_or_invalid_geometry_is_rejected(start, bounds, obstacles, clearance):
    with pytest.raises(ValueError):
        plan_route(start, (8, 5), bounds, obstacles, clearance)


def test_excessive_obstacle_count_is_rejected():
    with pytest.raises(ValueError, match="obstacles"):
        plan_route((1, 5), (8, 5), BOUNDS, [(2, 2, 3, 3)] * 257)


def test_approach_stops_at_configured_distance_toward_target():
    assert approach_position((3, 4), (0, 0), 2.5) == pytest.approx((1.5, 2))


def test_approach_from_inside_radius_can_move_to_the_requested_distance():
    assert approach_position((0.5, 0), (0, 0), 2) == pytest.approx((2, 0))


def test_approach_rejects_coincident_actor_locations():
    with pytest.raises(ValueError, match="coincident"):
        approach_position((2, 1), (2, 1), 1)


def test_conflict_checks_the_movement_between_interval_endpoints():
    assert segments_conflict((0, 0), (4, 0), (2, -2), (2, 2), 0)


def test_geometrically_crossing_paths_can_cross_at_different_times():
    assert not segments_conflict((0, 0), (4, 0), (2, -1), (2, 3), 0.25)


def test_parallel_movement_respects_combined_personal_space():
    assert segments_conflict((0, 0), (4, 0), (0, 0.5), (4, 0.5), 0.75)


@pytest.mark.parametrize(
    "start,end,clearance",
    [((1, 3), (-2, -6), 0), ((14, -17), (-16, 23), 1)],
)
def test_exact_contact_counts_as_conflict(start, end, clearance):
    assert segments_conflict(start, end, (0, 0), (0, 0), clearance)
