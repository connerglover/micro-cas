"""M0.2: the desktop shims (shim/ti_system.py, shim/ti_draw.py, shim/ti_graphics.py) and
tests/support/keyscript.py.

DESIGN.md section 20.9: key replay, escape injection, a draw transcript, the screen-text dump,
and running an entry program with real depths. The UI draws through ti_draw (FASTBOOT.md);
the ti_graphics shim remains for the older release checker (build/check_release.py).
"""
import os
import struct
import sys
import zlib

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, 'tests', 'support'), os.path.join(_ROOT, 'shim')):
    if _p not in sys.path:              # conftest normally did this already
        sys.path.insert(0, _p)

import keyscript as KS                  # noqa: E402
import ti_draw as TD                    # noqa: E402
import ti_graphics as G                 # noqa: E402
import ti_system as TS                  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_shims():
    KS.reset_shims()
    G.reset()
    yield
    KS.reset_shims()
    G.reset()


# ====================================================================== ti_system: key replay
def test_wait_key_replays_then_stops():
    TS.load([93, 95, 94, 105])
    assert [TS.wait_key() for _ in range(4)] == [93, 95, 94, 105]
    with pytest.raises(TS.StopScript):
        TS.wait_key()
    with pytest.raises(TS.StopScript):  # and keeps stopping
        TS.wait_key()
    assert TS.KEYS_READ == [93, 95, 94, 105]
    assert TS.OVERRUN[0] == 2


def test_stopscript_escapes_the_entry_loop_handlers():
    # the event loop (DESIGN 16.2) catches Exception and KeyboardInterrupt; StopScript must pass
    assert issubclass(TS.StopScript, BaseException)
    assert not issubclass(TS.StopScript, Exception)
    assert not issubclass(TS.StopScript, KeyboardInterrupt)
    TS.load([])
    caught = None
    try:
        try:
            TS.wait_key()
        except (Exception, KeyboardInterrupt):
            caught = 'handler'
    except TS.StopScript:
        caught = 'stop'
    assert caught == 'stop'


def test_feed_and_remaining():
    TS.load([92])
    TS.feed([93, 94])
    assert TS.remaining() == [92, 93, 94]
    assert TS.wait_key() == 92
    assert TS.remaining() == [93, 94]


def test_bad_items_rejected():
    with pytest.raises(ValueError):
        TS.load(['5'])
    with pytest.raises(ValueError):
        TS.after(0)


def test_idle_polls():
    TS.load([])
    assert TS.get_key() == TS.NOKEY == 0
    assert TS.getKey() == 0
    assert TS.escape() is False
    assert TS.POLLS == 3


# ====================================================================== ti_system: injection
def test_clear_injected_at_nth_poll_through_escape():
    TS.load([105, TS.after(3)])
    assert TS.wait_key() == 105
    assert [TS.escape() for _ in range(5)] == [False, False, True, False, False]
    assert TS.FIRED == [(3, TS.CLEAR)]
    assert TS.BUF == []                 # escape consumed the press
    with pytest.raises(TS.StopScript):
        TS.wait_key()
    assert TS.MISSED == []


def test_clear_injected_through_get_key():
    TS.load([105, TS.after(2)])
    TS.wait_key()
    assert [TS.get_key() for _ in range(3)] == [0, 45, 0]
    assert TS.escape() is False         # one press, one consumer


def test_injection_relative_to_its_key():
    # the second ENTER's press counts polls from that ENTER, not from the start
    TS.load([105, 105, TS.after(2), 92])
    TS.wait_key()
    for _ in range(10):                 # the first computation polls 10 times, no press
        assert TS.escape() is False
    assert TS.wait_key() == 105
    assert [TS.escape(), TS.escape()] == [False, True]
    assert TS.wait_key() == 92
    assert TS.FIRED == [(12, TS.CLEAR)]


def test_marker_before_key_arms_for_that_key():
    TS.load([TS.after(1), 105])
    assert TS.wait_key() == 105
    assert TS.escape() is True


def test_unfired_injection_is_missed_not_delivered():
    TS.load([105, TS.after(50), 92])
    TS.wait_key()
    for _ in range(3):
        TS.escape()                     # a short computation: 3 polls only
    assert TS.wait_key() == 92          # the press never happened
    assert TS.MISSED == [(50, TS.CLEAR)]
    assert TS.FIRED == []


def test_typeahead_key_reaches_wait_key_first():
    TS.load([105, TS.after(1, 83), 92])
    TS.wait_key()
    assert TS.escape() is False         # a digit is not [clear]
    assert TS.wait_key() == 83          # typed during the computation
    assert TS.wait_key() == 92


