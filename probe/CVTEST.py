# CVTEST: transfer this ASCII file with ALL bundled CV*.py files to the EVO.
# Run CVTEST from the Python app. Photograph every page; ENTER continues.
# CLEAR at a page prompt stops. Send the pages and final PASS count back.
# This tests the real engine, not desktop shims. Heap -1 means unavailable.
# Only bounded 3/6/8-frame probes run here; risky 9/10-frame stress is PROBE6.
import gc
import math
import time
import ti_system as TS
import CVNODE as K
import CVALG as A
import CVPARSE as P
import CVPRINT as PR
import CVRUN as R

P.SESS = R
MEM = getattr(gc, 'mem_free', None)
if MEM is not None:
    K.MEMFREE = MEM
    R.MEMFREE = MEM
K.ESC = getattr(TS, 'escape', None)
R.BUSY = None
CLOCK = getattr(time, 'ticks_ms', None)
MILLISECONDS = CLOCK is not None
if CLOCK is None:
    CLOCK = getattr(time, 'monotonic', None) or getattr(time, 'time', None)
DIFF = getattr(time, 'ticks_diff', None)
if 'PAUSE' not in globals():
    PAUSE = MEM is not None
PAGE = 1
LINES = 0
PASSED = 0
RESULTS = []
FAILURES = []
DEPTHS = []
MATH_RESULTS = []
ENGINE_MATH = []


def out(s):
    global PAGE, LINES
    print(str(s)[:30])
    LINES += 1
    if LINES == 8:
        print('-- p%d: screenshot, key --' % PAGE)
        if PAUSE and TS.wait_key() == 45:
            raise KeyboardInterrupt()
        PAGE += 1
        LINES = 0


def check(record, mode, expected):
    if mode == 'msg':
        return record[0] == 'msg' and expected in record[1]
    if record[0] != 'ans':
        return False
    if mode == 'text':
        return record[1] == expected
    try:
        value = float(record[2] if record[2] is not None else record[1])
        return abs(value - expected) <= 2e-8 * (1 + abs(expected))
    except (ValueError, TypeError):
        return False


# command, comparison, expected, angle mode (0 radians, 1 degrees).
CASES = (
    ('1/3+1/6', 'text', '1/2', 0),
    ('(1+i)*(1-i)', 'text', '2', 0),
    ('i^2', 'text', '-1', 0),
    ('sqrt(72)', 'num', math.sqrt(72), 0),
    ('sqrt(8/27)', 'num', math.sqrt(8/27), 0),
    ('surd(-8,3)', 'text', '-2', 0),
    ('log(8,2)', 'text', '3', 0),
    ('cos(pi/3)', 'text', '1/2', 0),
    ('sin(pi/6)', 'text', '1/2', 0),
    ('simplify(sin(x)^2+cos(x)^2)', 'text', '1', 0),
    ('expand((x+1)^3)', 'text', 'x^3+3*x^2+3*x+1', 0),
    ('together((x^2-1)/(x-1))', 'text', 'x+1', 0),
    ('factor(360)', 'text', '2^3*3^2*5', 0),
    ('solve(x^2-5*x+6,x)', 'text', 'x=2,x=3', 0),
    ('solve(2^x=8,x)', 'text', 'x=3', 0),
    ('solve(x^2+1,x)', 'msg', 'no solution', 0),
    ('sqrt(x^2)', 'text', 'abs(x)', 0),
    ('approx(1/7)', 'num', 1/7, 0),
    ('diff(x^3,x)', 'text', '3*x^2', 0),
    ('diff(sin(x),x)', 'text', 'cos(x)', 0),
    ('diff(x^3,x,2)', 'text', '6*x', 0),
    ('diff(ln(x),x)', 'text', '1/x', 0),
    ('diff(integrate(sin(t^2),t,0,x^2),x)', 'text', '2*x*sin(x^4)', 0),
    ('grad(x*y,[x,y])', 'text', '[y,x]', 0),
    ('limit(sin(x)/x,x,0)', 'text', '1', 0),
    ('limit((1-cos(x))/x^2,x,0)', 'text', '1/2', 0),
    ('limit(x*ln(x),x,0,1)', 'text', '0', 0),
    ('limit((1+1/x)^x,x,oo)', 'num', math.e, 0),
    ('limit(x^3/exp(x),x,oo)', 'text', '0', 0),
    ('limit(sqrt(x^2+x)-x,x,oo)', 'text', '1/2', 0),
    ('limit(1/x,x,0)', 'msg', 'does not exist', 0),
    ('limit(sin(1/x),x,0)', 'msg', 'oscillates', 0),
    ('integrate(x^2,x,0,1)', 'num', 1/3, 0),
    ('integrate(sin(x),x,0,pi)', 'text', '2', 0),
    ('integrate(1/(2+cos(x)),x,0,2*pi)', 'num', 2*math.pi/math.sqrt(3), 0),
    ('integrate(sqrt(1-x^2),x,0,1)', 'num', math.pi/4, 0),
    ('integrate(exp(x^2),x,0,1)', 'num', 1.4626517459071816, 0),
    ('integrate(1/x^2,x,1,oo)', 'text', '1', 0),
    ('integrate(1/sqrt(x),x,0,1)', 'text', '2', 0),
    ('integrate(exp(-x),x,0,oo)', 'text', '1', 0),
    ('integrate(1/x,x,1,oo)', 'msg', 'diverges', 0),
    ('integrate(1/x^2,x,-1,1)', 'msg', 'diverges', 0),
    ('sum(k^2,k,1,10)', 'text', '385', 0),
    ('sum(1/(k*(k+1)),k,1,oo)', 'text', '1', 0),
    ('sum(1/k^2,k,1,oo)', 'num', math.pi**2/6, 0),
    ('sum((-1)^k/k,k,1,oo)', 'num', -math.log(2), 0),
    ('riemann(x^2,x,0,1,4,mid)', 'num', 21/64, 0),
    ("desolve([y''+y=0,y(0)=1,y'(0)=0],y)", 'text', 'y=cos(x)', 0),
    ('integrate(integrate(x*y,y,0,x),x,0,1)', 'text', '1/8', 0),
    ('polararea(2*cos(t),t,0,pi)', 'num', math.pi, 0),
    ('paramarea(t-sin(t),1-cos(t),t,0,2*pi)', 'num', 3*math.pi, 0),
    ('arclen(x^(3/2),x,0,4)', 'num', 8*(10**1.5-1)/27, 0),
    ('taylor(sin(x),x=0,5)', 'text', 'x-x^3/6+x^5/120+O(x^6)', 0),
    ('sin(30)', 'text', '1/2', 1),
    ('integrate(sin(x),x,0,180)', 'num', 360/math.pi, 1),
)

