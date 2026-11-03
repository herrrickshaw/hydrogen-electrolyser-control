import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# The golden baseline was recorded with naive local timestamps in India Standard Time;
# pin the zone so the comparison does not depend on the machine (CI runs in UTC).
os.environ["TZ"] = "Asia/Kolkata"
if hasattr(time, "tzset"):
    time.tzset()
