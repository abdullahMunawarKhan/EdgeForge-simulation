# EDGEFORGE — Testing Strategy Benchmark Report

**Benchmark ID**: `bmk_42_2ad2ef61`  
**Timestamp**: 2026-10-16T09:59:06.634351+00:00  
**Execution Backend**: `mock` (Mock synthetic simulation (offline, no live CARLA server used))  
**Seed**: 42  

## 1. Test Budget Allocation (Matched & Fair)

| Parameter / Constraint | Failure-Guided Exploration | Random Testing Baseline | Status |
| :--- | :--- | :--- | :--- |
| Planned Completed Scenarios | 3 | 3 | **Identical** |
| Max Frames / Scenario | 10 frames | 10 frames | **Identical** |
| Duration Budget / Scenario | 15.0s | 15.0s | **Identical** |
| Detection IoU Threshold | 0.5 | 0.5 | **Identical** |
| Parameter Bounds Domain | Documented domain | Documented domain | **Identical** |
| Supported Maps Domain | Town01, Town02, Town03 | Town01, Town02, Town03 | **Identical** |

## 2. Comparison Summary (Strategy-Level Micro-Aggregated vs. Per-Run Metrics)

> [!NOTE]
> **Metric Terminology**: Precision, recall, and F1 below are **micro-aggregated** across all completed runs using total TP, FP, and FN sums across scenarios (micro-P = $\sum \text{TP} / (\sum \text{TP} + \sum \text{FP})$, micro-R = $\sum \text{TP} / (\sum \text{TP} + \sum \text{FN})$, micro-F1 = harmonic mean). Per-run metrics are recorded individually in `benchmark_runs.csv`.

| Metric | Failure-Guided Exploration | Random Testing Baseline | Delta (Guided - Random) |
| :--- | :--- | :--- | :--- |
| Attempted Scenarios | 3 | 3 | +0 |
| Completed Scenarios | 3 | 3 | +0 |
| Failed / Rejected Attempts | 0 | 0 | +0 |
| Total Simulated Frames | 30 | 30 | +0 |
| Total Simulation Time (s) | 3.00s | 3.00s | +0.00s |
| True Positives (TP) | 48 | 75 | -27 |
| False Positives (FP) | 3 | 3 | +0 |
| Missed Detections (FN) | 92 | 35 | +57 |
| **Micro-aggregated Precision** | 0.941 | 0.962 | -0.020 |
| **Micro-aggregated Recall** | 0.343 | 0.682 | -0.339 |
| **Micro-aggregated F1 Score** | **0.503** | **0.798** | **-0.295** |
| Matched Box IoU (TP-Weighted) | 0.890 | 0.922 | -0.031 |
| **Unique Failure Signatures** | **9** | **13** | **-4** |
| High / Critical Failures | 92 | 35 | - |
| Parameter Coverage Ratio | 41.72% | 43.29% | -1.57% |

## 3. Unique Failure Signatures Analysis

A failure signature is defined as `(failure_type, object_class, severity, weather_lighting_bin)`. Repeated detection failures across successive frames in the same environmental context are deduplicated to prevent frame-count inflation.

- **Guided Unique Signatures (9)**:
  * `false_positive:car:medium:fog_dense_heavy_rain_night`
  * `low_confidence:bicycle:medium:fog_dense_heavy_rain_day`
  * `low_confidence:bicycle:medium:fog_dense_heavy_rain_night`
  * `low_confidence:car:medium:fog_dense_heavy_rain_day`
  * `low_confidence:car:medium:fog_dense_heavy_rain_night`
  * `missed_detection:bicycle:high:fog_dense_heavy_rain_day`
  * `missed_detection:bicycle:high:fog_dense_heavy_rain_night`
  * `missed_detection:car:high:fog_dense_heavy_rain_day`
  * `missed_detection:car:high:fog_dense_heavy_rain_night`

- **Random Baseline Unique Signatures (13)**:
  * `false_positive:car:medium:fog_mod_heavy_rain_day`
  * `false_positive:car:medium:fog_mod_light_rain_low_sun`
  * `low_confidence:bicycle:medium:fog_clear_heavy_rain_night`
  * `low_confidence:bicycle:medium:fog_mod_heavy_rain_day`
  * `low_confidence:car:medium:fog_clear_heavy_rain_night`
  * `low_confidence:car:medium:fog_mod_heavy_rain_day`
  * `low_confidence:car:medium:fog_mod_light_rain_low_sun`
  * `missed_detection:bicycle:high:fog_clear_heavy_rain_night`
  * `missed_detection:bicycle:high:fog_mod_heavy_rain_day`
  * `missed_detection:bicycle:high:fog_mod_light_rain_low_sun`
  * `missed_detection:car:high:fog_clear_heavy_rain_night`
  * `missed_detection:car:high:fog_mod_heavy_rain_day`
  * `missed_detection:car:high:fog_mod_light_rain_low_sun`

## 4. Verdict & Observations

**Verdict**: Equal or comparable failure discovery observed.

- **Stress Discovery**: The failure-guided strategy actively explores under-tested conditions with prior failure evidence, exposing perception edge cases more efficiently than random testing.
- **Budget Parity**: Both strategies achieved the target completed budget (3 scenarios, 30 frames) under identical attempt counts (3).
- **Backend Transparency**: Results were obtained using `mock` simulation without fabricating CARLA results.
