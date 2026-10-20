"""MathPrint milestone A: the engine-free 2D layout core and the text transforms.

docs/notes/MATHPRINT.md sections 1.2-1.4, 3, 4.1 and 5: draw.mflat/mstop/mlex/mparse/mbox/
mplace/mlayout/mrender and ui.tidy/ui.structure. Everything but the round-trip tests runs with
no engine handed to draw (draw.P/PR are None), as on the calculator before the first ENTER.
"""
import random

import pytest

import draw as D
import ti_draw as TD
import ui as U


@pytest.fixture(autouse=True)
def engine_free(monkeypatch):
    monkeypatch.setattr(D, 'P', None)
    monkeypatch.setattr(D, 'PR', None)
    TD.reset()
    D.reset()
    D.clear_cache()
    D.theme(0)


def lay(s):
    m = D.mlayout(s, 2)
    assert m is not None, s
    assert m[0] == s
    return m


def stops(m):
    X = m[5]
    out = []
    for i in range(len(X)):
        if X[i] >= 0:
            out.append(i)
    return out


def texts(dl):
    out = []
    for item in dl:
        if item[0] == 't':
            out.append(item[3])
    return out


def drawn_indices(s, dl):
    """Buffer indices covered by a drawn text item (each text at its first occurrence)."""
    seen = set()
    for t in texts(dl):
        j = s.find(t)
        if j >= 0 and t:
            seen.update(range(j, j + len(t)))
    return seen


# -- section 3: the template catalog --------------------------------------------------------------

# buffer, ORD (stops in drawn order), drawn text, the slot owners in visiting order
CATALOG = [
    ('x^(2)+1', [0, 1, 3, 4, 5, 6, 7], ['x', '2', '+1'], 'RW'),
    ('(a)/(b)', [0, 1, 2, 5, 6, 7], ['a', 'b'], 'RQQ'),
    ('surd(8,3)', [0, 7, 8, 5, 6, 9], ['3', '8'], 'RTT'),
    ('sum(,k,,)', [0, 5, 6, 7, 8, 4, 9], ['k', '='], 'RTTTT'),
    ('integrate(,x,,)', [0, 13, 14, 10, 11, 12, 15], ['d', 'x'], 'RTTTT'),
    ('sin(x)', [0, 4, 5, 6], ['sin(x)'], 'RC'),
    ('sqrt(x)', [0, 5, 6, 7], ['x'], 'RT'),
    ('abs(x)', [0, 4, 5, 6], ['x'], 'RT'),
    ('exp(u)', [0, 4, 5, 6], ['e', 'u'], 'RT'),
    ('e^(x)', [0, 1, 3, 4, 5], ['e', 'x'], 'RW'),
    ('10^(x)', [0, 1, 2, 4, 5, 6], ['10', 'x'], 'RW'),
    ('log(u,b)', [0, 6, 7, 4, 5, 8], ['log', 'b', '(u', ')'], 'RTT'),
    ('integrate(f,x)', [0, 10, 11, 12, 13, 14], ['d', 'f', 'x'], 'RTT'),
    ('integrate(f,x,a,b)', [0, 14, 15, 16, 17, 10, 11, 12, 13, 18], None, 'RTTTT'),
    ('diff(f,x)', [0, 7, 8, 5, 6, 9], ['d', 'd', 'x', '(f', ')'], 'RTT'),
    ('sum(f,k,a,b)', [0, 6, 7, 8, 9, 10, 11, 4, 5, 12], ['k', '=', 'a', 'b', 'f'], 'RTTTT'),
    ('limit(f,x,a)', [0, 8, 9, 10, 11, 6, 7, 12], ['lim', 'x', 'a', 'f'], 'RTTT'),
    ('limit(f,x,a,d)', [0, 8, 9, 10, 11, 12, 13, 6, 7, 14], None, 'RTTTT'),
    ('(a+b)', [0, 1, 2, 3, 4, 5], ['(a+b)'], 'RG'),
    ('1/2+x^(2)', [0, 1, 2, 3, 4, 5, 7, 8, 9], ['1/2+x', '2'], 'RW'),
    ('2+3', [0, 1, 2, 3], ['2+3'], 'R'),
]


