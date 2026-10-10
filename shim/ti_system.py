"""Desktop stand-in for the TI-84 EVO `ti_system` module (DESIGN.md sections 4, 16.10, 20.9).

Desktop only: it never ships, the depth checker does not count its frames (it is not under
src/), and the subset lint does not apply. It still avoids f-strings and big stdlib modules so
that an optional MicroPython smoke tier (section 20.10) could reuse it.

The real module is native; this one replays a **key script** and models the cancel poll.

Key script
    `load(items)` sets the script. An item is either
      * an int key code (TI-BASIC getKey codes, DESIGN 16.4), or `ON` (the [on] key);
      * `after(n, code=CLEAR)`: the user presses `code` during a computation, exactly at the
        n-th poll (`escape()` or `get_key()` call) after the key that started it was read.
        An after() directly behind a key (only other after() items between) binds to that
        key; any other after() (at the head of the script, or behind a mark) binds to the
        next key;
      * `mark(label)`: when the program next waits for a key (it is idle again), call
        `MARK_HOOK[0](label)`; keyscript.py uses it to snapshot the screen.

    `wait_key()` returns the next key and raises `StopScript` at the end of the script.
    `StopScript` derives from BaseException, so the entry loop's `except Exception` and
    `except KeyboardInterrupt` (DESIGN 16.2) let it through.

Cancel model (provisional until PROBE6 reports, see `NOKEY` and `LATCH_CLEAR`)
    * A key pressed during a computation goes into a type-ahead buffer. [clear] also sets the
      escape latch.
    * `escape()` returns True once per [clear] press and consumes that press.
    * `get_key()` returns the oldest buffered key (consuming it, a [clear] too), else `NOKEY`.
    * `wait_key()` returns buffered keys before scripted ones.
    * An `after(n)` press whose poll never comes (the computation was shorter) is dropped when
      the program next calls `wait_key()`, and listed in `MISSED`.
    * `ON` raises KeyboardInterrupt: from the poll at which it fires, or from `wait_key()`.
    * `LATCH_CLEAR = True` models a device on which a [clear] read by `wait_key()` also leaves
      the escape latch set (a stale latch would cancel the next computation at once).
"""
CLEAR = 45          # [clear]
ON = -1             # pseudo code for [on]: raises KeyboardInterrupt, never returned
NOKEY = 0           # get_key() with no key pressed [A: PROBE6 'poll' settles it]
LATCH_CLEAR = False  # see the module docstring


class StopScript(BaseException):
    """The key script is exhausted: ends a scripted run of the entry program."""


def after(n, code=CLEAR):
    """Script item: press `code` at the n-th poll (n >= 1) of a computation (module doc)."""
    if type(n) is not int or n < 1:
        raise ValueError('after(n): n must be an int >= 1')
    return ('after', n, code)


def mark(label):
    """Script item: call MARK_HOOK(label) when the program next waits for a key."""
    return ('mark', label)


# ---------------------------------------------------------------- state (see reset())
SCRIPT = []         # the loaded items
POS = 0             # next item index
POLLS = 0           # escape() + get_key() calls since load()
ARMED = []          # [[poll index, code], ...] presses waiting for their poll
BUF = []            # type-ahead: keys pressed during a computation, not yet consumed
LATCH = [False]     # the escape latch
KEYS_READ = []      # every key returned by wait_key(), in order
FIRED = []          # (poll index, code) of every after() press that fired
MISSED = []         # (poll index, code) of after() presses dropped unfired
CALLS = []          # other calls: ('disp_at', ...), ('sleep', s), ...
OVERRUN = [0]       # wait_key() calls after the script ended
LISTS = {}          # store_list / recall_list
CLOCK = [0.0]       # seconds "slept" through sleep()/wait()
MARK_HOOK = [None]  # callable(label) or None


def reset():
    """Forget the script and every log; LATCH_CLEAR goes back to False."""
    global SCRIPT, POS, POLLS, LATCH_CLEAR
    SCRIPT = []
    POS = 0
    POLLS = 0
    LATCH_CLEAR = False
    del ARMED[:]
    del BUF[:]
    LATCH[0] = False
    del KEYS_READ[:]
    del FIRED[:]
    del MISSED[:]
    del CALLS[:]
    OVERRUN[0] = 0
    LISTS.clear()
    CLOCK[0] = 0.0
    MARK_HOOK[0] = None


def load(items):
    """Reset, then set the key script (see the module docstring)."""
    global SCRIPT
    reset()
    SCRIPT = list(items)
    for it in SCRIPT:
        _check_item(it)