def test_cleared_computation_does_not_leave_a_clear_key():
    TS.load([105, TS.after(1), 92])
    TS.wait_key()
    assert TS.escape() is True
    assert TS.wait_key() == 92


def test_unconsumed_clear_reaches_wait_key():
    TS.load([105, TS.after(1), 92])
    TS.wait_key()
    TS.get_key()                        # consumed by get_key: returns 45
    TS.load([105, TS.after(1), 92])
    TS.wait_key()
    TS.press(TS.CLEAR)                  # pressed, but nobody polls
    assert TS.wait_key() == TS.CLEAR
    assert TS.escape() is False         # the latch went with the key


def test_on_raises_keyboard_interrupt():
    TS.load([105, TS.after(2, TS.ON), TS.ON, 92])
    TS.wait_key()
    TS.escape()
    with pytest.raises(KeyboardInterrupt):
        TS.escape()                     # the 2nd poll
    with pytest.raises(KeyboardInterrupt):
        TS.wait_key()                   # [on] while idle
    assert TS.wait_key() == 92


def test_latch_clear_model():
    TS.load([45, 105])
    TS.LATCH_CLEAR = True
    assert TS.wait_key() == 45
    assert TS.wait_key() == 105
    assert TS.escape() is True          # stale latch from the [clear] read by wait_key
    TS.load([45, 105])                  # load() resets LATCH_CLEAR to False
    TS.wait_key()
    TS.wait_key()
    assert TS.escape() is False


def test_marks_call_hook_when_idle():
    seen = []
    TS.load([105, TS.mark('a'), TS.after(1), 92, TS.mark('b')])
    TS.MARK_HOOK[0] = lambda lab: seen.append((lab, TS.POLLS))
    TS.wait_key()
    assert seen == []                   # not while the computation runs
    TS.escape()
    TS.escape()
    assert TS.wait_key() == 92
    assert seen == [('a', 2)]
    with pytest.raises(TS.StopScript):
        TS.wait_key()
    assert seen == [('a', 2), ('b', 2)]
    assert TS.FIRED == []               # the after(1) belonged to key 92, nobody polled
    assert TS.MISSED == [(3, TS.CLEAR)]


def test_other_ti_system_calls():
    TS.load([92, 45, 93])
    TS.disp_clr()
    TS.disp_at(3, 'hi', 'left')
    TS.disp_cursor(0)
    TS.sleep(0.5)
    TS.wait(1)
    TS.disp_wait()                      # reads keys until [clear]
    assert TS.wait_key() == 93
    TS.store_list('L1', [1, 2])
    assert TS.recall_list('L1') == [1, 2]
    assert TS.recall_list('L2') == []
    assert TS.recall_RegEQ() == ''
    assert TS.CLOCK[0] == 1.5
    names = [c[0] for c in TS.CALLS]
    assert names == ['disp_clr', 'disp_at', 'disp_cursor', 'sleep', 'wait', 'disp_wait',
                     'store_list', 'recall_list', 'recall_list', 'recall_RegEQ']
    for n in TS.VERIFIED:
        assert callable(getattr(TS, n))


# ====================================================================== ti_graphics: transcript
def test_transcript_records_calls_in_order():
    G.setColor(247, 248, 250)
    G.fillRect(0, 14, 320, 144)
    G.setColor((17, 20, 25))
    G.setFont(1)
    G.drawString('x^2', 10, 20)
    G.drawLine(0, 0, 5, 5)
    G.setPen(1, 0)
    assert G.CALLS == [('setColor', 247, 248, 250), ('fillRect', 0, 14, 320, 144),
                       ('setColor', 17, 20, 25), ('setFont', 1), ('drawString', 'x^2', 10, 20),
                       ('drawLine', 0, 0, 5, 5), ('setPen', 1, 0)]
    assert G.transcript_text().splitlines() == [
        'setColor 247 248 250', 'fillRect 0 14 320 144', 'setColor 17 20 25', 'setFont 1',
        "drawString 'x^2' 10 20", 'drawLine 0 0 5 5', 'setPen 1 0']


def test_queries_are_counted_not_transcribed():
    G.string_size('abc')
    G.getPixel(0, 0)
    G.hsv_to_rgb(0, 1, 1)
    G.fillRect(0, 0, 1, 1)
    assert G.CALLS == [('fillRect', 0, 0, 1, 1)]
    assert G.COUNTS == {'string_size': 1, 'getPixel': 1, 'hsv_to_rgb': 1, 'fillRect': 1}


def test_transcript_text_is_ascii_and_stable():
    G.drawString(chr(0x3c0) + '/2', 0, 0)
    G.fillPolygon([(0, 0), (4, 0), (0, 4)])
    t = G.transcript_text()
    t.encode('ascii')
    assert t.splitlines() == ["drawString '\\u03c0/2' 0 0", 'fillPolygon ((0,0),(4,0),(0,4))']


