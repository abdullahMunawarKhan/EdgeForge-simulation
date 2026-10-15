"""
CARLA-specific simulation layer for EdgeForge.

All code that imports and talks directly to the CARLA Python API lives
in this package.  The rest of EdgeForge (perception / analysis / config /
data) must NOT depend on carla – that way they remain testable without a
running simulator.

Currently exposed test scripts:
  - camera_test.py       : Spawns a vehicle + RGB camera and streams frames.
  - spawn_vehicle.py     : Basic vehicle spawning smoke test.
  - test_connection.py   : Minimal CARLA connection health check.

TODO:
  * carla_world.py       : Managed CARLA world + synchronous mode wrapper.
  * vehicle_controller.py: Ego-vehicle control interface (manual / autopilot / agent).
  * sensor_manager.py    : Spawn + configure sensors and pipe data to the perception stack.
  * scenario_runner.py   : Load scenario configs and orchestrate traffic, events, checks.
  * data_recorder.py     : Record sensor data + ground-truth for later training/analysis.
"""

__all__: list = []
