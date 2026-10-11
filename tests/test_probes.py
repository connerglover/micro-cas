"""Desktop dry runs of the device probes (M0.3, DESIGN.md Appendix B).

Each probe runs in a fresh interpreter as the device runs it
(`from NAME import *`), twice:

* with no `ti_*` modules (the desktop fallback path), and
* with small stub `ti_system`/`ti_graphics` modules written into the temp
  directory, so that the key, poll and drawing paths run too. The stub
  `wait_key` prints the marker `@K`, so the page length can be checked.

Every printed line must be at most 30 characters and every page (the lines
between two key waits) at most 9 lines. The probes must also stay inside the
device's Python 3.4 subset (no f-strings, annotations, ...) and be ASCII.
"""
import ast
import io
import os
import re
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE_DIR = ROOT / "probe"
PROBES = ("PROBE5", "PROBE6", "PROBE7", "PROBEK2", "PRBMEM")
MODULES = PROBES + ("PRBIMP",)
MAXW = 30          # characters per printed line
MAXPAGE = 9        # lines between two key waits (8 + the prompt)
PROMPT = re.compile(r"-- p\d+: screenshot, key --$")
DEVICE_MODULES = {"gc", "sys", "math", "time", "array", "collections",
                  "ti_system", "ti_graphics", "ti_draw"}

TI_SYSTEM_STUB = r'''
# wait_key replays STUB_KEYS (then 105, ENTER) and prints the marker @K.
# get_key returns STUB_GETKEY on every 40th call during the first STUB_HOLD
# seconds (default 1) after a wait_key: a key held down after a key press.
import os
import time
_KEYS = [int(k) for k in os.environ.get("STUB_KEYS", "").split(",") if k]
_GETKEY = int(os.environ.get("STUB_GETKEY", "0"))
_HOLD = float(os.environ.get("STUB_HOLD", "1"))
_c = [0, 0]
_t = [time.monotonic()]


def wait_key():
    print("@K")
    _t[0] = time.monotonic()
    if _KEYS:
        return _KEYS.pop(0)
    return 105


def get_key():
    _c[0] += 1
    if _GETKEY and _c[0] % 40 == 0 and time.monotonic() - _t[0] < _HOLD:
        return _GETKEY
    return 0


getKey = get_key


def escape():
    _c[1] += 1
    return _c[1] % 9 == 0


def disp_clr():
    print("@CLR")


def sleep(s):
    pass
'''

TI_GRAPHICS_STUB = r'''
# A 320x210 RGB565-like frame buffer. drawString draws a pattern per code
# point; the code points in _MISSING draw a hollow box (a "tofu" glyph).
import os
W, H = 320, 210
WHITE = (248, 252, 248)
_BASE = os.environ.get("STUB_BASELINE") == "1"
_fb = [[WHITE] * W for _ in range(H)]
_col = [(0, 0, 0)]
_font = [1]
_SIZES = {0: (6, 10), 1: (8, 14), 2: (10, 18)}
_MISSING = (0x222b, 0x4e00)


def _q(c):
    return (c[0] & 0xF8, c[1] & 0xFC, c[2] & 0xF8)


def setColor(*a):
    if len(a) == 3:
        _col[0] = _q(a)
    elif len(a) == 1 and isinstance(a[0], tuple) and len(a[0]) == 3:
        _col[0] = _q(a[0])
    else:
        raise TypeError("color")


def _put(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        _fb[y][x] = c


def setPixel(x, y, c=None):
    _put(x, y, _q(c) if c is not None else _col[0])


def getPixel(x, y):
    if 0 <= x < W and 0 <= y < H:
        return _fb[y][x]
    raise ValueError("off screen")


def fillRect(x, y, w, h):
    x0, x1 = max(0, x), min(W, x + w)
    if x1 > x0:
        for j in range(max(0, y), min(H, y + h)):
            _fb[j][x0:x1] = [_col[0]] * (x1 - x0)


def drawRect(x, y, w, h):
    for i in range(w):
        _put(x + i, y, _col[0])
        _put(x + i, y + h - 1, _col[0])
    for j in range(h):
        _put(x, y + j, _col[0])
        _put(x + w - 1, y + j, _col[0])


def drawLine(x1, y1, x2, y2):
    n = max(abs(x2 - x1), abs(y2 - y1), 1)
    for k in range(n + 1):
        _put(x1 + (x2 - x1) * k // n, y1 + (y2 - y1) * k // n, _col[0])


def setFont(n):
    if n not in _SIZES:
        raise ValueError("font")
    _font[0] = n


def string_size(s):
    w, h = _SIZES[_font[0]]
    return (w * len(s), h)


def drawString(s, x, y):
    w, h = _SIZES[_font[0]]
    top = y - h + 1 if _BASE else y
    for k, ch in enumerate(s):
        cp = ord(ch)
        x0 = x + k * w
        if cp in _MISSING:
            for i in range(w - 1):
                _put(x0 + i, top, _col[0])
                _put(x0 + i, top + h - 1, _col[0])
            for j in range(h):
                _put(x0, top + j, _col[0])
                _put(x0 + w - 2, top + j, _col[0])
            continue
        bits = (cp * 2654435761) & 0xFFFFFFFF
        for j in range(h):
            for i in range(w - 1):
                if (bits >> ((i * 7 + j * 3) % 32)) & 1:
                    _put(x0 + i, top + j, _col[0])


def cls():
    setColor(255, 255, 255)
    fillRect(0, 0, W, H)


def setPen(*a):
    pass
'''


