from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from edgeforge.simulation.clear_traffic import clear_traffic


class FakeActor:
    def __init__(self, actor_id: int) -> None:
        self.id = actor_id
        self.destroy = Mock(return_value=True)


class FakeActorList(list[FakeActor]):
    def filter(self, pattern: str) -> list[FakeActor]:
        return {
            "vehicle.*": [actor for actor in self if actor.id in (1, 2)],
            "controller.ai.walker": [actor for actor in self if actor.id == 3],
            "walker.pedestrian.*": [actor for actor in self if actor.id == 4],
        }[pattern]


def test_clear_traffic_preserves_lowest_id_vehicle_by_default() -> None:
    actors = [FakeActor(actor_id) for actor_id in range(1, 5)]
    world = SimpleNamespace(get_actors=lambda: FakeActorList(actors))

    clear_traffic(world)

    assert not actors[0].destroy.called
    assert actors[1].destroy.called
    assert actors[2].destroy.called
    assert actors[3].destroy.called


def test_clear_traffic_preserves_explicit_vehicle_id() -> None:
    actors = [FakeActor(actor_id) for actor_id in range(1, 5)]
    world = SimpleNamespace(get_actors=lambda: FakeActorList(actors))

    clear_traffic(world, keep_vehicle_id=2)

    assert actors[0].destroy.called
    assert not actors[1].destroy.called
    assert actors[2].destroy.called
    assert actors[3].destroy.called


def test_clear_traffic_rejects_unknown_preserved_vehicle() -> None:
    actors = [FakeActor(actor_id) for actor_id in range(1, 5)]
    world = SimpleNamespace(get_actors=lambda: FakeActorList(actors))

    with pytest.raises(ValueError, match="Vehicle actor 99 was not found"):
        clear_traffic(world, keep_vehicle_id=99)

    assert all(not actor.destroy.called for actor in actors)
