# UI implementation reference

The editable implementation is `src/casevo.py`, `ui.py`, `draw.py`, `menu.py`,
`menub.py`, `catalog.py`, and `forms.py`. Release packaging embeds the application
in a single minified `CASEVO.py`; users transfer that generated file. See
[installation and device acceptance](../INSTALL.md).

## Screens and control flow

The current coordinate system is 320 x 210. The status strip occupies y=0..13;
results occupy 14..157; the contextual signature is at 158..169; the editor is
170..189; the five function-key buttons are 190..209. Drawable dimensions, font
measurements, and key behavior still require physical-device confirmation.

An empty editor shows the newest answer as a large centered result. Typing shows
up to three compact history entries instead. Up enters history selection; the
selected entry is shown large. Results can scroll horizontally. Messages use
text. The editor is limited to 256 characters and scrolls to keep the caret visible.

The entry point runs its event loop at module scope to avoid a wrapper frame:
`wait_key` -> `U.key` -> optional `R.go` -> `U.show`. `U.key` returns `None`,
`U.QUIT`, or a job tuple. Calculation and F4 jobs pass through the same runner.
`U.boot` injects native cancellation, memory, and busy-display hooks. Session data
remain in the runner as text, separate from the temporary expression arena.

`U.key`, `U.show`, `U.boot`, and `U.panic` are level 1. `U.redraw` and `U.busy`
are level 2. Menu screens run at level 2. The current implementation redraws the
whole shell after editor keys; the dirty-region optimization from DESIGN 16.9 is
not implemented. Its performance must be measured on the EVO.

## Keys

The tables are in `ui.PLAIN`, `ui.SECOND`, and `ui.ALPHA`. Function keys use
codes 11..15; the remaining codes follow the TI getKey map. Physical confirmation
is separate from key-script coverage.

| Key (code) | Plain action | With 2nd |
|---|---|---|
| F1..F5 (11..15) | Menu, recall, setup, forms, help | Same action |
| MODE (22) | Setup | Quit |
| DEL (23) | Backspace; delete `ans()` atomically | Same action |
| Left/right (24/26) | Caret movement, or answer scrolling | Home/end in nonempty editor |
| Up/down (25/34) | History navigation | Jump five history entries |
| X,T,theta,n (32) | `x` | `t` |
| MATH (41) | Calculus command tab | TEST relation picker |
| VARS (44) | Recall | Recall |
| CLEAR (45) | Clear/back/hide hero; computation cancel | Same action |
| Reciprocal (51) | `^-1` | No insertion |
| SIN/COS/TAN (52..54) | Function call prefix | Inverse function prefix |
| Power (55) | `^` | `pi` |
| Square (61) | `^2` | `sqrt(` |
| Comma (62) | `,` | `E` scientific exponent |
| Parentheses (63/64) | `(` / `)` | `{` / `}` |
| Divide (65) | `/` | `e` |
| LOG (71) | `log(` | `10^(` |
| Multiply (75) | `*` | `[` |
| LN (81) | `ln(` | `e^(` |
| Subtract (85) | `-` | `]` |
| STO (91) | `=>` | No insertion |
| Zero (102) | `0` | All command tab |
| Decimal (103) | `.` | `i` |
| Negative (104) | `-` without leading Ans | `ans()` |
| ENTER (105) | Evaluate, or paste selected result | ENTRY recall, or selected input |

2nd (21) and ALPHA (31) are normally one-shot. ALPHA twice or 2nd ALPHA locks
lowercase entry; 2nd toggles lowercase/uppercase while locked; ALPHA unlocks.
The modifier chip shows the active state. Alpha letters use these positions:

| Key positions | Letters/text |
|---|---|
| MATH, APPS, PRGM | `a b c` |
| Reciprocal, SIN, COS, TAN, power | `d e f g h` |
| Square, comma, left/right parentheses, divide | `i j k l m` |
| LOG, 7, 8, 9, multiply | `n o p q r` |
| LN, 4, 5, 6, subtract | `s t u v w` |
| STO, 1, 2 | `x y z` |
| X,T,theta,n or 3 | `theta` |
| 0, decimal | Space, prime `'` |

