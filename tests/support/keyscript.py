"""End-to-end key scripts (DESIGN.md section 20.9).

Runs the entry program `src/casevo.py` itself against the desktop shims, so the depth checker
sees the real chain (entry body at depth 0, `U.key`/`R.go` at 1, ...), and returns a `Session`
with the history, Ans, the draw transcript and the screen-text dump.

Script syntax (FlowCE `tools/emu/cases/*.tsv` style)::

    2+3{enter}*2{enter}            plain text is typed with the key table of DESIGN 16.4
    {2nd,(-)}{left}{del}           {name,name,...}: raw keys by name (KEY) or by code ({105})
    integrate(x^9,x){enter}{clear@1}   {name@N}: press that key at the N-th cancel poll
                                   (escape()/get_key() call) of the computation started by
                                   the key just before it (write it right after that key);
                                   {on@N} raises KeyboardInterrupt at that poll
    {snap} {snap:label}            when the program next waits for a key, save the screen text

Typing: each run of plain text is cut greedily into the longest texts that one key inserts
(`sin(` is the sin key, `pi` is 2nd ^, `x` is X,T,theta,n, letters are alpha + key, `=` `!=`
`<` `<=` `>` `>=` `!` go through the TEST picker: 2nd math, then 1-7). `-` is always the minus
key, which triggers the leading-operator rule on an empty line after a result (`_` types (-)).
A literal `{` or `}` needs `{2nd,(}` / `{2nd,)}`. Uppercase letters other than `E` (2nd ,)
have no key sequence here.

Typical use::

    s = run('2+3{enter}*2{enter}')
    assert s.ans == ...            # R.ANS of the session
    assert '10' in s.screen        # the screen-text dump at the end
"""
import builtins
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, 'src')
SHIM = os.path.join(ROOT, 'shim')
ENTRY = os.path.join(SRC, 'casevo.py')

for _p in (SHIM, SRC):                  # conftest normally did this already
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ti_draw as TD                    # noqa: E402  (the shims)
import ti_system as TS                  # noqa: E402

StopScript = TS.StopScript
CLEAR = TS.CLEAR
ON = TS.ON

# ---------------------------------------------------------------- key names -> codes
KEY = {
    'f1': 11, 'f2': 12, 'f3': 13, 'f4': 14, 'f5': 15,
    'y=': 11, 'window': 12, 'zoom': 13, 'trace': 14, 'graph': 15,
    'menu': 11, 'recall': 12, 'setup': 13, 'forms': 14, 'help': 15,
    '2nd': 21, 'mode': 22, 'del': 23, 'left': 24, 'up': 25, 'right': 26,
    'alpha': 31, 'xttn': 32, 'xt': 32, 'stat': 33, 'down': 34,
    'math': 41, 'frac': 42, 'apps': 42, 'prgm': 43, 'vars': 44, 'clear': 45,
    '^': 51, 'pow': 51, 'x^n': 51, 'sin': 52, 'cos': 53, 'tan': 54, '/': 55, 'div': 55,
    'sq': 61, 'x^2': 61, 'comma': 62, '(': 63, 'lparen': 63, ')': 64, 'rparen': 64,
    '*': 65, 'mul': 65, 'times': 65,
    'log': 71, '7': 72, '8': 73, '9': 74, '-': 75, 'sub': 75, 'minus': 75,
    'ln': 81, '4': 82, '5': 83, '6': 84, '+': 85, 'add': 85, 'plus': 85,
    'sto': 91, 'sto>': 91, '1': 92, '2': 93, '3': 94, '<>': 95, 'test': 95,
    '0': 102, '.': 103, 'dot': 103, '(-)': 104, 'neg': 104, 'enter': 105,
    'on': ON,
}

NAME = {
    11: 'f1', 12: 'f2', 13: 'f3', 14: 'f4', 15: 'f5', 21: '2nd', 22: 'mode', 23: 'del',
    24: 'left', 25: 'up', 26: 'right', 31: 'alpha', 32: 'xttn', 33: 'stat', 34: 'down',
    41: 'math', 42: 'frac', 43: 'prgm', 44: 'vars', 45: 'clear', 51: '^', 52: 'sin',
    53: 'cos', 54: 'tan', 55: '/', 61: 'sq', 62: 'comma', 63: '(', 64: ')', 65: '*',
    71: 'log', 72: '7', 73: '8', 74: '9', 75: '-', 81: 'ln', 82: '4', 83: '5', 84: '6',
    85: '+', 91: 'sto', 92: '1', 93: '2', 94: '3', 95: '<>', 102: '0', 103: '.', 104: '(-)',
    105: 'enter', ON: 'on',
}

