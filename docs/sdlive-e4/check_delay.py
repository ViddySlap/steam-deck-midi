"""Serial diagnostic of requested positive sleep versus deadline-based delay."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/showready'))
from timing_ab import sensitivity_delay

rows = []
for label, call in (('positive-sleep', lambda: time.sleep(.002)), ('deadline-yield', sensitivity_delay)):
    values = []
    for _ in range(20):
        start = time.perf_counter_ns()
        call()
        values.append((time.perf_counter_ns() - start) / 1e6)
    assert len(values) == 20 and min(values) >= 2
    rows.append({'method': label, 'milliseconds': values, 'min': min(values), 'max': max(values)})
result = {'command': [sys.executable, '-B', str(Path(__file__).resolve())],
          'qualification': 'DIAGNOSTIC; load unverified', 'results': rows}
(ROOT / 'docs/sdlive-e4/evidence/delay-probe.json').write_text(json.dumps(result, indent=2) + '\n', encoding='ascii')
print(json.dumps(rows))