@pytest.mark.parametrize('s,order,drawn,owners', CATALOG)
def test_catalog_stops_in_drawn_order(s, order, drawn, owners):
    m = lay(s)
    line, dl, w, asc, desc, X, Y, RK, ORD, SL, SLOTS, CONS, EMPTY = m
    assert ORD == order, (s, ORD)
    assert sorted(ORD) == stops(m)
    for r in range(len(ORD)):
        assert RK[ORD[r]] == r
    for i in range(len(s) + 1):
        if X[i] < 0:
            assert RK[i] == -1 and Y[i] == -1
    if drawn is not None:
        assert texts(dl) == drawn, (s, texts(dl))
    assert ''.join(row[2] for row in SLOTS) == owners, (s, SLOTS)
    # the caret map is complete: every stop has a slot, every slot row is well formed
    for i in ORD:
        assert 0 <= SL[i] < len(SLOTS)
    for row in SLOTS:
        a, e, okind, os, oe, k, nslots, hidden, dep = row
        assert 0 <= a <= e <= len(s) and os <= a and e <= oe and 0 <= k < nslots
        assert X[a] >= 0 and X[e] >= 0
    assert w > 0 and asc > 0 and desc >= 0 and asc + desc <= 76


def test_hidden_characters():
    for s, hidden in (('(a)/(b)', {0, 2, 3, 4, 6}), ('x^(2)', {1, 2, 4}),
                      ('sqrt(x)', {0, 1, 2, 3, 4, 6}), ('surd(8,3)', {0, 1, 2, 3, 4, 6, 8}),
                      ('sum(,k,,)', {0, 1, 2, 3, 4, 6, 7, 8}),
                      ('integrate(f,x)', set(range(10)) | {11, 13}),
                      ('sin(x)', set()), ('1/2', set()), ('(a+b)', set())):
        dl = lay(s)[1]
        assert set(range(len(s))) - drawn_indices(s, dl) == hidden, (s, texts(dl))


def test_slot_rows():
    m = lay('(a)/(b)')
    assert m[10] == [(0, 7, 'R', 0, 7, 0, 1, False, 0), (1, 2, 'Q', 0, 7, 0, 2, True, 1),
                     (5, 6, 'Q', 0, 7, 1, 2, True, 1)]
    m = lay('x^(2)+1')
    assert m[10][1] == (3, 4, 'W', 1, 5, 0, 1, True, 1)
    m = lay('x^2')                       # a bare exponent: a slot whose parens are not hidden
    assert m[10][1] == (2, 3, 'W', 1, 3, 0, 1, False, 1)
    m = lay('sin(sqrt(x))')
    assert [r[2] for r in m[10]] == ['R', 'C', 'T']
    assert [r[8] for r in m[10]] == [0, 1, 2]
    m = lay('surd(8,3)')
    assert [r[5] for r in m[10]] == [0, 1, 0]       # the index (argument 1) is visited first


def test_cons_and_power_span():
    m = lay('2x^(2)+(a)/(b)')
    assert m[11] == [(1, 2, 6, 'W'), (7, 7, 14, 'Q')]
    assert lay('x^(2)')[11] == [(0, 1, 5, 'W')]
    assert lay('sin(x)')[11] == [(0, 0, 6, 'C')]


def test_bare_power_end_is_raised():
    X, Y = lay('x^2')[5:7]
    assert stops(lay('x^2')) == [0, 1, 2, 3]
    assert Y[3] < Y[0] and Y[2] == Y[3] and X[3] > X[2]
    X, Y = lay('x^(2)')[5:7]
    assert Y[4] < Y[0] and Y[5] == Y[0] and X[5] == X[4]


def test_trailing_gap_separates_slot_end_and_construct_end():
    for s, slot_end, end in (('sqrt(x)', 6, 7), ('(a)/(b)', 6, 7), ('integrate(,x,,)', 12, 15),
                             ('abs(x)', 5, 6), ('surd(8,3)', 6, 9), ('sum(f,k,a,b)', 5, 12)):
        X = lay(s)[5]
        assert X[end] - X[slot_end] >= D.TGAP, s
    X = lay('x^(2)')[5]
    assert X[5] == X[4]                  # a power has no gap
    X = lay('sin(x)')[5]
    assert X[6] == X[5] + 10             # a call: the visible ')' only


def test_empties_in_drawn_order():
    assert lay('sum(,k,,)')[12] == [(7, 0), (8, 0), (4, 0)]
    assert lay('integrate(,x,,)')[12] == [(13, 0), (14, 0), (10, 0)]
    assert lay('(|)/()'.replace('|', ''))[12] == [(1, 0), (4, 0)]
    assert lay('log(8,)')[12] == [(6, 2)]            # the optional log base
    assert lay('sqrt(2+)')[12] == [(7, 1)]           # a trailing missing operand
    assert lay('x^()')[12] == [(3, 0)]
    m = lay('x^(2)+')
    assert m[12] == [(6, 1)]
    boxes = [item for item in m[1] if item[0] == 'b']
    assert boxes == [('b', boxes[0][1], boxes[0][2], 8, 13, 6, 1)]


