# MathPrint editor research (handoff input)

Collected 2026-10-20 by a research workflow before the design phase. Two reports: external behavior (TI-Nspire CX II CAS, FlowCE) and cas-evo integration constraints. Sources and uncertainty marks are the agents' own; verify before relying on them.


---

# Research report: 2D entry on the TI-Nspire CX II CAS Calculator and in FlowCE

Sources were fetched on 2026-10-20. FlowCE was read at commit `259ef337008a7da9f9a18f1d7ebc49c29aea4985` (HEAD, 2026-10-15). The local copies of the FlowCE files and the Nspire PDF text used for this report were not kept; fetch them again if needed.

Labels used below:
- **[SRC]**: read directly in the source or document.
- **[INF]**: inferred.
- **[UNVERIFIED]**: not confirmed by any source found.

---

## Part A: FlowCE (tommyb3ll/FlowCE)

### A.1 Data model: a flat text buffer re-parsed on every key, not a tree [SRC]
- The edit line is one plain giac string (`Edit_Line`) with an integer caret (`Current_Col`). The header comment of `mathinput.cc` says the user edits a plain giac string with a caret index, and the module draws that string as 2D math.
- The structure exists only in the text. Each template is ordinary giac syntax:

  | Template | Text in the buffer |
  |---|---|
  | Fraction | `(a)/(b)` |
  | Exponent | `x^(2)` |
  | Radical | `sqrt(a)` |
  | Nth root | `surd(a,n)` |
  | Absolute value | `abs(a)` |
  | Integral | `integrate(f,x[,a,b])` |
  | Derivative | `diff(f,x)` |
  | Sum | `sum(f,k,a,b)` |
  | Limit | `limit(f,x,a)` |
  | e^ | `exp(a)` |
  | Taylor | `series(f,x,a,n)` |

- Parentheses that serve as template structure are **hidden** when drawn. This applies to an operand of `/` or the exponent of `^` that is exactly `(..)`, and to the parens and commas of the special calls.
- **Evaluation needs no conversion step**, because the buffer is already the giac input. On ENTER:
  - `console_empty_slot()` finds an empty template box, such as `(,` `,,` `,)` `()` or `sqrt()`. Instead of evaluating, it moves the caret there and shows "fill in the empty box".
  - `console_autoclose()` closes any unclosed brackets, as TI-OS does.
  - `ti_rewrite` and `ti_implicit_mult` (tiinput.cc) insert `*` for implicit multiplication (`2x`, `sin x`, `sin^2(x)` becomes `sin(x)^2`, and so on).
- The editor is split into **pure functions of (buffer, caret)**, with no persistent tree:
  - `mi_build(s,len,caret,metrics,out)` produces a display list and the caret location.
  - `mi_move(s,len,caret,dir,metrics)` returns the new caret, or -1 when up/down leaves the expression.
  - `mi_backspace(...)` returns the span to delete.
  - `me_key(s,cap,&caret,key)` handles structure-aware keys by editing the text in place with `memmove`, without allocating.
  - `me_backspace(s,&caret)` handles structural deletion.

  Files: `src/mathinput.{h,cc}` (~1000 lines), `src/mathedit.{h,cc}` (~290 lines), the glue in `src/mathinput_glue.cc`, and `src/console.cc`.

### A.2 Parser and layout pipeline (`mathinput.cc`) [SRC]
- **Pipeline:** lex, then a tolerant recursive-descent parse into a **static pool of 16-byte nodes** (MAXN=192), then `measure` bottom-up, then `place` top-down. The place pass emits the display ops and the caret location of every buffer position 0..len, in increasing order.
- **Node kinds:**
  - Leaves: TEXT, OP, OPU, SEP, DOT, BLANK, FLAT, PI, INF, THETA, EMPTY.
  - Containers: ROW, GROUP, CALL.
  - 2D constructs: FRAC, POW, SQRT, SURD, ABS, INT, DEFINT, DIFF, SUM, LIM, EXP, SER.
- **Precedence levels, lowest to highest:** `; ,` < `:= => ->` < relations < `+ -` < `* /` and implicit multiplication < prefix `- + ! '` < `^ **` (right-associative) < postfix `! '` < primaries.
  - Levels 1–5 are kept as flat rows.
  - **`/` takes the whole level-5 term to its left as the numerator.**
- **The parser never fails:**
  - A missing operand becomes an empty box (`K_EMPTY`), drawn as `MI_BOX`.
  - An unclosed group runs to the end of the buffer.
  - Stray closers are drawn as plain text.
  - Past the budget (nesting > 24, ~176 nodes, ~384 ops, or layout recursion > RMAX=52), the rest of the buffer is drawn as one plain-text op.
- **Display list op codes:** TEXT, DOT, HLINE, SQRT, INTEGRAL, SIGMA, L/RPAREN, L/RBRACKET, L/RBRACE, BAR, BOX, HINT. Each op is a box (x, y, w, h) relative to the baseline, plus a buffer position and length. The renderer is a single loop over the ops (`mi_draw` in the glue, or `ui_math_draw`).
- **Layout rules** (y grows down, baseline 0, axis = −asc/3):
  - **Fraction:** bar at the axis; numerator and denominator centered; width = max + 2·gap. The classic metrics use a 1 px bar and 2 px gaps.
  - **Power:** exponent in the small font, its bottom at 45% of the base's ascent.
  - **Radical:** sign 6 px wide, overbar 2 px above the content.
  - **Integral:** sign as tall as the content + 4. Bounds in the small font at the bottom-right and top-right, never overlapping. Then f, a 2 px gap, "d", and x.
  - **diff:** `d/(d x)` drawn as a fraction, then f, in parentheses if f is a sum.
  - **sum:** Σ (2·asc tall), with `k=a` below and `b` above, then f.
  - **limit:** "lim" over `x→a` (small), then f.
  - **exp:** "e" with a superscript.
  - Integrate, diff, sum and limit end with a 2 px trailing gap, so that "after the construct" and "end of the last slot" are different caret locations.
