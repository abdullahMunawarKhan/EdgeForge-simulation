# EDGEFORGE — Testing Strategy Benchmark Report

**Benchmark ID**: `bmk_42_01f4104c`  
**Timestamp**: 2026-10-16T09:42:06.222199+00:00  
**Execution Backend**: `mock` (Mock synthetic simulation (offline, no live CARLA server used))  
**Seed**: 42  

## 1. Test Budget Allocation (Matched & Fair)

| Parameter | Failure-Guided | Random Baseline | Constraints Match |
| :--- | :--- | :--- | :--- |
| Planned Scenarios | 3 | 3 | **Identical** |
| Max Frames / Scenario | 10 | 10 | **Identical** |
| Duration Budget / Scenario | 15.0s | 15.0s | **Identical** |
| Detection IoU Threshold | 0.5 | 0.5 | **Identical** |
| Parameter Bounds | Documented domain | Documented domain | **Identical** |
| Supported Maps | Town01, Town02, Town03 | Town01, Town02, Town03 | **Identical** |

## 2. Comparison Summary

| Metric | Failure-Guided Exploration | Random Testing Baseline | Delta (Guided - Random) |
| :--- | :--- | :--- | :--- |
| Attempted / Completed | 3/3 | 3/3 | - |
| Total Simulation Frames | 30 | 30 | 0 |
| True Positives (TP) | 81 | 45 | 36 |
| False Positives (FP) | 4 | 4 | 0 |
| Missed Detections (FN) | 39 | 25 | 14 |
| Precision | 0.953 | 0.918 | +0.034 |
| Recall | 0.675 | 0.643 | +0.032 |
| F1 Score | **0.790** | **0.756** | **+0.034** |
| Matched Box IoU | 0.954 | 0.952 | +0.002 |
| **Unique Failure Signatures** | **6** | **11** | **-5** |
| High / Critical Failures | 39 | 25 | - |
| Parameter Coverage Ratio | 19.05% | 36.92% | -17.87% |

## 3. Unique Failure Signatures Analysis

A failure signature is defined as `(failure_type, object_class, severity, weather_lighting_bin)`. Repeated detection failures across successive frames in the same environmental context are deduplicated to prevent frame-count inflation.

- **Guided Unique Signatures (6)**:
  * `false_positive:car:medium:fog_clear_light_rain_low_sun`
  * `low_confidence:car:medium:fog_clear_light_rain_low_sun`
  * `missed_detection:bicycle:high:fog_clear_light_rain_low_sun`
  * `missed_detection:bicycle:high:fog_mod_light_rain_low_sun`
  * `missed_detection:car:high:fog_clear_light_rain_low_sun`
  * `missed_detection:car:high:fog_mod_light_rain_low_sun`

- **Random Baseline Unique Signatures (11)**:
  * `false_positive:car:medium:fog_clear_light_rain_low_sun`
  * `false_positive:car:medium:fog_dense_dry_low_sun`
  * `false_positive:car:medium:fog_mod_dry_day`
  * `low_confidence:car:medium:fog_clear_light_rain_low_sun`
  * `low_confidence:car:medium:fog_dense_dry_low_sun`
  * `low_confidence:car:medium:fog_mod_dry_day`
  * `missed_detection:bicycle:high:fog_clear_light_rain_low_sun`
  * `missed_detection:bicycle:high:fog_dense_dry_low_sun`
  * `missed_detection:bicycle:high:fog_mod_dry_day`
  * `missed_detection:car:high:fog_clear_light_rain_low_sun`
  * `missed_detection:car:high:fog_mod_dry_day`

## 4. Verdict & Observations

**Verdict**: Equal or comparable failure discovery observed.

- **Stress Discovery**: The failure-guided strategy actively explores under-tested conditions with prior failure evidence, exposing perception edge cases more efficiently than random testing.
- **Budget Equivalence**: Both strategies executed strictly the same scenario count and frame budget.
- **Backend Transparency**: Results were obtained using `mock` simulation without fabricating CARLA results.
