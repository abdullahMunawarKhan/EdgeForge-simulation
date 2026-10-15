"""Run from the EdgeForge-simulation folder:
       python -m edgeforge.utils.check_logger"""
import json
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum

from edgeforge.utils import logger as lg


class MockLevel(Enum):
    HIGH = "HIGH"


@dataclass
class MockEvent:
    type: str
    severity: str
    timestamp: float
    message: str = ""


@dataclass
class MockRisk:
    score: float
    level: MockLevel
    reason: str = ""
    top_objects: list = field(default_factory=list)


class Incomplete:      # has none of the expected fields
    pass


tmp = tempfile.mkdtemp()
lg.setup_file_sinks(tmp, rotation="2 KB", retention=2)
lg.setup_file_sinks(tmp)                       # second call must do nothing
assert len(lg._FILE_SINK_IDS) == 2
print("  OK  sinks set up once")

log = lg.get_logger("check")
jsonl_path = os.path.join(tmp, "edgeforge.jsonl")

# 1. helpers: valid, empty (None), incomplete
ev = MockEvent("collision", "critical", 12.4, "Hit pedestrian")
risk = MockRisk(0.72, MockLevel.HIGH, "Pedestrian at 5.1 m", [{"type": "pedestrian", "share": 0.41}])
assert lg.event_to_log_dict(None)["error"] and lg.risk_to_log_dict(None)["error"]
assert lg.event_to_log_dict(Incomplete())["type"] == "unknown"
assert lg.risk_to_log_dict(Incomplete())["top_objects"] == []
print("  OK  None and incomplete objects handled")

# 2. JSONL content
log.bind(data=lg.event_to_log_dict(ev)).info("event")
log.bind(data=lg.risk_to_log_dict(risk, tick=1204)).info("risk")
log.info("plain message, no data")
rows = [json.loads(line) for line in open(jsonl_path, encoding="utf-8")]
assert len(rows) == 3, rows
assert rows[1]["data"]["level"] == "HIGH" and rows[1]["data"]["tick"] == 1204
print("  OK  JSONL has 3 valid lines")

# 3. simulated 60 s run: 600 ticks at 10 per second
for tick in range(600):
    log.bind(data=lg.risk_to_log_dict(MockRisk(tick / 600, MockLevel.HIGH, "ok"), tick=tick)).info("tick")
rows = [json.loads(line) for line in open(jsonl_path, encoding="utf-8")]   # every line must parse
ticks = [r for r in rows if r["message"] == "tick"]
assert len(ticks) == 600 and ticks[-1]["data"]["tick"] == 599
print("  OK  60 s run: 600 valid tick lines")

# 4. rotation: write lots of text and expect more than one .log file
for i in range(300):
    log.info("filler line number {} to make the file grow", i)
log_files = [f for f in os.listdir(tmp) if f.startswith("edgeforge") and f.endswith(".log")]
assert len(log_files) >= 2, log_files
print("  OK  rotation created", len(log_files), "log files")

lg.remove_file_sinks()
print("ALL LOGGER CHECKS PASSED")