- **Fixed-width font on the classic (pre-Focus) device path:** `mi_device_metrics = {{8,11,3},{5,7,2},2,...}`, meaning big glyphs are 8 px wide with 11 px ascent and 3 px descent, and small glyphs are 5 px wide with 7/2. A plain line fits a 15 px console row. This is the closest analog to cas-evo's single fixed font.
- **The Focus UI in FlowCE 1.9 is different:** proportional STIX Two fonts at 8 sizes (34…10 px), anti-aliased.

### A.3 Caret model and navigation [SRC]
- The caret is a **buffer index**. Each position maps to the (x, top, height) of the deepest slot containing it.
- Positions inside hidden structure alias the previous visible position, so the caret never stops between structure characters. This covers function names, hidden `( ) , / ^`, and multi-character names such as `sin`, which the caret steps over as one unit.
- **Left/right:** move to the nearest position with a *different drawn location*.
  - For constructs whose slots are not drawn in buffer order, `vmove` walks them in **drawn order** (table `vorder`):
    - DEFINT: lower → upper → integrand → var
    - SUM: k → a → b → body
    - LIM: var → value → body
    - DIFF: var → body
    - SURD: index → radicand
  - Right from just before such a construct enters its first drawn slot. Leaving the last slot lands beside the construct.
- **Up/down:**
  - Candidates are the positions inside the innermost enclosing 2D construct that has any, then the next construct outwards.
  - A power's base line counts as "weakly inside" the power: down from the exponent reaches the base, but up from the main line returns -1.
  - Ranking:
    1. Entirely below or above the caret's vertical range.
    2. Then partially lower or higher.
    3. Then vertical distance, quantized to half a small line.
    4. Then smallest |dx|.
    5. Then smallest index.
  - With no enclosing construct, `mi_move` returns **-1**. The console then moves into the history (UP) or opens the command search (DOWN on the edit line).
- **Exponent exit:** RIGHT at the end of the exponent goes back to the baseline. The hidden `)` aliases, so one keypress is enough.
- The caret is drawn as a 2 px bar with the slot's height. In the small font it is the small height.

### A.4 Keys and templates [SRC: `console.cc` ~1810–1840, 2450–2490; `mathedit.cc`]
- **`keytostring`**: in 2D mode, any key that produces `^` or `name(` gets its closer appended, and the caret moves inside: `^` becomes `^()`, `sin(` becomes `sin()`. Key strings:

  | Key | Inserts |
  |---|---|
  | `^` | `^()` |
  | √ | `sqrt()` |
  | ln | `ln()` |
  | log | `log10()`, drawn as "log" |
  | 10^x | `10^()` |
  | e^x | `exp()`, drawn as e with a superscript box |
  | x² | `^(2)` via `me_key ME_SQUARE`, an exponent that can be extended |
  | x⁻¹ | `^(-1)` via `ME_RECIP` |
  | sin, cos, … | `sin()`, … |

- **`/`** (`me_key`): the term left of the caret in the current slot becomes the numerator. A term is the longest run ending at the caret of operands joined by implicit multiplication, with their `^` exponents and postfix `! '`.

  | Before | After |
  |---|---|
  | `x\|` | `(x)/(\|)` |
  | `2sin(x)\|` | `(2sin(x))/(\|)` |
  | `a+b\|` | `a+(b)/(\|)` |
  | `-x\|` | `-(x)/(\|)` |
  | `(a+b)\|` | `(a+b)/(\|)` (group reused) |
  | `a+\|` (no term) | `a+(\|)/()` |

- **`(` `[` `{`**:
  - Right after an empty `^(` it does nothing, so the exponent box is the group.
  - Otherwise it inserts the opener at the caret and the closer at the **end of the current slot**: `|x+1` becomes `(|x+1)`.
  - In an empty denominator, the group is the user's own, inside the box.
- **`)`**:
  - Steps over a closer right after the caret. After the `)` of a denominator or exponent it also steps over the next closer, because no bracket is visible there.
  - Otherwise it wraps the slot's text: `x+1|` becomes `(x+1)|`.
- **`,` `=` `<` `>` `]` `}`** in a denominator or exponent: the caret first moves out of that group (repeatedly while still in one), then the key is inserted. A `,` before an empty argument steps into the next box: `irem(17|,)` becomes `irem(17,|)`.
- **`+` `-`** right after a group that is a whole denominator: the caret leaves the denominator, so `1/(x+1)+2` typed linearly comes out as expected.
- **Operator on an empty line** (`+ − × ÷ ^ x² x⁻¹ sto→`): inserts `ans()` first, drawn as "Ans", TI-style. `2nd (-)` is Ans.
- **Templates from the `math` key and the F-menus** (`focus_menu.cc`, `mi_get_template`). The number is the caret offset after insertion.
  - `()/()` 1
  - `^()` 2
  - `sqrt()` 5
  - `surd(,)` 5
  - `abs()` 4
  - `integrate(,x)` 10
  - `integrate(,x,,)` 10
  - `diff(,x)` 5
  - `sum(,k,,)` 4
  - `limit(,x,)` 6
  - `e^()` 3
  - `series(,x,0,5)`
  - In menus: `solve(,x)`, `factor()`, `ln()`, `exp()`, trig functions, and others.
- **Labeled empty boxes** (`MI_F_HINTS`): an empty argument of a catalog call shows its argument name, in small italics inside a box. A help line under the input shows the command's description and an example.
- **Default variables:** `x` (and `k` for sum) are pre-filled. Backspace treats them as empty when deciding whether a template is empty.

