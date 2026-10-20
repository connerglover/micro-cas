"""Structural 2D layout and clipped drawing through ti_draw (one 10 x 15 font)."""
import pytest
import draw as D
import ti_draw as TD
import parse as P
import printer as PR
import node as K

ON_EVO = {'set_color', 'fill_rect', 'draw_text', 'draw_line'}


def lay(s, width=300, height=92):
    """draw.layout's (dl, w, asc, h) as a dict; whether the text fell back to one plain line,
    and the box kinds, come from the parts layout() runs (tree, measure)."""
    dl, w, asc, h = D.layout(s, width, height)
    try:
        code = P.rpn(P.lex(s))
        if len(code) > 400:
            raise ValueError('layout size')
        boxes, root = D.measure(D.tree(code))
        kinds, fallback = set(b[5] for b in boxes), False
    except Exception:
        kinds, fallback = set(), True
    return {'dl': dl, 'w': w, 'h': h, 'asc': asc, 'desc': h - asc, 'vw': width, 'vh': height,
            'overflow': w > width or h > height, 'fallback': fallback, 'kinds': kinds}


def paint(box, x, y, scrollx=0, scrolly=0):
    """The answer view's drawing: box in its view (x, y, vw, vh), shifted left by scrollx and
    up by scrolly, clipped to the view and the screen (ui.redraw draws answers this way)."""
    clip = (max(x, 0), max(y, 0), min(x + box['vw'] - 1, D.W - 1), min(y + box['vh'] - 1, D.H - 1))
    D.render(box['dl'], x - scrollx, clip, y - scrolly)


@pytest.fixture(autouse=True)
def screen(monkeypatch):
    # ui.engine() hands draw its engine modules on the device; here the test does it
    monkeypatch.setattr(D, 'P', P)
    monkeypatch.setattr(D, 'PR', PR)
    TD.reset()
    D.reset()
    D.clear_cache()
    D.theme(0)


def cells(calls):
    """(left, top, right, bottom) of every draw_text cell in a transcript."""
    out = []
    for c in calls:
        if c[0] == 'draw_text':
            out.append((c[1], c[2] - 17, c[1] + 10 * len(c[3]) - 1, c[2] - 3))
    return out


@pytest.mark.parametrize('source,kind', [
    ('2/3', 'frac'), ('x^(2/3)', 'sup'), ('sqrt(x+1)', 'sqrt'),
    ('surd(x+1,3)', 'root'), ('(x+1)*(x-1)', 'paren'), ('abs(x+1)', 'abs'),
    ('sin(x)', 'call'), ('integrate(x^2,x)', 'integral'),
    ('integrate(x,x,0,1)', 'integral'), ('diff(x^2,x)', 'derivative'),
    ('sum(k^2,k,1,10)', 'sum'), ('limit(sin(x)/x,x,0)', 'limit'),
    ('[x,2/3]', 'list'), ('x=1,x=2', 'row'), ('O(x^6)', 'call'),
])
def test_special_layout(source, kind):
    box = lay(source)
    assert not box['fallback'], source
    assert kind in box['kinds']
    assert box['w'] > 0 and box['h'] > 0
    assert all(isinstance(v, int) for item in box['dl'] for v in item[1:3])
    # every item lies inside the box: nothing is drawn above, below or beside it
    paint(box, 0, 20)
    for left, top, right, bottom in cells(TD.CALLS):
        assert 0 <= left and right < box['w'] and 20 <= top and bottom < 20 + box['h'], source


def test_fraction_is_stacked_and_exponent_is_raised():
    frac = lay('2/3')
    texts = [a for a in frac['dl'] if a[0] == 't']
    assert texts[0][2] != texts[1][2]
    assert any(a[0] == 'l' for a in frac['dl'])
    power = lay('x^(y^2)')
    ts = {a[3]: a for a in power['dl'] if a[0] == 't'}
    assert all(len(a) == 4 for a in ts.values())        # one font: no size field
    assert ts['2'][2] < ts['y'][2] < ts['x'][2]          # each script level is raised again
    assert ts['x'][1] < ts['y'][1] < ts['2'][1]


def test_scripts_stay_sensible_with_one_font():
    for source, most in (('x^2', 25), ('2/3', 35), ('x^(y^2)', 40),
                         ('integrate(x,x,0,1)', 50), ('sum(k^2,k,1,10)', 62),
                         ('limit(sin(x)/x,x,0)', 42), ('surd(x,3)', 26)):
        box = lay(source)
        assert box['h'] <= most, (source, box['h'])


def test_fitting_scroll_and_clip():
    box = lay('abcdefghij+klmnopqrstuvwxyz', width=60, height=36)
    assert box['overflow'] and box['w'] > 60
    paint(box, 10, 20, scrollx=25)
    assert cells(TD.CALLS)
    for left, top, right, bottom in cells(TD.CALLS):
        assert 10 <= left and right < 70 and 20 <= top and bottom < 56
    for name, *args in TD.CALLS:
        if name == 'draw_line':
            assert 10 <= args[0] < 70 and 10 <= args[2] < 70
            assert 20 <= args[1] < 56 and 20 <= args[3] < 56