SECOND = 21
ALPHA = 31

# DESIGN 16.4 as data: code -> (plain, 2nd, alpha). A string is the text the key inserts; a
# string starting with '@' is an action; None means the key does nothing in that state.
KEYTEXT = {
    11: ('@menu', None, None),
    12: ('@recall', None, None),
    13: ('@setup', None, None),
    14: ('@forms', None, None),
    15: ('@help', None, None),
    22: ('@setup', '@quit', None),
    23: ('@del', None, None),
    24: ('@left', '@home', None),
    25: ('@up', '@pageup', None),
    26: ('@right', '@end', None),
    32: ('x', 't', 'theta'),
    33: (None, None, None),
    34: ('@down', '@pagedown', None),
    41: ('@menu:calculus', '@test', 'a'),
    42: ('/', None, 'b'),
    43: (None, None, 'c'),
    44: ('@recall', None, None),
    45: ('@clear', None, None),
    51: ('^', None, 'd'),
    52: ('sin(', 'asin(', 'e'),
    53: ('cos(', 'acos(', 'f'),
    54: ('tan(', 'atan(', 'g'),
    55: ('/', 'pi', 'h'),
    61: ('^2', 'sqrt(', 'i'),
    62: (',', 'E', 'j'),
    63: ('(', '{', 'k'),
    64: (')', '}', 'l'),
    65: ('*', 'e', 'm'),
    71: ('log(', '10^(', 'n'),
    72: ('7', None, 'o'),
    73: ('8', None, 'p'),
    74: ('9', None, 'q'),
    75: ('-', '[', 'r'),
    81: ('ln(', 'e^(', 's'),
    82: ('4', None, 't'),
    83: ('5', None, 'u'),
    84: ('6', None, 'v'),
    85: ('+', ']', 'w'),
    91: ('=>', None, 'x'),
    92: ('1', None, 'y'),
    93: ('2', None, 'z'),
    94: ('3', None, 'theta'),
    95: ('@test', None, None),
    102: ('0', '@menu:all', ' '),
    103: ('.', 'i', "'"),
    104: ('-', 'ans()', None),
    105: ('@enter', '@entry', None),
}

# The TEST picker (2nd math, D16): item n is picked with the digit key n.
TEST_OPS = ('=', '!=', '<', '<=', '>', '>=', '!')
DIGIT = (None, 92, 93, 94, 82, 83, 84, 72, 73, 74)     # digit n -> key code


def _typing_table():
    """text -> shortest key sequence; ties prefer plain, then alpha, then 2nd, then low codes."""
    best = {}
    for code in sorted(KEYTEXT):
        for col, prefix, rank in ((0, [], 0), (2, [ALPHA], 1), (1, [SECOND], 2)):
            t = KEYTEXT[code][col]
            if t is None or t[0] == '@':
                continue
            cand = (len(prefix) + 1, rank, code, prefix + [code])
            if t not in best or cand < best[t]:
                best[t] = cand
    out = {}
    for t in best:
        out[t] = best[t][3]
    for n in range(len(TEST_OPS)):
        out.setdefault(TEST_OPS[n], [SECOND, 41, DIGIT[n + 1]])
    out['_'] = [104]                    # FlowCE's spelling of the (-) key
    return out


TYPE = _typing_table()
_LONGEST = max(len(t) for t in TYPE)


def type_keys(text, words=True):
    """Key codes that type `text`. words=False uses only one-character keys (letters are then
    spelled with alpha, `sin(` as s, i, n, ()."""
    out = []
    i = 0
    while i < len(text):
        for n in range(min(_LONGEST if words else 2, len(text) - i), 0, -1):
            t = text[i:i + n]
            if t in TYPE and (words or n == 1 or t in TEST_OPS):
                out.extend(TYPE[t])
                i += n
                break
        else:
            raise ValueError('no key sequence types %r (in %r); use {raw,keys}'
                             % (text[i], text))
    return out


