"""Prepare native MicroPython smoke tests of the actual single-file release.

    python build/micro_smoke.py
    python build/micro_smoke.py --run /path/to/micropython --heap 512000

This is not an EVO emulator: native object sizes, recursion limits, graphics and
keyboard behavior differ. In particular a 64-bit Unix build cannot establish the
calculator's heap requirements. Shims allocate no framebuffer or draw transcript.
Without --run this command only writes files and prints reproducible commands.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]

GRAPHICS = '''# Minimal native-MicroPython smoke shim; no framebuffer or transcript.
FONT = 0
ERROR = None
def noop(*args):
    pass
setColor = noop
fillRect = noop
drawLine = noop
def setFont(font):
    global FONT
    FONT = font
def string_size(text):
    return (len(text) * (6 if FONT else 8), 12 if FONT else 18)
def drawString(text, x, y):
    global ERROR
    low = text.lower()
    if ERROR is None:
        for bad in ('internal error', 'display error', 'out of memory',
                    'expression too complex', 'interrupted'):
            if bad in low:
                ERROR = text
                break
'''

SYSTEM = '''# Replay 2+3 ENTER, then 2nd MODE; probe pages always receive ENTER.
import gc
KEYS = (93, 95, 94, 105, 21, 22)
POS = 0
PROBE = False
class ScriptExhausted(BaseException):
    pass
def escape():
    return False
def get_key():
    return 0
def wait_key():
    global POS
    if PROBE:
        return 105
    if POS == 0 or POS == 4:
        gc.collect()
        print('heap %s: %d' % ('boot' if POS == 0 else 'result', gc.mem_free()))
    if POS >= len(KEYS):
        raise ScriptExhausted('UI did not quit after 2nd MODE')
    key = KEYS[POS]
    POS += 1
    return key
'''

UI = '''# Import the unchanged release and run its real module-level event loop.
import gc
import ti_system as TS
import ti_graphics as G
gc.collect()
print('Native MicroPython smoke; not an EVO emulator')
print('heap initial: %d' % gc.mem_free())
import CASEVO
assert TS.POS == len(TS.KEYS), 'key replay did not finish'
assert G.ERROR is None, G.ERROR
assert CASEVO.R[{ans}] == '5', ('wrong answer', CASEVO.R[{ans}])
assert CASEVO.U[{status}] == '', ('UI status', CASEVO.U[{status}])
assert len(CASEVO.R[{hist}]) == 1, 'expected one evaluated input'
assert CASEVO.R[{hist}][0][2] == 'ans', CASEVO.R[{hist}][0]
print('UI PASS: 2+3 = 5; normal quit')
'''

PROBE = '''# Import the unchanged self-contained release probe; auto-advance pages.
import gc
import ti_system as TS
TS.PROBE = True
gc.collect()
print('Native MicroPython smoke; not an EVO emulator')
print('heap initial: %d' % gc.mem_free())
import CVTEST
gc.collect()
print('heap final: %d' % gc.mem_free())
assert CVTEST.TOTAL == 55, ('unexpected probe count', CVTEST.TOTAL)
assert CVTEST.PASSED == CVTEST.TOTAL, ('failed probe cases', CVTEST.FAILURES)
assert not CVTEST.FAILURES, CVTEST.FAILURES
assert len(CVTEST.RESULTS) == CVTEST.TOTAL, 'incomplete probe'
for row in CVTEST.RESULTS:
    assert row[1], ('failed probe row', row)
for depth, passed in CVTEST.DEPTHS:
    assert passed, ('failed native depth probe', depth)
for name, record in CVTEST.ENGINE_MATH:
    assert 'internal error' not in record[1].lower(), (name, record)
print('PROBE PASS: 55/55')
'''


def prepare(dist, output):
    """Copy immutable release bytes and validate every generated script's syntax."""
    dist, output = Path(dist).resolve(), Path(output).resolve()
    if output == dist:
        raise ValueError('smoke output must differ from the release directory')
    paths = [dist / name for name in ('CASEVO.py', 'CVTEST.py', 'release.json')]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(str(path) + '; run python build/release.py first')
    meta = json.loads(paths[2].read_text('ascii'))
    names = meta['names']
    scripts = {
        'ti_graphics.py': GRAPHICS,
        'ti_system.py': SYSTEM,
        'ui.py': UI.format(ans=repr(names.get('ANS', 'ANS')),
                           status=repr(names.get('STATUS', 'STATUS')),
                           hist=repr(names.get('HIST', 'HIST'))),
        'probe.py': PROBE,
    }
    for name, source in scripts.items():
        ast.parse(source, filename=name, feature_version=(3, 4))
        compile(source, name, 'exec')
    output.mkdir(parents=True, exist_ok=True)
    for path in paths[:2]:
        target = output / path.name
        shutil.copyfile(path, target)
        assert target.read_bytes() == path.read_bytes()
    for name, source in scripts.items():
        (output / name).write_text(source, encoding='ascii', newline='\n')
    hashes = []
    for name in ('CASEVO.py', 'CVTEST.py'):
        hashes.append(hashlib.sha256((output / name).read_bytes()).hexdigest() + '  ' + name)
    (output / 'SHA256SUMS').write_text('\n'.join(hashes) + '\n', encoding='ascii', newline='\n')
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--output', type=Path, help='default: DIST/micro-smoke')
    parser.add_argument('--run', metavar='MICROPYTHON', help='explicitly run this native executable')
    parser.add_argument('--heap', type=int, default=512000,
                        help='native MicroPython heap bytes (default 512000 = 500 KiB)')
    parser.add_argument('--suite', choices=('all', 'ui', 'probe'), default='all')
    args = parser.parse_args(argv)
    if args.heap <= 0:
        parser.error('--heap must be a positive byte count')
    output = prepare(args.dist, args.output or args.dist / 'micro-smoke')
    print('Prepared ' + str(output))
    print('Not an EVO emulator; native object sizes and limits differ, especially on 64-bit hosts.')
    print('No framebuffer is allocated. Each script runs in its own process.')
    scripts = ('ui.py', 'probe.py') if args.suite == 'all' else (args.suite + '.py',)
    executable = args.run or 'micropython'
    if args.run and Path(executable).is_file():
        executable = str(Path(executable).resolve())
    print('From the generated directory, run:')
    for script in scripts:
        command = [executable, '-X', 'heapsize=' + str(args.heap), script]
        print('  ' + shlex.join(command), flush=True)
        if args.run:
            subprocess.run(command, cwd=output, check=True)


if __name__ == '__main__':
    main()
