"""Structural 2D layout and clipped drawing, independent of platform glyph fonts."""
import pytest
import draw as D
import ti_graphics as G
import parse as P
import node as K


@pytest.fixture(autouse=True)
def screen():
    G.reset()
    D.clear_cache()
    D.theme(0)


@pytest.mark.parametrize('source,kind', [
    ('2/3', 'frac'), ('x^(2/3)', 'sup'), ('sqrt(x+1)', 'sqrt'),
    ('surd(x+1,3)', 'root'), ('(x+1)*(x-1)', 'paren'), ('abs(x+1)', 'abs'),
    ('sin(x)', 'call'), ('integrate(x^2,x)', 'integral'),
    ('integrate(x,x,0,1)', 'integral'), ('diff(x^2,x)', 'derivative'),
    ('sum(k^2,k,1,10)', 'sum'), ('limit(sin(x)/x,x,0)', 'limit'),
    ('[x,2/3]', 'list'), ('x=1,x=2', 'row'), ('O(x^6)', 'call'),
])
def test_special_layout(source, kind):
    box = D.layout(source)
    assert not box['fallback'], source
    assert kind in box['kinds']
    assert box['w'] > 0 and box['h'] > 0
    assert all(isinstance(v, int) for item in box['dl'] for v in item[1:3])


def test_fraction_is_stacked_and_exponent_is_small():
    frac = D.layout('2/3')
    texts = [a for a in frac['dl'] if a[0] == 't']
    assert texts[0][2] != texts[1][2]
    assert any(a[0] == 'l' for a in frac['dl'])
    power = D.layout('x^(y^2)')
    ts = {a[3]: a for a in power['dl'] if a[0] == 't'}
    assert ts['x'][4] == 0 and ts['y'][4] == ts['2'][4] == 1
    assert ts['2'][2] < ts['y'][2] < ts['x'][2]


def test_fitting_scroll_and_clip():
    box = D.layout('abcdefghij+klmnopqrstuvwxyz', width=60, height=36)
    assert box['small'] and box['overflow']
    D.paint(box, 10, 20, scrollx=25)
    for name, *args in G.CALLS:
        if name == 'drawString':
            assert 10 <= args[1] < 70 and 20 <= args[2] < 56
        elif name == 'drawLine':
            assert 10 <= args[0] < 70 and 10 <= args[2] < 70
            assert 20 <= args[1] < 56 and 20 <= args[3] < 56


def test_parser_session_and_arena_untouched():
    before = K.NN
    box = D.layout('x+1')
    assert K.NN == before and not box['fallback']


def test_caps_and_messages_fallback():
    assert D.layout('(' * 25 + 'x' + ')' * 25)['fallback']
    assert D.layout('+'.join(['x'] * 202))['fallback']
    assert D.layout('does not exist: left 0, right 1')['fallback']


def test_cache_and_metrics_fallback(monkeypatch):
    monkeypatch.setattr(G, 'string_size', None)
    D.layout('sqrt(2)')
    for n in range(10):
        D.layout('x+' + str(n))
    assert len(D.CACHE) <= 5 and D.CACHE_BYTES <= 4096
    D.clear_cache()
    assert not D.CACHE and D.CACHE_BYTES == 0


def test_palette_and_native_calls():
    D.theme(1)
    box = D.layout('sqrt(2)/pi')
    D.paint(box, 10, 20)
    assert not G.assumed_calls()
    assert all(a[0] != 'drawString' or all(ord(c) < 128 for c in a[1]) for a in G.CALLS)
    assert D.COLORS['BG'] == (12, 15, 20)


@pytest.mark.parametrize('s', ['1/(x+1)', 'x^(y^2)', 'sqrt(x+1)',
    'integrate(x^2,x,0,1)', 'sum(k^2,k,1,10)', 'limit(sin(x)/x,x,0)'])
def test_layout_text_cells_do_not_overlap(s):
    box = D.layout(s)
    D.paint(box, 0, 0)
    assert not G.OVERDRAW


def test_every_t1_print_golden_parses():
    from pathlib import Path
    path = Path(__file__).parent / 'golden' / 'print_t1.txt'
    for line in path.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        parts = line.split('|', 2)
        if len(parts) == 3 and not parts[-1].startswith('!'):
            assert not D.layout(parts[-1])['fallback'], line