def parse(script, words=True):
    """A script string -> a list of key codes and ti_system markers (see the module doc)."""
    out = []
    i = 0
    nsnap = 0
    while i < len(script):
        j = script.find('{', i)
        if j < 0:
            j = len(script)
        if j > i:
            out.extend(type_keys(script[i:j], words))
        if j >= len(script):
            break
        k = script.find('}', j + 1)
        if k < 0:
            raise ValueError('unclosed { in key script %r' % script)
        for tok in script[j + 1:k].split(','):
            tok = tok.strip()
            if tok == 'snap' or tok.startswith('snap:'):
                nsnap += 1
                out.append(TS.mark(tok[5:] if tok.startswith('snap:') else 'snap%d' % nsnap))
            elif '@' in tok and tok.index('@') > 0:
                name, n = tok.rsplit('@', 1)
                out.append(TS.after(int(n), _code(name)))
            else:
                out.append(_code(tok))
        i = k + 1
    return out


def _code(tok):
    if tok in KEY:
        return KEY[tok]
    if tok.isdigit() and len(tok) > 1:
        return int(tok)
    raise ValueError('unknown key name %r (see keyscript.KEY)' % tok)


def entry(text, words=True):
    """Keys that type one input line and press ENTER. A leading '-' is typed with (-), so the
    leading-operator rule does not turn it into ans()-."""
    ks = type_keys(text, words)
    if text.startswith('-'):
        ks[0] = 104
    return ks + [105]


def case(inp, keys='', words=True):
    """A FlowCE case row (name<TAB>input<TAB>keys) as keys: type the input, ENTER, then keys."""
    return (entry(inp, words) if inp else []) + parse(keys, words)


def describe(items):
    """Readable form of a key list: 'xttn ^ 2 enter {clear@3}'."""
    out = []
    for it in items:
        if type(it) is tuple and it[0] == 'after':
            out.append('{%s@%d}' % (NAME.get(it[2], str(it[2])), it[1]))
        elif type(it) is tuple:
            out.append('{snap:%s}' % it[1])
        else:
            out.append(NAME.get(it, str(it)))
    return ' '.join(out)


def decode(items):
    """Reference typist for tests: the text a 1D editor inserts for `items`, with one-shot 2nd
    and alpha (no alpha lock, no editing). Actions appear as '{name}'; markers are skipped."""
    out = []
    mod = 0                             # 0 plain, 1 2nd, 2 alpha
    test = False
    for it in items:
        if type(it) is tuple:
            continue
        if test:
            test = False
            n = DIGIT.index(it) if it in DIGIT else 0
            if not 1 <= n <= len(TEST_OPS):
                raise ValueError('TEST picker: no item for key %r' % (it,))
            out.append(TEST_OPS[n - 1])
            continue
        if it == SECOND:
            mod = 0 if mod == 1 else 1
            continue
        if it == ALPHA:
            mod = 0 if mod == 2 else 2
            continue
        t = KEYTEXT.get(it, (None, None, None))[mod]
        mod = 0
        if t is None:
            raise ValueError('key %s does nothing in that state' % NAME.get(it, it))
        if t == '@test':
            test = True
        elif t[0] == '@':
            out.append('{%s}' % t[1:])
        else:
            out.append(t)
    return ''.join(out)


# ---------------------------------------------------------------- running the entry program
ALIASES = {'K': 'node', 'A': 'alg', 'P': 'parse', 'PR': 'printer', 'R': 'run', 'D': 'draw',
           'U': 'ui', 'M': 'menu', 'FO': 'forms', 'CA': 'catalog'}


