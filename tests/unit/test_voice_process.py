import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from engine.voice.process import run_worker


def test_worker_capture_and_timeout(tmp_path):
    result = run_worker([sys.executable, '-c', 'import sys; print(sys.stdin.read())'], 'payload', timeout=5, env=os.environ.copy())
    assert result.returncode == 0 and result.stdout.strip() == 'payload'
    script = tmp_path / 'descendant.py'
    marker = tmp_path / 'heartbeat'
    script.write_text('import time\nfrom pathlib import Path\np=Path(' + repr(str(marker)) + ')\n'
                      'for i in range(300):\n p.write_text(str(i))\n time.sleep(.1)\n')
    parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,' + repr(str(script)) + ']); time.sleep(30)'
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_worker([sys.executable, '-c', parent], '', timeout=1, env=os.environ.copy())
    assert time.monotonic() - start < 5
    assert marker.is_file()
    last = marker.read_text()
    time.sleep(.3)
    assert marker.read_text() == last