# --------------------------------------------------------------------------
# helpers


def stand_in(lines):
    """Source of a stand-in for the generated PRBLnnn modules (M0.5)."""
    out = []
    k = 0
    while len(out) + 5 <= lines:
        out += ["def f%d(t, a):" % k, " r = 0", " for x in t:",
                "  r += x * a", " return r"]
        k += 1
    while len(out) < lines:
        out.append("N%d = %d" % (len(out), len(out)))
    return "\n".join(out) + "\n"


def run_probe(tmp, name, stubs, keys=(), getkey=0, prelude="", extra=None,
              env_extra=None, omit=()):
    """Run `from name import *` in a fresh interpreter in a copy of probe/.

    Returns (exit code, stdout lines, stderr)."""
    d = tmp / ("run_" + name)
    d.mkdir()
    for f in PROBE_DIR.iterdir():
        if f.suffix in (".py", ".mpy") and f.name not in omit:
            shutil.copy(f, d / f.name)
    if stubs:
        (d / "ti_system.py").write_text(TI_SYSTEM_STUB, encoding="ascii")
        (d / "ti_graphics.py").write_text(TI_GRAPHICS_STUB, encoding="ascii")
    for fname, src in (extra or {}).items():
        (d / fname).write_text(src, encoding="ascii")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "ascii"
    env["STUB_KEYS"] = ",".join(str(k) for k in keys)
    env["STUB_GETKEY"] = str(getkey)
    env.update(env_extra or {})
    code = ("import sys; sys.path.insert(0, %r)\n%s\nfrom %s import *\n"
            % (str(d), prelude, name))
    p = subprocess.run([sys.executable, "-c", code], cwd=str(d), env=env,
                       capture_output=True, text=True, timeout=300,
                       stdin=subprocess.DEVNULL)
    return p.returncode, p.stdout.splitlines(), p.stderr


def check_screen(name, lines):
    """Every line <= MAXW chars; every page <= MAXPAGE lines; framing."""
    text = [s for s in lines if s not in ("@K", "@CLR")]
    long = [s for s in text if len(s) > MAXW]
    assert not long, "%s prints lines over %d chars: %r" % (name, MAXW, long)
    seg = 0
    worst = 0
    for s in lines:
        if s == "@K":
            seg = 0
        elif s != "@CLR":
            seg += 1
            worst = max(worst, seg)
            if PROMPT.match(s):      # without stubs there is no @K marker
                seg = 0
    assert worst <= MAXPAGE, "%s: a page has %d lines" % (name, worst)
    assert text[0].startswith(name + " v1"), text[0]
    assert text[-1].startswith("== %s end, p" % name), text[-1]


def logical(lines):
    """The printed lines with markers and prompts dropped and wrapped lines
    (continuations start with a space) joined again."""
    res = []
    for s in lines:
        if s in ("@K", "@CLR") or PROMPT.match(s):
            continue
        if s.startswith(" ") and res:
            res[-1] += s
        else:
            res.append(s)
    return res


def value(lines, label):
    """The rest of the first logical line that starts with `label `."""
    for s in logical(lines):
        if s.startswith(label + " "):
            return s[len(label) + 1:]
    raise AssertionError("no line %r in %r" % (label, logical(lines)))


# --------------------------------------------------------------------------
# static checks: device names, ASCII, the Python 3.4 subset