class Session(object):
    """The outcome of run(). Module objects are the session's own (fresh) instances."""

    def __init__(self, items, ended, mods, snaps):
        self.items = items              # the script
        self.ended = ended              # 'script' (StopScript) or 'quit' (the loop ended)
        self.mods = mods                # {module name: module} imported from the device dirs
        self.snaps = snaps              # [(label, screen text, transcript length)]
        self.screen = TD.screen_text()  # the screen-text dump at the end
        self.texts = TD.texts()
        self.calls = list(TD.CALLS)     # the ti_draw transcript
        self.overdraw = list(TD.OVERDRAW)
        self.offscreen = list(TD.OFFSCREEN)     # calls that reached outside the screen
        self.counts = dict(TD.COUNTS)   # ti_draw calls by name (a raising call counts too)
        self.colors = TD.COUNTS.get('set_color', 0)
        self.read = list(TS.KEYS_READ)  # keys returned by wait_key
        self.left = TS.remaining()      # script items never read
        self.fired = list(TS.FIRED)     # (poll, code) of after() presses that fired
        self.missed = list(TS.MISSED)   # after() presses whose poll never came
        self.polls = TS.POLLS
        self.tscalls = list(TS.CALLS)

    def mod(self, name):
        return self.mods.get(ALIASES.get(name, name))

    def __getattr__(self, name):        # s.K, s.R, s.U, ... (only the aliases)
        if name in ALIASES:
            return self.mods.get(ALIASES[name])
        raise AttributeError(name)

    @property
    def hist(self):
        return getattr(self.mods.get('run'), 'HIST', None)

    @property
    def ans(self):
        return getattr(self.mods.get('run'), 'ANS', None)

    def snap(self, label):
        for lab, text, n in self.snaps:
            if lab == label:
                return text
        raise KeyError(label)

    def transcript_text(self, start=0, end=None):
        return TD.transcript_text(self.calls[start:end])


def _norm_dir(d):
    return os.path.normcase(os.path.abspath(d)) + os.sep


def _modules_in(dirs):
    out = {}
    for name, m in list(sys.modules.items()):
        f = getattr(m, '__file__', None)
        if f and os.path.normcase(os.path.abspath(f)).startswith(dirs):
            out[name] = m
    return out


# Checks run on every Session before run() returns, e.g. registered by conftest: no record of
# kind 'internal error', the session's node table back at BASE. A check fails by raising.
AFTER_RUN = []


def reset_shims():
    """Fresh ti_system and ti_draw state."""
    TS.reset()
    TD.reset()


def run(script=(), program=None, fresh=True, latch_clear=False, words=True):
    """Run the entry program (default src/casevo.py) on a key script.

    script       a script string (see the module doc) or a list of codes and markers.
    program      the entry program file; default ENTRY (src/casevo.py). The bundled tier
                 sets keyscript.SRC and keyscript.ENTRY to the dist/device files.
    fresh        True: the run imports its own fresh device modules, as on the device, where
                 each run is a new interpreter; afterwards sys.modules is restored, so modules
                 that other tests imported are untouched. The session keeps its modules.
    latch_clear  ti_system.LATCH_CLEAR for this run (a [clear] read by wait_key leaves the
                 escape latch set).

    The run ends when the script is exhausted (StopScript) or the event loop exits. Any other
    exception escaping the entry program propagates (after sys.modules is restored). Then every
    function in AFTER_RUN is called with the Session.
    """
    items = parse(script, words) if isinstance(script, str) else list(script)
    path = os.path.abspath(program or ENTRY)
    with open(path, 'r', encoding='utf-8') as f:
        code = compile(f.read(), path, 'exec')
    dirs = tuple(sorted(set((_norm_dir(SRC), _norm_dir(os.path.dirname(path))))))
    saved = _modules_in(dirs) if fresh else {}
    for name in saved:
        del sys.modules[name]
    reset_shims()
    TS.load(items)
    TS.LATCH_CLEAR = latch_clear
    snaps = []

    def hook(label):
        snaps.append((label, TD.screen_text(), len(TD.CALLS)))

    TS.MARK_HOOK[0] = hook
    g = {'__name__': 'CASEVO', '__builtins__': builtins}
    ended = None
    mods = {}
    try:
        try:
            exec(code, g)
            ended = 'quit'
        except StopScript:
            ended = 'script'
        sess = Session(items, ended, None, snaps)
    finally:
        TS.MARK_HOOK[0] = None
        mods = _modules_in(dirs)
        if fresh:
            for name in mods:
                sys.modules.pop(name, None)
            sys.modules.update(saved)
    sess.mods = mods
    sess.globals = g
    for fn in AFTER_RUN:
        fn(sess)
    return sess
