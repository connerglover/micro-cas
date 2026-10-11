"""Canonical command output is independent of Python dictionary/hash seed."""
import os
from pathlib import Path
import subprocess
import sys


def test_t1_hashseed_determinism():
    root = Path(__file__).resolve().parents[1]
    code = "import sys;sys.path[:0]=['src','tests/support'];import cascheck as C;C.fresh();print([C.answer(s) for s in ('factor(x^6-1)','expand((x+y+z)^3)','simplify(sin(x)^4-cos(x)^4)','solve(x^2-2,x)')])"
    outputs = []
    for seed in ('0', '17', '123456'):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        p = subprocess.run([sys.executable, '-c', code], cwd=root, env=env, text=True, capture_output=True, timeout=60)
        assert p.returncode == 0, p.stderr
        outputs.append(p.stdout)
    assert outputs[0] == outputs[1] == outputs[2]