### A.5 Deletion semantics [SRC: `console.cc` ~3040–3080, `mathedit.cc` `me_backspace`, `mathinput.cc` `mi_backspace`]
Checked in this order on DEL (backspace):
1. `ans()` before the caret is deleted as a whole.
2. `sin(x)|`: the caret steps **into** the group, `sin(x|)`, instead of deleting the `)`.
3. `me_backspace`, when the caret is right after the opener of a closed group:
   - **Call:** `f(|a,b)` becomes `|a`. The name, brackets and other arguments go, unless removing the brackets would change the meaning, in which case they stay: `2sqrt(|x+1)` becomes `2(|x+1)`.
   - **Exponent:** `x^(|)` becomes `x|`. A non-empty exponent `x^(|2)` becomes `x|^(2)`, so the caret just moves out.
   - **Denominator:** `(a)/(|)` becomes `a|`. A non-empty denominator `(a)/(|b)` becomes `(a|)/(b)`, so the caret moves to the end of the numerator.
   - **Numerator:** `(|a)/()` becomes `|a`. `(|a)/(b)` becomes `|(a)/(b)`. `(|)/()` becomes `|`.
   - **Other groups:** brackets removed: `(|a+b)` becomes `|a+b`.
   - **After a comma:** the caret moves before it: `f(a,|b)` becomes `f(a|,b)`.
4. `x/(|)` or `x^(|)`: the `/()` or `^()` is removed and `x` stays.
5. `mi_backspace` (layout-aware):
   - A visible character deletes one glyph. `pi`, `oo` and multi-character operators like `<=` go as a whole.
   - A hidden structure character deletes the **whole construct if all its slots are empty**. Otherwise it **acts like LEFT**.

In short: backspacing into a non-empty template moves the caret instead of deleting it, and an empty template is deleted in one keypress.

### A.6 History display and recall [SRC: `focus.cc`, `console.cc`]
- **History inputs are re-laid out from their stored text** with `MI_F_TIDY`. This also hides the user's own parentheses around a whole numerator or denominator, so typed `1/(x+1)` displays without them.
  - They use smaller sizes (`IN_LV=5`, max width 286, max height 34), are left-aligned, and are drawn in a subdued color.
  - Results use `MI_F_IMPLDOT`, where `*` before a letter or `(` is drawn as a 1 px gap. They use `OUT_LV=3`, max width 292, max height 64.
  - Results too wide even at the smallest size are wrapped at top-level `+`/`-` onto up to 6 lines.
- **Navigation:** UP from the edit line, when `mi_move` returns -1, selects the last calculation. In history mode, up/down move one entry and left/right select its input or its result.
- **Recall:** ENTER on a selected history line returns to the edit line and calls `Console_Input(str)`, which **inserts the text at the caret** (the caret position is preserved).
- **2nd ENTER (ENTRY):** clears the edit line and puts the previous input there. Pressing again goes one input further back.
- The classic non-Focus console reserved extra 15 px rows (`LINE_TYPE_CONT`) for a 2D input in the history (`console_rows_of(L)`).

### A.7 Overflow and scrolling [SRC: `focus.cc` `hero_prepare`, `ui_math.cc`]
- **Auto-shrink first:** `ui_math_refit` rebuilds at the previous size level. If too big, it steps down. If there is room (8% margin, estimated linearly), it tries one size up.
  - The cost is usually **one `mi_build` per key**, and two when growing.
  - `ui_math_fit` jumps close to the target size by linear estimate, then steps.
- **Horizontal scroll** when the layout is still wider than 296 px:
  - `hx = W/2 − caret.x` (caret centered), clamped so the left edge is ≤ 12 and the right edge is ≥ W−12.
  - The layout is vertically centered in the hero box.
- **Clipping:** text ops are drawn whole or not at all, and lines are clipped to the box.

### A.8 Performance techniques [SRC]
- A static node pool with fixed budgets and no allocation in parsing; only the display-list `vector` is reserved once per build (`reserve(nops+1)`).
- Hard caps that degrade to plain text rather than failing or recursing deeply.
- Recursion depth is capped (MAXD=24 parser, RMAX layout); a/b/c chains nest without parser recursion.
- A single layout description (`cons()`) serves measuring, decoration output and slot origins (three modes), so the geometry is written once.
- `mi_move` and `mi_backspace` re-run parse + measure + place in a "location mode" with no ops output; `OUT=0`, so no op allocation.
- Caches in `focus.cc`:
  - A 72-entry **fitted-size cache** keyed on (pointer, djb2 hash, max level, max size, flags).
  - A 16-entry **built-layout cache**, so a banded repaint does not rebuild entries.
  - A wrapped-result cache.
- Repaint is split into "everything" and "edit line only" (`Console_Disp(0)` after edits).
- Host benchmark `t_perf()`: a ~100-character integral, sum and limit expression measures cost per `mi_build` and `mi_move`. The numbers are printed, not asserted.
- Host tests (`tests/host/test_mathinput.cc` ~1000 lines, `test_mathedit.cc` ~500 lines) check, among other things, that LEFT then RIGHT returns to an equivalent location.

---

## Part B: TI-Nspire CX II CAS Calculator app

Key-glyph decoding of the TI PDFs: `/` = ctrl, `g` = shift, `p` = ÷, `l` = ^, `q` = x², `u` = eˣ, `s` = 10ˣ, `t` = template key, `·` = enter, `e` = tab. This is [INF] from standard Nspire key fonts, and it is consistent with the online calculator's shortcut table.

### B.1 Entry line
- The guidebook says expressions "are displayed in standard mathematical notation as you enter them." [SRC: CX II guidebook]
- `^` opens a superscript box. You type the base, press ^, type the exponent, and then **► (right arrow) returns the cursor to the baseline**. The worked example types `2^8`, presses ►, then `*43/12`. [SRC: guidebook and Reference Guide, "Exponent template"]
- Templates appear "on the entry line with small blocks at positions where you can enter elements. A cursor shows which element you can enter." [SRC: Reference Guide]

### B.2 Template keys [SRC: Reference Guide, "Expression Templates"; guidebook shortcut table]

| Template | Handheld key |
|---|---|
| Fraction | ctrl + ÷ |
| Exponent | ^ |
| Square root | ctrl + x² |
| Nth root | ctrl + ^ |
| e exponent | eˣ |
| Log with base | ctrl + 10ˣ (base slot; leave it empty for base 10) |
| Integral | shift + + |
| Derivative | shift + − |
| Template palette | t, or ctrl + ; |

