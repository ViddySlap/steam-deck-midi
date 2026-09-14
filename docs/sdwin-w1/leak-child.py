import os
import sys
import time
from pathlib import Path
root = Path(sys.argv[1])
(root / 'leak-child.pid').write_text(str(os.getpid()), encoding='ascii')
while not (root / 'leak-stop').exists():
    time.sleep(0.05)