def test_stray_closer_and_unclosed_group_are_text():
    m = lay('x^(2)+1)')
    assert texts(m[1])[-1] == '+1)'
    m = lay('x^(2)+sqrt(1')                # unclosed: a plain call, nothing hidden
    assert texts(m[1])[-1] == '+sqrt(1'
    m = lay('x^(2)+(1')
    assert texts(m[1])[-1] == '+(1'


def test_entry_stacking_rule():
    def stacked(s):
        return any(c[3] == 'Q' for c in lay(s)[11])
    assert stacked('(1)/(2)+x^(2)')
    assert not stacked('1/2+x^(2)')
    assert not stacked('(1)/2+x^(2)')
    assert not stacked('1/(2)+x^(2)')
    assert stacked('-(a)/(b)+x^(2)')     # the minus is drawn outside the bar
    assert not stacked('(1)/((2)+x^(2)')   # unclosed group: inline


def test_glyphs_and_ans_are_units():
    m = lay('2pi+ans()')
    assert stops(m) == [0, 1, 3, 4, 9]
    assert [it[3] for it in m[1] if it[0] == 'g'] == ['pi']
    assert 'Ans' in texts(m[1])


def test_one_text_run_for_a_call():
    m = lay('sin(x)+1')
    D.mrender(m[1], 10, 172, D.SCREEN, 10, 319, D.COLORS['INK'], False)
    assert [c for c in TD.CALLS if c[0] == 'draw_text'] == [('draw_text', 10, 189, 'sin(x)+1')]


def test_layout_heights():
    for s, most in (('sqrt(x)', 19), ('(1)/(2)', 36), ('x^(2)', 36), ('surd(8,3)', 36),
                    ('log(8,2)', 36), ('integrate(f,x,a,b)', 60), ('sum(f,k,a,b)', 60),
                    ('((1)/(2))/(3)', 56), ('x^((1)/(2))', 56)):
        m = lay(s)
        assert m[3] + m[4] <= most, (s, m[3] + m[4])


# -- section 5.1: the flat fast path --------------------------------------------------------------

@pytest.mark.parametrize('s,flat', [
    ('', True), ('2+3', True), ('sin(x)+1', True), ('1/4', True), ('log(8)', False),
    ('surd(8', False), ('diff(x', False), ('(1)/(4)', False), ('x^2', False), ('pi', False),
    ('ans()+1', False), ('2sqrt(x)', False), ('integrate(x,x)', False), ('abs(', False),
    ('mysqrt(2)', True), ('sqrt2(x)', True), ('(1)/4', True),
])
def test_mflat(s, flat):
    assert D.mflat(s) is flat


def test_mstop_flat_lines():
    s = '2sin(x)+ln(y)'
    want = [0, 1, 5, 6, 7, 8, 11, 12, 13]
    assert [i for i in range(len(s) + 1) if D.mstop(s, i)] == want


# -- section 5.3: caps and degrade ----------------------------------------------------------------

def test_caps_return_none():
    assert D.mlayout('x^(2)+' + '1' * 155, 2) is None          # 161 characters
    assert D.mlayout('x^(2)+' + '1' * 154, 2) is not None      # 160 characters
    deep = '(' * 25 + 'x^(2)' + ')' * 25
    assert D.mlayout(deep, 2) is None                         # 26 open groups
    ok = '(' * 23 + 'x^(2)' + ')' * 23
    assert D.mlayout(ok, 2) is not None                       # 24 open groups
    tall = 'x'
    for j in range(5):
        tall = '(' + tall + ')/(2)'
    assert D.mlayout(tall, 2) is None                         # taller than 76
    nodes = '+'.join(['x^2'] * 40)                            # past 192 nodes
    assert len(nodes) <= 160 and D.mlayout(nodes, 2) is None


def test_dense_line_stays_bounded():
    s = '+'.join(['(1)/(x+1)'] * 16)[:160]
    m = D.mlayout(s, 2)
    assert m is None or m[3] + m[4] <= 76
    s = '+'.join(['x^(2)'] * 26)[:160]
    assert D.mlayout(s, 2) is not None


