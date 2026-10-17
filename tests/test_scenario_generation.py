from __future__ import annotations

import random

import pytest

from edgeforge.scenarios.executor import validate_scenario_config
from edgeforge.scenarios.generated import generate
from edgeforge.scenarios.generator import CARLA_WEATHER_PRESETS, SUPPORTED_MAPS
from edgeforge.simulation.mock_client import MockCarlaClient


@pytest.mark.parametrize("backend", ["mock", "carla", "detect"])
def test_generated_scenarios_use_backend_supported_options(backend: str) -> None:
    template = generate.load_template()
    weather_options = (
        set(CARLA_WEATHER_PRESETS)
        if backend == "carla"
        else set(CARLA_WEATHER_PRESETS).intersection(
            MockCarlaClient.PRESET_WEATHER
        )
    )

    for index in range(1, len(generate.SCENARIO_TYPES) + 1):
        scenario = generate.build_scenario(
            template,
            index,
            random.Random(index),
            backend=backend,
        )

        assert scenario["simulation"] == {"backend": backend}
        assert scenario["weather"] in weather_options
        assert scenario["map"] in SUPPORTED_MAPS
        assert scenario["sensors"]["rgb_camera"]["enabled"] is True
        assert scenario["sensors"]["collision"]["enabled"] is True
        assert scenario["sensors"]["lane_invasion"]["enabled"] is True
        assert all(
            not scenario["sensors"][name]["enabled"]
            for name in ("lidar", "imu", "gnss")
        )
        is_valid, errors, normalized = validate_scenario_config(scenario)
        assert is_valid, errors
        assert normalized["simulation"]["backend"] == backend


def test_generated_scenarios_are_reproducible_and_selectable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(generate, "OUTPUT_DIR", tmp_path)

    paths = generate.generate_scenarios(count=2, seed=13, backend="mock")
    first_contents = [path.read_text(encoding="utf-8") for path in paths]

    generate.generate_scenarios(count=2, seed=13, backend="mock")

    assert first_contents == [
        path.read_text(encoding="utf-8") for path in paths
    ]
    assert all('"backend": "mock"' in content for content in first_contents)


def test_generated_scenario_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="Unsupported backend"):
        generate.build_scenario(
            generate.load_template(),
            1,
            random.Random(1),
            backend="gpu",
        )
