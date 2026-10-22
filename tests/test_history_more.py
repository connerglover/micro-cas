"""v1.0.1: the earlier-history indicator (docs/notes/MATHPRINT.md 7.1, 7.2).

When older history entries are hidden above the page, the top of the history area shows an
up arrow (a stroked glyph, draw.GLYPHS) and 'Press up for earlier entries' in the SUB color.
Its row is reserved only then: no entry is drawn in the band, and with everything shown the
entries keep the whole area. It is part of a full redraw only; typing never repaints it.
"""
import keyscript as KS
import ti_draw as TD

MORE = 'earlier entries'
FLAT6 = ''.join('%d+%d{enter}' % (i, i) for i in range(1, 7))       # PAGEMAX + 1 entries
FLAT5 = ''.join('%d+%d{enter}' % (i, i) for i in range(1, 6))       # all fit
# three flat entries over three stacked ones: without the reserved band the 3+3 entry would
# start at row 25, inside the indicator's row; one entry fewer and all fit (1+1 at row 27)
TALL = '1+1{enter}2+2{enter}3+3{enter}1{frac}3{enter}{frac}x{right}2{enter}{frac}y{right}2{enter}'


def ui(s):
    return s.mods['ui']


def shown(s):
    return [t for t in s.texts if MORE in t[2]]


def band_free(s):
    """Nothing but the indicator (text and its arrow strokes) in rows 20..37 of the stage."""
    for t in s.texts:
        if 20 <= t[1] <= 37 and MORE not in t[2]:
            return False
    for c in s.calls:
        if c[0] == 'draw_line' and 20 <= min(c[2], c[4]) <= 37 and max(c[1], c[3]) > 16:
            return False
    return True


def clean(s):
    assert s.overdraw == [] and s.offscreen == []


def test_long_history_shows_the_indicator_in_sub():
    s = KS.run(FLAT6)
    t = shown(s)
    assert len(t) == 1
    sub = s.mods['draw'].COLORS['SUB']
    assert t[0][1] == 21 and t[0][3] == tuple(sub)
    assert t[0][2].startswith('Press up') and len(t[0][2]) <= 31
    assert '1+1' not in s.screen and '2+2' in s.screen        # the oldest is the hidden one
    clean(s)


def test_short_history_has_no_indicator():
    for script in ('', '1+1{enter}', FLAT5):
        s = KS.run(script)
        assert shown(s) == [], script
        clean(s)


def test_tall_entries_reserve_the_band():
    s = KS.run(TALL)
    assert len(shown(s)) == 1
    assert band_free(s)
    clean(s)


def test_scroll_mode_at_the_newest_and_the_oldest():
    s = KS.run(FLAT6 + '{up}')
    assert ui(s).MODE == 1 and ui(s).SEL == 5
    assert len(shown(s)) == 1
    clean(s)
    s = KS.run(FLAT6 + '{up}' * 6)
    assert ui(s).SEL == 0 and '1+1' in s.screen
    assert shown(s) == []
    clean(s)
    s = KS.run(TALL + '{up}' * 6)
    assert ui(s).SEL == 0 and shown(s) == []
    s = KS.run(TALL + '{up}' * 3)
    assert len(shown(s)) == 1 and band_free(s)
    clean(s)


def test_clear_deletes_entries_until_the_history_fits():
    s = KS.run(FLAT6 + '{up}{clear}')
    assert len(s.hist) == 5 and shown(s) == []
    s = KS.run(TALL + '{up}{clear}')
    assert len(s.hist) == 5 and shown(s) == []
    assert [t[1] for t in s.texts if t[2] == '1+1'] == [27]  # the band is not kept
    clean(s)
    s = KS.run(TALL + '{up}' + '{clear}' * 5)
    assert len(s.hist) == 1 and shown(s) == []
    clean(s)


def test_typing_never_repaints_the_indicator():
    s = KS.run(FLAT6 + '{snap:a}2+3x')
    n = s.snaps[0][2]
    after = [c for c in s.calls[n:] if c[0] == 'draw_text']
    assert after and all(MORE not in c[3] for c in after)
    assert len(shown(s)) == 1                               # still on the screen
    full = KS.run(FLAT6 + '{snap:a}')
    assert len(shown(full)) == 1
    clean(s)


def test_full_redraws_after_menus_forms_and_scrolls_keep_it():
    # a closed menu, a cancelled calculation, F5 and a wide answer's DX scroll all repaint
    # the page in full; the indicator comes back with it and the band stays free
    for tail in ('{math}{clear}', '{vars}{clear}',
                 'integrate(sin(x)^9*cos(x)^7,x){enter}{clear@1}', '{f5}',
                 'expand((x+1)^9){enter}{right}{right}', '{frac}{frac}{frac}1{clear}'):
        s = KS.run(FLAT6 + tail)
        assert len(shown(s)) == 1, tail
        assert band_free(s), tail
        clean(s)