def test_ints_required_like_micropython():
    with pytest.raises(TypeError):
        G.fillRect(1.5, 0, 2, 2)
    with pytest.raises(TypeError):
        G.drawString('a', 0, 2.0)
    with pytest.raises(TypeError):
        G.setColor(1.0, 2, 3)
    with pytest.raises(ValueError):
        G.setColor(256, 0, 0)
    with pytest.raises(TypeError):
        G.setColor(1, 2)
    with pytest.raises(TypeError):
        G.drawString(5, 0, 0)
    with pytest.raises(ValueError):
        G.setFont(7)
    assert G.CALLS == []


def test_names():
    for n in G.VERIFIED + G.ASSUMED:
        assert callable(getattr(G, n))
    G.drawCircle(10, 10, 3)
    G.fillRect(0, 0, 1, 1)
    assert G.assumed_calls() == ['drawCircle']


# ====================================================================== ti_graphics: screen
def test_pixels_and_clipping():
    G.setColor(255, 0, 0)
    G.fillRect(-5, -5, 10, 10)          # clipped, no error
    assert G.getPixel(0, 0) == (255, 0, 0)
    assert G.getPixel(4, 4) == (255, 0, 0)
    assert G.getPixel(5, 5) == (255, 255, 255)
    G.setPixel(319, 209, (0, 0, 255))
    assert G.pixel(319, 209) == (0, 0, 255)
    assert G.getPixel(400, 0) == (0, 0, 0)
    G.setColor(0, 255, 0)
    G.drawLine(10, 10, 20, 15)
    assert G.pixel(10, 10) == G.pixel(20, 15) == (0, 255, 0)
    G.drawRect(30, 30, 5, 4)
    assert G.pixel(30, 30) == G.pixel(34, 33) == (0, 255, 0)
    assert G.pixel(32, 31) == (255, 255, 255)
    G.drawLine(-100, 300, 500, -40)     # far off screen: clipped silently


def test_fills():
    G.setColor(0, 0, 0)
    G.fillCircle(50, 50, 5)
    assert G.pixel(50, 50) == G.pixel(55, 50) == G.pixel(50, 45) == (0, 0, 0)
    assert G.pixel(54, 54) == (255, 255, 255)
    G.fillPolygon([(100, 100), (110, 100), (100, 110)])
    assert G.pixel(101, 101) == (0, 0, 0)
    assert G.pixel(109, 109) == (255, 255, 255)
    G.fillArc(200, 100, 21, 21, 0, 90)  # the upper-right quarter
    assert G.pixel(215, 105) == (0, 0, 0)
    assert G.pixel(205, 115) == (255, 255, 255)
    G.cls()
    assert G.pixel(50, 50) == (255, 255, 255)


def test_hsv_to_rgb():
    assert G.hsv_to_rgb(0, 1, 1) == [255, 0, 0]
    assert G.hsv_to_rgb(120, 1, 1) == [0, 255, 0]
    assert G.hsv_to_rgb(240, 1, 0.5) == [0, 0, 128]


def test_string_size_per_font():
    assert G.string_size('abc') == (24, 18)     # font 0: FlowCE big metrics
    G.setFont(1)
    assert G.string_size('abc') == (18, 12)     # font 1: small
    G.configure(fonts={0: (10, 12, 3)})
    assert G.string_size('ab') == (20, 15)
    G.reset()
    assert G.FONTS == {0: (8, 14, 4), 1: (6, 9, 3)}


def test_text_items_and_screen_text():
    G.drawString('RAD', 2, 0)
    G.drawString('2+3', 0, 40)
    G.setFont(1)
    G.drawString('5', 300, 46)
    assert G.texts() == [(2, 0, 'RAD', 0, (0, 0, 0)), (0, 40, '2+3', 0, (0, 0, 0)),
                         (300, 46, '5', 1, (0, 0, 0))]
    assert G.screen_text() == 'RAD\n2+3 5'
    assert G.find('+') == [(0, 40, '2+3', 0, (0, 0, 0))]
    assert G.texts_in(0, 0, 320, 14) == [(2, 0, 'RAD', 0, (0, 0, 0))]
    assert G.screen_text(0, 30, 320, 40) == '2+3 5'


def test_adjacent_items_join_without_space():
    G.drawString('x', 10, 50)           # 8 px wide in font 0
    G.setFont(1)
    G.drawString('2', 18, 44)           # superscript right after it
    G.drawString('+1', 40, 50)
    assert G.screen_text() == 'x2 +1'


def test_fill_covering_text_erases_it():
    G.drawString('old', 10, 100)
    G.setColor(255, 255, 255)
    G.fillRect(0, 95, 320, 30)
    assert G.texts() == []
    assert G.OVERDRAW == []


