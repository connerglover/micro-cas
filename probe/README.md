# Calculator probes: what to run and what to send back

These small programs measure how Python behaves on the TI-84 EVO. Their results settle open
questions in `docs/DESIGN.md`. Most of the work is taking screenshots.

## Before you start

1. **Back up the calculator** with TI Connect CE. The last part of PROBE6 and of PROBE5 can freeze
   the calculator (each probe warns you on screen first).
2. **Send these files to the calculator**, the same way as the earlier PROBE files:
   `PROBEK2.py`, `PROBE7.py`, `PRBMEM.py`, `PRBMOD.py`, `PROBE6.py`, `PROBE5.py`, `PRBIMP.py`.
3. **Optional:** also send `PRBMPY.mpy`. If TI Connect CE refuses it, skip it and tell us.
4. To take a screenshot, use TI Connect CE's screen capture or a phone photo. Either is fine.

## How every probe behaves

- You start a probe from the Python app, as with the earlier probes. Every run starts fresh.
- It prints short lines. When the screen is full, it stops at a line like
  `-- p3: screenshot, key --`. **Take a screenshot, then press any key.**
- The last line is `== PROBE6 end, p5 ==`. Take a screenshot of that screen too. The number is
  the page count, so you can check that no screenshot is missing.
- If a probe stops with an error message, take a screenshot and go on with the next probe.

## Run them in this order

| # | probe | what you do | about |
|---|---|---|---|
| 1 | `PROBEK2` | Key codes. It names one key at a time: press that key once. If it says `Again`, press the same key once more. Then it asks you to keep your hands off the keys, to hold RIGHT for 3 seconds, and to press any keys it never named (write down their names), then CLEAR three times. Last, press ON (this may stop the probe; that is fine). | 5 min |
| 2 | `PROBE7` | Drawing. Drawing screens ask a yes/no question: **ENTER = yes, CLEAR = no**. If a screen is blank or shows only text, press CLEAR. When it shows the **glyph sheet**, take a screenshot of it, then press a key. | 3 min |
| 3 | `PRBMEM` | Memory. Nothing to do but screenshots. | 1 min |
| 4 | `PROBE6` | **The most important one.** When it says `POLL`, press ENTER, then tap CLEAR about once a second until the countdown (2 1 0 2 1 0) ends, then let go. The last part is risky. | 1 min |
| 5 | `PROBE5` | Nothing to do but screenshots. The last part is risky. | 1 min |

## If the calculator freezes

This can only happen near the end of PROBE6 (after a `sort mode` line) or PROBE5 (after a `nest`
line). That is a result, not a failure.

1. Take a photo of the screen. The last line on it is the answer.
2. If no key works for a minute, reset the calculator as its manual describes.
3. If the probe files are gone, send them again. Then go on with the next probe in the list.

## What to send back

- All screenshots, in order, grouped by probe. Names like `PROBE6-1.png` help but are not needed.
- From PROBEK2: the names of the extra keys you pressed, in the order you pressed them (or
  "none").
- For a freeze: which probe, and the photo of its last screen.
- Whether TI Connect CE accepted `PRBMPY.mpy`.

## Later (not now)

When the M0.5 task has made `PRBL100.py`, `PRBL200.py` and `PRBL300.py`, send them and run
`PRBMEM` and `PROBE6` again. Until then, PROBE6 shows `imp6 E:ImportError` and PRBMEM shows
`PRBL100 missing`; both are expected.

## For developers

- Each probe also runs on the desktop: `cd probe` and then
  `python -c "from PROBE6 import *"`. With no `ti_*` modules it never waits and skips the key,
  poll and drawing parts. `tests/test_probes.py` runs every probe that way and again with stub
  `ti_system`/`ti_graphics` modules.
- Rules for probe code: Python 3.4 subset, ASCII only, every printed line at most 30 characters,
  at most 8 lines per page plus the prompt line. Deep code (depth 9 and 10) may call only
  natives.
- How to read each result line: `docs/notes/M0.3.md`.
