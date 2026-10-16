"""EdgeForge scenario generation, configurations, and runner integration."""

__all__ = [
    "ScenarioGenerator",
    "ScenarioCandidate",
    "RankedScenario",
    "ScoreBreakdown",
    "generate_and_rank_scenarios",
    "RandomScenarioGenerator",
    "ExecutionStatus",
    "ExecutionResult",
    "ScenarioExecutionManager",
    "validate_scenario_config",
    "TestingStrategyBenchmark",
    "compute_failure_signature",
    "PerRunRecord",
    "StrategyBenchmarkMetrics",
]


def __getattr__(name: str):
    if name in {
        "ScenarioGenerator",
        "ScenarioCandidate",
        "RankedScenario",
        "ScoreBreakdown",
        "generate_and_rank_scenarios",
        "RandomScenarioGenerator",
    }:
        import edgeforge.scenarios.generator as _generator

        return getattr(_generator, name)

    if name in {
        "ExecutionStatus",
        "ExecutionResult",
        "ScenarioExecutionManager",
        "validate_scenario_config",
    }:
        import edgeforge.scenarios.executor as _executor

        return getattr(_executor, name)

    if name in {
        "TestingStrategyBenchmark",
        "compute_failure_signature",
        "PerRunRecord",
        "StrategyBenchmarkMetrics",
    }:
        import edgeforge.scenarios.benchmark as _benchmark

        return getattr(_benchmark, name)

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