def test_partial_fill_keeps_text_until_fully_covered():
    G.drawString('abcd', 0, 0)          # 32 x 18
    G.fillRect(10, 0, 2, 18)            # a caret through the text
    assert G.screen_text() == 'abcd'
    G.fillRect(0, 0, 16, 18)
    assert G.screen_text() == 'abcd'
    G.fillRect(16, 0, 16, 18)           # two fills together cover it
    assert G.screen_text() == ''


def test_lines_never_erase_text():
    G.drawString('ab', 0, 0)
    for y in range(0, 18):
        G.drawLine(0, y, 15, y)
    assert G.screen_text() == 'ab'


def test_overdraw_is_logged_but_identical_redraw_is_not():
    G.drawString('x+1', 0, 0)
    G.drawString('x+1', 0, 0)           # same text, same place: harmless
    assert G.OVERDRAW == []
    assert G.screen_text() == 'x+1'
    G.drawString('x+2', 0, 0)           # different text without a clear: garbled on device
    assert G.OVERDRAW == [('x+1', 0, 0, 'x+2', 0, 0)]
    assert G.screen_text() == 'x+2'


def test_offscreen_text():
    G.drawString('gone', 400, 0)
    G.drawString('half', 300, 0)        # 32 px wide, 20 visible
    assert G.screen_text() == 'half'
    assert G.CALLS[0] == ('drawString', 'gone', 400, 0)


def test_baseline_convention():
    G.configure(text_y='baseline')
    G.drawString('a', 0, 20)
    assert G.texts() == [(0, 6, 'a', 0, (0, 0, 0))]     # top = 20 - ascent 14


def test_push_pop_image_restores_pixels_and_text():
    G.drawString('under', 20, 50)
    G.drawString('outside', 20, 150)
    G.pushImage(0, 40, 320, 60)
    G.setColor(200, 200, 200)
    G.fillRect(0, 40, 320, 60)          # a menu card covers the stage
    G.setColor(0, 0, 0)
    G.drawString('menu', 30, 60)
    assert G.screen_text() == 'menu\noutside'
    G.popImage()
    assert G.screen_text() == 'under\noutside'
    assert G.pixel(5, 45) == (255, 255, 255)
    with pytest.raises(IndexError):
        G.popImage()


def test_push_pop_keeps_changes_outside_the_region():
    G.drawString('wide text', 0, 50)    # 72 px wide
    G.pushImage(0, 40, 40, 30)
    G.setColor(255, 255, 255)
    G.fillRect(0, 40, 40, 30)
    G.fillRect(40, 40, 40, 30)          # outside the pushed region: erased for good
    assert G.texts() == []
    G.popImage()                        # only the left part comes back: still visible
    assert G.screen_text() == 'wide text'


