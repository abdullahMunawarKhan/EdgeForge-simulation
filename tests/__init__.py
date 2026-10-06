"""
EdgeForge tests package.

Conventions:
  * Tests that need a running CARLA server must be decorated with
    ``@pytest.mark.carla`` so CI (and ``pytest -m "not carla"``) can skip them.
  * Tests that load a YOLO model or require GPU can be marked
    ``@pytest.mark.perception``.
"""
