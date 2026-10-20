"""Prepare native MicroPython smoke tests of the actual multi-file release.

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
import sys


ROOT = Path(__file__).resolve().parents[1]

GRAPHICS = '''# Minimal native-MicroPython smoke shim for ti_draw; no framebuffer or transcript.
# fill_rect raises like the device below width/height 2 (docs/notes/FASTBOOT.md).
ERROR = None
def get_screen_dim():
    return [319, 209]
def set_color(r, g, b):
    pass
def fill_rect(x, y, w, h):
    if w < 2 or h < 2:
        raise ValueError('tidrawException')
def draw_line(x1, y1, x2, y2):
    pass
def clear():
    pass
def draw_text(x, y, text):
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
import sys
# The runners execute with cwd set to this directory. Avoid interning the host
# checkout's absolute path once per imported page in the constrained heap.
sys.path[0]=''
KEYS = (93, 85, 94, 105, 21, 22)
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
import ti_draw as G
gc.collect()
print('Native MicroPython smoke; not an EVO emulator')
print('heap initial: %d' % gc.mem_free())
import CASEVO
assert TS.POS == len(TS.KEYS), 'key replay did not finish'
assert G.ERROR is None, G.ERROR
R = CASEVO.R
assert getattr(R, {ans}) == '5', ('wrong answer', getattr(R, {ans}))
assert len(getattr(R, {hist})) == 1, 'expected one evaluated input'
assert getattr(R, {hist})[0][2] == 'ans', getattr(R, {hist})[0]
print('UI PASS: 2+3 = 5; normal quit')
'''

# Typed through tests/support/keyscript.py, so the key stream follows the MathPrint editor
# (docs/notes/MATHPRINT.md 11.1): autoclosed calls, x^n boxes; tests/test_mathprint_keys.py
# checks that each command is typed back to the same text and answer.
UI_CASES = (
    ('2+3', '5'),
    ('integrate(1/(2+cos(x)),x,0,2*pi)', '2*sqrt(3)*pi/3'),
    ('integrate(integrate(x*y,y,0,x),x,0,1)', '1/8'),
    ('polararea(2*cos(t),t,0,pi)', 'pi'),
    ('paramarea(t-sin(t),1-cos(t),t,0,2*pi)', '3*pi'),
    ('arclen(x^(3/2),x,0,4)', '8*(10*sqrt(10)-1)/27'),
    ('2+3', '5'),
)


def calculus_ui(names):
    """Replay the heap-sensitive cases through real editing and result drawing."""
    sys.path.insert(0, str(ROOT / 'tests/support'))
    import keyscript
    script = ''.join(command + '{enter}' for command, _ in UI_CASES) + '{2nd,mode}'
    keys = tuple(keyscript.parse(script))
    assert all(type(key) is int for key in keys)
    return '''import ti_system as TS
import ti_draw as G
TS.KEYS={keys}
import CASEVO
assert TS.POS==len(TS.KEYS), 'key replay did not finish'
assert G.ERROR is None,G.ERROR
history=getattr(CASEVO.R,{hist})
expected={expected}
assert len(history)==len(expected),history
for row,want in zip(history,expected):
 assert row[2]=='ans' and row[1]==want,row
assert getattr(CASEVO.R,{ans})=='5'
print('UI CALCULUS PASS: 7 commands; normal quit')
'''.format(keys=repr(keys), hist=repr(names.get('HIST', 'HIST')),
           ans=repr(names.get('ANS', 'ANS')), expected=repr(tuple(value for _, value in UI_CASES)))

# MathPrint lines typed after a first result (docs/notes/MATHPRINT.md 0.8, 5.3): with the
# engine loaded, a 2D layout that runs out of memory frees the idle families and soft packs and
# tries again, so ordinary long lines stay 2D (ED1D false) at the documented minimum heap.
EDIT_LINES = (
    'sum((k^2+1)/(k^3+2k+1),k,1,10)+integrate(sqrt(x^2+1)/(x+1),x,0,1)+diff(x^3/(x^2+1),x)+1',
    '{frac}1{down}x^2{right}{right}+' * 6,
    'sum((k^2+1)/(k^3+2k+1),k,1,10)+integrate(sqrt(x^2+1)/(x+1),x,0,1)+diff(x^3/(x^2+1),x)+1'
    '+sqrt(x^2+1)/(x+2)+x^3',
)


def edit_ui(names):
    """Type each EDIT_LINES line after 2+3 ENTER and record (len(LINE), ED1D) before CLEAR."""
    sys.path.insert(0, str(ROOT / 'tests/support'))
    import keyscript
    keys = list(keyscript.parse('2+3{enter}'))
    watch = []
    for line in EDIT_LINES:
        keys.extend(keyscript.parse(line))
        watch.append(len(keys))
        keys.extend(keyscript.parse('{clear}'))
    keys.extend(keyscript.parse('{2nd,mode}'))
    assert all(type(key) is int for key in keys)
    return '''import sys
import ti_system as TS
import ti_draw as G
TS.KEYS={keys}
WATCH={watch}
STATES=[]
_wait=TS.wait_key
def wait():
    if TS.POS in WATCH:
        u=sys.modules['CASUI']
        STATES.append((len(getattr(u,{line})),getattr(u,{flat})))
    return _wait()
TS.wait_key=wait
import CASEVO
assert TS.POS==len(TS.KEYS), 'key replay did not finish'
assert G.ERROR is None,G.ERROR
assert len(STATES)==len(WATCH),STATES
for n,flat in STATES:
 assert n>=70 and not flat,('a long 2D line went 1D',STATES)
assert max(n for n,flat in STATES)>=120,STATES
assert getattr(CASEVO.R,{ans})=='5' and len(getattr(CASEVO.R,{hist}))==1
print('UI EDIT PASS: %d long 2D lines stay 2D; normal quit' % len(STATES))
'''.format(keys=repr(tuple(keys)), watch=repr(tuple(watch)),
           line=repr(names.get('LINE', 'LINE')), flat=repr(names.get('ED1D', 'ED1D')),
           ans=repr(names.get('ANS', 'ANS')), hist=repr(names.get('HIST', 'HIST')))

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

STARTUP = '''# Stop at CVTEST's first page, after the real resident engine loads.
import gc
import ti_system as TS
TS.wait_key=iter(()).__next__
try:
 import CVTEST
except StopIteration:
 gc.collect()
 print('STARTUP PASS: resident engine; %d bytes free' % gc.mem_free())
else:
 raise AssertionError('CVTEST did not reach its first diagnostic page')
'''


def prepare(dist, output, archive=None):
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
        'ti_draw.py': GRAPHICS,
        'ti_system.py': SYSTEM,
        'ui.py': UI.format(ans=repr(names.get('ANS', 'ANS')),
                           hist=repr(names.get('HIST', 'HIST'))),
        'probe.py': PROBE,
        'startup.py': STARTUP,
        'ui_calculus.py': calculus_ui(names),
        'ui_edit.py': edit_ui(names),
    }
    for name, source in scripts.items():
        ast.parse(source, filename=name, feature_version=(3, 4))
        compile(source, name, 'exec')
    output.mkdir(parents=True, exist_ok=True)
    files = {name: dist / name for name in meta['files']}
    if archive is not None:
        archive = Path(archive)
        manifest = json.loads((archive / 'archive.json').read_text('ascii'))
        if not manifest.get('runtimeCompilation') is False:
            raise ValueError('archive still requires runtime compilation')
        if {f['module'] + '.py' for f in manifest['files']} != set(files):
            raise ValueError('archive and release modules differ')
        files = {}
        for info in manifest['files']:
            name = info['name']
            if Path(name).name != name or Path(name).suffix not in ('.py', '.mpy'):
                raise ValueError('unsafe archive member: ' + name)
            path = archive / name
            data = path.read_bytes()
            if len(data) != info['bytes'] or hashlib.sha256(data).hexdigest() != info['sha256']:
                raise ValueError('archive checksum mismatch: ' + name)
            files[name] = path
            # A stale .py would silently shadow the bytecode under test.
            alternate = output / (info['module'] + ('.py' if name.endswith('.mpy') else '.mpy'))
            if alternate.is_file():
                alternate.unlink()
    for name, path in files.items():
        target = output / path.name
        shutil.copyfile(path, target)
        assert target.read_bytes() == path.read_bytes()
    for name, source in scripts.items():
        (output / name).write_text(source, encoding='ascii', newline='\n')
    hashes = []
    for name in sorted(files):
        hashes.append(hashlib.sha256((output / name).read_bytes()).hexdigest() + '  ' + name)
    (output / 'SHA256SUMS').write_text('\n'.join(hashes) + '\n', encoding='ascii', newline='\n')
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--output', type=Path, help='default: DIST/micro-smoke')
    parser.add_argument('--archive', type=Path, help='test actual MPY v5 archive files instead of source carriers')
    parser.add_argument('--run', metavar='MICROPYTHON', help='explicitly run this native executable')
    parser.add_argument('--heap', type=int, default=512000,
                        help='native MicroPython heap bytes (default 512000 = 500 KiB)')
    parser.add_argument('--suite', choices=('all', 'ui', 'ui_calculus', 'ui_edit', 'probe', 'startup'),
                        default='all')
    args = parser.parse_args(argv)
    if args.heap <= 0:
        parser.error('--heap must be a positive byte count')
    output = prepare(args.dist, args.output or args.dist / 'micro-smoke', args.archive)
    print('Prepared ' + str(output))
    print('Not an EVO emulator; native object sizes and limits differ, especially on 64-bit hosts.')
    print('No framebuffer is allocated. Each script runs in its own process.')
    scripts = (('ui.py', 'ui_calculus.py', 'ui_edit.py', 'probe.py') if args.suite == 'all' else
               (args.suite + '.py',))
    executable = args.run or 'micropython'
    if args.run and Path(executable).is_file():
        executable = str(Path(executable).resolve())
    print('From the generated directory, run:')
    for script in scripts:
        command = [executable, '-X', 'heapsize=' + str(args.heap), script]
        print('  ' + shlex.join(command), flush=True)
        if args.run:
            result = subprocess.run(command, cwd=output, capture_output=True, text=True)
            print(result.stdout, end='')
            print(result.stderr, end='', file=sys.stderr)
            result.check_returncode()
            marker = script[:-3].upper().replace('_', ' ') + ' PASS:'
            if marker not in result.stdout or 'Traceback (most recent call last)' in result.stdout + result.stderr:
                raise SystemExit('Native suite did not complete: ' + script)


if __name__ == '__main__':
    main()