def test_screenshot_png(tmp_path):
    G.setColor(36, 92, 204)
    G.fillRect(0, 0, 10, 10)
    G.drawString('hi', 20, 20)
    p = G.screenshot(str(tmp_path / 's.png'), scale=2)
    data = open(p, 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    w, h = struct.unpack('>II', data[16:24])
    assert (w, h) == (640, 420)
    i = data.index(b'IDAT')
    n = struct.unpack('>I', data[i - 4:i])[0]
    raw = zlib.decompress(data[i + 4:i + 4 + n])
    assert len(raw) == 420 * (1 + 640 * 3)
    assert raw[1:4] == bytes((36, 92, 204))


# ====================================================================== ti_draw: the EVO's semantics
def test_ti_draw_transcript_and_color_count():
    TD.set_color(247, 248, 250)
    TD.fill_rect(-1, -1, 321, 211)
    TD.set_color(17, 20, 25)
    TD.draw_text(5, 19, 'RAD')
    TD.draw_line(0, 19, 319, 19)
    assert TD.CALLS == [('set_color', 247, 248, 250), ('fill_rect', -1, -1, 321, 211),
                        ('set_color', 17, 20, 25), ('draw_text', 5, 19, 'RAD'),
                        ('draw_line', 0, 19, 319, 19)]
    assert TD.transcript_text().splitlines() == [
        'set_color 247 248 250', 'fill_rect -1 -1 321 211', 'set_color 17 20 25',
        "draw_text 5 19 'RAD'", 'draw_line 0 19 319 19']
    assert TD.COUNTS['set_color'] == 2 and TD.OFFSCREEN == []
    assert TD.get_screen_dim() == [319, 209]
    for n in TD.VERIFIED:
        assert callable(getattr(TD, n))


def test_ti_draw_strict_arguments():
    with pytest.raises(TypeError):
        TD.set_color((1, 2, 3))             # one tuple is not three channels
    with pytest.raises(TypeError):
        TD.set_color(1.0, 2, 3)
    with pytest.raises(ValueError):
        TD.set_color(256, 0, 0)
    with pytest.raises(TypeError):
        TD.fill_rect(1.5, 0, 2, 2)
    with pytest.raises(TypeError):
        TD.draw_text(0, 17, 5)
    with pytest.raises(TypeError):
        TD.draw_text(0, 17.0, 'a')
    with pytest.raises(TypeError):
        TD.draw_line(0, 0, 1, 1.0)
    for w, h in ((1, 5), (5, 1), (0, 0), (-3, 4)):
        with pytest.raises(TD.tidrawException):
            TD.fill_rect(10, 10, w, h)
    assert TD.CALLS == []


def test_ti_draw_fill_rect_fills_the_interior_only():
    TD.set_color(255, 0, 0)
    TD.fill_rect(10, 20, 4, 3)              # columns 11..13, rows 21..22
    assert TD.pixel(11, 21) == TD.pixel(13, 22) == (255, 0, 0)
    for x, y in ((10, 21), (14, 21), (11, 20), (11, 23)):
        assert TD.pixel(x, y) == (255, 255, 255)
    TD.fill_rect(-1, -1, 321, 211)          # the whole screen, nothing off it
    assert TD.pixel(0, 0) == TD.pixel(319, 209) == (255, 0, 0)
    assert TD.OFFSCREEN == []
    TD.fill_rect(-2, 5, 4, 4)               # interior column -1 is off the screen
    TD.fill_rect(300, 200, 21, 11)          # interior reaches column 320 and row 210
    assert TD.OFFSCREEN == [('fill_rect', -2, 5, 4, 4), ('fill_rect', 300, 200, 21, 11)]


def test_ti_draw_text_cell_and_screen_text():
    TD.draw_text(5, 19, 'RAD')              # cell 5..34 x 2..16
    TD.draw_text(10, 189, '2+3')            # cell 10..39 x 172..186
    TD.draw_text(40, 189, 'x')              # adjacent: joins without a space
    assert TD.texts() == [(5, 2, 'RAD', (0, 0, 0)), (10, 172, '2+3', (0, 0, 0)),
                          (40, 172, 'x', (0, 0, 0))]
    assert TD.screen_text() == 'RAD\n2+3x'
    assert TD.screen_text(0, 150, 320, 60) == '2+3x'
    assert TD.find('+') == [(10, 172, '2+3', (0, 0, 0))]
    assert TD.texts_in(0, 0, 320, 19) == [(5, 2, 'RAD', (0, 0, 0))]
    assert TD.OFFSCREEN == []
    TD.draw_text(0, 16, 'a')                # first ink row -1
    TD.draw_text(0, 213, 'b')               # last ink row 210
    TD.draw_text(315, 100, 'c')             # columns 315..324
    assert [c[3] for c in TD.OFFSCREEN] == ['a', 'b', 'c']


def test_ti_draw_fill_erases_text_and_lines_never_do():
    TD.draw_text(10, 117, 'old')            # cell 10..39 x 100..114
    TD.draw_line(0, 105, 319, 105)
    assert TD.screen_text() == 'old'
    TD.fill_rect(19, 99, 2, 17)             # a caret-wide fill: the rest stays visible
    assert TD.screen_text() == 'old'
    TD.set_color(255, 255, 255)
    TD.fill_rect(-1, 98, 321, 18)           # rows 99..114 cover the cell
    assert TD.texts() == [] and TD.OVERDRAW == []


def test_ti_draw_text_does_not_erase_and_overdraw_is_logged():
    TD.draw_text(0, 17, 'x+1')
    TD.draw_text(0, 17, 'x+1')              # the same text again: harmless
    assert TD.OVERDRAW == [] and TD.screen_text() == 'x+1'
    TD.draw_text(10, 17, 'y')               # over a different live text: both stay, garbled
    assert TD.OVERDRAW == [('x+1', 0, 0, 'y', 10, 0)]
    assert len(TD.texts()) == 2


def test_ti_draw_clear_and_screenshot(tmp_path):
    TD.draw_text(0, 17, 'gone')
    TD.clear()
    assert TD.texts() == [] and TD.CALLS[-1] == ('clear',)
    TD.set_color(36, 92, 204)
    TD.fill_rect(-1, -1, 11, 11)
    data = open(TD.screenshot(str(tmp_path / 's.png'), scale=1), 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('>II', data[16:24]) == (320, 210)


# ====================================================================== keyscript: parsing
def test_parse_flowce_style():
    assert KS.parse('2+3{enter}') == [93, 85, 94, 105]       # the Evo keypad (DESIGN 16.4)
    assert KS.parse('*2{enter}') == [65, 93, 105]
    assert KS.parse('{sq}{enter}') == [61, 105]
    assert KS.parse('{x^n}{enter}') == [51, 105]
    assert KS.parse('{<>}') == [95]
    assert KS.parse('{(-)}2{enter}') == [104, 93, 105]
    assert KS.parse('{sto}a{enter}') == [91, 31, 41, 105]
    assert KS.parse('{2nd,(-)}{left}{left}{(-)}{right}*3{enter}') == \
        [21, 104, 24, 24, 104, 26, 65, 94, 105]
    assert KS.parse('{2nd,enter}{105}') == [21, 105, 105]


def test_parse_markers():
    assert KS.parse('{enter}{clear@3}') == [105, ('after', 3, 45)]
    assert KS.parse('{on@7}') == [('after', 7, TS.ON)]
    assert KS.parse('{snap}1{snap:end}{snap}') == \
        [('mark', 'snap1'), 92, ('mark', 'end'), ('mark', 'snap3')]


def test_parse_errors():
    with pytest.raises(ValueError):
        KS.parse('{nosuchkey}')
    with pytest.raises(ValueError):
        KS.parse('{enter')
    with pytest.raises(ValueError):
        KS.parse('A')                   # uppercase other than E has no sequence
    with pytest.raises(ValueError):
        KS.parse('"')


def test_typing_uses_function_keys():
    assert KS.type_keys('sin(x)') == [52, 32, 64]
    assert KS.type_keys('asin(x)') == [21, 52, 32, 64]
    assert KS.type_keys('sqrt(2)') == [21, 61, 93, 64]
    assert KS.type_keys('e^(x)') == [21, 81, 32, 64]
    assert KS.type_keys('ans()') == [21, 104]
    assert KS.type_keys('2pi') == [93, 21, 55]
    assert KS.type_keys('x^2') == [32, 61]
    assert KS.type_keys('3E-2') == [94, 21, 62, 75, 93]
    assert KS.type_keys('y') == [31, 92]
    assert KS.type_keys("y'") == [31, 92, 31, 103]
    assert KS.type_keys('a b') == [31, 41, 31, 102, 31, 42]
    assert KS.type_keys('sin(x)', words=False) == [31, 81, 31, 61, 31, 71, 63, 32, 64]


def test_typing_mathprint_powers_and_fractions():
    # docs/notes/MATHPRINT.md 11.1: x^n (51) opens an exponent box that RIGHT (26) leaves; ^2 is
    # x^2 (61); / is the divide key (55); the fraction key (42) and 2nd x^n are actions
    assert KS.type_keys('x^3+1') == [32, 51, 94, 26, 85, 92]
    assert KS.type_keys('1/2') == [92, 55, 93]
    assert KS.type_keys('x^2') == [32, 61]
    assert KS.type_keys('e^(x)') == [21, 81, 32, 64]
    assert KS.type_keys('x^(2/3)+1') == [32, 51, 63, 93, 55, 94, 64, 85, 92]
    assert KS.type_keys('x^-1') == [32, 51, 75, 92]
    assert KS.type_keys('x^-1*2') == [32, 51, 75, 92, 26, 65, 93]
    assert KS.type_keys('x^23') == [32, 51, 93, 94]
    assert KS.type_keys('x^2^3+1') == [32, 51, 93, 51, 94, 26, 26, 85, 92]
    assert KS.type_keys('2^sin(x)+1') == [93, 51, 52, 32, 64, 26, 85, 92]
    assert KS.type_keys('x^ab') == [32, 51, 31, 41, 26, 31, 42]
    assert KS.type_keys('x^pi+1') == [32, 51, 21, 55, 26, 85, 92]
    assert KS.KEYTEXT[42] == ('@frac', '@templates', 'b')
    assert KS.KEYTEXT[51] == ('^', '@surd', 'd')
    assert KS.decode([32, 51, 94, 26, 85, 92]) == 'x^3+1'
    assert KS.decode([42, 21, 42, 21, 51]) == '{frac}{templates}{surd}'
    assert KS.decode([32, 51, 94, 26, 26]) == 'x^3{right}'


def test_typing_relations_use_the_test_picker():
    assert KS.type_keys('x=2') == [32, 21, 41, 92, 93]
    assert KS.type_keys('x<=2') == [32, 21, 41, 82, 93]
    assert KS.type_keys('x!=2') == [32, 21, 41, 93, 93]
    assert KS.type_keys('3!') == [94, 21, 41, 72]
    assert KS.type_keys('5=>a') == [83, 91, 31, 41]


def test_keytext_matches_design_table():
    # spot checks against DESIGN 16.4, one per row kind
    assert KS.KEYTEXT[52] == ('sin(', 'asin(', 'e')
    assert KS.KEYTEXT[104] == ('-', 'ans()', None)
    assert KS.KEYTEXT[103] == ('.', 'i', "'")
    assert KS.KEYTEXT[22] == ('@setup', '@quit', None)
    assert KS.KEYTEXT[41] == ('@menu:calculus', '@test', 'a')
    assert KS.KEYTEXT[102] == ('0', '@menu:all', ' ')
    for code, name in KS.NAME.items():
        assert KS.KEY[name] == code


def test_typing_round_trips_through_reference_typist():
    import random
    rnd = random.Random(7)
    alphabet = list('0123456789+-*/^(),.abcdefghijklmnopqrstuvwxyz [] {} E\'')
    alphabet = [c for c in alphabet if c not in '{}']
    tokens = alphabet + ['sin(', 'acos(', 'ln(', 'log(', 'sqrt(', 'e^(', '10^(', 'pi',
                         'ans()', '=', '!=', '<', '<=', '>', '>=', '!', '=>', 'theta', '^2',
                         '^-1']
    for _ in range(500):
        s = ''.join(rnd.choice(tokens) for _ in range(rnd.randint(1, 12)))
        assert KS.decode(KS.type_keys(s)) == s, s
        assert KS.decode(KS.type_keys(s, words=False)) == s, s


def test_entry_and_case_helpers():
    assert KS.entry('-x') == [104, 32, 105]
    assert KS.entry('2-x') == [93, 75, 32, 105]
    assert KS.case('5', '{2nd,(-)}{del}7{enter}') == [83, 105, 21, 104, 23, 72, 105]
    assert KS.case('', '{enter}') == [105]
    assert KS.describe([32, 61, 105, ('after', 3, 45), ('mark', 'a')]) == \
        'xttn sq enter {clear@3} {snap:a}'
    assert KS.decode([21, 105, 21, 41, 92]) == '{entry}='


# ====================================================================== keyscript: running
ENTRY = '''\
import ti_system as TS
import fakeui as U
U.boot()
while True:
    try:
        k = TS.wait_key()
        a = U.key(k)
        if a is U.QUIT:
            break
        if a is not None:
            r = U.go(a)
            U.show(a, r)
    except KeyboardInterrupt:
        U.panic(1)
    except Exception:
        U.panic(3)
'''

FAKEUI = '''\
import ti_system as TS
import ti_draw as TD
QUIT = ['quit']
LINE = ['']
HIST = []
ANS = ['0']
MOD = [0]
DIG = {102: '0', 92: '1', 93: '2', 94: '3', 82: '4', 83: '5', 84: '6', 72: '7', 73: '8',
       74: '9', 85: '+'}
ESC = [None]


def boot():
    ESC[0] = TS.escape
    TD.set_color(255, 255, 255)
    TD.fill_rect(-1, -1, 321, 211)
    TD.set_color(0, 0, 0)
    TD.draw_text(2, 17, 'RAD')


def key(k):
    if k == 21:
        MOD[0] = 1
        return None
    if MOD[0] == 1 and k == 22:
        return QUIT
    MOD[0] = 0
    if k == 105:
        job = ('eval', LINE[0])
        LINE[0] = ''
        return job
    if k == 45:
        LINE[0] = ''
    elif k in DIG:
        LINE[0] = LINE[0] + DIG[k]
    edit()
    return None


def edit():
    TD.set_color(255, 255, 255)
    TD.fill_rect(-1, 169, 321, 21)
    TD.set_color(0, 0, 0)
    TD.draw_text(0, 189, LINE[0])


def go(job):
    text = job[1]
    total = 0
    for part in text.split('+'):
        total = total + work(int(part))
        if ESC[0]():
            return 'Interrupted'
    ANS[0] = str(total)
    return ANS[0]


def work(n):
    return leaf(n)


def leaf(n):
    return n


def show(job, r):
    HIST.append((job[1], r))
    TD.set_color(255, 255, 255)
    TD.fill_rect(-1, 18, 321, 152)
    TD.set_color(0, 0, 0)
    y = 19
    for inp, res in HIST[-4:]:
        TD.draw_text(0, y + 17, inp)
        TD.draw_text(310 - 10 * len(res), y + 35, res)
        y = y + 36
    edit()


def panic(n):
    HIST.append(('', 'panic %d' % n))
'''


@pytest.fixture
def fake_entry(tmp_path, monkeypatch):
    d = tmp_path / 'dev'
    d.mkdir()
    (d / 'casevo.py').write_text(ENTRY)
    (d / 'fakeui.py').write_text(FAKEUI)
    monkeypatch.syspath_prepend(str(d))
    sys.modules.pop('fakeui', None)
    yield str(d / 'casevo.py')
    sys.modules.pop('fakeui', None)


def test_run_replays_keys_and_dumps_screen(fake_entry):
    s = KS.run('2+3{enter}{snap:one}10{enter}', program=fake_entry)
    assert s.ended == 'script'
    assert s.mod('fakeui').HIST == [('2+3', '5'), ('10', '10')]
    assert s.mod('fakeui').ANS == ['10']
    assert s.screen == 'RAD\n2+3\n5\n10\n10'
    assert s.snap('one') == 'RAD\n2+3\n5'
    assert s.read == [93, 85, 94, 105, 92, 102, 105]
    assert s.left == []
    assert s.overdraw == []
    assert ('draw_text', 2, 17, 'RAD') in s.calls
    assert s.offscreen == []
    assert s.transcript_text(0, 2) == 'set_color 255 255 255\nfill_rect -1 -1 321 211'


def test_run_cancel_by_injected_clear(fake_entry):
    s = KS.run('1+1+1+1{enter}{clear@2}2{enter}', program=fake_entry)
    ui = s.mod('fakeui')
    assert ui.HIST == [('1+1+1+1', 'Interrupted'), ('2', '2')]
    assert s.fired == [(2, 45)]
    assert s.missed == []


def test_run_on_key_reaches_the_loop_handler(fake_entry):
    s = KS.run('1+1{enter}{on@1}3{enter}', program=fake_entry)
    assert s.mod('fakeui').HIST == [('', 'panic 1'), ('3', '3')]


def test_run_quit_ends_the_loop(fake_entry):
    s = KS.run('5{2nd,mode}7{enter}', program=fake_entry)
    assert s.ended == 'quit'
    assert s.left == [72, 105]      # 7 and ENTER were never read


def test_run_isolates_device_modules(fake_entry):
    import importlib
    ui0 = importlib.import_module('fakeui')     # a module some other test imported
    ui0.HIST.append('mine')
    s1 = KS.run('1{enter}', program=fake_entry)
    s2 = KS.run('2{enter}', program=fake_entry)
    assert sys.modules['fakeui'] is ui0          # restored after each run
    assert ui0.HIST == ['mine']
    assert s1.mod('fakeui') is not s2.mod('fakeui')
    assert s1.mod('fakeui').HIST == [('1', '1')]
    assert s2.mod('fakeui').HIST == [('2', '2')]


def test_run_not_fresh_shares_modules(fake_entry):
    s1 = KS.run('1{enter}', program=fake_entry, fresh=False)
    s2 = KS.run('2{enter}', program=fake_entry, fresh=False)
    assert s1.mod('fakeui') is s2.mod('fakeui')
    assert s2.mod('fakeui').HIST == [('1', '1'), ('2', '2')]


def test_run_propagates_other_errors_and_restores(fake_entry, tmp_path):
    bad = tmp_path / 'dev' / 'bad.py'
    bad.write_text('import fakeui\nraise ValueError("boom")\n')
    with pytest.raises(ValueError):
        KS.run('1', program=str(bad))
    assert 'fakeui' not in sys.modules


def test_run_depths_are_real(fake_entry):
    evodepth = pytest.importorskip('evodepth')
    d = os.path.dirname(fake_entry)
    try:
        dc = evodepth.DepthChecker([d], entry_files=[fake_entry], native_penalty=0,
                                   dunder_penalty=0)
    except TypeError:
        pytest.skip('evodepth has no entry_files option')
    with dc:
        KS.run('1+2{enter}', program=fake_entry)
    # entry body 0 > U.go 1 > work 2 > leaf 3: the runner and the shims add no frames
    assert dc.max_depth == 3, dc.max_stack
    assert [s.split('@')[0] for s in dc.max_stack[-3:]] == \
        ['fakeui.py:go', 'fakeui.py:work', 'fakeui.py:leaf']
    assert dc.violations == []


def test_after_run_hooks(fake_entry, monkeypatch):
    seen = []
    monkeypatch.setattr(KS, 'AFTER_RUN', [lambda s: seen.append(s.mod('fakeui').HIST[:])])
    KS.run('4{enter}', program=fake_entry)
    assert seen == [[('4', '4')]]

    def check(s):
        assert s.ended == 'quit', 'expected the program to quit'
    monkeypatch.setattr(KS, 'AFTER_RUN', [check])
    with pytest.raises(AssertionError):
        KS.run('4{enter}', program=fake_entry)


def test_session_aliases(fake_entry):
    s = KS.run('', program=fake_entry)
    assert s.R is None and s.hist is None and s.ans is None   # no run.py in the fake
    with pytest.raises(AttributeError):
        s.nosuch
    assert KS.ALIASES['K'] == 'node' and KS.ALIASES['U'] == 'ui'