def feed(items):
    """Append items to the current script (keeps the logs)."""
    for it in items:
        _check_item(it)
        SCRIPT.append(it)


def remaining():
    """The script items not read yet."""
    return SCRIPT[POS:]


def press(code):
    """Press a key now, as during a computation: it goes into the type-ahead buffer (a [clear]
    also sets the escape latch; ON raises KeyboardInterrupt at once)."""
    _fire_code(code)


def _check_item(it):
    if type(it) is int:
        return
    if type(it) is tuple and len(it) == 3 and it[0] == 'after':
        return
    if type(it) is tuple and len(it) == 2 and it[0] == 'mark':
        return
    raise ValueError('bad key-script item: %r' % (it,))


def _fire_code(code):
    if code == ON:
        raise KeyboardInterrupt()
    BUF.append(code)
    if code == CLEAR:
        LATCH[0] = True


def _poll():
    global POLLS
    POLLS += 1
    i = 0
    while i < len(ARMED):
        at, code = ARMED[i]
        if at <= POLLS:
            del ARMED[i]
            FIRED.append((POLLS, code))
            _fire_code(code)
        else:
            i += 1


def _take_buffered():
    k = BUF.pop(0)
    if k == CLEAR:
        LATCH[0] = False
    return k


# ---------------------------------------------------------------- the device API
def wait_key():
    """Block for a key: the next buffered key, else the next scripted key."""
    global POS
    while ARMED:                         # the computation window has ended
        at, code = ARMED.pop(0)
        MISSED.append((at, code))
    if BUF:
        k = _take_buffered()
        KEYS_READ.append(k)
        return k
    while POS < len(SCRIPT):
        it = SCRIPT[POS]
        POS += 1
        if type(it) is tuple:
            if it[0] == 'after':
                ARMED.append([POLLS + it[1], it[2]])
            elif MARK_HOOK[0] is not None:
                MARK_HOOK[0](it[1])
            continue
        while POS < len(SCRIPT) and type(SCRIPT[POS]) is tuple and SCRIPT[POS][0] == 'after':
            ARMED.append([POLLS + SCRIPT[POS][1], SCRIPT[POS][2]])
            POS += 1
        if it == ON:
            KEYS_READ.append(ON)
            raise KeyboardInterrupt()
        if it == CLEAR and LATCH_CLEAR:
            LATCH[0] = True
        KEYS_READ.append(it)
        return it
    OVERRUN[0] += 1
    raise StopScript('key script ended after %d keys' % len(KEYS_READ))


def get_key():
    """Non-blocking: the oldest key pressed during a computation, else NOKEY. Counts a poll."""
    _poll()
    if BUF:
        return _take_buffered()
    return NOKEY


def getKey():
    """EVO name from the PROBE2 listing; assumed to behave as get_key() [A]."""
    return get_key()


def escape():
    """True once per [clear] press (consuming it), else False. Counts a poll."""
    _poll()
    if LATCH[0]:
        LATCH[0] = False
        if CLEAR in BUF:
            BUF.remove(CLEAR)
        return True
    return False


def disp_clr():
    CALLS.append(('disp_clr',))


def disp_at(*args):
    CALLS.append(('disp_at',) + tuple(args))


def disp_cursor(*args):
    CALLS.append(('disp_cursor',) + tuple(args))


def disp_wait():
    """CE documentation: pauses until [clear] is pressed. Reads keys until a [clear]."""
    CALLS.append(('disp_wait',))
    while wait_key() != CLEAR:
        pass


def sleep(seconds):
    """Records the call and advances CLOCK; never really sleeps."""
    CALLS.append(('sleep', seconds))
    CLOCK[0] += seconds


def wait(seconds):
    CALLS.append(('wait', seconds))
    CLOCK[0] += seconds


def store_list(name, values):
    CALLS.append(('store_list', name))
    LISTS[name] = list(values)


def recall_list(name):
    CALLS.append(('recall_list', name))
    return list(LISTS.get(name, []))


def recall_RegEQ():
    CALLS.append(('recall_RegEQ',))
    return ''


# Names verified on the EVO (PROBE2). Every one of them is defined above.
VERIFIED = ('disp_at', 'disp_clr', 'disp_cursor', 'disp_wait', 'escape', 'getKey', 'get_key',
            'recall_RegEQ', 'recall_list', 'sleep', 'store_list', 'wait', 'wait_key')