The editor's leading-operator rule inserts `ans()` on an empty line for arithmetic,
power, reciprocal, square, and STO keys. Negative (104) remains a unary minus.
ENTER on an empty line repeats the last input. Repeated 2nd ENTER walks older
inputs until the recalled line is edited. Empty template slots move the caret
instead of starting calculation. History paste wraps compound results in parentheses.

## Menus and forms

F1 opens Algebra. Left/right cycles Algebra, Calculus, Trig, More, and All. Rows
show a signature and help text; six rows fit per page. Up/down selects; ENTER
inserts; numeric keys choose entries relative to the displayed page. ALPHA letters
filter by prefix; DEL removes a filter character. CLEAR or F1 closes the screen.
The TEST picker has seven relations, chosen with left/right and ENTER or 1..7.

Templates contain required argument slots, with the caret in the first slot.
`solve`, `factor`, `expand`, `simplify`, `partfrac`, `integrate`, `diff`, `limit`,
and `taylor` wrap an existing line when the caret is at its end; an empty line
uses `ans()` when available. Other entries insert at the caret.

F2 contains Ans, the latest ten successful results, stored variables, and stored
functions. F3 toggles RAD/DEG and Paper/Night immediately. Clearing history or
definitions requires local confirmation; CLEAR cancels that confirmation. About
shows the version, available heap, and loaded runtime families. F5 shows the
enclosing command's signature, explanation, and example, or a shortcut summary.
ENTER inserts a command example at the caret.

F4 calls `R.go(('form', index))`, operating on the original answer parsed inertly.
Available forms cycle through simplified, one fraction, factored, expanded, and
decimal; exact constant results try decimal first. Duplicate character multisets
are skipped, then the cycle returns to exact. A form updates the displayed text
and Ans without appending history. Held integrate/sum/limit answers are left alone.
The optional trigonometric forms are not included. The complete offer-predicate
table in DESIGN 14 is broader than the current implementation's filters.

## Drawing API

| API | Contract |
|---|---|
| `D.layout(text, width=300, height=110)` | Level 3; returns display-list box and fit metadata |
| `D.paint(box, x, y, scrollx=0, scrolly=0)` | Level 3; clips graphics to the box viewport |
| `D.text(s, x, y, small=False, color=None)` | Level 3; native text, default INK color |
| `D.theme(n)` / `D.settheme(n)` | Level 3; selects Paper or Night palette |
| `D.clear_cache()` | Level 3; releases cached display lists |

Layout converts answer text through `P.lex` and `P.rpn`, then constructs boxes and
display lists iteratively. It never builds a second expression arena. Fractions,
powers, square/nth roots, parentheses, absolute values, calls, lists, integrals,
derivatives, sums, and limits have dedicated layout forms. Mathematical symbols
use small vector drawings where native glyph availability is uncertain.

The box dictionary contains `dl`, `kinds`, `w`, `h`, `asc`, `desc`, `fallback`,
`small`, `overflow`, `vw`, and `vh`. Display items are text (`t`), clipped lines
(`l`), or vector glyphs (`g`). Large text is tried first, then small; oversized or
invalid input can fall back to plain text. Limits are 400 RPN tokens and nesting
24. The cache holds at most five entries and an estimated 4 KB, and is cleared
before every calculation. `COLORS` is a dictionary keyed by BG, INK, SUB, LINE,
ACC, ACCSOFT, CARD, BAR, and BARINK.

## Validation boundary

`tests/test_ui.py` exercises the actual entry loop with calculator key scripts:
calculation chains, negative entry, recall, atomic Ans deletion, slots, history
paste, assignment, F4/theme, help, cancellation, quit, and history clearing.
`tests/test_menu.py` covers relation selection, templates, recall, settings, help,
and command/macro catalog coverage. `tests/test_forms.py` checks cycling, Ans,
inert old results, held calculus, and history length. `tests/test_layout.py` checks
box kinds, clipping, scripts, fallbacks, cache limits, and printed-answer parsing.

Graphics tests use deterministic desktop shims rather than calculator screenshots.
They establish display-list and event behavior, not native font metrics, redraw
speed, free-heap behavior, USB transfer acceptance, or physical cancellation.
Strict depth checking and generated-bundle checks must also pass for the release;
physical-device acceptance remains pending until the installation checks run.