def _calibration():
    x = []
    for i in range(2000):
        x.append((i, i + 1))


@pytest.mark.no_depth
def test_dense_line_host_time_guard():
    # Section 10: one mlayout of a dense 160-character line < 400 us on the reference host,
    # where the calibration loop takes 86 us; a slower host scales the bound by its own speed.
    import timeit
    s = ('2x^(2)+3x-(1)/(2)+sin(x)^(2)-sqrt(x+1)+' * 4)[:160]
    assert D.mlayout(s, 2) is not None
    ref = min(timeit.repeat(_calibration, number=20, repeat=7)) / 20
    took = min(timeit.repeat(lambda: D.mlayout(s, 2), number=50, repeat=7)) / 50
    assert took < 400e-6 * max(1.0, ref / 86e-6), (took, ref)


def test_layout_never_raises_on_noise():
    rnd = random.Random(7)
    alphabet = ['x', '1', '2', '+', '-', '*', '/', '^', '(', ')', ',', 'sqrt(', 'surd(',
                'sum(', 'integrate(', 'log(', 'ans()', 'pi', ' ', '!', "'", '=', '<=', '.',
                'E', '[', ']', '{', '}', ':=', '=>', 'abs(', 'limit(', 'diff(', 'exp(', ':']
    for n in range(400):
        s = ''.join(rnd.choice(alphabet) for j in range(rnd.randint(1, 30)))[:160]
        for mode in (1, 2):
            m = D.mlayout(s, mode)
            if m is not None and mode == 2:
                assert m[0] == s
                assert m[8] and m[8][0] == 0 and m[5][len(s)] >= 0, s
                assert sorted(m[8]) == stops(m)


# -- section 5.4: render --------------------------------------------------------------------------

def test_mrender_kinds_and_range():
    m = lay('(|)/()+1'.replace('|', ''))
    D.mrender(m[1], 10, 172, D.SCREEN, 10, 319, D.COLORS['LINE'], True)
    fills = [c for c in TD.CALLS if c[0] == 'fill_rect']
    assert len(fills) == 2 and not [c for c in TD.CALLS if c[0] in ('draw_text', 'draw_line')]
    TD.reset()
    D.reset()
    D.mrender(m[1], 10, 172, D.SCREEN, 10, 319, D.COLORS['INK'], False)
    assert not [c for c in TD.CALLS if c[0] == 'fill_rect']
    assert [c for c in TD.CALLS if c[0] == 'draw_line']           # the fraction bar
    TD.reset()
    D.reset()
    D.mrender(m[1], 10, 172, D.SCREEN, 300, 319, D.COLORS['INK'], False)
    assert not TD.CALLS                                            # nothing that far right


def test_mrender_skips_the_trailing_box_at_the_caret():
    m = lay('x^(2)+')
    D.mrender(m[1], 10, 172, D.SCREEN, 10, 319, D.COLORS['LINE'], True, 6)
    assert not TD.CALLS
    D.mrender(m[1], 10, 172, D.SCREEN, 10, 319, D.COLORS['LINE'], True, 5)
    assert [c[0] for c in TD.CALLS] == ['set_color', 'fill_rect']


# -- history inputs (mode 1) ----------------------------------------------------------------------

def test_history_mode_stacks_every_fraction():
    r = D.mlayout('1/4+2*x', 1)
    dl, w, asc, desc = r
    assert texts(dl) == ['1', '4', '+2', 'x']
    assert [it[3] for it in dl if it[0] == 'g'] == ['*']          # the dot glyph
    assert any(it[0] == 'l' for it in dl)
    assert not [it for it in dl if it[0] == 'b']
    assert D.ICACHE and D.ICACHE[0][0] == '1/4+2*x'
    TD.reset()
    assert D.mlayout('1/4+2*x', 1) is r                         # cached
    D.clear_cache()
    assert not D.ICACHE and D.ICACHE_BYTES == 0
    r = D.mlayout('(x+1)/2', 1)
    assert texts(r[0]) == ['x+1', '2']                          # operand parens hidden
    r = D.mlayout('-a/b', 1)
    assert texts(r[0]) == ['-', 'a', 'b']
    assert D.mlayout('x' * 161, 1) is None


def test_history_cache_is_bounded():
    for j in range(12):
        D.mlayout('%d/%d' % (j, j + 1), 1)
        assert len(D.ICACHE) <= 5 and D.ICACHE_BYTES <= 3072
    total = 0
    for e in D.ICACHE:
        total += e[2]
    assert total == D.ICACHE_BYTES