- Absolute value, piecewise (2-piece or N-piece, prompting for N), system of 2 or N equations, dd°mm'ss", matrices (2×2, 1×2, 2×1, m×n with a dialog), sum Σ, product Π, 1st/2nd/nth derivative, definite and indefinite integral, and limit are all in the palette or Catalog.
- The limit template uses `−` in the direction slot for a left-hand limit and `+` for a right-hand limit.
- In a matrix template, shift+enter adds a column and @ adds a row.
- **Plain ÷ vs ctrl+÷:**
  - [SRC: MathBits] While typing, plain ÷ shows `3 / 5` linearly, and **after ENTER it is pretty-printed as a stacked fraction** in the history. Ctrl+÷ gives a true stacked fraction template in the entry line. After typing something, ctrl+÷ makes it the numerator and waits for the denominator.
  - [UNVERIFIED] Exactly how much of the preceding text ctrl+÷ captures as the numerator.
- An open parenthesis gets a temporary **gray** close parenthesis. It turns black when you type it or type past it. [SRC: guidebook, "Inserting into an Expression"]

### B.3 Navigation [SRC: guidebook, "Positioning the Cursor in an Expression"]
- Tab, ◄, ►, ▲ and ▼ move the cursor through the expression; it "moves to the closest valid position in the direction that you press."
- A template "may force the cursor to move through its parameters" off the geometric path. The guidebook's example: moving up from the main argument of an integral always goes to the top limit.
- The online calculator lists tab and shift+tab as "Move through fields or zones." [SRC: online calculator CAS shortcuts]
- Dummies describes typing the numerator, then [TAB] to the denominator. [SRC: search snippet, Dummies]
- [UNVERIFIED] Whether Tab skips filled slots or simply cycles all slots.
- Shift + arrows selects. Ctrl+8 and ctrl+2 jump to the beginning and end of the line (online calculator). [SRC]

### B.4 Deletion
- [SRC] To delete part of an expression, select it with shift+arrows and press Del. Del also deletes one character left of the cursor.
- [UNVERIFIED, from memory and not confirmed] Backspacing into a template moves into it or deletes characters inside it, and deleting all of a template's contents and then pressing Del removes the empty template. No TI document describing this was found.

### B.5 History and recall [SRC: guidebook, "Working with the Calculator History"; Reference Guide]
- Each entry/result pair is saved. Both are shown in pretty print: the expression on the left, the result right-aligned, and the result moves to the next line if it does not fit.
- **The history cannot be edited.** ▲/▼ scroll and select an expression or result; shift+arrows select a sub-expression. **Enter copies the selection "and insert[s] it into the entry line."** The copy is a structured 2D object that is then editable.
- [UNVERIFIED] Whether the copy is inserted at the cursor or replaces the entry line. The wording "insert" suggests insertion at the cursor.
- Ctrl+C and ctrl+V also work. Selecting a result by scrolling captures its full precision regardless of the Float setting.
- Del on a selected history item removes the pair. Menu > Actions > Clear History clears it; ctrl+esc undoes.
- TI notes that a large history causes a "processing slowdown."
- Ctrl+enter forces an approximate result.

### B.6 Height growth and overflow
- [SRC, indirect] The entry line shows 2D templates in place, so it must grow vertically for fractions, Σ, integrals and similar.
- [UNVERIFIED] The exact growth behavior and horizontal scrolling for over-wide input. The general knowledge is that the entry line grows in height to fit its tallest construct and scrolls horizontally, but no TI document describing this was found.

---

## Part C: Observations relevant to cas-evo [INF; facts, not a design]
- FlowCE shows that a **text buffer plus re-parse on every key** works on a slower CPU (eZ80 at 48 MHz). It needs no tree data structure, no conversion before evaluation, and recall is plain text insertion. Its costs per key are one parse+measure+place for drawing, plus one more for each arrow or backspace.
- The Nspire behaviors that FlowCE does not reproduce:
  - Tab cycling through slots. FlowCE uses arrows in drawn order, and ENTER jumps to the first empty box.
  - The gray temporary parenthesis. FlowCE instead auto-inserts the closer at the end of the slot.
  - Shift+arrow selection.
  - A dedicated log-base template. FlowCE has `log10()` and no base slot.
  - Matrix, piecewise and system templates.
- In FlowCE, the `/` key always creates a stacked fraction from the term to its left. The Nspire splits this between plain ÷ (linear while typing, pretty after ENTER) and ctrl+÷ (a template).