@pytest.mark.parametrize("name", MODULES)
def test_probe_source_is_device_python(name):
    path = PROBE_DIR / (name + ".py")
    assert re.fullmatch(r"[A-Z][A-Z0-9]{0,7}", name)
    raw = path.read_bytes()
    raw.decode("ascii")                       # ASCII only
    src = raw.decode("ascii")
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.JoinedStr, ast.NamedExpr, ast.AnnAssign,
                             ast.AsyncFunctionDef, ast.AsyncFor,
                             ast.AsyncWith, ast.Await, ast.Match,
                             ast.MatMult, ast.TypeAlias)):
            bad.append(type(node).__name__)
        if isinstance(node, (ast.FunctionDef, ast.Lambda)):
            a = node.args
            if a.posonlyargs or a.kwonlyargs:
                bad.append("posonly/kwonly")
            for arg in a.args + [a.vararg, a.kwarg]:
                if arg is not None and arg.annotation is not None:
                    bad.append("annotation")
            if getattr(node, "returns", None) is not None:
                bad.append("annotation")
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if any(isinstance(e, ast.Starred) for e in node.elts) and \
                    not isinstance(getattr(node, "ctx", None), ast.Store):
                bad.append("PEP 448 display")
        if isinstance(node, ast.Dict) and None in node.keys:
            bad.append("PEP 448 dict")
        if isinstance(node, ast.Call):
            if sum(isinstance(a, ast.Starred) for a in node.args) > 1:
                bad.append("PEP 448 call")
        if isinstance(node, ast.Raise) and node.cause is not None:
            bad.append("raise from")
        if isinstance(node, ast.Compare) and \
                isinstance(node.left, ast.Name) and node.left.id == "__name__":
            bad.append("__main__ guard")
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name in DEVICE_MODULES or a.name.startswith("PRB"), \
                    a.name
        if isinstance(node, ast.ImportFrom):
            assert node.module in DEVICE_MODULES, node.module
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.NUMBER and "_" in tok.string:
            bad.append("1_000")
    assert not bad, "%s uses %s" % (name, sorted(set(bad)))
    compile(src, str(path), "exec")


def test_prbmpy_is_an_mpy_file():
    data = (PROBE_DIR / "PRBMPY.mpy").read_bytes()
    assert data[:1] == b"M"                   # MicroPython .mpy magic
    assert data[1] >= 5                       # format version


# --------------------------------------------------------------------------
# dry runs without ti_* modules (the probes' own desktop fallback)


@pytest.mark.parametrize("name", PROBES)
def test_dry_run_without_ti_modules(tmp_path, name):
    rc, lines, err = run_probe(tmp_path, name, stubs=False)
    assert rc == 0, err
    check_screen(name, lines)
    if name == "PROBE7":
        assert "no ti_graphics: stop" in lines
    if name == "PROBEK2":
        assert "no ti_system: stop" in lines
    if name == "PROBE6":
        assert value(lines, "poll") == "no ti_system"


# --------------------------------------------------------------------------
# dry runs with stub ti_system / ti_graphics


def test_probe5_dry_run(tmp_path):
    rc, lines, err = run_probe(tmp_path, "PROBE5", stubs=True)
    assert rc == 0, err
    check_screen("PROBE5", lines)
    assert value(lines, "name") == "PROBE5"
    assert value(lines, "dictord") == "xambzcqe"
    assert value(lines, "stable") == "bdfhjlacegik kc12"
    for lab in ("plain", "sortk", "map", "minkey", "eval", "lcomp", "genexp",
                "eq", "init", "hash", "str", "add", "lamb", "imptop",
                "impfn"):
        assert re.match(r"\d+/\d+", value(lines, lab)), lab
    assert "nest done" in lines
    assert not any(" E:" in s for s in logical(lines)
                   if s.startswith("nest"))           # CPython: all ok


def test_probe6_dry_run(tmp_path):
    rc, lines, err = run_probe(
        tmp_path, "PROBE6", stubs=True, getkey=45,
        extra={"PRBL300.py": stand_in(300)}, env_extra={"STUB_HOLD": "6.5"})
    assert rc == 0, err
    check_screen("PROBE6", lines)
    plain = int(value(lines, "plain"))
    # tryit, lambda, tramp and the generator: 4 frames; send() costs none
    assert int(value(lines, "ingen")) == plain - 4
    assert value(lines, "tramp") == "200 201"
    assert value(lines, "throw") == "1 2"
    assert value(lines, "ret") == "val=7"
    assert value(lines, "del") == "list 4 arr 4 app ok"
    assert value(lines, "bytea") == "4000 1"
    for lab in ("asin2", "log0", "sqrtm1", "0**-1", "cbrt", "ovf", "exp1k",
                "logm1", "infinf", "intinf", "nanck"):
        assert any(s.startswith("math %s " % lab) or s == "math " + lab
                   for s in lines), lab
    assert value(lines, "math nanck") == "[True, True, False]"
    for lab in ("exc9", "exc10", "gc10"):
        assert value(lines, lab) == "ok", lab
    assert value(lines, "cmp src") == "300 lines"
    for lab in ("imp6", "cmp6", "cmp8", "cmp9"):
        assert value(lines, lab).startswith("ok"), lab
    esc = re.fullmatch(r"esc (\d+) q (\d+) n (\d+)", value(lines, "poll"))
    assert esc and int(esc.group(1)) > 0
    assert re.fullmatch(r"45( 45)* n \d+", value(lines, "poll keys"))
    assert value(lines, "sort9") == "ok ok ok"


