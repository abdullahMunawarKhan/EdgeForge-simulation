"""Run from the EdgeForge-simulation folder:
       python -m edgeforge.config.check_settings"""
import os

from pydantic import ValidationError

from edgeforge.config.settings import Settings


def fresh():
    """Build a new Settings, ignoring any .env file on your computer."""
    return Settings(_env_file=None)


def must_fail(fn, label):
    try:
        fn()
    except ValidationError:
        print(f"  OK  rejected: {label}")
    else:
        raise AssertionError(f"should have rejected: {label}")


# 1. defaults
s = fresh()
assert (s.LIDAR_CHANNELS, s.LIDAR_POINTS_PER_SECOND, s.LIDAR_RANGE_M) == (32, 56000, 10.0)
assert (s.YOLO_MODEL_PATH, s.YOLO_NMS_IOU, s.YOLO_DEVICE) == ("yolov8n.pt", 0.7, "cpu")
assert (s.LOG_DIR, s.RUN_DIR, s.METRICS_FORMAT) == ("logs", "runs", "csv")
assert s.RISK_OBJECT_WEIGHTS == {"pedestrian": 1.5, "bicycle": 1.2, "car": 1.0}
assert s.CAMERA_FOV == 90            # old setting still there
print("  OK  defaults + old settings intact")

# 2. environment override
os.environ["YOLO_DEVICE"] = "cuda"
os.environ["LIDAR_CHANNELS"] = "64"
assert fresh().YOLO_DEVICE == "cuda" and fresh().LIDAR_CHANNELS == 64
del os.environ["YOLO_DEVICE"], os.environ["LIDAR_CHANNELS"]
assert fresh().YOLO_DEVICE == "cpu"
print("  OK  env override")

# 3. invalid values must be rejected
must_fail(lambda: Settings(_env_file=None, LIDAR_CHANNELS=0), "channels = 0")
must_fail(lambda: Settings(_env_file=None, YOLO_DEVICE="tpu"), "device tpu")
must_fail(lambda: Settings(_env_file=None, YOLO_NMS_IOU=1.5), "nms_iou 1.5")
must_fail(lambda: Settings(_env_file=None, METRICS_FORMAT="xlsx"), "format xlsx")
must_fail(lambda: Settings(_env_file=None, RISK_OBJECT_WEIGHTS={"car": -1}), "negative weight")
print("ALL SETTINGS CHECKS PASSED")