def test_negative_scroll_centers_and_the_screen_clips():
    box = lay('2/3')
    paint(box, 10, 40, (box['w'] - 300) // 2, (box['h'] - 92) // 2)
    xs = [c[0] for c in cells(TD.CALLS)]
    assert all(140 <= x <= 170 for x in xs)
    TD.reset()
    D.reset()
    paint(lay('x+1'), 300, 200)                  # mostly off the screen
    assert TD.OFFSCREEN == []


def test_parser_session_and_arena_untouched():
    before = K.NN
    box = lay('x+1')
    assert K.NN == before and not box['fallback']


def test_caps_and_messages_fallback():
    assert lay('(' * 25 + 'x' + ')' * 25)['fallback']
    assert lay('+'.join(['x'] * 202))['fallback']
    assert lay('does not exist: left 0, right 1')['fallback']


def test_cache_bounds():
    lay('sqrt(2)')
    for n in range(10):
        lay('x+' + str(n))
    assert len(D.CACHE) <= 6 and D.CACHE_BYTES <= 4096
    D.clear_cache()
    assert not D.CACHE and D.CACHE_BYTES == 0


def test_palette_and_native_calls():
    D.theme(1)
    box = lay('sqrt(2)/pi')
    paint(box, 10, 20)
    assert set(TD.COUNTS) <= ON_EVO
    assert all(a[0] != 'draw_text' or all(ord(c) < 128 for c in a[3]) for a in TD.CALLS)
    assert D.COLORS['BG'] == (12, 15, 20)
    assert TD.COUNTS['set_color'] == 1                  # one color for a whole answer


@pytest.mark.parametrize('s', ['1/(x+1)', 'x^(y^2)', 'sqrt(x+1)',
    'integrate(x^2,x,0,1)', 'sum(k^2,k,1,10)', 'limit(sin(x)/x,x,0)', 'surd(x+1,3)'])
def test_layout_text_cells_do_not_overlap(s):
    box = lay(s)
    paint(box, 0, 0)
    assert not TD.OVERDRAW


def test_every_t1_print_golden_parses():
    from pathlib import Path
    path = Path(__file__).parent / 'golden' / 'print_t1.txt'
    for line in path.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        parts = line.split('|', 2)
        if len(parts) == 3 and not parts[-1].startswith('!'):
            assert not lay(parts[-1])['fallback'], line


# -- the EVO helpers: exact rectangles, the text anchor, clipping and the color cache ----------

def test_rect_is_exact_and_clipped():
    D.rect(5, 7, 3, 2, (1, 2, 3))
    assert TD.CALLS == [('set_color', 1, 2, 3), ('fill_rect', 4, 6, 4, 3)]
    assert TD.pixel(5, 7) == TD.pixel(7, 8) == (1, 2, 3)
    assert TD.pixel(4, 7) == TD.pixel(8, 8) == TD.pixel(5, 6) == TD.pixel(5, 9) == (255,) * 3
    del TD.CALLS[:]
    D.rect(0, 0, 320, 210)
    D.rect(-5, -5, 10, 10)
    D.rect(315, 205, 50, 50)
    D.rect(1, 1, 1, 1)                                  # one pixel: fill_rect(0, 0, 2, 2)
    D.rect(10, 10, 0, 5)                                # empty: no call (w + 1 would be 1)
    D.rect(400, 10, 5, 5)
    assert TD.CALLS == [('fill_rect', -1, -1, 321, 211), ('fill_rect', -1, -1, 6, 6),
                        ('fill_rect', 314, 204, 6, 6), ('fill_rect', 0, 0, 2, 2)]
    assert TD.OFFSCREEN == []


def test_text_anchor_and_clipping():
    D.text('ab', 3, 20)
    assert TD.CALLS == [('draw_text', 3, 37, 'ab')]
    assert TD.texts() == [(3, 20, 'ab', (0, 0, 0))]
    del TD.CALLS[:]
    D.text('abcdef', 290, 0)                            # 3 characters fit: 290..319
    D.text('abcdef', -15, 30)                           # the first 2 are cut
    D.text('low', 0, 196)                               # rows 196..210: off the screen
    D.text('top', 0, -1)
    D.text('', 0, 0)
    assert TD.CALLS == [('draw_text', 290, 17, 'abc'), ('draw_text', 5, 47, 'cdef')]
    assert TD.OFFSCREEN == []


def test_color_is_cached():
    D.color((1, 2, 3))
    D.color((1, 2, 3))
    D.text('x', 0, 0, (1, 2, 3))
    D.rect(0, 20, 5, 5, (1, 2, 3))
    assert TD.COUNTS['set_color'] == 1
    D.reset()                                           # e.g. after the shim was reset
    D.color((1, 2, 3))
    assert TD.COUNTS['set_color'] == 2


def test_lines_are_clipped_to_the_screen():
    D.line(-50, 100, 400, 100, (0, 0, 0))
    D.line(500, 500, 600, 600)
    assert TD.CALLS[1:] == [('draw_line', 0, 100, 319, 100)]
    assert TD.OFFSCREEN == []


def test_wrap():
    assert D.wrap('Differentiate once, or n times, in x.', 31) == \
        ['Differentiate once, or n times,', 'in x.']
    assert D.wrap('a' * 40, 31) == ['a' * 31, 'a' * 9]
    assert D.wrap('', 31) == [] and D.wrap('short', 31) == ['short']


def test_cache_is_lru():
    D.clear_cache()
    for n in range(6):
        lay('x+' + str(n))
    lay('x+0')                         # a hit moves it to the end
    lay('x+9')                         # so x+1 gives way, not x+0
    keys = [c[0][0] for c in D.CACHE]
    assert 'x+0' in keys and 'x+1' not in keys
    D.clear_cache()