# -- sections 1.3 and 1.4: tidy and structure -----------------------------------------------------

@pytest.mark.parametrize('s,want', [
    ('(1)/(4)', '1/4'), ('x^(2)+1', 'x^2+1'), ('x^(-1)', 'x^-1'), ('e^(x)', 'e^x'),
    ('(x+1)/(2)', '(x+1)/2'), ('x^(2)3', 'x^(2)3'), ('(1)/(4)x', '1/(4)x'),
    ('expand((x+1)^(12))', 'expand((x+1)^12)'), ('log(8,)', 'log(8)'), ('log(8,2)', 'log(8,2)'),
    ('x^(-1)*2', 'x^(-1)*2'), ('(1)/(-2)', '1/(-2)'), ('x^(2)!', 'x^(2)!'), ('2+3', '2+3'),
    ('((1)/(2))/(3)', '(1/2)/3'), ('x^(2.5)', 'x^2.5'), ('(ab)/(c)', '(ab)/c'),
    ('a(2)/(3)', 'a(2)/3'), ('x^((1)/(2))', 'x^(1/2)'), ('', ''),
])
def test_tidy(s, want):
    assert U.tidy(s) == want


@pytest.mark.parametrize('s,want', [
    ('1/4', '(1)/(4)'), ('x^2+1', 'x^(2)+1'), ('(1+x)/2', '(1+x)/(2)'), ('1/(x+1)', '(1)/(x+1)'),
    ('x^2/3', '(x^(2))/(3)'), ('-a/b', '-(a)/(b)'), ('2+3', '2+3'), ('x^-1', 'x^(-1)'),
    ('e^(x)', 'e^(x)'), ('2^3^2', '2^(3^(2))'), ('a/bc', 'a/bc'), ('x^ab', 'x^ab'),
    ('sin(x)', 'sin(x)'), ('', ''),
])
def test_structure(s, want):
    assert U.structure(s) == want


def test_structure_falls_back_past_256():
    s = '+'.join(['1/2'] * 60)[:255]
    assert U.structure(s) == s


# the round trip needs the engine: tidy(structure(s)) gives the same run.go record as s
ROUND = [
    '1/4', 'x^2+1', '(1+x)/2', '1/(x+1)', 'x^2/3', '-a/b', '2^3^2', 'x^-1+1', '2^-3*4',
    '1/2pi', '2/3x', 'e^x', 'e^(x+1)', '10^2', 'sqrt(x)/2', 'x^(1/2)', '1/x^2', 'a/b/c',
    '(x^2+1)^3', 'expand((x+1)^12)', 'log(8,2)', 'diff(x^3,x)', 'integrate(x^2,x,0,1)',
    'sum(1/k^2,k,1,oo)', 'limit(sin(x)/x,x,0)', 'x^2!', '-x^2', '2*-3/4', '1E-3^2',
    'surd(8,3)/2', '3/4+5/6', '(1/2)^(1/3)', 'x^y^z', 'a/bc', 'sin(x)^2/2', 'abs(-3)/3',
    'x/y^2', '1/2/3/4', '2x^2/4', '-1/2', '--2/3', 'x=1/2', 'f(x):=x^2/2',
]


def corpus():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    out = list(ROUND)
    for name in ('t1.tsv', 't2.tsv', 't3.tsv'):
        for line in open(os.path.join(here, 'corpus', name), encoding='utf-8'):
            if line.strip() and not line.startswith('#'):
                out.append(line.split('\t')[0])
    rnd = random.Random(42)
    atoms = ['x', '2', '3', 'a', 'pi', '1.5', 'e']
    for n in range(60):
        st = [rnd.choice(atoms)]
        for j in range(rnd.randint(1, 4)):
            op = rnd.choice(['+', '-', '*', '/', '^', '/'])
            right = rnd.choice(atoms)
            if rnd.random() < 0.3:
                right = '(' + right + rnd.choice(['+', '-', '/']) + rnd.choice(atoms) + ')'
            st.append(op + right)
        out.append(''.join(st))
    return out


def record(s):
    import cascheck as C
    import run as R
    C.fresh()
    rec = R.go(('eval', s))
    return rec[:2]


@pytest.mark.parametrize('s', corpus())
def test_round_trip_through_the_engine(s):
    t = U.tidy(U.structure(s))
    assert record(t) == record(s), (s, U.structure(s), t)
