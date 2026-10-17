
"""
Generate varied EdgeForge scenario configuration files.

The generated JSON preserves the structure of default_scenario.json.
Run from the project root:
    python -m edgeforge.scenarios.generated.generate
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path
from typing import Any

from edgeforge.scenarios.generator import CARLA_WEATHER_PRESETS, SUPPORTED_MAPS
from edgeforge.simulation.mock_client import MockCarlaClient


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_PATH = (
    PROJECT_ROOT / "edgeforge" / "scenarios" / "configs"
    / "default_scenario.json"
)
OUTPUT_DIR = Path(__file__).resolve().parent

SCENARIO_COUNT = 100
RANDOM_SEED = 42

CARLA_WEATHER_OPTIONS = tuple(CARLA_WEATHER_PRESETS)
MOCK_WEATHER_OPTIONS = tuple(
    name for name in CARLA_WEATHER_OPTIONS
    if name in MockCarlaClient.PRESET_WEATHER
)
MAP_OPTIONS = SUPPORTED_MAPS
SUPPORTED_BACKENDS = ("mock", "carla", "detect")

SCENARIO_TYPES = [
    "low_traffic",
    "urban_mixed_traffic",
    "dense_traffic",
    "pedestrian_heavy",
    "bicycle_heavy",
    "reduced_visibility",
    "sensor_comparison",
    "high_speed",
]


def load_template() -> dict[str, Any]:
    """Load the existing default scenario configuration."""
    with TEMPLATE_PATH.open("r", encoding="utf-8") as file:
        template = json.load(file)

    required_keys = {
        "name",
        "description",
        "version",
        "weather",
        "map",
        "duration_seconds",
        "traffic",
        "ego_vehicle",
        "sensors",
        "risk_analysis",
        "notes",
    }

    missing = required_keys - template.keys()
    if missing:
        raise ValueError(
            f"Default scenario template is missing keys: {sorted(missing)}"
        )

    return template


def build_scenario(
    template: dict[str, Any],
    index: int,
    rng: random.Random,
    backend: str = "mock",
) -> dict[str, Any]:
    """Create one reproducible scenario using the template structure."""
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unsupported backend '{backend}'. Choose one of {SUPPORTED_BACKENDS}."
        )

    scenario = copy.deepcopy(template)
    scenario_type = SCENARIO_TYPES[(index - 1) % len(SCENARIO_TYPES)]

    scenario["name"] = f"generated_{index:03d}_{scenario_type}"
    scenario["description"] = (
        f"Generated EdgeForge scenario #{index}: {scenario_type.replace('_', ' ')}"
    )
    weather_options = (
        CARLA_WEATHER_OPTIONS
        if backend == "carla"
        else MOCK_WEATHER_OPTIONS
    )
    scenario["weather"] = rng.choice(weather_options)
    scenario["map"] = rng.choice(MAP_OPTIONS)
    scenario["simulation"] = {"backend": backend}
    scenario["duration_seconds"] = rng.choice([30, 60, 90, 120])

    traffic = scenario["traffic"]
    ego = scenario["ego_vehicle"]
    sensors = scenario["sensors"]

    # Vary traffic based on the scenario category.
    if scenario_type == "low_traffic":
        traffic["vehicles"] = rng.randint(0, 5)
        traffic["pedestrians"] = rng.randint(0, 5)
        traffic["bicycles"] = rng.randint(0, 2)

    elif scenario_type == "dense_traffic":
        traffic["vehicles"] = rng.randint(15, 35)
        traffic["pedestrians"] = rng.randint(5, 20)
        traffic["bicycles"] = rng.randint(2, 10)

    elif scenario_type == "pedestrian_heavy":
        traffic["vehicles"] = rng.randint(3, 15)
        traffic["pedestrians"] = rng.randint(20, 40)
        traffic["bicycles"] = rng.randint(0, 8)

    elif scenario_type == "bicycle_heavy":
        traffic["vehicles"] = rng.randint(3, 15)
        traffic["pedestrians"] = rng.randint(2, 15)
        traffic["bicycles"] = rng.randint(10, 25)

    else:
        traffic["vehicles"] = rng.randint(3, 20)
        traffic["pedestrians"] = rng.randint(2, 20)
        traffic["bicycles"] = rng.randint(0, 10)

    # The speed_limit field follows the template's existing units/convention.
    ego["speed_limit"] = rng.choice([20, 30, 40, 50, 60, 80, 100])
    ego["spawn_point_index"] = rng.randint(0, 20)

    # Keep RGB camera enabled, varying its resolution and capture interval.
    camera = sensors["rgb_camera"]
    camera["enabled"] = True
    camera["width"], camera["height"] = rng.choice(
        [(640, 480), (1280, 720), (1920, 1080)]
    )
    camera["fov"] = rng.choice([70, 90, 110])
    camera["tick"] = rng.choice([0.05, 0.1, 0.2])

    # These modalities are still stubs in both current sensor adapters.
    for sensor_name in ("lidar", "imu", "gnss"):
        if sensor_name in sensors:
            sensors[sensor_name]["enabled"] = False

    # Keep event sensors and risk analysis enabled for evaluation.
    sensors["collision"]["enabled"] = True
    sensors["lane_invasion"]["enabled"] = True
    scenario["risk_analysis"]["enabled"] = True
    scenario["risk_analysis"]["threshold"] = rng.choice(
        [0.5, 0.6, 0.7, 0.8]
    )

    scenario["notes"] = [
        f"Scenario category: {scenario_type}",
        "Generated from default_scenario.json.",
        f"Generated for the {backend} backend.",
        "LiDAR, IMU, and GNSS remain disabled until their adapters are implemented.",
    ]

    return scenario


def generate_scenarios(
    count: int = SCENARIO_COUNT,
    seed: int = RANDOM_SEED,
    backend: str = "mock",
) -> list[Path]:
    """Generate scenario JSON files and return their paths."""
    if count < 1:
        raise ValueError("count must be at least 1")
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unsupported backend '{backend}'. Choose one of {SUPPORTED_BACKENDS}."
        )

    template = load_template()
    rng = random.Random(seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    generated_paths: list[Path] = []

    for index in range(1, count + 1):
        scenario = build_scenario(template, index, rng, backend=backend)
        output_path = OUTPUT_DIR / f"scenario_{index:03d}.json"

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(scenario, file, indent=2)
            file.write("\n")

        # Verify that the written file is valid JSON and preserves the schema.
        with output_path.open("r", encoding="utf-8") as file:
            saved_scenario = json.load(file)

        if saved_scenario.keys() != template.keys() | {"simulation"}:
            raise ValueError(f"Unexpected schema in {output_path.name}")

        generated_paths.append(output_path)

    print(f"Generated {len(generated_paths)} scenarios in: {OUTPUT_DIR}")
    print(f"Template used: {TEMPLATE_PATH}")
    return generated_paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate EdgeForge scenarios.")
    parser.add_argument("--count", type=int, default=SCENARIO_COUNT)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument(
        "--backend",
        choices=SUPPORTED_BACKENDS,
        default="mock",
        help="Backend to target; 'detect' uses only options supported by both.",
    )
    args = parser.parse_args()
    generate_scenarios(count=args.count, seed=args.seed, backend=args.backend)