# These bounded, nonrecursive chains do not invoke natives at their deepest level.
def d1():
    return 1
def d2():
    return d1()+1
def d3():
    return d2()+1
def d4():
    return d3()+1
def d5():
    return d4()+1
def d6():
    return d5()+1
def d7():
    return d6()+1
def d8():
    return d7()+1


out('CVTEST v1: real engine')
out('heap -1 = not available')
for depth, fn in ((3, d3), (6, d6), (8, d8)):
    try:
        ok = fn() == depth
    except RuntimeError:
        ok = False
    DEPTHS.append((depth, ok))
    out('depth %d: %s' % (depth, 'PASS' if ok else 'FAIL'))

# Report platform-native edge behavior without assuming CPython's exceptions.
for name, fn, arg in (('sin0', math.sin, 0), ('sqrt4', math.sqrt, 4),
                      ('asin2', math.asin, 2), ('log0', math.log, 0),
                      ('sqrt-1', math.sqrt, -1), ('exp1000', math.exp, 1000)):
    try:
        value = str(fn(arg))
    except Exception as error:
        value = type(error).__name__
    MATH_RESULTS.append((name, value))
    out('math ' + name + ': ' + value)

for name in ('inverse0', 'oddroot', 'overflow'):
    try:
        value = 0.0 ** -1 if name == 'inverse0' else (-8.0) ** (1/3) if name == 'oddroot' else 1e308 * 10
        value = str(value)
    except Exception as error:
        value = type(error).__name__
    MATH_RESULTS.append((name, value))
    out('math ' + name + ': ' + value)

# The same edges through the bundled parser, constructors and nrun/approx path.
for name, command in (('asin2', 'approx(asin(2))'), ('log0', 'approx(ln(0))'),
                      ('sqrt-1', 'approx(sqrt(-1))'), ('inverse0', 'approx(0^-1)'),
                      ('oddroot', 'approx((-8)^(1/3))'), ('overflow', 'approx(1E308*10)')):
    record = R.go(('eval', command))
    ENGINE_MATH.append((name, record))
    out('engine ' + name + ':')
    out(record[1])

TOTAL = len(CASES)
for index in range(TOTAL):
    command, mode, expected, deg = CASES[index]
    R.SET['deg'] = deg
    gc.collect()
    before = MEM() if MEM is not None else -1
    start = CLOCK() if CLOCK is not None else 0
    record = R.go(('eval', command))
    finish = CLOCK() if CLOCK is not None else 0
    elapsed = DIFF(finish, start) if MILLISECONDS and DIFF is not None else finish-start
    elapsed = int(elapsed if MILLISECONDS else elapsed*1000)
    after = MEM() if MEM is not None else -1
    passed = check(record, mode, expected) and K.NN == K.BASE
    RESULTS.append((index+1, passed, elapsed, before, after))
    if passed:
        PASSED += 1
    else:
        FAILURES.append((index+1, command, record))
    out('%02d %s %dms' % (index+1, 'PASS' if passed else 'FAIL', elapsed))
    out('heap %d -> %d' % (before, after))
    if not passed:
        out(command)
        out(record[1])
R.SET['deg'] = 0
out('CVTEST: %d/%d PASS' % (PASSED, TOTAL))
out('Send all pages incl. final.')