## Sources
- FlowCE repository: https://github.com/tommyb3ll/FlowCE (files: `src/mathinput.{h,cc}`, `src/mathedit.{h,cc}`, `src/mathinput_glue.cc`, `src/console.cc`, `src/focus.{h,cc}`, `src/focus_menu.cc`, `src/ui_math.{h,cc}`, `src/tiinput.h`, `tests/host/test_mathinput.cc`, `README.md`)
- [TI-Nspire CAS Reference Guide (Expression Templates)](https://education.ti.com/download/en/ed-tech/0AF942A4AC0E47ABA20853691FA6712E/21717C07E942465BAB415753181078C7/TI-NspireCAS_Reference_Guide_EN.pdf)
- [TI-Nspire CX II Handheld Guidebook (Calculator chapter; shortcut table)](https://education.ti.com/download/en/ed-tech/BBB9825DB8884175BAEA7CCB24DE9DBC/8E397FE4BC834CB988CD75EB8B2F7402/TI-Nspire_CXII-HH_Guidebook_EN.pdf)
- [TI eGuide: Entering and Evaluating Math Expressions](https://education.ti.com/html/webhelp/EG_TINspire/EN/content/m_calculator/ca_enter_evaluate_math_expr.HTML)
- [TI eGuide: Working with the Calculator History](https://education.ti.com/html/webhelp/EG_TINspire/EN_GB/content/m_calculator/ca_working_with_calc_history.HTML)
- [TI online calculator (CAS) keyboard shortcuts](https://education.ti.com/html/eguides/nspire/EG_Nspire/EN/content/eg_onlinecalc/m_onlinecalc/oc_keyboard_cas.HTML)
- [MathBits: Fractions on TI-Nspire](https://mail.mathbits.com/MathBits/TINSection/General/FractionsTN.html)
- [MathBits: Entering Expressions on TI-Nspire](https://www.mathbits.com/MathBits/TINSection/General/Entering%20Expressions.html)
- [Dummies: Copy, paste and edit expressions and answers](https://dummies.com/article/copy-paste-and-edit-expressions-and-answers-183437)
- [Dummies: Evaluate expressions using primary and secondary keys (Tab to the denominator; search snippet)](https://www.dummies.com/article/technology/electronics/graphing-calculators/evaluate-expressions-in-ti-nspire-using-primary-and-secondary-keys-183388)

---

# What a MathPrint input editor in cas-evo must integrate with and must not break

I read every file you listed, rebuilt with `build/release.py` (it succeeded), and measured the per-key draw cost through `keyscript`. These pass locally: lint, framelint, and `pytest tests/test_ui.py tests/test_fastboot.py tests/test_layout.py tests/test_menu.py tests/test_release.py --strict-depth` (204 passed). The native `micro_smoke` suites only run in CI.

**Main points:**
- **No engine while typing.** Editing must work before the engine loads. `draw.layout` needs `P.lex`/`P.rpn`, so the editor cannot use it on each key.
- **`LINE` as the shared text.** Everything else reads or writes the plain-text `LINE`. A 2D editor should produce or consume that same text.
- **Fraction-key risk.** `keyscript` types `/` with key 42, the fraction-template key. Changing that key's meaning changes the behaviour of existing scripts and the native UI suites.

---

## 1. Every place `LINE` and `CUR` are read or written, and what each relies on

The state lives in `src/ui.py:23-36`: `LINE`, `CUR`, `XOFF` (editor scroll), `MOD`, `MODE` (history select), `SEL`, `HERO`, `DX`, `ENTRYPOS`, `LASTENTRY`, `STATUS`, `NOTE`, `FULL`, `VIEW`. On the calculator these globals live in CASUI. CASUX code reaches them as `CASUI.LINE` etc. (see `dist/CASUX.py`).

| Where | What | What it relies on |
|---|---|---|
| `enclosing()` ui.py:118-132 (L3) | Scans backwards from `CUR` with a paren depth counter and returns the name before the unmatched `(` | `LINE` is linear text. Feeds the hint line (redraw ui.py:216-217, `HINT`/`ALIAS` at :66-75) and `menu.open(..., enclosing())` (F5 help, :415). |
| `insert(text, offset=None)` ui.py:135-142 (L3) | **256-char limit**: `len(LINE)+len(text) > 256` sets STATUS `'Input limit: 256 characters'` and inserts nothing. Inserts at `CUR` and moves `CUR` by `len(text)` or by `offset`. | Side effects: `MODE=0`, `STATUS=''`, `HERO = not LINE`, `DX=0`, `NOTE=''`. All alpha, plain and 2nd keys, history paste, and menu results go through it. |
| `wrapped(text)` ui.py:145-152 | History-result paste: an atom (letters, digits, `.`) is pasted bare; anything else becomes `(text)` | `test_ui.py:31` requires `2/3{enter}x^{up}{enter}` to give exactly `LINE == 'x^(2/3)'`. |
| `empty_slot()` ui.py:155-172 (L3) | Returns the caret index of the first `(,`, `,,` or `,)`; or `()` after a name in `HINT`, `ALIAS` or **`P.FNAMES` (needs the engine)**; or a line ending in `+-*/^,(=`. Returns -1 otherwise. | Called only after `engine()` in the ENTER path (:390-394), which sets `CUR=pos` and STATUS `'fill in the empty slot'`. Template slots must serialize to these patterns, or this function must change. Tests: `test_ui.py:25,96-103` (`sin() sqrt() abs() exp() log() surd() d()` keep `LINE` and put `CUR` at `len(name)+1`). |
| redraw ui.py:184 | Hero shown when `bool(hist) and (MODE or (not LINE and HERO))` | An empty `LINE` shows the hero; the first typed key changes `VIEW` and forces a full redraw. |
| redraw ui.py:241-244, 255-260 | `XOFF` clamped so `CUR - XOFF <= 29`; `LINE[XOFF:XOFF+30]` drawn at (10,172); caret is `draw_line(x,171,x,187)` with `x = 9+10*(CUR-XOFF)`; `<` at x=0 and `>` at x=310 | One text row, 30 columns, 10 px per character. |
| `key()` CLEAR ui.py:345-353 | Leaves MODE, else empties `LINE`/`CUR`, else hides the hero; calls `TS.escape()` | |
| `key()` DEL ui.py:354-361 | **Deletes `ans()` as one unit** when `at < CUR <= at+5` (uses `rfind('ans()', 0, CUR+4)`); otherwise deletes one character | `pi`, `theta`, `sin(` are deleted one character at a time today. Test: `test_ui.py:20`. |
| `key()` left/right ui.py:362-369 | With MODE set or an empty line, scrolls the answer (`DX += ±24`). 2nd moves home/end; otherwise moves `CUR` by ±1. | |
| `key()` ENTER in MODE ui.py:380-382 | `insert(e[0])` (2nd: the input) or `insert(wrapped(e[1]))` (the result) | |
| `key()` 2nd ENTER ui.py:383-388 (ENTRY recall) | `ENTRYPOS` advances while `LINE == LASTENTRY`; sets `LINE = hist[-1-ENTRYPOS][0]` and `CUR = len(LINE)` **directly, with no 256 check** | History inputs are run's autoclosed text (`run.py:206,422`, `HIST.append([LINE, ...])` at :617), so they can be longer than the typed line. |
| `key()` ENTER ui.py:389-396 | Loads the engine if `LINE` is non-empty, then checks empty slots, then returns `job=('eval', LINE or hist[-1][0])` | The engine receives `LINE` as text. |
| `key()` menu ui.py:401-432 | Calls `R.need('menu').open(kind, LINE, CUR, enclosing())`; `line` and `cur` are unused inside `menu.open` (menu.py:22). The result is `(text, wrap, offset)`. | **Menu wrap** (:422-430): only when `CUR == len(LINE)` and (`LINE` or `R.ANS`); puts `LINE or 'ans()'` after the first `(` of the template; if the result is over 256, sets the limit STATUS and keeps `LINE` unchanged (`test_ui.py:78-93`, including the exact 256 / `CUR==255` case). |
| `key()` leading operator ui.py:433-439 | On an empty `LINE` with `R` loaded and `R.ANS` set, keys `51,55,61,65,75,85,91,95` (plain only) insert `ans()` first. Key 42 (fraction) and 104 `(-)` are not in the list. | |
| `show()` ui.py:449-458 | After `eval`: `LINE=''`, `CUR=0`, `MODE=0`, `HERO=True`, `DX=0`, `ENTRYPOS=-1`; then a full redraw | |
| `panic()` ui.py:477-505 (stays in CASUI) | Draws `LINE[max(0,CUR-29):+30]` as plain text at (10,172) | Must work **without CASUX or the layout code**: `test_ui.py:118-148` deletes `redraw`, `enclosing`, `wrapped`, `empty_slot`, `layout`, `paint`, `tree`, `measure`, `place`, `render`. A 2D editor needs a plain-text fallback here. |

Templates and other text sources:
- `menub.insertion` (menub.py:22-29) returns `prefix + ','*required + ')'` with `offset=len(prefix)`; `wrap` is true for the action commands `solve factor expand simplify partfrac integrate diff limit taylor` (menu.py:10).
- The TEST picker returns operators.
- Help (menu.py:124-125) returns an example string.
- Recall (menub.py:33-51) returns `'ans()'`, `'(' + result + ')'`, or a name.

Key tables are `PLAIN`, `SECOND`, `ALPHA` (ui.py:53-63), for example `61:'^2'`, 2nd 61 `'sqrt('`, 2nd 51 `'surd('`, 2nd 71 `'10^('`, 2nd 81 `'e^('`, key 42 `'/'`. The engine's input syntax a template can produce:
- `surd(u,n)` takes the radicand first.
- `log(u,b)` (`parse.FARGS`, parse.py:108).
- `integrate(f,x[,a,b])`, `diff(f,x[,n])`, `sum(f,k,a,b)`, `limit(f,x,a[,dir])`, `abs(u)`.

`run.start` applies autoclose (run.py:422; `MAXOPEN` 64), `ti_rewrite` and implicit multiplication.

**Tests that check `LINE`/`CUR` exactly:** test_ui.py:17,22,33,58,82,91-92,101-102,123-136 and test_fastboot.py:57-84 (`LINE=='1+2'`, `LINE=='sin(x'`).

## 2. The redraw pipeline and its current per-key cost

Screen rows (ui.py:38-44):

| Rows | Contents |
|---|---|
| 0..18 | Status (rule at 19) |
| 20..150 | Stage: hero input at y=22; answer view 10..309 × 40..131, `HEROH=92`; footer at 134. Or a list of up to 5 entries stacked up from 150, `LISTH=60`. |
| 151..168 | Hint text at 153 (rule at 169) |
| 170..189 | **Editor**: text top 172, caret rows 171..187 |
| 190..209 | F-key tabs (fill at 191, labels at 193) |

A text cell is 10 px wide and 15 rows of ink (draw.py:13-16; `text()` uses `TY=17`). docs/notes/UI.md:10-12 still gives older row numbers and an older key table, and says partial redraw is not implemented. Both are stale; DESIGN 16.4 and ui.py are current.

**`redraw()`** (ui.py:175-270, L2):
- A full repaint happens when `FULL` is set or `VIEW != (theme, MODE, SEL, hero, DX, len(hist))`.
- Otherwise it is **partial**: three background fills (status 0..18, hint 151..168, editor 170..189), then the hint, status, `LINE`, chip, caret and scroll markers.
- Drawing is grouped by color (BG, SUB, INK, ACC) because `set_color` is slow and cached in `D.color` (draw.py:58-63).
- History layouts come from `D.layout` with a cache of 5 entries / 4 KB (draw.py:369-396). The cache is cleared before every job (ui.py:440-445).

Measured with my scratch script, counting shim calls per key:

| Situation | `set_color` | `fill_rect` | `draw_text` | `draw_line` |
|---|---|---|---|---|
| Ordinary edit key or arrow (partial) | 4 | 3 | 2 (`RAD` + line) | 1 (caret) |
| Inside a call (hint shown) | 4 | 3 | 3 | 1 |
| First key after an answer (hero turns into list: full redraw) | 6 | 6 | 10-13 | 4-12 |
| Full redraw after 3 answers | 166 | 133 | 150 | 70 |

The partial path is about 10 ti_draw calls per key; a status, chip or `<`/`>` marker adds one `draw_text` each.

Tests that pin this:
- `test_fastboot.py:176-194`: a partial redraw uses at most 4 `set_color` and **exactly** these fills: `('fill_rect',-1,-1,321,20)`, `(-1,150,321,19)`, `(-1,169,321,21)`.
- `test_fastboot.py:196-203`: `typing.colors <= 4*31 + 6*2` for 30 keys.
- `test_fastboot.py:144-157` (19 SCREENS scripts): no offscreen draws, no `OVERDRAW` (text drawn over a different live text cell), every `draw_text` string ASCII 32..126 and at most 32 characters, every fill at least 2×2.

Host timing (CPython, desktop): `D.layout` takes 23 to 98 µs for typical inputs; a partial redraw takes about 97 µs, mostly shim overhead. FASTBOOT.md:29-34 estimates the EVO at about 75 times slower, so roughly 2-7 ms of layout compute per key. On the device the ti_draw calls cost more than the compute, `set_color` most of all.

Constraints on a 2D editor:
- **Height.** A fraction or exponent needs about 25-50 px (test_layout.py:64-70 bounds hero heights: `x^2` ≤25, `2/3` ≤35, integral ≤50, sum ≤62). Growing the editor upward means moving the stage boundary, the hint row and the rule at 169. Any change in editor height must force `FULL`.
- **No engine on a key.** `D.layout` needs `P` (the engine), which is not loaded while typing. The editor needs its own small tokenizer and box builder, or it can reuse `draw.leaf`/`row`/`frame`/`large` fed by its own structure.
- **Hidden brackets.** `measure` drops `P` parentheses inside frac/sup/sqrt (draw.py:174-177), so caret mapping through `layout` is ambiguous.
- **Text count.** Rows use `gap=2` (draw.py:160), so leaves are not on the 10 px grid and every leaf is a separate `draw_text`.
- **Cache.** Running editor layouts through the shared `CACHE` would push out cached history layouts.

## 3. Call-depth levels available to new editor functions

The rule (framelint.py docstring; evodepth.py:172-212): a callee's level must be greater than its caller's; levels run 1..7; strict mode allows 8 frames (the device limit is 10). The current UI chains, with level-6 leaves:
- `casevo` body (0) → `key`/`show`/`boot`/`panic` (1) → `redraw` (2) → `D.layout` (3) → `D.tree`/`D.measure`/`D.place` (4) → `D.row`/`D.frame`/`D.large` (5) → `D.leaf` (6). `layout` also calls `P.lex` (L6) and `P.rpn` (L7).
- `redraw` (2) → `D.paint` (3) → `D.render` (4) → `D.text`/`D.rect`/`D.line` (5) → `D.color`/`D.clipped_line` (6).
- `key` (1) → `insert`, `enclosing`, `empty_slot`, `wrapped` (3); `engine`, `busy` (2) → `status` (3) → `D.text` (5).
- `key` (1) → `menu.open` (2) → `menub.*` (3) and `D.text` (5).

`framelint --report` shows the deepest UI chain is level 6 (`ui.busy > ui.status > draw.text > draw.color`).

Where new functions can go:
- **Key handling:** helpers at L2-L4 called from `key` (L1). Anything that may load the engine must be L2 (as `engine()` is).
- **Painting:** an editor paint function at L3, called from `redraw`. It can call `D.render` (L4), `D.text`/`D.rect`/`D.line` (L5), and `D.tree`/`D.measure`/`D.place` (L4). It **cannot** call `D.layout` or `D.paint`, which are also L3.
- **Box building:** L4, calling `D.row`/`D.frame`/`D.large` (L5) and `D.leaf` (L6).

A caret-to-box map or slot search built at L3-L4 still leaves L5-L7 free for the existing primitives.

Code rules from framelint and lint:
- No recursion and no nested functions.
- Module bodies may only call builtins.
- Imports inside functions only in `ui.engine`, `run.need`, `run.go`, `run.room`.
- No comprehensions, generator expressions, lambdas, `with` statements, or `key=` arguments (each costs a hidden frame).

## 4. Where new UI code can live, and size headroom

Pack layout (`build/manifest.py:128-166`):
- `CASUI = ('draw','ui')`, kind `ui`, resident.
- `CASUX`, kind `view`, holds placed functions and tables: `ui.key show redraw boot engine insert enclosing empty_slot wrapped`, `draw.leaf row frame large tree measure place layout render paint`, and `ui.PLAIN SECOND ALPHA HINT ALIAS`.
- `PACKMAX = 60000`; `ROOMS['layout'] = 'CASUX'`.

Current sizes from this build (`dist/release.json`, `sizes.txt`):

| Item | Size |
|---|---|
| CASUI | ~3,540 B bytecode (always resident) |
| CASUX | ~11,156 B bytecode; reload estimate 16,130 B of heap (`room.layout`) |
| `CVUI` | 414 minified lines of a 500 budget; 14.1 of 16 KB est |
| `CVDRAW` | **342 of 350 lines**; 10.5 of 13 KB est |
| `CVMENU` / `CVMENUB` | 153 and 42 lines (class U) |
| CASEVO launcher | 512 B |

`bundle._check_output` (bundle.py:908-913) **fails the build** on a line-budget overrun, so new code in draw.py needs a higher budget in `MODULES` or a different home.

Rules:
- **Boot imports.** Boot may import only `ui`/`view` packs (`test_release.py:355`; AGENTS.md). Anything the editor needs before the engine must be in CASUI or CASUX. Class `U` lazy modules (like `menu`) are reached only through `R.need`, which needs the engine, so they are not usable for typing.
- **Prefer CASUX, keep CASUI small.** CASUI code stays resident during computation and takes heap from the engine (ui_calculus passes at 189,776 B, with under 2 KB spare in an earlier measurement, FASTBOOT.md:176). CASUX is unloaded only while a computation runs (`run.py` VIEW, INGO; `test_release.py:194-229`). Arithmetic keeps it loaded; family commands shed it below `SHEDAT` (64 KB) and reload it before `show`. A bigger CASUX raises reload pressure (each archive import is estimated at seconds) but does not affect engine compute.
- **Placement.** Each function placed in CASUX must be listed explicitly as `'ui.fn'`/`'draw.fn'` in the CASUX tuple. Unlisted functions stay in their home pack (CASUI, resident).
- **No mutable globals in view packs.** A module whose home is a soft or view pack may not assign its own globals (packs.py:250-252, "a reload would lose them"). Editor state therefore belongs in `ui`'s globals (CASUI), as `key()` already does through `CASUI.X`. View packs are reached only as `__import__('CASUX').name` and must never be stored in a global (AGENTS.md; packs.py:592, 769).
- **A new module is allowed but touches several places:**
  - `tests/support/lint.py` `ALIASES` (a fixed alias) and `RESIDENT` (it must be class R to be imported at module level, framelint.py:280-284);
  - a `manifest.MODULES` row (`CV` plus up to 6 characters, class, line and KB budgets; `bundle.check_manifest` cross-checks the lint map);
  - `PACKS` membership;
  - `tests/test_fastboot.py:20` `UI_SIDE` and the allowed-imports list at :46-55.

  Putting its home in CASUX means it holds no state. The simpler route is to add functions to `ui.py`/`draw.py` and place them in CASUX, raising the line budgets.

## 5. Test harnesses and exact commands

**`tests/support/keyscript.py`.** `KS.run(script)` runs the real `src/casevo.py` against the shims and returns a `Session`:
- `.mods['ui'].LINE`/`.CUR`, `.hist`, `.ans`;
- `.screen` (screen text), `.calls` (draw transcript), `.counts`, `.colors` (number of `set_color` calls);
- `.overdraw`, `.offscreen`;
- `.snap(label)` from `{snap:label}`.

Script syntax: `{2nd,x^n}`, `{f1}`, `{clear@1}`, `{frac}` (42), `{<>}` (95), `_` for `(-)`.

**Compatibility risk.** The typing table picks the lowest key code, so `/` is typed with **42 (the fraction key)**, `^` with 51, `sqrt(` with 2nd 61, and letters with alpha one at a time. `KS.decode` is a 1D reference typist. `build/micro_smoke.py:106-127` builds the native `ui_calculus` key stream from `keyscript.parse` (cases such as `integrate(1/(2+cos(x)),x,0,2*pi)`), and the `ui` suite replays `(93,85,94,105,21,22)` = `2+3`, ENTER, 2nd MODE. If key 42 becomes a template that grabs the preceding operand, or `)` behaves differently inside a slot, these sequences must still produce equivalent input, or `keyscript` must be updated with them.

**`shim/ti_draw.py`.** Strict device semantics: integer arguments, `fill_rect` w and h at least 2, no `set_color` with fewer than 3 arguments. Records `CALLS`, `COUNTS`, `OFFSCREEN`, `OVERDRAW`, `TEXTS`, and offers `texts()`, `screen_text()`, `texts_in()`, `pixel()`, and `screenshot(path)` (PNG).

**`build/check_release.py`.** Runs the packed release with a strict depth check and a fake heap. `tests/test_release.py` covers boot loading only ui/view packs, a view pack reloaded after being cut short, 2nd MODE quitting when CASUX cannot load, and entry scripts with `max_depth <= 8`.

Commands (Windows, from the repo root):
```
.venv/Scripts/python tests/support/lint.py src
.venv/Scripts/python tests/support/framelint.py            # add --report for deepest chains
.venv/Scripts/python -m pytest -q tests/test_ui.py tests/test_fastboot.py tests/test_layout.py tests/test_menu.py --strict-depth
.venv/Scripts/python -m pytest -q -m "not slow" --strict-depth
.venv/Scripts/python build/release.py                      # pack sizes, PackError checks, dist/release.json
.venv/Scripts/python -m pytest -q tests/test_release.py --strict-depth   # needs dist
.venv/Scripts/python -m pytest -q -m "not slow" --strict-depth --bundled
.venv/Scripts/python build/check_release.py
```

`build/archive.py` and `micro_smoke` (startup 95,000 / ui 173,360 / ui_calculus 189,776 / probe 212,000 / 64-bit 500,000) need the pinned v1.12 mpy-cross and the cas32/cas64 runtimes. They exist only in CI (`.github/workflows/build.yml:81-113`); no `dist/archive` exists locally. The startup suite imports only CASK1 and CASK2 (through CVTEST), so UI size does not affect it.

## 6. Python subset rules for new code (lint.py)

**Syntax:**
- Must parse as Python 3.4: no f-strings, `:=`, annotations, async, `@`, `raise ... from`, star-unpacking in displays, `{**d}`, keyword-only or positional-only parameters, or underscores in numbers.
- Source files must be ASCII.
- No decorators, no dunder function definitions, no `__name__ == '__main__'`.
- Classes only as empty Exception subclasses.
- No comprehensions, generator expressions, lambdas or `with` (hidden frames); write loops.

**Calls:**
- No `key=` argument.
- `map`/`filter` only with builtin callables.
- No stepped slices.
- `startswith`/`endswith` without a tuple argument.
- No `rsplit(None, n)`.
- No `round()`/`repr()` and no `%e/%f/%g` formats without `#@float-ok`.
- Iterating a dict or set needs sorting or `#@unordered-ok`.
- No direct recursion.

**Banned names:** `reversed frozenset format vars ascii open compile eval exec property staticmethod classmethod super exit quit delattr NotImplemented RecursionError ModuleNotFoundError breakpoint help __slots__`.

**Banned attributes:** `bit_length to_bytes from_bytes isqrt gcd lcm comb perm prod fsum log2 log10 hypot removeprefix removesuffix casefold ljust rjust center zfill title capitalize swapcase isalnum isnumeric isdecimal isidentifier isprintable expandtabs translate maketrans format_map popitem`, and dunder attributes other than `__name__`/`__dict__`. `isalpha` and `isdigit` are allowed (ui.py already uses them).

**Imports:**
- No `from x import`; use `import x as FIXEDALIAS`.
- Banned modules include `re functools itertools string struct json io copy operator heapq bisect`.
- Only `ui`, `draw`, `menu`, `menub` and `casevo` may import `ti_*`.
- `ti_graphics` is rejected.
- The UI may not import engine modules at module level; it uses `X = None  #@lazy mod` and binds them in `ui.engine` (ui.py:11-15).

**Drawing:** only through draw.py's `rect`/`text`/`line`/`color` → `ti_draw` `set_color`/`fill_rect`/`draw_text`/`draw_line` (`clear()` is avoided because it is slow). Text is ASCII 32..126 and at most about 31 characters per call. Glyphs not in the font are drawn as vector strokes (`draw.GLYPHS`).