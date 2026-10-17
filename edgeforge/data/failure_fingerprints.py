"""Canonical failure signatures shared by validation and benchmark workflows."""

from __future__ import annotations

from typing import Any, Mapping


def compute_failure_signature(
    failure: Any,
    scenario_conditions: Mapping[str, Any] | None = None,
) -> str:
    """Build the stable condition-binned signature used to deduplicate failures."""
    if isinstance(failure, Mapping):
        failure_type = failure.get("failure_type", "unknown_type")
        object_class = failure.get("object_class") or "unknown_class"
        severity = failure.get("severity", "medium")
        embedded_conditions = failure.get("scenario_conditions") or {}
    else:
        failure_type = getattr(failure, "failure_type", "unknown_type")
        object_class = getattr(failure, "object_class", None) or "unknown_class"
        severity = getattr(failure, "severity", "medium")
        embedded_conditions = getattr(failure, "scenario_conditions", {}) or {}

    conditions = (
        scenario_conditions
        if scenario_conditions is not None
        else embedded_conditions
    )
    weather = conditions.get("weather", {})
    if isinstance(weather, str) or (
        isinstance(weather, Mapping) and isinstance(weather.get("preset"), str)
    ):
        from edgeforge.scenarios.generator import CARLA_WEATHER_PRESETS

        preset_name = weather if isinstance(weather, str) else weather["preset"]
        preset_values = CARLA_WEATHER_PRESETS.get(preset_name, {})
        if isinstance(weather, Mapping):
            weather = {**preset_values, **{k: v for k, v in weather.items() if k != "preset"}}
        else:
            weather = preset_values

    if isinstance(weather, Mapping):
        fog = float(weather.get("fog_density", 0.0))
        precipitation = float(weather.get("precipitation", 0.0))
        sun_altitude = float(weather.get("sun_altitude_angle", 60.0))
    else:
        fog, precipitation, sun_altitude = 0.0, 0.0, 60.0

    if fog < 20.0:
        fog_bin = "fog_clear"
    elif fog <= 60.0:
        fog_bin = "fog_mod"
    else:
        fog_bin = "fog_dense"

    if precipitation < 10.0:
        rain_bin = "dry"
    elif precipitation <= 50.0:
        rain_bin = "light_rain"
    else:
        rain_bin = "heavy_rain"

    if sun_altitude < 0.0:
        sun_bin = "night"
    elif sun_altitude <= 25.0:
        sun_bin = "low_sun"
    else:
        sun_bin = "day"

    return (
        f"{failure_type}:{object_class}:{severity}:"
        f"{fog_bin}_{rain_bin}_{sun_bin}"
    )