@pytest.mark.parametrize("baseline", (0, 1))
def test_probe7_dry_run(tmp_path, baseline):
    rc, lines, err = run_probe(
        tmp_path, "PROBE7", stubs=True,
        env_extra={"STUB_BASELINE": str(baseline)})
    assert rc == 0, err
    check_screen("PROBE7", lines)
    assert value(lines, "scr") == "320x210"
    assert value(lines, "neg") == "x 0 y 0 corner 1"
    assert value(lines, "setColor") == "rgb ok tup ok int E:TypeError"
    assert value(lines, "setPixel") == "xyc ok xy ok"
    assert value(lines, "setFont ok") == "0 1 2"
    assert value(lines, "default font") == "1"
    assert value(lines, "f1 M(8, 14)") == "10M(80, 14)"
    # the stub font lacks the integral sign: it must come out as tofu
    assert value(lines, "f1 tofu:") == "int"
    own = value(lines, "f1 own:").split()
    for g in ("pi", "rt", "Sig", "inf", "apx", "le", "ge", "ne", "to", "th"):
        assert g in own, g
    dy = 13 if baseline else 0                 # font 1 is 14 px high
    assert value(lines, "text dy") == "%d lh 18" % dy
    assert value(lines, "steps") == "y y y y y"
    assert value(lines, "px steps") == "kept kept kept kept kept"
    assert value(lines, "after print:") == "y px kept"
    assert value(lines, "after disp_clr") == "ok: y px kept"
    for lab in ("fill", "str", "setpx", "getpx", "frame"):
        assert re.match(r"[\d.]+ (ms|us)$", value(lines, lab)), lab
    assert value(lines, "mpy import").startswith("E:")


def _probek2_keys():
    tree = ast.parse((PROBE_DIR / "PROBEK2.py").read_text(encoding="ascii"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "KEYS":
            return ast.literal_eval(node.value)
    raise AssertionError("KEYS not found")


def test_probek2_dry_run(tmp_path):
    keys = _probek2_keys()
    assert len(keys) == 49
    assert len({c for _, c in keys}) == 49
    script = [105]                           # the first page's prompt
    for name, code in keys:
        if name == "sin":
            script += [99, code]             # a slip, corrected
        elif name == "cos":
            script += [77, 77]               # a confirmed other code
        elif name == "tan":
            script += [1, 2, 3]              # never agrees
        else:
            script.append(code)
    script += [105, 105]                     # idle start, hold start
    script += [57, 45, 45, 45]               # one extra key, then 3 x CLEAR
    rc, lines, err = run_probe(tmp_path, "PROBEK2", stubs=True,
                               keys=script, getkey=26)
    assert rc == 0, err
    check_screen("PROBEK2", lines)
    assert value(lines, "match") == "47 of 49"
    assert value(lines, "cos") == "77 exp 53 new"
    assert value(lines, "tan") == "3 exp 54 ?"
    assert not any(s.startswith("sin ") for s in lines)
    assert value(lines, "extra") == "57"
    assert value(lines, "hold right:").startswith("26 x")
    assert value(lines, "idle get_key").startswith("0")
    assert value(lines, "idle getKey").startswith("0")
    assert value(lines, "on code") == "105"


@pytest.mark.parametrize('missing', [False, True], ids=['generated', 'missing'])
def test_prbmem_dry_run(tmp_path, missing):
    # a fake gc.mem_free runs the ballast search on the desktop too
    rc, lines, err = run_probe(
        tmp_path, "PRBMEM", stubs=True,
        prelude="import gc\ngc.mem_free = lambda: 150000",
        omit=("PRBL200.py", "PRBL300.py") if missing else ())
    assert rc == 0, err
    check_screen("PRBMEM", lines)
    assert value(lines, "sys.modules") == "yes"
    assert value(lines, "delmod") == "ok reimport new"
    assert value(lines, "dictclr") == "ok"
    for name in ("PRBMOD", "PRBL100", "PRBL200", "PRBL300"):
        if missing and name in ("PRBL200", "PRBL300"):
            assert value(lines, name) == "missing"
            continue
        assert re.fullmatch(r"cost -?\d+ ms \d+ kept -?\d+ k2 -?\d+ "
                            r"kD -?\d+ peak -?\d+", value(lines, name)), name
    for lab in ("tup2", "tup4", "tup9", "gen", "slot", "arr", "dent"):
        assert re.fullmatch(r"-?\d+", value(lines, lab)), lab
