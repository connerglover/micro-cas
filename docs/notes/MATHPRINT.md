# MathPrint input editor: implementation spec

> **Provenance.** A 3-design judge panel produced this spec on 2026-10-20. Three designs
> (text-backed FlowCE model, structured token buffer, performance-first) were each scored
> by three judges. Scores, out of 10:
>
> | Design | UX faithfulness | Performance / device safety | Integration risk / testability | Total |
> |---|---|---|---|---|
> | text (text-backed, FlowCE model) | 8 | 7 | 7 | **22** |
> | struct (structured buffer) | 7 | 7 | 6 | 20 |
> | perf (performance-first) | 6 | 8 | 6 | 20 |
>
> No judge found a fatal flaw in **text**, so it is the base. The judges' fixes and the
> runners-up's best ideas are folded in. §0.2 lists each change.
>
> This document is the spec the implementation follows. Input research is in
> [MATHPRINT-RESEARCH.md](MATHPRINT-RESEARCH.md).
>
> **Status.** Milestone A (the engine-free layout core, §5, and `tidy`/`structure`, §1.3–1.4)
> is implemented and tested (`tests/test_mathprint_layout.py`); §0.4 lists where the code
> settled a detail differently. Milestone B (the keys, §2–4, `emodel` and PENDING, §6.5,
> recall/paste/ENTRY, §7.4, the picker, §3.2, the Classic setting, §8, and the keyscript
> typist, §11.1) is implemented and tested (`tests/test_mathprint_keys.py`); §0.5 lists its
> decisions. Milestone C (the screen: rows and entry height, §6.1–6.3, the redraw with
> `STATVIEW`/`HINTVIEW` and the entry paint `epaint` with its caret-strip and diff paths, §6.4,
> the history page, §7.1–7.3, and the §10 cost pins) is implemented and tested
> (`tests/test_mathprint_screen.py`, `tests/test_fastboot.py`); §0.6 lists its decisions.
> Milestone D (packaging, §9.2–9.3, and the full host acceptance: lint, framelint, the
> not-slow suite in both tiers, `build/release.py`, `build/transfer.py`,
> `build/check_release.py`) passes; §0.7 records the measured pack sizes. The native
> MicroPython runs (`build/archive.py`, `micro_smoke --run`) still need the pinned v1.12
> `mpy-cross`.
> All EVO timings below are estimates (host time × 75,
> FASTBOOT.md); the draw-call counts come from the shim. Hardware acceptance needs an EVO
> run.

Notation:
- `|` is the caret inside a buffer string.
- `before → after` shows `(LINE, CUR)` around a key.
- "Hidden" means buffer characters that are not drawn.
- `L<n>` is a framelint `#@L` level.

---

## 0. Summary

### 0.1 Decisions

| Topic | Decision |
|---|---|
| Model | `ui.LINE` (str ≤ 256) and `ui.CUR` stay the single editor state, in engine syntax. A template is ordinary text, e.g. `(a)/(b)`, `x^(2)`, `sqrt(u)`, `surd(u,n)`, `log(u,b)`, `abs(u)`, `integrate(f,x[,a,b])`, `diff(f,x)`, `sum(f,k,a,b)`, `limit(f,x,a[,dir])`, `e^(u)`, `10^(u)`, `exp(u)`. Its structural parens, names and commas are hidden when drawn. No tree survives between keys. |
| Fast path | A **flat** line (no 2D construct, §5.1) is drawn exactly like today's 1D row, with no lexing or layout. |
| 2D layout | Engine-free, non-recursive: lexer, tolerant shunting-yard parser, box build with the existing `draw.row/frame/large/leaf`, then placement. Every 2D line is laid out again on each text-changing key. Arrows, home/end and up/down reuse the stored caret map (`EDMAP`) and do no layout. |
| ÷ versus fraction (Nspire) | **55** inserts a linear `/`, drawn inline while typing. **42** is the fraction template with term capture (`(a+b)|` → `(a+b)/(|)`). In the entry, a `/` is stacked only when both operands are hidden-paren groups `(..)/(..)`. After ENTER, every history input is drawn with all `/` stacked by precedence. |
| ENTER | Map-based empty-slot check first, with no engine. Then `engine()` and today's textual check. Then `job = ('eval', tidy(LINE))`. `tidy` strips structure parens around one-token operands, so HIST stays short 1D text (`1/4`, `x^2`). |
| Recall | ENTRY (2nd ENTER) and input paste go through `structure(text)`, which re-wraps bare `/` and `^` operands, so the recalled input is 2D again. Result pastes keep today's `wrapped()`, plus one rule: inside an empty hidden slot the text is pasted bare. |
| Shell | Nspire-style page. The hero is removed. A history list is always shown: pretty input on the left, result right-aligned, on one row when both fit. An ACCSOFT band marks the selection. The hint row doubles as the focused entry's footer and keeps today's strings. The entry box grows in steps (20/40/60/80 px) and shrinks only when LINE becomes empty. Geometry at EH = 20 is pixel-identical to today. |
| Per-key draw | Status and hint rows repaint only when their text changes. The caret is drawn in INK. The entry box uses a dirty-region diff (2D text change), a 2 px caret strip (2D caret move) or a full row (flat lines). Typical key: **2 `set_color`, 1 `fill_rect`, 1 `draw_text`, 1 `draw_line`**; today it is 4/3/2/1. |
| Picker | 2nd+42 opens an engine-free template picker in CASUX with 13 rows. A parameter `x`/`k` at position ≥ 1 is prefilled (FlowCE), also in `menub.insertion`. |
| Setting | F3 Setup row 5, `Entry: MathPrint/Classic`, is a ui global. Classic is today's editor exactly, and it shares the 1D path used for degrading. |
| Placement | Every new function goes in the existing `ui.py`/`draw.py`, placed in **CASUX**. CASUI gains globals only (plus a one-line change to `status`, `clear_cache` and `panic`). The highest framelint level stays **6**. Engine modules are unchanged. |
| Model refresh | One L2 function, `emodel()`, owns the editor model (flat test, layout, map, PENDING, caret snap, EH, scroll). `key` calls it before dispatch and before `redraw`; `show` and `boot` call it before `redraw`. `redraw` never lays out the entry (§6.4). |

### 0.2 What changed from the text design, and why

| Judge finding (source) | Resolution here |
|---|---|
| 55 drew stacked while typing (ux), so 42 and 55 looked alike | Entry stacking rule `(..)/(..)` (§1.2); 55 stays inline. History stacks everything. |
| A bare `1/4` had no caret stop around the fraction body (ux) | In the entry, bare `/` is inline text, so every index is a stop. Recall wraps operands (`structure`). |
| `)` with nothing to step over wrapped the slot (ux) | `)` inserts a literal `)` (perf). The layout draws a stray closer as text, and the engine reports it. |
| The hint was folded into the status row (ux) | The hint row is kept. It doubles as the footer (perf). |
| `surd()` typed with 2nd 51 became `surd(,)` (ux) | keyscript 2nd 51 becomes the action `@surd`. Text `surd(` is typed with alpha letters, so the test is unchanged (§11.1). |
| ACC caret costs a color per key (perf) | INK caret. `CARETC` is one constant if the device shows it needs ACC. |
| Prototype `edit.py` failed lint: a generator and `isalnum` (perf) | Explicit rule: loops only, `isalpha`/`isdigit` only (§9.4). |
| Full lex and parse on every text key (perf) | Flat fast path (struct). Arrows do no layout (text). |
| Full entry repaint every key (perf) | Dirty-region diff for 2D lines (perf), with a pixel-equivalence property test (§12) against stale pixels (risk). |
| Map-based `empty_slot` dropped `P.FNAMES` (risk) | Two stages: an engine-free template stage, then today's textual stage after `engine()`. |
| Hero and hint tests would need re-deriving (risk) | At EH = 20, every row and fill rectangle equals today's. The footer strings are unchanged. §11.3 lists each pin. |
| DEL `2sqrt(|x+1)` changed the meaning (struct) | Perf's paren-keeping unwrap: `2(|x+1)`. |
| Index-first caret broke `{2nd,x^n}8,3` (perf) | Caret starts in the radicand and `,` steps to the index. The index is still drawn first and visited first by → (§3). |
| `slot_at`(L4) was called from `empties`(L4) (perf) | §9 levels are checked: callee > caller everywhere, maximum level 6. |
| New module homed in a view pack is unproven (perf, risk) | No new module. |
| `x^(…)` after a fraction or power binds to the wrong operand | 51/61 right after a stacked fraction or power wrap it in a visible group first (struct). |

### 0.3 Completeness review (2026-10-20)

An adversarial pass against the code (`ui.py`, `draw.py`, `menu.py`, `menub.py`,
`catalog.py`, `build/packs.py`, `framelint.py`, `lint.py`, the tests) changed the spec as
follows. Each item is folded into the section named.

| Gap found | Fix |
|---|---|
| The map was refreshed only in `redraw`, after the key had already edited with it; after `panic` (map `None`) the first key used flat rules on a 2D line, and ENTER's refresh would re-run a layout that `EFAIL`/`ED1D` had banned | `emodel()` (L2) owns the model, keyed by `EMODEL = (LINE, CLASSIC)`; `key` runs it before dispatch and before every `redraw`; stale-map rule for every structural lookup (§1.1, §2, §6.5) |
| `HERO` in `VIEW` forced a full redraw on the first key after every answer, contradicting the §10 pins | `HERO` only drives `HINTVIEW` (§6.4) |
| Answers laid out with two caps (92 focused, 60 others) need 6 cache keys for a 5-entry FIFO cache: every MODE redraw misses every lookup | one `D.layout(e[1], 300, 92)` key per answer, view height applied at render time (§7.1) |
| ←/→ repainted everything right of the leftmost caret column: cost grew with the line | caret-only path: a 2 px strip and the items meeting it (§6.4, §10) |
| `mrender` drew boxes and ink in one call: a full redraw would need a 7th `set_color` | `mrender` draws one kind in one color per call (§5.4) |
| Prefill of `x` filled the *first* parameter of `sin(x)`, `sqrt(x)`, `purge(x,...)`, `paramarea(x,…)` | prefill only at position ≥ 1 (§3) |
| 2a deleted the base with an empty exponent (`x^(|)` → nothing); the power's span was undefined | a power's span starts at `^`; `CONS` carries the base start `cs` (§4.1, §4.3, §5.2) |
| ↓ from an exponent had no candidate although the table said `x|^(2)` | explicit power rules for ↑/↓ (§4.4) |
| DEL at the first slot of a call with other filled slots fell to rule 5 and deleted a `(` | rule 2e′ (←) (§4.3) |
| The keep-parens test let `a-sqrt(x+1)` and `2*(a+b)/()` lose their meaning on DEL | keep `(U)` unless the construct is alone in its slot (§4.3) |
| `)` inside a template slot inserted a stray closer that broke the template; `)` inside an autoclosed group left `(3)x+1)` | `)` moves the autoclosed closer, is a no-op in hidden/template slots, literal only at the root (§2) |
| Stage 2 (`empty_slot`) flagged `log(u,)` although the base is optional | log-base skip in `empty_slot` (§2.2) |
| `ui.TPL` and `ui.TGAP` were read by draw functions, but draw never imports ui | both are `draw` constants (§1.1, §9) |
| `CPLAIN`/`CSECOND` duplicated the tables | one set of tables; `edkey` intercepts action keys and autocloses `name(` texts (§2) |
| Unspecified: 2nd ↑/↓, 2nd ←/→ in MODE, keys with no entry, picker ←/→/digits/closing, who applies a picker row, Classic + picker, setup row 5 with arrows/digit 6, `VIEWEND` after Clear history, EXOFF after deletion, scroll-marker baseline, `status()` vs `STATVIEW`, history-input `MemoryError`, `enclosing` on `2sin(` | specified in §2, §3.2, §6.1, §6.3, §6.4, §7, §8 |
| `parse.mclose` already exists | the new draw function is `mshut` (§5.2, §9) |
| The spec cited a scratchpad prototype path and a shim-only font property | removed as evidence; §12.7 is the acceptance check, and no paint path relies on the font (§6.4) |

### 0.4 Milestone A implementation notes (2026-10-20)

Where the layout core (`draw.py`) or the text transforms (`ui.py`) settled a detail the
sections below left open or got wrong. Each section is edited to match.

| Spec said | Code does, and why |
|---|---|
| `mbox` builds boxes in index order (postorder node indices) | A row extended in place (and a sign hoisted over a fraction, and a power's slot) gets kids with higher indices, so index order is not children-first. `mbox` walks the reachable nodes children-first with an explicit stack instead (still no recursion) (§5.2) |
| Node kind `X` (postfix) | Not used. A postfix `!`/`'`, a stray closer and any other `?` character cling to the adjacent operand as an `R` row (after an operand; before the next one when an operand is expected). Juxtaposing them would add an implicit product: `x^ 2` would then read `(x^ )*2` (§5.2) |
| Spaces are juxtaposition separators | They cling, as above; the engine ignores them |
| `E` box item `('b', 1, -12, 8, 13)` | `('b', 1, -11, 8, 13)`: at −12 the box began one row above its own text cell and above the content box (an empty integral upper bound landed at y −1) (§5.2) |
| `mrender(dl, dx, dy, clip, x0, x1, c, boxes)` | An extra `cur=-1`: the buffer index of the caret, so the trailing-operand box at the caret can be skipped; each `'b'` item carries `(pos, flags)` (§5.4) |
| `mreduce(nodes, vals, op)`; `mshut`, `mpush` unspecified | `mreduce(nodes, vals, op, mode)` (the stacking rule needs the mode); `mpush(nodes, vals, ops, op, mode)`; `mshut(s, nodes, vals, ops, pos, how, expect, trail, mode)`; `mparse` returns `(nodes, root)` (§9.1) |
| `tleaf(boxes, s)` | `tleaf(boxes, i0, i1, txt, ti)`: a buffer slice `[i0, i1)` (cut once when the display list is built, so runs merge) or a literal `txt` when `i0 < 0` |
| Precedence from `parse.PREC` | draw cannot read the engine: the same table is the CASUX constant `draw.MPREC` (§9.2) |
| `TGAP` on every template box | Editor (mode 2) only: the gap separates two caret stops, and history inputs have no caret |
| A stacked fraction with a signed numerator (`-a/b`) unspecified in the parser | The parser follows `parse.PREC` (`neg` 6 > `/` 5), then hoists the sign over the bar: `N(Q(a, b))`, the same value, drawn with the minus outside (§1.2) |
| `structure` wraps every non-group operand | It leaves alone a construct with an operand that ends in a letter right before `(` (`1/x(x+1)`, `e^x(x+1)`): `x(…)` is a product, but a call if `x` is a user function, and wrapping would change which (§1.4) |
| Names follow `PREC` only | Names follow the engine's reading too (verification of milestone A; `parse.iscall`, `ti_rewrite`, `ti_implicit`), via `D.mcall` (L5) and the constant `D.MFNT` (a copy of `parse.FNT`). A single letter other than `f`, `g`, `h` before `(` is a product: `1/x(x+1)` is `(1/x)(x+1)` and `e^x(x+1)` is `e^x*(x+1)` (the first version drew `x(x+1)` as the denominator/exponent, and `structure` wrapped it, which changed the recalled answer). Letters before an `FNT` function or a template are cut off (`xsqrt(4)` is `x*sqrt(4)` and draws the √ template; `ysin(x)` is `y*sin(x)`). A multi-letter name the engine may cut (`ab` is `a*b`: `x^ab` is `b*x^a`, `1/ab` is `b/a`), or a call it may read as a product (`ab(2)`, `xexpand(x)`), outside brackets in the right operand of `^` or of a stacked `/` keeps that operator inline text: its extent depends on session names that draw cannot see, so no picture is drawn that the engine might not evaluate. `x^(ab)` and `1/sin(x)` are 2D as before (§1.2, §5.2) |
| Performance (not specified) | Contiguous text leaves merge while a row is built (`2+3*x` is one leaf, one box, one text item); leaf stops are written inline. Host: a dense 160-character line lays out in 200–340 µs (`test_dense_line_host_time_guard`) |

### 0.5 Milestone B implementation notes (2026-10-20)

Where the editor keys settled a detail the sections below left open, or where the spec
contradicted itself or the code. Each section is edited to match.

| Spec said | Code does, and why |
|---|---|
| The fraction key captures `a*b|` as `a*(b)/(|)`, and `2*(a+b)/(|)` is a DEL example of a stacked fraction | With `*` and `/` left-associative, `2*(a)/(b)` parsed as `(2*(a))/(b)`, which the entry rule (§1.2) draws inline, so the captured fraction was not stacked. `draw.mreduce` (mode 2) now makes a group that follows `*` or a juxtaposition the numerator when the denominator is a group, as it already hoists a sign: `2*(a)/(b)` is `2*[(a)/(b)]`, the same value. After an inline `/` it does not (`a/(b)/(c)` is `(a/b)/c`); a row records whether its last operator was `/` in its aux field (§1.2, §5.2) |
| 42 in a bare exponent (`x^2|`) | The capture stays in the exponent slot, which gets its parens first: `x^((2)/(|))`. Without them `x^(2)/()` would leave the exponent (§2.1) |
| 2f: `f(a,|b)` → `f(a|,b)`; flat lines: "a call's commas are visible, so DEL after one deletes it by rule 5" | The two disagreed on the same (flat) line. A call's commas are visible text, flat or 2D: DEL after one deletes it (rule 5), `f(a,|b)` → `f(a|b)`. 2f (act like ←) applies to templates only, whose commas are hidden (§4.3) |
| 2f example `integrate(f,x,|0,1)` → `integrate(f,x|,0,1)` | The lower bound `a` is the first slot of `∫ₐᵇ` in drawn order (§3), so 2e′ applies: `|integrate(f,x,0,1)`. A 2f example is `integrate(f,x,0,|1)` → `integrate(f,x,0|,1)` (§4.3) |
| Keep-`(U)` test: a top-level `+ - = < > ,`, `=>`, `:=` or relation | Also `* / ^`: `a/sqrt(x*y)` must not become `a/x*y`, nor `sqrt(x^2)^3` `x^2^3`. The parens stay only when the construct has a neighbour (§4.3) |
| `)` rules (1)–(4) | (2′): the innermost bracket around the caret is a visible opener of the same type with no closer at all (an unbalanced recalled or Classic text): `)` inserts its closer (`(x+1|` → `(x+1)|`) instead of doing nothing (§2) |
| Flat current slot: the innermost bracket pair, else the line | A top-level comma ends it too, as a 2D slot does: `(` in `sin(|a,b)` gives `sin((|a),b)` on both paths (§4.1) |
| `edkey` handles the editing keys | It takes DEL (calling `edmove(-1)` when `eddel` returns True: `eddel` and `edmove` are both L3), the arrows outside MODE, up/down outside MODE, the template keys and the text keys. `key` keeps CLEAR, MODE, ENTER, F4, the menus and the picker (§2, §9.1) |
| `paste(text, bare)` | `bare` is the unwrapped result (or None): `paste` (L3) cannot call `wrapped` (L3), so `key` passes both (§7.4, §9.1) |
| `edins(op)` | `edins(op, t='')`: `t` is the bracket for `open`/`close` and the text for `text` (§9.1) |
| Helpers | New L4 helpers `spans(o, cl)` (top-level argument spans), `keep(os, oe, u)` (the keep test), `blank(a, e, k, os)` (a slot that is empty or holds its prefill, through the CASUX constant `ui.PREFILL`), and L5 `bmatch(s, i, d)` (the matching bracket) (§9.1, §9.2) |
| Menu PENDING "if the line is 2D" | `key` sets PENDING for every MathPrint menu text with a `(`; `emodel` drops it on a flat line, so the offset stands there (§2) |
| Picker row 1.2 on an empty line | `^(|)` (an empty base box), the same as the 51 key |
| ENTER: stage 1 | `2+|` on a **flat** line has no map: stage 1 finds nothing and stage 2 (engine) reports it, as before. On a 2D line the trailing box is found by stage 1 |
| `emodel` step 4 | It keeps `EH` and `EXOFF` as §6.1/§6.3 say, but `redraw` still draws the buffer 1D until milestone C; `XOFF` stays `redraw`'s |
| `test_empty_slot_never_evaluates` "holds" | It asserted `len(s.hist) == 0`; with stage 1 the engine never loads, so `s.hist` is None: the test now asserts `not s.hist and 'run' not in s.mods` (§11.2) |
| keyscript: "a name" as an exponent operand | One letter only (`x^ab` is `x^a*b` to the engine), a glyph, or `name(...)`. A `^` right after a **group** exponent cannot be typed inside the box (its `)` has left it): it is typed after it and the 51 wrap rule gives `(x^(2))^(…)`, so scripts write such a nested exponent inside the group (§11.1) |
| Budgets | CVUI measured 1093 lines / 29.9 KB: budget `('ui', 'CVUI', 'R', 1200, 33)`. CASUX ~28.5 KB, CASUI ~3.8 KB (`build/release.py`) (§9.2) |
| `)` rule (2): move the closer of the visible group or call around CUR | (Verification of milestone B.) Not when a top-level comma lies between CUR and that closer: `f(a|,b)` + `)` gave `f(a)|,b`, which takes the later arguments out of the call. Such a slot has nothing to close, so rule (4) applies (no-op). The last argument still closes early: `max(a,b|+1)` → `max(a,b)|+1` (§2) |
| Leading-operator key set `51 55 61 65 75 85 91 95` | 95 (`< >`) has no text: with history it is the F4 branch of `key`, and without history (Clear history keeps Ans) Classic's table guard inserts nothing. `edkey` ran the rule before its table lookup, so it left a stray `ans()`; MathPrint now applies the rule to `51 55 61 65 75 85 91` only (§2, §11.3) |
| Stage 2's log-base skip: the name before `(` is exactly `log` | The name as the layout reads it (`D.mcall`, after leading digits): `2log(100,)` and `xlog(100,)` draw log_b and `tidy` drops their base, but stage 2 refused them (§2.2) |
| ENTER: `tidy(LINE)` | Not on the line a panic ran on (`LINE == EFAIL`): `tidy` parses it like the layout, which must not run again on it (§5.3); the structure parens are plain 1D text to the engine (§2.2) |

### 0.6 Milestone C implementation notes (2026-10-20)

Where the screen code settled a detail the sections below left open, or where the spec did
not match the code. Each section is edited to match.

| Spec said | Code does, and why |
|---|---|
| `EKEY = (LINE, CUR, XOFF, EXOFF, EH, EFLAT, theme)` | `EKEY = (LINE, CUR, geometry, caret column, caret top)` with geometry `(flat, XOFF, EXOFF, EH, theme BG, content top, ascent)`. The old caret's place is needed by the strip and diff paths, and a change of content top or ascent (a taller numerator with the same `EH`) moves every item and the markers' baseline, so it takes the full entry repaint (§6.4) |
| `EDL`: the new absolute display list | The items of `EDMAP[1]` shifted to the screen, with the trailing box at the caret (flag 1, `pos == CUR`) left out and every `'b'` item's `pos`/`flags` set to 0: two lists then compare pairwise by what is drawn. A caret move that would show or hide such a box (onto or off a trailing `E`) takes the diff path, not the caret strip (§6.4) |
| Caret strip `rect(ocx-1, oy-1, 2, 17)` | `rect(lx, cy-1, 2, 17)`, `lx` the column of the old caret line (`9 + X - EXOFF`) and `cy` its text top: the same two columns. `<` is repainted by the diff path only when `x0 < 10`; `>` whenever it shows (the diff region always reaches it, the caret strip never) |
| Batch order BG, ACCSOFT, LINE, SUB, INK, ACC | Full: BG, ACCSOFT (tabs, band), LINE (rules, then the entry's boxes), INK (the entry, caret, status, answers), SUB (inputs, messages, hint), ACC (chip, labels, footer label): one `epaint` call paints the entry's two batches back to back, so it stays one L3 call and ≤ 6 colors. Partial: BG fills (status, hint, entry), LINE/INK (entry), INK (status), SUB (hint), ACC (footer label, chip) |
| Footer: SUB hint row | Left part SUB, the right part (`exact  F4`) ACC, as today's hero drew it. `HINTVIEW = (left, right, EY)` |
| History input: 1D if `h > 36`; one row if both heights ≤ 40 | 1D only past `LISTH` (60), one row when the result is ≤ 60 high and the widths fit. With 36 every ∫ₐᵇ and Σ input (48–60 px) fell back to `integrate(x^2,x,0,1)`, which is what MathPrint is meant to replace (screenshot review). A message result shares the row when it is one line |
| `VIEWEND` recomputed "starting from SEL" | `redraw` plans backwards from `VIEWEND` (or `SEL` when `SEL > VIEWEND`); when `SEL` is above the page it runs a forward pass from `SEL` (the same height rules) and plans backwards again from the new `VIEWEND`: at most 3 passes, inline in `redraw`, because a helper at L3 could not call `D.mlayout` (L3) |
| `DX` clamped when the focused answer is wider than 300 | Clamped to the focused answer's overflow in every full redraw, so to 0 when it has none (today's hero left `DX` growing with each → on a narrow answer) |
| §12.7 "`TD.pixel` after each key" | `tests/test_mathprint_screen.py` drives `ui.key` engine-free from 7 seed lines, 200 sequences × 16 keys (text keys, templates, DEL, ←/→/↑/↓, home/end), and compares rows `EY..189` and the visible texts with a forced full entry repaint (`EDIFF = False`, `EKEY = None`) |
| `VIEW = (theme, MODE, SEL, VIEWEND, DX, len(hist), EH)` | (Verification of milestone C.) `VIEW` also holds `span`, the focused answer's overflow at the last full redraw, and `redraw` clamps `DX` to it before comparing: ←/→ on an empty line with an answer that fits made a full 6-color redraw only to clamp `DX` back to 0 (§10: a no-op key draws nothing) (§6.4) |
| History input: 1D when the layout returns None or raises `MemoryError` | (Verification of milestone C.) Any `Exception` from the mode-1 layout draws that input 1D. A layout bug on one history input otherwise raised out of every full redraw, so every key ended in `panic` until the history was cleared; `EFAIL` only guards the entry line (§7.1) |
| Budgets | CVUI measured 1284 lines / 34.0 KB: budget `('ui', 'CVUI', 'R', 1400, 37)`. CASUX ~30.9 KB, CASUI ~3.9 KB (`build/release.py`) |

### 0.7 Milestone D: packaging and acceptance (2026-10-20)

| Spec said | Code does, and why |
|---|---|
| §9.2 PACKS: every new function listed explicitly in CASUX | Done, and checked: of the `ui`/`draw` functions only `clock`, `since`, `secs`, `room`, `status`, `busy`, `reason`, `panic` and `theme`, `reset`, `color`, `rect`, `text`, `line`, `clipped_line`, `wrap`, `clear_cache` stay in CASUI, the same set as before MathPrint |
| §9.2 budgets "about 10 % over the measurement" | CVDRAW `1020/27` left 4 % line headroom after the milestone A review; now `('draw', 'CVDRAW', 'R', 1075, 28)`. CVUI `1400/37` is 9 % over 1287 lines / 34.1 KB and stays |
| §9.2 CASUX ~21 KB, reload ~30 KB | Measured 30,929 B and 43,812 B (`dist/release.json`). The editor needs more code than the 12.5 B/line estimate allowed for. CASUX still fits PACKMAX with 29 KB spare. `run.room('layout')` now asks for ~27.7 KB more free heap than before MathPrint before CASUX reloads after a heavy command; whether native `ui_calculus` still passes at 189,776 is the open gate (§12.9), not run here (no MicroPython v1.12 `mpy-cross` for `build/archive.py`) |
| §9.3 boot ~+10 KB | +20.1 KB of bytecode (≈ +28 KB heap at 1.4×). Boot still loads only CASUI + CASUX |
| §10 host guard: a dense 160-character `mlayout` < 400 µs | Measured 375–395 µs (lex ~37, parse ~115, boxes ~72, place ~125): 97 % of the guard, so `test_dense_line_host_time_guard` failed once in a full `--bundled` run and passed alone (5/5) and in the next full runs. Two device-oriented trims went in (`row` compares instead of two `max` calls per child; `mplace` keeps the open text run in locals and inlines the stop record for construct ends); on the host they are within noise. The bound was not loosened. A real margin needs a parser fast path for flat runs (operands joined by `+ - *` that merge into one leaf anyway), left for a follow-up |

### 0.8 Review fixes (2026-10-20)

An independent review after milestone D (keys, features, looks, performance and native
device lenses) confirmed the defects below; each fix has a regression test in
`tests/test_mathprint_review.py` (or the named file).

| Finding | Fix |
|---|---|
| Classic: ← could not get left of `name(` (the flat `D.mstop` snap undid each step) | `emodel` snaps only MathPrint flat lines (§6.5); Classic has ±1 arrows again |
| ENTER sent `sin(2+)`, `(2*)`, `2*()` to the engine (autoclose hid the trailing operator) | `empty_slot` also reports an operator before a closer and a nameless `()` (§2.2) |
| A menu action inserted itself inside `sin(x|)` or a trailing denominator | the wrap test treats "only closers after the caret" as the end (§2) |
| Classic menu templates were prefilled (`diff(,x)`) | prefill in MathPrint only (§3, §8) |
| A `MemoryError` in `tidy`/`structure` panicked ENTER, ENTRY and paste | caught: the 1D text is used (§1.3, §1.4) |
| `2E+` then 42 drew `2E+`¾ but evaluated `(2E+3)/4` | `tidy` keeps the parens after `E+`/`E-`; the capture takes a whole E-number (§1.3, §2.1) |
| `!`/`'` after leaving a power or fraction box bound to the last slot | `wrapend` wraps the box first, as 51/61 do (§2) |
| 42 after `{1,2}` or `1/2` gave a flat line; 51/61/42 at a power's base stop split the power | reuse only a `(` group; capture an inline `a/b`; the base stop counts as the power's end (§2, §2.1) |

---

## 1. Data model

### 1.1 State (ui globals; home CASUI)

| Global | Type, initial | Meaning |
|---|---|---|
| `LINE`, `CUR` | `''`, `0` | Unchanged names. After every `emodel()` (so at every `redraw`), `CUR` is a caret stop (§4.1). |
| `XOFF` | `0` | Character scroll of the **flat/1D** row, as today. |
| `EXOFF` | `0` | Pixel scroll of the **2D** entry. |
| `EH` | `20` | Entry box height, one of 20/40/60/80. |
| `EDMAP` | `None` | Caret map of the last 2D layout of `LINE` (§5.2, "Result"), or `None` for a flat/1D line. |
| `EMODEL` | `None` | `(LINE, CLASSIC)` for which `emodel()` last built the model. The model is rebuilt only when this differs, so a degraded line (`ED1D`, `EFAIL`) is not laid out again until the text changes, and the F3 Classic toggle rebuilds it. Set to `None` before every job and in `panic`. |
| `EFLAT` | `True` | The current line is drawn and edited flat/1D (§5.1, §5.3). Set by `emodel()`. |
| `EDL`, `EKEY` | `None` | Last painted entry: its display list (absolute coordinates, hidden boxes left out) and `(LINE, CUR, geometry, caret column, caret top)`, geometry `(flat, XOFF, EXOFF, EH, theme, content top, ascent)` (§0.6). Used by the diff paint. |
| `PENDING` | `None` | `(a, b)`: put the caret in the first empty slot (drawn order) inside `LINE[a:b]`. Resolved in `emodel()` (§6.5). |
| `ED1D` | `False` | The current line is drawn 1D because the layout is over its caps or raised `MemoryError`. |
| `EFAIL` | `None` | The `LINE` for which `panic` (reason 0 or 3) ran. While `LINE == EFAIL`, it is drawn 1D, so a failing layout is never retried in a loop. |
| `CLASSIC` | `False` | F3 setting (§8). |
| `VIEWEND` | `-1` | Index of the bottom-most history entry shown in MODE (§7.2). |
| `STATVIEW`, `HINTVIEW` | `None` | What the status row and the hint row last showed. A row is repainted only when this changes. |
| `HERO` | `True` | Now means "show the focused entry's footer in the hint row". CLEAR on an empty line clears it. It only affects `HINTVIEW`; it is **not** part of `VIEW`, so it never causes a full redraw. |
| `draw.ICACHE`, `draw.ICACHE_BYTES` | `[]`, `0` | History-input layouts (§7.3). |
| `draw.TPL`, `draw.TGAP`, `draw.MPREC` | constants | The template table (§1.2), the trailing gap (§3.1) and the operator precedences of `parse.PREC` (§1.2). They live in **draw**, not ui, because `draw.mflat/mparse/mbox` read them and draw never imports ui; ui code reads `D.TPL`. |

**Stale-map rule.** Every structural lookup in the editing code (`edslot`, `edterm`, `leave`,
the 51/61 wrap test, `empty_map`, `paste`'s bare test) reads `EDMAP` only when
`EDMAP is not None and EDMAP[0] == LINE`. Otherwise (a flat line, a degraded line, or a key
that already changed LINE once, such as the leading-operator `ans()` insert) it uses the
flat-line bracket scan of §4.1 and treats every bracket as visible. This keeps a stale map
from indexing a different buffer.

`MOD`, `MODE`, `SEL`, `DX`, `ENTRYPOS`, `LASTENTRY`, `STATUS`, `NOTE`, `FULL` and `VIEW` are
unchanged; `VIEW` gains fields (§6.4).

### 1.2 Structure is the text

`draw.TPL = {'sqrt':(1,), 'abs':(1,), 'exp':(1,), 'surd':(2,), 'log':(2,), 'integrate':(2,4), 'diff':(2,), 'sum':(4,), 'limit':(3,4)}`
(argument counts allowed for the template form). Code that scans for "a TPL name followed by
`(`" uses a lookup `name in TPL` on the name it has already cut out, never iteration over the
dict (the lint rejects unordered dict iteration without `#@unordered-ok`).

**Bare powers.** Text that was not typed with 51/61 (a help example, an F2 recall, a result
paste, a line typed in Classic) can hold a bare `B^E`. It is drawn as a power. Its exponent
slot end and the power's end are the same buffer index; by the "strictly deeper record wins"
rule of §4.1 that stop is drawn raised, at the end of the exponent. Typing `+`, `-`, `=` or
`,` there lands at the baseline because that is how the text parses; typing a digit extends
the exponent (`x^2|` + `3` → `x^23`), and a letter after a letter makes a name the engine
cuts (`x^ab` is `b*x^a`), so the `^` is then drawn inline (`x^ab`, §0.4). This is WYSIWYG
with the caret, and recall (`structure`) is the only path that adds parens.

**Names.** The picture also follows how the engine reads names (`parse.iscall`,
`ti_rewrite`, `ti_implicit`), as far as it can without the session: one letter other than
`f`, `g`, `h` (or `pi`, `oo`, `theta`) before `(` is a product, not a call (`x(x+1)`);
letters before a function of `parse.FNT` (`D.MFNT`) or a template name are a separate
product factor (`xsqrt(4)`, `kln(2)`; before `surd`, `integrate`, `diff`, `sum`, `limit`
at most two letters, as the engine cuts at most three pieces). A right operand of `^`, or of
a stacked `/`, that holds a multi-letter name or an unknown multi-letter call outside
brackets keeps that operator inline: the engine may cut the name into a product
(`1/ab` is `b/a`) unless the session defines it, which draw cannot know.

| In-buffer form | Drawn as | Hidden characters |
|---|---|---|
| `A/B` where both operands are exactly one closed `( … )` group (**entry**); any `/` (**history**, mode 1) | stacked fraction. Numerator = the precedence-5 term to the left; denominator = the unary/power operand to the right. | `/`, and the parens of an operand that is exactly one group |
| `A/B` otherwise, in the entry | inline text `/` | none |
| `B^E` | power; E is raised | `^`, and E's parens when E is exactly one group |
| `name(args)`, name in `TPL`, argument count allowed | template (§3) | the name, its parens and its top-level commas |
| `sqrt()`, `abs()`, `exp()` | the template with one empty slot (an empty list counts as one empty argument when the minimum count is 1) | as above |
| `name(args)` otherwise | plain call, drawn as text, e.g. `sin(x)`, `log(x)`, `surd()` | none |
| `( … )` elsewhere | visible group: text parens when one row high, stroked `frame('paren')` when taller | none |
| `ans()` | `Ans` (one unit) | – |
| `pi`, `theta`, `oo` | `draw.GLYPHS` strokes (one unit) | – |
| `*` | text `*` in the entry; the dot glyph in history inputs (as in answers) | – |

The 2D view follows `parse.PREC` (`'=>' ':='` 1, relations 3, `+ -` 4, `* /` and implicit
product 5, `neg` 6, `^` 7; `^`, `=>` and `:=` are right-associative). The picture is
therefore what the engine evaluates. `-a/b` with a stacked fraction is drawn with the minus
outside the bar; the value is the same.

### 1.3 `tidy(s)` (ENTER, MathPrint only), L3

`tidy` parses `s` in mode 1 (`D.mlex`, `D.mparse`, no boxes). It removes a structure-paren
pair `(`…`)` around a fraction operand or exponent when all of these hold:

1. The operand is exactly one group: `s[a] == '('` and its match is the operand's last character.
2. The interior is one leaf token: a number made of `[0-9.]`, or a single letter. An exponent
   may also be `-` followed by a number, provided the character after the group is the end of
   the line or one of `+ - , ) = < >`.
3. The character before `(` is not a letter, digit or `.`, nor a `+`/`-` that follows a
   digit's `E` (`2E+(3)/(4)` keeps its numerator parens: `2E+3` would lex as one number,
   `D.mlex`, and change what was drawn).
4. The character after `)` is not a letter, digit, `.`, `(`, `[`, `!`, `'` or `^`.

It also turns `log(u,)` (empty base) into `log(u)`. Pairs are removed right to left in a
single pass. A `MemoryError` in the parse returns `s` unchanged (the 1D text Classic sends),
so ENTER degrades instead of panicking (§0.8).

| Input | Output |
|---|---|
| `(1)/(4)` | `1/4` |
| `x^(2)+1` | `x^2+1` |
| `x^(-1)` | `x^-1` |
| `e^(x)` | `e^x` |
| `(x+1)/(2)` | `(x+1)/2` |
| `x^(2)3` | unchanged (rule 4) |
| `(1)/(4)x` | `1/(4)x` |
| `expand((x+1)^(12))` | `expand((x+1)^12)` |

`run.start` still applies autoclose, Ans, `ti_rewrite` and implicit multiplication. The
engine is unchanged.

### 1.4 `structure(s)` (recall only), L3

`structure` parses `s` in mode 1. For every stacked fraction operand and every exponent
that is not exactly one group, it inserts `(` at the operand's start and `)` at its end.
Insertions are collected as `(pos, ch)` tuples, sorted with a plain `list.sort()`, and
applied right to left. If the result is longer than 256 characters, or the parse raises
`MemoryError`, `s` is returned unchanged (ENTRY recall and history paste then give the 1D
text, §0.8). A fraction or power over a name the engine may cut is not one in the mode-1
parse (it stays inline, §1.2), so `a/bc` is left alone: the engine reads it as `(a/b)c`. A
construct with an operand that ends in a letter right before `(` is left alone too:
`1/x(x+1)` is `(1/x)(x+1)`, but a call if `x` is a user function, and wrapping `x` alone or
`x(x+1)` would decide that (§0.4).

| Input | Output |
|---|---|
| `1/4` | `(1)/(4)` |
| `x^2+1` | `x^(2)+1` |
| `(1+x)/2` | `(1+x)/(2)` |
| `1/(x+1)` | `(1)/(x+1)` |
| `x^2/3` | `(x^(2))/(3)` |
| `-a/b` | `-(a)/(b)` |
| `a/bc`, `x^ab`, `1/x(x+1)`, `e^x(x+1)` | unchanged |
| `2/xsqrt(4)` | `(2)/(x)sqrt(4)` |

Round trip: `tidy(structure(s))` must evaluate to the same `run.go` record as `s` (test §12.4).

---

## 2. Keys (MathPrint; Classic is §8)

Every edit goes through `ui.put(line, cur)` (L4). If `len(line) > 256`, it sets
`STATUS = 'Input limit: 256 characters'` and changes nothing. Otherwise it applies
`insert()`'s side effects: `MODE = 0`, `STATUS = ''`, `DX = 0`, `NOTE = ''` and
`HERO = not line`. Modifier handling (21, 31, lock, chip), 2nd MODE quit and the MODE
(history) branches of `key` are unchanged unless a row below says otherwise.

**Leave rule (`ui.leave`, L4).** While `CUR` is at the end of a hidden denominator or
exponent slot, `CUR` moves to that construct's end. The keys `,`, `=>` and the TEST
relations (`=`, `!=`, `<`, `<=`, `>`, `>=`) apply this rule always. `+` (85) and `−` (75)
apply it only when the slot's whole content is one visible group (struct's rule): with
`(1)/((x+1)|)`, typing `+` gives `(1)/((x+1))+|`.

**Leading-operator rule.** Unchanged. On an empty LINE with `R.ANS` set, plain keys
51, 55, 61, 65, 75, 85 and 91 insert `ans()` first (95, also in today's set, has no text in
the editor: Classic's table guard inserts nothing for it, and neither does `edkey`; §0.5). The keys 42 and 104 do not, nor
does a picker row.

**Dispatch order in `key` (L1).** Today's order is kept; new branches slot in as follows.
1. 21 (2nd) and 31 (alpha) change `MOD`, then `emodel()` (a no-op unless stale) and
   `redraw()`, as today. **Every** `redraw` call is preceded by `emodel()`.
2. `if EMODEL != (LINE, CLASSIC): emodel()` (normally a no-op; it matters after `panic` and
   after a menu changed CLASSIC).
3. `mod >= 2 and k in ALPHA` → plain insert of the letter (so alpha+42 is still `b`).
4. 2nd MODE → `QUIT`; CLEAR; DEL; ←/→; ↑/↓; ENTER; F4/95; menus; as listed below.
5. 2nd 42 → picker (MathPrint only).
6. Otherwise, in MathPrint, `edkey(k, mod)`; in Classic, today's `PLAIN`/`SECOND` insert.
   A key with no entry does nothing, and the following `redraw` makes no ti_draw call
   (§6.4 step 6).
7. If a job was set: `STATUS = 'Calculating...'`, `emodel()`, `redraw()`, then free the
   editor (`EDMAP = EDL = EKEY = None`, `EMODEL = None`, `PENDING = None`) and
   `D.clear_cache()`; else `emodel()`, `redraw()`.

**Tables.** `PLAIN`, `SECOND` and `ALPHA` stay exactly as today (Classic uses them as
today). In MathPrint, `edkey` handles the action keys (42, 51, 61, 62, 63, 64, 2nd 51,
2nd 63, 2nd 64, 2nd 75, 2nd 85) itself and otherwise inserts the table text, with one
rule: a table text ending in `(` (`sin(`, `log(`, `ln(`, `asin(`, `sqrt(`, `10^(`, `e^(`)
is inserted as `text + ')'` with the caret before the `)`. There are no separate
MathPrint tables.

| Key | MathPrint behaviour | Examples |
|---|---|---|
| digits, `.`, alpha letters, `x`/`t`/`theta` (32), `E` (2nd 62), `i` (2nd 103), `pi` (2nd 55), `e` (2nd 65), space, `'`, `*` (65), `(-)` (104, `-`), 2nd (−) (`ans()`) | Plain insert at CUR. `ans()` is inserted whole. | `x|` + `2` → `x2|` |
| `+` 85, `−` 75 | Leave rule (group-only form), then insert. | |
| `=>` 91 | Leave rule, then insert. | `x^(2|)` → `x^(2)=>|` |
| **55 ÷** | Insert a bare `/`. Drawn inline. | `1|` → `1/|` |
| **42 fraction** | Term capture (§2.1). | `x|` → `(x)/(|)` |
| **51 xⁿ** | (`ui.wrapend`) At a power's base stop (`CUR` = `os` of a W, where ↓ lands) `CUR` first moves to that power's end `oe`. If `CUR` equals the end `oe` of a stacked fraction (Q) or power (W) in `EDMAP.CONS` (fresh map only), wrap that construct, from its full start `cs` (the numerator start, or the **base** start of a power) to `oe`, in `(`…`)` first. Then insert `^()` with the caret inside. Typing `+` inside stays in the exponent. → leaves it. Only the power itself is wrapped, never a preceding factor. | `x|` → `x^(|)`; `x^(2)|` → `(x^(2))^(|)`; `2x^(2)|` → `2(x^(2))^(|)`; `x|^(2)` → `(x^(2))^(|)` |
| `!` (TEST menu), `'` (alpha .) | The same wrap (`wrapend`, without the base-stop move), then insert: a postfix after a power or fraction box applies to the whole box, as on the Nspire. Inside a box it stays inside. | `3^(2)|` → `(3^(2))!|`; `(3)/(2)|` → `((3)/(2))!|`; `3^(2|)` → `3^(2!|)` |
| **61 x²** | Same wrap rule, then insert `^(2)` with the caret after it. | `x|` → `x^(2)|`; `sin(x|)` → `sin(x^(2)|)`; `x|^(2)` → `(x^(2))^(2)|` |
| 2nd 61 √ | `sqrt(|)` | |
| 2nd 51 ⁿ√ | `surd(|,)`: caret in the radicand (offset 5, not PENDING). `,` steps to the index. | `{2nd,x^n}8,3` → `surd(8,3)` |
| 2nd 71 10ˣ, 2nd 81 eˣ | `10^(|)`, `e^(|)` | |
| 71 log, 81 ln, 52–54 sin cos tan, 2nd 52–54 asin… | `log(|)`, `ln(|)`, `sin(|)` and so on. The closer goes in at once. `log(` stays a plain call; log base b comes from the picker. | |
| 63 `(`, 2nd 63 `{`, 2nd 75 `[` | In an empty hidden exponent (`x^(|)`): no-op, because the box is the group. Otherwise insert the opener at CUR and its closer at the **end of the current slot** (§4.1; for a flat line, the innermost unmatched bracket pair, else the end of the line). | `|x+1` → `(|x+1)`; `1/|4` → `1/(|4)`; at the end: `(|)` |
| 64 `)`, 2nd 64 `}`, 2nd 85 `]` | First match: (1) `LINE[CUR]` is the same closer, hidden or visible: step over it; at a hidden numerator closer this lands on the denominator start. (2) CUR is inside a visible group or a plain call (the innermost bracket pair around CUR that lies inside the current slot) whose opener is the same bracket type and whose closer is further right: **move** that closer to CUR. This undoes the autoclose of key 63 when the user closes earlier. Not when a top-level comma of that pair lies between CUR and the closer (it would take the later arguments out of the call): then (4) (§0.5). (3) The current slot is the root: insert the closer literally (the layout draws it as text; the engine reports it). (2′) The innermost bracket is a visible opener of the same type with no closer: insert the closer (`(x+1|` → `(x+1)|`; §0.5). (4) Otherwise (inside a hidden or template slot, with nothing to close): no-op. | `x^(2|)` → `x^(2)|`; `sin(x|)` → `sin(x)|`; `2(3|x+1)` → `2(3)|x+1`; `sin(a|+b)` → `sin(a)|+b`; `x+1|` → `x+1)|`; `integrate(f|,x)` → unchanged; `f(a|,b)` → unchanged |
| 62 `,` | Leave rule. Then, if `LINE[CUR] == ','`, step over it; else insert `,`. | `surd(8|,)` → `surd(8,|)`; `integrate(x^(2|),x)` → `integrate(x^(2),|x)` |
| ← → (24/26) | MODE or empty LINE: `DX ± 24`, as today. Otherwise move to the previous/next stop in drawn order (§4.2). No layout. | |
| 2nd ← / 2nd → | MODE or empty LINE: `DX ± 24`, as today. Otherwise home / end: `CUR = 0` / `len(LINE)`. | |
| ↑ (25) | MODE: as today (2nd ↑ moves 5). Empty LINE: enter history (as today, if any). 2nd ↑ with a non-empty LINE: enter history directly, as today. Otherwise `edvert(-1)` (§4.4). If that returns False and history exists: `MODE, SEL = 1, len(hist)-1`. | `x^(|)` ↑ → history |
| ↓ (34) | MODE: as today (2nd ↓ moves 5; past the newest leaves MODE). Otherwise `edvert(+1)` (2nd ↓ too); nothing if False. | `(a|)/(b)` ↓ → `(a)/(b|)` |
| DEL (23) | §4.3 | |
| CLEAR (45), with or without 2nd | Unchanged order: leave MODE; else empty LINE (`CUR = XOFF = EXOFF = 0`, `PENDING = None`; `emodel` then sets `EH = 20`); else `HERO = False`. Always `STATUS = ''` and `TS.escape()`. `ENTRYPOS`/`LASTENTRY` are untouched, as today. | |
| ENTER (105) | MODE: paste the result (§7.4). Otherwise (§2.2): two-stage empty-slot check, then the job. | |
| 2nd ENTER | MODE: paste `structure(e[0])`. Otherwise ENTRY recall: `ENTRYPOS` as today; `LINE = structure(hist[-1-ENTRYPOS][0])`, `CUR = len(LINE)`, `LASTENTRY = LINE`. No 256 check, as today. | |
| **2nd 42** (new) | MathPrint: `row = picker()` (§3.2), then `key` applies the row (rows 1–2 through `edins`, the others through `put` + PENDING). Classic: nothing, as today. | |
| F1, math (41), 2nd math (TEST), vars (44), F2, F3, mode (22), F5, 2nd 0 | `R.need('menu').open(kind, LINE, CUR, enclosing())`, unchanged. The result goes through today's wrap/limit code (an action wraps the whole line when the caret is at its end; in MathPrint also when only closers `) ] }` follow it, since autoclosed and hidden closers sit after a caret that looks like it is at the end: `sin(x|)` + simplify → `simplify(sin(x))`, §0.8), then `insert(text, offset)`. If `text` contains `(` and the line is 2D, `PENDING = (start, start + len(text))`; on a flat line PENDING is not set and the offset stands. A TEST relation (`=`, `!=`, `<`, `<=`, `>`, `>=`, not `!`) first applies the leave rule. After the menu: `VIEWEND = min(VIEWEND, len(hist)-1)` (Clear history may have emptied it). | |
| F4, `< >` (95) | Unchanged (needs history; `95` with no history does nothing). | |
| Any other key or modifier combination (33, 43, 2nd digits, 2nd 91, …) | No entry in any table: nothing changes and no ti_draw call is made. | |

### 2.1 Fraction term capture (42 and picker row 1), in `edins`

Scan left from `CUR` inside the current slot. The term is made of:
- letters, digits, `.`, `'` and `!`;
- a bare `^` and its base;
- a closed bracket group, jumping to its opener and then over a call name before it;
- a hidden exponent closer, jumping to its `^(` and continuing to the base;
- an inline `/` between two such terms, so `1/2|` gives `(1/2)/(|)` (stacked, `1/2` inline in
  the numerator) rather than `1/(2)/(|)`, which the layout keeps inline after the `/` (§0.8);
- the sign of an E-number, `2E+3|` → `(2E+3)/(|)` (the `+`/`-` after a digit's `E` with a
  digit after it, as `D.mlex` reads it);
- a hidden denominator closer (CUR, or the scan, at the `oe` of a stacked fraction):
  jumping to the fraction's full start `cs`, so `(a)/(b)|` gives `((a)/(b))/(|)` and
  never splits the fraction.

The scan stops at a slot start or at any of `+ - * = < > ,` and the 2-character
relations, and at a `/` with nothing captured yet (`1/|` gives `1/(|)/()`). At a power's
base stop (`x|^(2)`) the capture starts from the power's end: `(x^(2))/(|)`. Only text left of CUR is captured: `ab|c` → `(ab)/(|)c`.

The group is **reused** (only `/()` is inserted) exactly when the captured term is one
visible paren group `( … )` (not a list `{…}` or matrix `[…]`, which the entry rule would
not stack: `{1,2}|` gives `({1,2})/(|)`) with no name and no other factor before it, i.e. the term
starts at the group's opener. `2(a+b)|` captures `2(a+b)` and gives `(2(a+b))/(|)`.

After `*` (`a*b|` → `a*(b)/(|)`) the fraction is stacked because the layout makes the group
after `*` the numerator (§0.5). In a bare exponent the slot gets its parens first:
`x^2|` → `x^((2)/(|))`.

The scan reads the fresh map when there is one (stale-map rule, §1.1); otherwise it treats
`)` as a visible closer, which gives the same text for every row below.

| Before | After |
|---|---|
| `x|` | `(x)/(|)` |
| `2sin(x)|` | `(2sin(x))/(|)` |
| `a+b|` | `a+(b)/(|)` |
| `-x|` | `-(x)/(|)` |
| `(a+b)|` (free group, no name before it) | `(a+b)/(|)` (the group is reused: insert `/()` only) |
| `x^(2)|` | `(x^(2))/(|)` |
| `ans()|` | `(ans())/(|)` |
| `sqrt(x|)` | `sqrt((x)/(|))` |
| `a+|`, or an empty line | `a+(|)/()`, `(|)/()` |

### 2.2 ENTER (not MODE, not 2nd)

```
pos = -1
if LINE and not CLASSIC:
    pos = empty_map()                    # stage 1: engine-free; the model is fresh (key step 2)
if pos < 0 and LINE:
    engine()                             # the first ENTER loads the engine
    pos = empty_slot()                   # stage 2: today's textual rules + the log-base skip
if pos >= 0:
    CUR, STATUS = pos, 'fill in the empty slot'
elif LINE or hist:
    job = ('eval', (LINE if CLASSIC or LINE == EFAIL else tidy(LINE)) or hist[-1][0])
```

`empty_map()` (L3) never lays out (the model is already fresh: `key` ran `emodel()` at
step 2 of its dispatch, and a degraded line must not be laid out again).
- **2D line (fresh `EDMAP`):** the buffer index of the first `E` node in drawn order, in
  `EDMAP.EMPTY`. It excludes the empty base of a 2-argument `log`, which is optional and
  removed by `tidy`. The "trailing operand at the caret" flag of an `E` only affects
  drawing (§5.4); `empty_map` counts that `E` (`2+|` ENTER → caret stays, message shown).
- **Flat, degraded or `EFAIL` line (no map):** a textual scan for hidden empties that
  stage 2 does not know: the first of `^()`, `/()` and `()/(` gives the index just inside
  the empty pair. Otherwise -1.

`empty_slot()` (stage 2) keeps today's rules with one change: a `,)` hit whose closer ends
a `log(` call (the name as `D.mcall` reads it after leading digits, so `2log(` and `xlog(`
too) with exactly two top-level arguments is skipped (the empty base is optional),
and the search continues after it. Without this, `log(8,)` from picker row 1.7 would be
refused at stage 2. In MathPrint it also reports what autoclose hides from the old
trailing-operator test (§0.8): an empty group `()` with no name before it (`2*(|)`), and an
operator `+ - * / ^ = < >` right before a closer (`sin(2+|)`, `(2*|)`), with the caret before
the closer. Classic keeps the old rules.

Before a job (key step 7, after the last `redraw`): `EDMAP = EDL = EKEY = None`,
`EMODEL = None`, `PENDING = None`, then `D.clear_cache()` (which also empties ICACHE), as
today.

---

## 3. Template catalog

**Drawn order** is both the ←/→ visiting order and the "first empty slot" order. The
**engine text** is what `tidy` emits.

| Template | Inserted by → buffer (caret) | 2D rendering (one 10 px font; boxes from `draw.frame/large`) | Slots, drawn order | Engine text |
|---|---|---|---|---|
| Fraction | 42, picker 1 → `(T)/(|)` or `(|)/()` | `frame('frac')`: bar at baseline−4, both operands centred, w = max+4, **+3 px trailing gap** | num, den | `a/b`; `(a+1)/(b-1)` |
| Linear ÷ | 55 → `a/b` | entry: inline text; history: as a fraction | – | as typed |
| Power | 51, picker 2 → `B^(|)` | `frame('sup')`: exponent bottom at `-(a*9//20)`, x = base.w+1 | exp | `x^2`, `x^(n+1)` |
| Square | 61 → `B^(2)|` | as power | exp | `x^2` |
| √ | 2nd 61, picker 3 → `sqrt(|)` | `frame('sqrt')` + 3 px | radicand | `sqrt(u)` |
| ⁿ√ | 2nd 51, picker 4 → `surd(|,)` | `frame('root')` (index raised at the left) + 3 px | **index, radicand** | `surd(u,n)` |
| eˣ | 2nd 81, picker 5 → `e^(|)` | power with base `e` | exp | `e^u` / `e^(u)` |
| `exp(u)` (catalog or typed) | `exp(|)` | `frame('sup')` of leaf `e` and u | u | `exp(u)` |
| 10ˣ | 2nd 71, picker 6 → `10^(|)` | power | exp | `10^u` |
| log_b | picker 7 → `log(,)`; PENDING puts the caret on b | text `log`, then b lowered 6 px at x 30, then `(u)` (text parens if one row, else stroked) + 3 px | **b, u** | `log(u,b)`; an empty b gives `log(u)` |
| \|x\| | picker 8 → `abs(|)` | `frame('abs')` + 3 px | u | `abs(u)` |
| ∫ | picker 9, catalog → `integrate(|,x)` | `large('integral')`, `d`, x; + 3 px | f, x | `integrate(f,x)` |
| ∫ₐᵇ | picker 10 → `integrate(,x,|,)` | `large('integral')` with bounds + 3 px | **a, b, f, x** | `integrate(f,x,a,b)` |
| d/dx | picker 11, catalog → `diff(|,x)` | `frame('frac')` of `d` over `d x`, then f in parens (text parens if one row) + 3 px | **x, f** | `diff(f,x)` |
| Σ | picker 12, catalog → `sum(,k,|,)` | `large('sum')`; `k=a` below, b above + 3 px | **k, a, b, f** | `sum(f,k,a,b)` |
| lim | picker 13, catalog → `limit(,x,|)` | `large('limit')`, `x->a` below; the 4-argument form draws dir as a superscript on a; + 3 px | **x, a, (dir), f** | `limit(f,x,a[,dir])` |
| Call | `sin(|)` … | text: name + `(` + args + `)`, merged into one run when one row high | args in order | as typed |
| Group | `(|)` | text parens if one row, else `frame('paren')` | interior | as typed |

**Prefill.** In the picker and in `menub.insertion` (MathPrint only; Classic keeps the old empty text, §8), a required parameter named exactly `x`
or `k` **at position 1 or later** is filled with its own name. `insertion(row)` builds the
text from the required parameter names (split on `,`): an empty string, or `x`/`k`. The
offset stays `len(prefix)`. Position 0 is never prefilled: every one-argument row
(`sin(x)`, `sqrt(x)`, `abs(x)`, `exp(x)`, `ln(x)`, …), `log(x,[b])`, `surd(x,n)`,
`purge(x,...)` and `paramarea(x,y,t,a,b)` name their *first* parameter `x`, and prefilling
it would give `sin(x)` or a ready-to-run `purge(x)`. Those rows stay as today
(`sin()`, `surd(,)`, `purge()`, `paramarea(,,,,)`).

| Catalog row | Text before | Text after |
|---|---|---|
| `diff(f,x,[n])` | `diff(,)` | `diff(,x)` |
| `integrate(f,x,[a,b])` | `integrate(,)` | `integrate(,x)` |
| `limit(f,x,a,[dir])` | `limit(,,)` | `limit(,x,)` |
| `sum(f,k,a,b)` | `sum(,,,)` | `sum(,k,,)` |
| `riemann(…)` | | `riemann(,x,,,)` |
| `arclen(…)` | | `arclen(,x,,)` |
| `taylor(f,x=a,[n])` | `taylor(,)` | unchanged |
| `solve(eq,[x])` | `solve()` | unchanged |

`test_calculus_template` (`result[0][result[2]] in ',)'`) still holds. With an action wrap
(F1 on a non-empty line), `diff(LINE,x)` is complete, so ENTER runs it at once; PENDING then
finds no empty slot and the offset stands.

A slot whose text is exactly its prefilled default counts as **empty for DEL rule 2a
only**. It is filled for `empty_map` and for PENDING.

**Every slot box handed to `frame`/`large` is a row box (`D.row(boxes, ids, 0)`), never a
`'paren'` box.** Otherwise `frame`'s paren stripping (draw.py:174-177) would hide parens the
user typed.

### 3.1 Trailing gap

`draw.TGAP = 3` px is added, in the editor (mode 2), to the width of every template box except power, group and call. Its
purpose: "end of the last slot" and "after the construct" must be distinct caret
positions. The text prototype showed `integrate(,x,,)` with both at the same pixel.

### 3.2 Picker: `ui.picker()` (L2, CASUX, engine-free)

- **Screen.** It is drawn like `menu.open`: full-screen BG, title `Templates` at (5, 2),
  rule at 19, rows at `22 + 17*j`, the selected row prefixed `>`, a rule at 188, and the
  footer `1-7 pick  CLEAR back` at (5, 192) in ACC. It runs its own `TS.wait_key` loop.
- **Pages.** 7 rows per page (a literal in `picker`, not a new global; `PAGE` is already a
  menu name). Page 1 holds rows 1–7 and page 2 rows 8–13, each numbered from 1.
- **Keys.**
  - ↑/↓ move the selection, wrapping, and change page as needed.
  - ←/→ flip the page (the selection keeps its number, clamped to the page).
  - Digit d (read through `PLAIN.get(k)` being a digit; `menu.DIGITS` is not reachable
    without the engine) picks row `page*7 + d - 1` at once; a digit past the last row of
    the page is ignored.
  - ENTER picks the selected row.
  - CLEAR, F1 or 2nd 42 returns None. Every other key is ignored. 2nd and alpha are not
    tracked inside the picker.
- **Result.** `picker()` returns the row index or None and changes no editor state. On
  return, `key` sets `FULL = True` and applies the row: rows 1–2 through `edins('frac')` /
  `edins('pow')` (L3, called from `key` L1, never from `picker` or `edkey`, which are both
  L2), the others through `put` with the PENDING / explicit caret of §3.

Rows, as (label, text, caret):

| Page.row | Label | Text | Caret |
|---|---|---|---|
| 1.1 | `n/d  fraction` | FRAC action | §2.1 |
| 1.2 | `x^n  power` | POW action | in the exponent |
| 1.3 | `sqrt  square root` | `sqrt()` | 5 |
| 1.4 | `n-root  nth root` | `surd(,)` | 5 (radicand) |
| 1.5 | `e^x` | `e^()` | 3 |
| 1.6 | `10^x` | `10^()` | 4 |
| 1.7 | `log_b  log base b` | `log(,)` | PENDING (b) |
| 2.1 | `|x|  absolute value` | `abs()` | 4 |
| 2.2 | `int  integral` | `integrate(,x)` | PENDING (f) |
| 2.3 | `int a..b  definite` | `integrate(,x,,)` | PENDING (a) |
| 2.4 | `d/dx  derivative` | `diff(,x)` | PENDING (f) |
| 2.5 | `sum  k=a..b` | `sum(,k,,)` | PENDING (a) |
| 2.6 | `lim  limit` | `limit(,x,)` | PENDING (a) |

---

## 4. Caret and deletion

### 4.1 Stops and slots (2D lines)

`D.mplace` walks the boxes depth-first with an explicit stack. It visits template children
in drawn order and calls `mmark(i, x, ytop, dep)` for each of these:
- each slot row's start and end index;
- each text leaf whose text equals its buffer slice: every interior index at `x + 10*k`;
- each glyph or alias leaf (`pi`, `theta`, `oo`, `Ans`): only its two ends;
- each construct: its outer start at its left edge and its outer end at its right edge
  (after `TGAP`).

`dep` is the slot depth: root 0, each slot one more than its owner. A record is replaced
only by one from a **strictly deeper** slot. Ties keep the first emission. Indices never
marked are non-stops: hidden structure, call-name interiors, glyph interiors.

`ORD` lists the stops by the emission sequence of their final record. It is built by
bucketing a per-index sequence number into a list of length `nseq`, then compacting (no
`sort`, no `key=`).

Each slot gets a row in `SLOTS`: `(s, e, okind, os, oe, k, nslots, hidden, dep)`, where
- `okind` ∈ `R` root, `Q` fraction, `W` power, `T` template, `G` group, `C` call;
- `[os, oe)` is the owner's buffer span. For a power (W) the span starts at the `^`, not
  at the base: `x^(2)` has `os = 1`, `oe = 5`. The base is not a slot of the power; its
  start is kept in `CONS` (`cs`, §5.2) for the 51/61 wrap rule;
- `k` is the slot's buffer index within its owner.

`SL[i]` is the slot id of stop i. A non-stop `CUR` (after a menu offset, a paste or
PENDING) snaps to the next stop in buffer order.

Prototype stop lists (text design, `t1.py`):

| Buffer | Stops | `ORD` |
|---|---|---|
| `x^(2)+1` | 0 1 3 4 5 6 7 | same (4 = end of exponent, top 0; 5 = after the power, baseline) |
| `(a)/(b)` | 0 1 2 5 6 7 | same |
| `surd(8,3)` | 0 5 6 7 8 9 | 0 7 8 5 6 9 |
| `sum(,k,,)` | 0 4 5 6 7 8 9 | 0 5 6 7 8 4 9 |
| `integrate(,x,,)` | | 0 13 14 10 11 12 15 |
| `sin(x)` | 0 4 5 6 | same |

**Flat lines** have no map. Every index is a stop except the interior of a call name before
its `(`, i.e. positions `start+1 .. index of '('`, where the call name is what `D.mcall`
(L5) keeps of the name (§1.2: none for `x(`, `sin` in `ysin(`). `D.mstop(s, i)` (L4) tests
this by a local scan.
The current slot is the interior of the innermost unmatched bracket pair around CUR, else
the whole line; a top-level comma ends it too, as on a 2D line (`ui.edslot`, §0.5).
`X[i] = 10*i`.

### 4.2 ← / → (`edmove`, L3)

- 2D: `CUR = ORD[RK[CUR] ± 1]`, skipping entries whose `(X, Y)` equals the current one.
  Clamp at the ends.
- Flat: `CUR ± 1`, then skip non-stops in the same direction.

| Before | Key | After |
|---|---|---|
| `x^(2|)+1` | → | `x^(2)|+1` (one press back to the baseline) |
| `(a|)/(b)` | → | `(a)/(|b)` |
| `(a)/(b|)` | → | `(a)/(b)|` |
| `|surd(8,3)` | → | `surd(8,|3)` (index first) |
| `surd(8,3|)` | → | `surd(|8,3)` |
| `sum(f,k,1,n|)` | → | `sum(|f,k,1,n)` |
| `sum(f,k,|1,n)` | ← | `sum(f,k|,1,n)` |
| `si|n(x)` | – | cannot occur (non-stop) |

### 4.3 DEL (`eddel`, L3), first matching rule

| # | Condition | Action | Examples |
|---|---|---|---|
| 1 | `ans()` straddles or ends at CUR (today's `rfind` rule) | delete it whole | `2ans()|` → `2|` |
| 2a | CUR at a slot start of a Q/W/T whose slots are all empty (prefill counts as empty) | delete the owner span `[os, oe)`. For a power that is `^(…)` only: **the base stays** (§4.1: a power's span starts at `^`) | `sum(,k,|,)` → `|`; `(|)/()` → `|`; `integrate(|,x)` → `|`; `x^(|)` → `x|` |
| 2b | power, exponent start, non-empty | `CUR = os` (before `^`) | `x^(|2)` → `x|^(2)` |
| 2c | fraction, denominator start | denominator empty: unwrap the numerator U (the keep-`(U)` test of 2e applies, with the fraction's own neighbours), caret at its end; else go to the numerator end | `(a)/(|)` → `a|`; `(a+b)/(|)` → `a+b|`; `2*(a+b)/(|)` → `2*(a+b)|`; `(a)/(|b)` → `(a|)/(b)` |
| 2d | fraction, numerator start | denominator empty: unwrap as in 2c, caret at its start; else `CUR = os` | `(|a)/()` → `|a`; `(|a)/(b)` → `|(a)/(b)` |
| 2e | template or call, first slot in drawn order, all other slots empty (prefill counts) | unwrap the content U. **Keep-`(U)` test:** keep the parens if U has a top-level `+ - * / ^ = < > ,`, `=>`, `:=` or relation, or a leading sign (`* / ^` added in milestone B, §0.5), **unless** the construct is alone in its slot: the char before its start is the line start, `(` (visible or hidden) or `,`, **and** the char at `oe` is the line end, `)` or `,`. (Any other neighbour, including `*`, `/`, `^`, `-` and `+`, keeps the parens: `a-sqrt(x+1)` must not become `a-x+1`.) | `2sqrt(|x+1)` → `2(|x+1)`; `a-sqrt(|x+1)` → `a-(|x+1)`; `sqrt(|x+1)` → `|x+1`; `sqrt(|x)` → `|x`; `sin(|x)` → `|x`; `sin(|)` → `|` |
| 2e′ | template or call, first slot in drawn order, some other slot non-empty | act like ← (to the construct's outer start); nothing is deleted | `f(|a,b)` → `|f(a,b)`; `surd(8,|3)` → `|surd(8,3)`; `integrate(f,x,|0,1)` → `|integrate(f,x,0,1)` |
| 2f | template, any other slot start (a call's commas are visible: rule 5 deletes them, `f(a,|b)` → `f(a|b)`; §0.5) | act like ← | `integrate(f,x,0,|1)` → `integrate(f,x,0|,1)`; `integrate(f,x,|0,1)` is 2e′ (a is drawn first) |
| 2g | visible group start | remove both brackets if matched; an unmatched opener falls through to rule 5 (deleted alone) | `(|a+b)` → `|a+b` |
| 3 | the previous stop p and CUR lie in one visible leaf | delete `LINE[p:CUR]` | `x+pi|` → `x+|`; `12|` → `1|` |
| 4 | CUR just after a construct (template, fraction, power, call, or a **matched** group) | if it is empty (prefill counts): delete it (for a power, `^(…)` only); else step into it (←) | `sqrt()|` → `|`; `sqrt(x)|` → `sqrt(x|)`; `x^(2)|` → `x^(2|)`; `(a+b)|` → `(a+b|)`; `sin(x)|` → `sin(x|)`; `x+1)|` (stray) → rule 5: `x+1|` |
| 5 | otherwise, `CUR > 0` | delete `LINE[CUR-1]` (never a hidden character: every hidden one sits at a slot start or construct end that an earlier rule takes) | |

Flat lines apply rules 1, 2e/2e′/2g (via a bracket scan around CUR; a call's commas are
visible, so DEL after one deletes it by rule 5, as on a 2D line), 4 for a matched `)` (an empty
call or group, prefill counting, is deleted with its name: `riemann(,x,,,)|` → `|`), and 5. Hidden
characters are never deleted one at a time; structure changes only through the rules
above, so the buffer stays well formed.

**Undecided cases now decided.**

| Before | DEL gives | Rule |
|---|---|---|
| `x^(|)` | `x|` | 2a (power span is `^(…)`) |
| `|x^(2)` (CUR 0) | unchanged | nothing before CUR |
| `x|^(2)` | `|^(2)` (empty base box shown) | 3 |
| `(|)/(b)` | `|()/(b)` | 2d (`CUR = os`) |
| `x^2|` (bare) | `x^|` (empty exponent box) | 3, then `x^|` DEL → `x|` by 2a |
| `log(|,8)` (u empty, b filled; drawn order b, u) | `log(|,8)` → ← to the end of b: `log(,8|)` | 2f (u is not first in drawn order) |
| `ans()|` inside `sqrt(ans()|)` | `sqrt(|)` | 1 |

### 4.4 ↑ / ↓ (`edvert`, L3) → bool

Candidates are the stops strictly inside the **innermost** Q, W or T span containing CUR
(`os < i < oe`). For ↑ they lie above (`Y[i] < Y[CUR] - 2`); for ↓, below
(`Y[i] > Y[CUR] + 2`). The best candidate minimises `(|ΔY| // 8, |ΔX|, i)`. If there is none,
the next outer construct is tried; if none is left, the function returns False. It does no
layout and reads `EDMAP` only. Flat lines (and a stale map) return False.

**Powers.** A power's span `[os, oe)` starts at `^` and holds only the exponent, so the
candidate rule alone finds nothing below an exponent. Two explicit rules close the gap:
- ↓ with CUR inside an exponent (`os < CUR < oe` of a W, and no Q/T inside the exponent
  gives a candidate first) → `CUR = os`, the stop just after the base.
- ↑ with `CUR == os` of a W (just after the base) → the exponent's start stop.

So ↓ then ↑ returns to the exponent, as §12.5 requires.

| From | ↓ | ↑ |
|---|---|---|
| `(a|)/(b)` | `(a)/(b|)` | False → history |
| `(1+(x|)/(2))/(3)` | `(1+(x)/(2|))/(3)` | – |
| `x^(2|)` | `x|^(2)` (power rule) | False → history (`test_history_fraction_paste` relies on this) |
| `x|^(2)` | False | `x^(|2)` (power rule) |
| integrand of `integrate(f,x,a,b)` | lower bound a | upper bound b |
| Σ body start, `sum(|f,k,1,n)` | the lower-row stop nearest in X: the end of a, `sum(f,k,1|,n)` (the row `k=a` is centred under Σ, left of the body) | b |

---

## 5. Engine-free layout

### 5.1 Flat check: `D.mflat(s)`, L4

`mflat(s)` returns True iff the line has no 2D construct. It returns False if `s` contains
any of the following, and True otherwise:
- `^`;
- the substring `)/(`;
- the name `pi`, `theta` or `oo` (a simple substring test is enough: a false hit only costs
  the 2D path);
- `ans()`;
- a TPL name directly followed by `(`, after `D.mcall` cut off letters before it
  (`xsqrt(4)` is not flat; `sqrt2(` is).

It is O(n) and allocation-free (`find` and `in`). A flat line is drawn as today's row
(`LINE[XOFF:XOFF+30]` at (10, top), character caret) and has `EDMAP = None`.

### 5.2 Pipeline: `D.mlayout(s, mode)`, L3

`mode` 1 is a history input: cached in ICACHE, no caret map, `*` drawn as the dot glyph,
every `/` stacked. `mode` 2 is the editor: never cached, entry stacking rule, returns the
map.

1. **`D.mlex(s)`, L4.** Returns a flat list of `(kind, start, end)`. Kinds:
   - `n` number: `[0-9.]` run, plus `E` and an optional sign and digits after a digit.
   - `a` name: a letter, then letters/digits.
   - `f` name directly followed by `(` that the engine reads as a call (`D.mcall`, §1.2):
     `x(` is `a`, and `xsqrt(` is `a` `x` then `f` `sqrt`.
   - `A` `ans()`.
   - `o` operator: longest of `=> := <= >= != + - * / ^ = < >`.
   - `(` `)` for `([{` and `)]}`.
   - `,`.
   - `!` postfix `!` and `'`.
   - `?` any other character (drawn as text; it clings to the adjacent operand, §0.4).
2. **`D.mparse(s, tk, mode)`, L4.** A shunting-yard over `PREC` with explicit operand and
   operator stacks. It never raises:
   - a missing operand becomes an `E` node at that index;
   - juxtaposition pushes an implicit `*`;
   - a stray closer, a postfix `!`/`'` and any `?` character become a text leaf that
     clings to the adjacent operand (an `R` row);
   - an unclosed group ends at `len(s)`;
   - a top-level comma list is an unbracketed group;
   - a `^`, or a stacked `/`, whose right operand holds a name the engine may cut (leaf
     flag 4) or an unknown multi-letter call outside brackets stays an inline row item
     (§1.2).

   It returns `None` past the caps: more than 24 open groups or more than 192 nodes
   (every appended node counts). Otherwise it returns `(nodes, root)`, the root being the
   line's slot. Nodes are lists `[kind, s, e, kids, aux]`; children are not always at lower
   indices (a row grows in place). Kinds:

   | Kind | Node |
   |---|---|
   | `L` | leaf |
   | `E` | empty |
   | `R` | row |
   | `N` | prefix minus/plus |
   | `S` | slot |
   | `Q` | stacked fraction |
   | `W` | power |
   | `G` | group |
   | `C` | call |
   | `T` | template |

   Construction rules:
   - `D.mpush` and `D.mshut` (L5) reduce through `D.mreduce` (L6), which builds rows,
     fractions and powers inline. (`mshut`, not `mclose`: `parse.mclose` already exists and
     is placed in CASIN; a second `mclose` would only confuse framelint reports and greps.)
   - A row extends the left row's kid list **in place**, so memory is O(n). The text
     prototype's first version was O(n²), with a 327 KB peak at 255 characters.
   - In mode 2, a `/` whose two operands are not both exactly one group becomes an inline
     row item. In mode 1, every `/` is a `Q`.
   - Contiguous text leaves merge while a row is built (glyphs never; in mode 1 neither do
     operators, which may be glyphs there).
3. **`D.mbox(s, nodes, root, mode)`, L4.** Walks the nodes reachable from the root
   children-first with an explicit stack (no recursion) and builds their boxes with:
   - the existing `D.row(…, gap=0)`, `D.frame`, `D.large` and `D.leaf` (glyphs, history
     mode);
   - the new `D.tleaf(boxes, i0, i1, txt, ti)` (L5, always text: `( ) , * <=` …; a buffer
     slice, or `txt` when `i0 < 0`);
   - inline geometry for `logb`.

   An `E` box is 10×15 with item `('b', 1, -11, 8, 13, pos, flags)` (flags: 1 trailing
   operand, 2 log base). Mode 1 E boxes have no item.
4. **`D.mplace(s, nodes, boxes, root, mode)`, L4.** An iterative walk with a child cursor.
   - It emits the display list in today's item format plus `'b'`.
   - It merges consecutive text items with the same top and contiguous x into one
     `('t', x, top, s[i0:i1])` slice. Each slice is materialised once.
   - In mode 2 it fills the map through `D.mmark` (L5).

**Result** (mode 2):
`(line, dl, w, asc, desc, X, Y, RK, ORD, SL, SLOTS, CONS, EMPTY)`.
- `X`, `Y` are lists of length `len+1` (x and text top; `X = -1` for a non-stop).
- `CONS` holds `(cs, os, oe, kind)` per construct: `cs` is the full start (the base start
  for W, the numerator start for Q, `os` otherwise).
- `EMPTY` holds `E` positions in drawn order, flagged for the trailing-operand-at-caret and
  log-base cases.

**Result** (mode 1): `(dl, w, asc, desc)`, or `None` past the caps of §5.3 (the caller then
draws the 1D text). Mode 1 emits no `'b'` items (an `E` in a history input, e.g. from a
Classic line `*2` that the engine refused, is drawn as a blank 10 px cell).

Nodes and boxes are dropped after the call. Only `EDMAP` and `EDL` are kept.

### 5.3 Caps and degrade to 1D

The line is drawn and edited as a flat line (structure parens visible, linear stops) when
any of these holds:
- `CLASSIC`;
- `LINE == EFAIL`;
- `len(LINE) > 160`;
- `mparse` returns None;
- the laid-out height exceeds 76;
- `D.mlayout` raises `MemoryError`. `emodel()` catches it, sets `EDMAP = None`, calls
  `gc.collect()` and sets `ED1D`; `EMODEL` is still set to `(LINE, CLASSIC)`, so only the
  next text change retries.

History inputs use the same caps (mode 1). `redraw` catches `MemoryError` around each
history `D.mlayout(e[0], 1)` and draws that input 1D (`e[0][:31]`); a persistent failure
there costs one exception per full redraw, never a loop through `panic`.

Width beyond 300 px scrolls (§6.3).

Memory (text prototype, tracemalloc on CPython; MicroPython about one third):

| Input | Peak |
|---|---|
| 10 characters | 8.5 KB |
| 33-character definite integral | 10 KB |
| 95 characters, 8 fractions | 46 KB |
| at the cap (177 characters, 181 nodes) | 76 KB |

Retained `EDMAP` + `EDL`: about 0.6 KB at 30 characters, at most about 4 KB. Both are freed
before every job and in `panic`.

### 5.4 Render: `D.mrender(dl, dx, dy, clip, x0, x1, c, boxes, cur=-1)`, L4

Draws, in color `c`, the items whose x-range meets `[x0, x1]` (item left edge ≤ `x1` and
right edge ≥ `x0`; `x1 = 319` for "everything right of `x0`"). One call draws one kind:
- `boxes=True`: only `'b'` items, as `D.rect` fills (the caller passes LINE). A box that
  is the trailing missing operand at the caret (`2+|`; flag 1 and `pos == cur`) is skipped,
  so typing linear text never flashes a box. The color is set only if an item is drawn.
- `boxes=False`: every other item: text through `D.text` with `clip`, lines and glyph
  strokes through `D.clipped_line` (the caller passes INK for the entry, SUB for history
  inputs).

Splitting by kind is what keeps a full redraw at ≤ 6 `set_color`: all box passes run in the
LINE batch and all ink passes in the SUB/INK batches (§6.4). It returns nothing. The caret
is drawn by `epaint`.

---

## 6. Screen geometry and redraw

### 6.1 Rows (320 × 210). `EY = 190 - EH`

| Rows | Contents | At EH = 20 (today) |
|---|---|---|
| 0..18 | Status: `RAD`/`DEG` at (5, 2) INK; STATUS at x 45, INK, `room()` columns; chip right-aligned at `315-10*len` in ACC. Rule at y 19 (LINE). | same |
| 20..EY−21 | History stage (§7). Entries stack upward from `SB = EY - 20`. | 20..149, SB 150 (today's list origin) |
| EY−19..EY−2 | Hint/footer row: fill `rect(0, EY-19, 320, 18)`, text at (5, EY−17) in SUB; the footer's right part at `315-10*len`. | 151..168, text 153 |
| EY−1 | Rule (LINE). | 169 |
| EY..189 | Entry box: fill `rect(0, EY, 320, EH)`; view x 10..309; markers `<` at (0, by−11) and `>` at (310, by−11) in INK, where `by = ytop + asc` is the content baseline (so a one-row line puts them at text top 172, as today). `<` shows when `XOFF`/`EXOFF` > 0; `>` when content remains right of the view. | 170..189 |
| 190..209 | F-key tabs, unchanged: ACCSOFT `rect(64i, 191, 63, 19)`, labels in ACC at 193. | same |

**Entry height.** For content height h:
- class = 20 if h ≤ 19, 40 if ≤ 36, 60 if ≤ 56, else 80;
- `EH = max(EH, class)` while LINE is non-empty;
- `EH = 20` when LINE is empty.

So there are at most 3 stage repaints per input, and none for linear input. Content top:
`ytop = EY + (EH - h)//2`, which is 172 for one text row, as today.

**Caret.** `D.line(cx-1, ytop+Y-1, cx-1, ytop+Y+15, INK)` with `cx = 10 + X[CUR] - EXOFF`.
For a one-row line this is today's `x = 9+10k`, rows 171..187. Flat lines use today's
formula exactly. `CARETC = 'INK'` is a single constant.

### 6.2 Height classes (text prototype)

| Content | h | EH |
|---|---|---|
| text, √, \|x\|, calls | 15–19 | 20 |
| x², a/b, ⁿ√, log_b | ≤ 36 | 40 |
| ∫ab, Σ, nested fraction, fraction in an exponent | ≤ 56 | 60 |
| Σ of a fraction, deeper nesting | ≤ 76 | 80 |
| taller | – | 1D (§5.3) |

### 6.3 Horizontal scroll

- **Flat/1D:** today's rule (`XOFF` in characters, `CUR - XOFF ≤ 29`).
- **2D:** with caret pixel `c = 9 + X[CUR] - EXOFF`:
  - if `c > 304`: `EXOFF = min(w - 290, X[CUR] + 9 - 304 + 60)`;
  - if `c < 10`: `EXOFF = max(0, X[CUR] - 60)`;
  - then always `EXOFF = min(EXOFF, max(0, w - 290))`, so deleting text never leaves the
    content scrolled off a now-short line.

  Each 60 px step repaints the entry once. Otherwise the diff paint applies.

### 6.4 Redraw (`redraw`, L2)

1. **Entry model.** Already fresh: `emodel()` (§6.5) ran just before. `redraw` never calls
   `D.mlayout` for the entry. Defensively, `redraw` paints the entry flat whenever
   `EDMAP is None or EDMAP[0] != LINE` (for example a test calling `u.redraw()` right after
   `panic`), so it can never index a stale map.
2. **Full or partial.** `full = FULL or VIEW != (theme, MODE, SEL, VIEWEND, DX, len(hist), EH, span)`,
   `span` the focused answer's overflow at the last full redraw; `DX` is first clamped to it,
   so ←/→ on an answer that fits is a no-op key (§0.6).
   `HERO` is deliberately not in `VIEW`: it only changes the hint row, which `HINTVIEW`
   covers. (With `HERO` in `VIEW`, the first key after every answer, and every key that
   empties or un-empties LINE, would cost a full 6-color redraw, contradicting the
   `test_first_key_after_answer_keeps_stage` and `typing.colors` pins of §10.) In a full
   redraw the focused answer's `DX` is clamped to `max(0, w - 300)`, as today's hero did.
3. **Full.** Paint everything in color batches:
   1. BG: screen.
   2. ACCSOFT: tabs and the selection band.
   3. LINE: rules and boxes.
   4. SUB: history inputs, messages, hint/footer.
   5. INK: status text, results, entry, caret, markers.
   6. ACC: chip and F-key labels.

   That is ≤ 6 `set_color`.
4. **Partial.** Each region repaints only if it changed:
   - status row when `STATVIEW != (STATUS[:room()], MOD, deg)`;
   - hint row when `HINTVIEW` changed;
   - entry when `LINE`, `CUR` or the geometry differ from `EKEY` (§0.6).

   All BG fills come first, then LINE (boxes), SUB (hint), INK, and ACC (chip, only when
   the status row repaints).
5. **Entry paint (`epaint(full)`, L3).** Three paths, first match:
   - **Full entry repaint** — a full redraw, a flat line, or `EFLAT`/`XOFF`/`EXOFF`/`EH`/
     `theme`, content top or ascent changed: `rect(0, EY, 320, EH)`, then the row, or
     `mrender(…, x0=10, x1=319, LINE, True)` and `mrender(…, INK, False)`, markers, caret.
   - **Caret only** — LINE (hence the display list) unchanged, only `CUR` moved (←/→,
     home/end, ↑/↓, `)`/`,` step-overs): erase the old caret with
     `rect(ocx-1, oy-1, 2, 17)` in BG (`ocx`, `oy` its old column and top), redraw the items
     that meet columns `ocx-1..ocx` (`mrender(…, x0=ocx-1, x1=ocx, …)`: boxes in LINE, then
     the rest in INK; a text run is redrawn whole at the same place), then the new caret.
     Typically 2 colors, 1 fill, 0–2 texts, 1–3 lines, independent of the line length.
     It does not rely on any font property: whatever ink the strip held is redrawn.
   - **2D diff** — the text changed: compare the new absolute display list with `EDL`
     pairwise in list order. `x0` is the minimum of: the left edges of all unequal pairs and
     of the unmatched tail, the old caret column, and the new caret column. Then:
     - `rect(x0, EY, 320 - x0, EH)`;
     - `mrender` every item whose right edge ≥ `x0` (boxes, then ink). An unchanged text
       run that straddles `x0` is redrawn whole at the same place; the shim records a
       replace, not an OVERDRAW. (A throwaway shim check during design confirmed this; it
       is not in the repository. §12.7's pixel-equivalence test is the acceptance check.
       The shim's font never inks columns 0 and 9 of a cell, but the device font is not
       measured, so no path depends on that.)
     - markers, caret;
   - Every path stores `EDL` and `EKEY`.

     The kill switch `EDIFF = True` exists: when False, the full entry repaint is always
     used (for both the caret-only and the diff path).
6. **Nothing changed** (2nd pressed twice, a key with no entry, a redraw with no edit): no
   ti_draw call.

`status(s)` (CASUI, used by `engine` and `busy` to draw at once) also sets
`STATVIEW = None`, so the next partial redraw repaints the status row it overwrote.

### 6.5 `emodel()` (L2, CASUX)

Called by `key` (before dispatch when stale, and before every `redraw`), `show` and `boot`.
It does no drawing.
1. If `EMODEL != (LINE, CLASSIC)`: set `EMODEL`; `EFLAT = CLASSIC or LINE == EFAIL or
   len(LINE) > 160 or D.mflat(LINE)`; for a 2D line, `EDMAP = D.mlayout(LINE, 2)` inside
   `try/except MemoryError` (§5.3); `None` or over-height → `EFLAT = True`, `EDMAP = None`.
2. Resolve `PENDING` (2D: first `E` of `EMPTY` inside `[a, b)`, the log base included;
   flat: drop it) and clear it.
3. Snap `CUR` to a stop (2D: next stop in buffer order; a flat MathPrint line: `D.mstop`;
   Classic: no snap, every index is a stop, so ← moves into a call name as before, §8).
4. Update `EH` (§6.1), then `XOFF` (flat) or `EXOFF` (2D) (§6.3).

Its deepest chain is `key 1 → emodel 2 → D.mlayout 3 → D.mparse 4 → D.mshut 5 →
D.mreduce 6`, the same depth as the old `redraw` chain.

---

## 7. History page

### 7.1 Entry layout (full redraw only)

The **focused** entry is `SEL` in MODE, else the newest. At most `PAGEMAX = 5` entries are
shown, stacked upward from `SB` while `top ≥ 21`. The focused entry is always shown, even
when it is taller than the stage: its result view height is then cut to what fits
(`min(92, SB - 21 - input height - 2)`, at least 15) and it is clipped to rows 20..SB.

**One layout per answer.** Every answer is laid out with the same key,
`D.layout(e[1], 300, 92)`, whatever view height it is shown in. The view height (92 for
the focused entry if the stage allows, else 60) is applied only at paint time, by calling
`D.render(box['dl'], dx, clip, dy)` (L4, from `redraw` L2) with a clip built in `redraw`,
instead of `D.paint` (which reads the cached `vh`). If the cap were part of the cache key,
the focused entry would need a sixth key next to the five `(…, 60)` keys, and the
5-entry FIFO answer CACHE (pop the oldest, no refresh on a hit) would then miss on
**every** lookup of every MODE ↑/↓ redraw. With one key per answer, a page of ≤ 5 answers
fits the cache (the `test_layout` pin) as long as their total cost stays under 4 KB, as
today.

| Part | Rule |
|---|---|
| Input | `D.mlayout(e[0], 1)`. If it returns None, raises (`MemoryError`, or any `Exception`: a layout bug; §0.6), or `w > 300` or `h > 60` (`LISTH`; §0.6), use 1D `e[0][:31]` (h 15). Drawn at x 5 through `mrender(…, SUB, False)` in the SUB batch. |
| Result, `R_ANS` | `D.layout(e[1], 300, 92)` (see above). Rendered right-aligned (`scrollx = min(0, w-300)`) into the view `(10, y, 300, cap)`; the focused entry uses `DX` (clamped to `w - 300`) when `w > 300`, with `<`/`>` at its row centre. |
| Result, `R_MSG` | SUB text, right-aligned at `310-10*len`; the focused one wraps into ≤ 3 lines of 30. |
| One row | If `in.w + res.w + 20 ≤ 300` and the result is ≤ 60 high (§0.6): baselines aligned, result right edge at 309. |
| Two rows | Otherwise the input, then the result right-aligned 2 px below. |
| Spacing | 3 px between entries. |
| Selection | In MODE, an ACCSOFT `rect(0, top-1, 320, h+2)` behind the selected entry, drawn in the ACCSOFT batch. |
| Welcome | No history: today's three texts, each drawn only if its row ends above `EY-21`. |

### 7.2 Scrolling

In MODE, `VIEWEND` is the bottom entry. `SEL > VIEWEND` sets `VIEWEND = SEL`. When SEL is
above the first entry shown, `VIEWEND` is recomputed: starting from SEL, add newer entries
while the page fits (≤ PAGEMAX steps, heights from the caches). Outside MODE the newest
entry is at the bottom.

### 7.3 Caches

- `draw.CACHE` (answers) is unchanged: 5 entries, 4 KB.
- `draw.ICACHE` holds history-input layouts `(text, result, cost)`: ≤ 5 entries,
  ≤ 3072 B, oldest dropped first, `cost = 24*len(dl) + len(text)`.
- The editor never uses either cache.
- `clear_cache()` (CASUI) empties both. It runs before every job and in `panic`.

### 7.4 Footer, recall, paste, ENTRY

**Hint row contents.**

| State | Shows |
|---|---|
| MODE | the selected entry's footer |
| LINE empty and `HERO` | the newest entry's footer |
| LINE non-empty | `HINT[ALIAS[enclosing()]]` (≤ 31 columns), or nothing |

The footer is today's text, unchanged:
- left: `('+ C  ' if F_PLUSC) + ('~ ' + approx if exact)`, cut to `29 - len(right)`;
- right: `label + '  F4'`.

An `R_MSG` entry has no footer (empty hint row), as today's hero showed none.
`test_decimal_form_hides_approximation_until_exact_returns` therefore holds.

**Recall and paste.**

| Action | Result |
|---|---|
| ENTER in MODE | `paste(wrapped(e[1]))`. If CUR is in an empty hidden fraction or exponent slot, the text is pasted bare. Result pastes are not `structure`d. |
| 2nd ENTER in MODE | paste `structure(e[0])` |
| F2 recall | inserts `ans()`, `(result)` or a name, unchanged |
| ENTRY | §2 |
| CLEAR | leaves MODE |

**`enclosing()`** scans back from CUR with a depth counter, as today. It skips unmatched
`(` whose name is empty (groups and hidden fraction/exponent parens) and continues outward.
So inside `integrate((x)/(|),x)` it returns `integrate`. The hint and F5 help follow.
The name is the letter/digit run before `(` with **leading digits dropped** (`2sin(x|)`
gives `sin`, not today's `2sin`); a run of digits only (`2(x|)`) counts as unnamed and is
skipped like a group. In Classic, `enclosing` behaves the same (the change is harmless
there and keeps one function).

---

## 8. MathPrint / Classic

F3 Setup gains **row index 5**, `Entry: MathPrint` / `Entry: Classic`. It is appended after
About, so indices 0–4 are unchanged.

`menu.open` setup branch: `selected < 2` toggles as today; `2, 3` confirm; `4` About;
`5` sets `U.CLASSIC = not U.CLASSIC` on ENTER, digit 6 and ←/→ (like rows 0–1; today's
code sends every `selected ≥ 4` to About, so the branch must test `== 4` explicitly). The
row label is `'Entry: ' + ('Classic' if U.CLASSIC else 'MathPrint')`, note
`'ENTER or arrows toggle'`. Six rows fit `menu.PAGE = 6`. `CLASSIC` is a CASUI ui global, not
an `R.SET` entry, so the editor can read it before the engine loads and `run` is unchanged;
it lasts for the session, like the other settings.

The toggle needs no extra code in `key`: the next `emodel()` sees `EMODEL != (LINE,
CLASSIC)` and rebuilds the model, and `key` already sets `FULL = True` after a menu.

Classic is **today's editor exactly**:
- today's `PLAIN`/`SECOND` tables, used directly (they are not changed for MathPrint);
- `insert()`, today's DEL, ±1 arrows, 1D row;
- no autoclose, no `tidy`, no `structure`, no map, no picker (2nd 42 does nothing);
- no caret snap (§6.5) and no `x`/`k` prefill in menu templates (`menub.insertion` gives
  `diff(,)` as before);
- ENTER skips stage 1 (§2.2).

History inputs stay 2D. Classic also serves as:
- the user's escape hatch;
- the device-timing fallback;
- the reference for old expectations.

---

## 9. Placement, levels, packs, budgets

### 9.1 Functions (framelint: callee level > caller level; maximum 6)

| Function | Module | #@L | Pack | Calls (level) |
|---|---|---|---|---|
| `key(k)` (changed) | ui | 1 | CASUX | engine 2, emodel 2, edkey 2, picker 2, redraw 2, menu.open 2; tidy/structure/paste/insert/empty_map/empty_slot/enclosing/wrapped/edins 3; leave 4 |
| `show(job, rec)` (resets EH, XOFF, EXOFF, EDMAP, EDL, EKEY, EMODEL, PENDING, VIEWEND) | ui | 1 | CASUX | emodel 2, redraw 2 |
| `boot` | ui | 1 | CASUX | emodel 2, redraw 2 |
| `panic(reason)` (also resets the entry globals, sets `EFAIL = LINE` for reasons 0/3, still draws plain `LINE` at (10, 172)) | ui | 1 | **CASUI** | D primitives only |
| `emodel()` (§6.5) | ui | 2 | CASUX | D.mlayout 3; D.mflat, D.mstop 4; gc.collect (native) |
| `edkey(k, mod)` (MathPrint editing keys) | ui | 2 | CASUX | edins, eddel, edmove, edvert, insert 3; leave, put 4 |
| `picker()` | ui | 2 | CASUX | D.rect/text/line 5, D.color 6, TS.wait_key (native) |
| `redraw()` (rewritten, §6.4; history plan inline) | ui | 2 | CASUX | D.mlayout, D.layout, D.theme, epaint, enclosing 3; D.render, D.mrender, room 4; D.text/rect/line 5; D.color 6 |
| `engine`, `busy` | ui | 2 | as today | unchanged |
| `edins(op, t='')`: `frac`, `pow`, `sq`, `open`, `close`, `comma`, `text` | ui | 3 | CASUX | edslot, edterm, leave, put 4; bmatch 5 |
| `eddel()` → True: move left instead | ui | 3 | CASUX | put, keep, blank, spans 4; bmatch, D.mcall 5 |
| `edmove(d, mod)`, `edvert(d)` → bool | ui | 3 | CASUX | D.mstop 4 |
| `paste(text, bare)` (`bare`: the unwrapped result, or None) | ui | 3 | CASUX | edslot, put 4 |
| `tidy(s)`, `structure(s)` | ui | 3 | CASUX | D.mlex, D.mparse 4 |
| `empty_map()` | ui | 3 | CASUX | – |
| `empty_slot()` (log-base skip, §2.2) | ui | 3 | CASUX | – |
| `enclosing()` (skips unnamed groups, drops leading digits) | ui | 3 | CASUX | – |
| `insert`, `wrapped` (unchanged) | ui | 3 | CASUX | – |
| `epaint(full)` | ui | 3 | CASUX | D.mrender 4; D.rect/text/line 5 |
| `status(s)` (also `STATVIEW = None`) | ui | 3 | CASUI | D.rect/text 5 |
| `wrapend(s, c, base)` → (s, c) (the 51/61/`!`/`'` wrap, §2) | ui | 4 | CASUX | – |
| `edslot(i)` → SLOTS row; `edterm(i)`; `leave(grp)`; `put(line, cur)` → bool; `spans(o, cl)`; `keep(os, oe, u)`; `blank(a, e, k, os)` | ui | 4 | CASUX | bmatch, D.mcall 5 |
| `bmatch(s, i, d)` (the matching bracket) | ui | 5 | CASUX | – |
| `mlayout(s, mode)` | draw | 3 | CASUX | mlex, mparse, mbox, mplace 4 |
| `clear_cache()` (also ICACHE) | draw | 3 | CASUI | – |
| `mflat(s)`, `mstop(s, i)`, `mlex(s)` | draw | 4 | CASUX | mcall 5 |
| `mcall(s, i, j)` (§1.2) | draw | 5 | CASUX | – |
| `mparse(s, tk, mode)` | draw | 4 | CASUX | mpush, mshut 5; mreduce 6 |
| `mbox(s, nodes, root, mode)` | draw | 4 | CASUX | row, frame, large, tleaf 5; leaf 6 |
| `mplace(s, nodes, boxes, root, mode)` | draw | 4 | CASUX | mmark 5 |
| `mrender(dl, dx, dy, clip, x0, x1, c, boxes, cur=-1)` | draw | 4 | CASUX | rect, text 5; clipped_line, color 6 |
| `mpush`, `mshut`, `mmark`, `tleaf` | draw | 5 | CASUX | mreduce 6 (mpush, mshut) |
| `mreduce(nodes, vals, op, mode)` | draw | 6 | CASUX | – |
| `menu.open` (setup row 5) | menu | 2 | CASMNU | unchanged calls |
| `menub.insertion` (prefill at position ≥ 1) | menub | 3 | CASMNU | – |

Checked against framelint: every edge above has callee level > caller level, and no
function is above 6. Edges that are easy to get wrong: `picker` is called by `key`, not by
`edkey` (both L2, so `edkey → picker` would be illegal), and `key` (L1 → `edins` L3)
applies the chosen row so that `picker` stays free of editor state; `emodel` and `redraw`
are both L2, so `redraw` must never call `emodel` (callers run it first); and `edkey` (L2)
must not call `emodel` either: `key` refreshes a stale model at dispatch step 2.

**Deepest chains** (7 frames including the casevo body; strict budget 8):
- `casevo 0 → key 1 → emodel 2 → D.mlayout 3 → D.mparse 4 → D.mshut 5 → D.mreduce 6`
- `casevo 0 → key 1 → redraw 2 → D.mlayout 3 → D.mparse 4 → D.mshut 5 → D.mreduce 6`
  (history inputs, mode 1)
- `key 1 → redraw 2 → epaint 3 → D.mrender 4 → D.text 5 → D.color 6`

**Tables and constants placed in CASUX** (each is bound once to a literal and never
assigned in a function, which `packs.Plan.constant` requires of a placed name).
- `ui`: `PLAIN`, `SECOND`, `ALPHA`, `HINT`, `ALIAS` (unchanged, as today), plus the new
  `TMPL` (picker rows, a tuple of tuples) and `PREFILL` (the prefilled second parameter per
  name, for DEL's empty test).
- `draw`: the new `TPL` (dict literal), `TGAP` (int), `MPREC` (dict) and `MFNT` (tuple). No
  CASUI function reads them;
  a CASUI function that read a CASUX name would be rejected by the packer ("reads … by
  name, which may be evicted").

**New globals (CASUI, about 0.3 KB).** Mutable or test-tunable, so they must live in the
`ui`-kind pack; a view pack may not hold a global that a function assigns
(`packs.py`: "lives in soft pack … but assigns globals").
- `ui`: `EXOFF`, `EH`, `EDMAP`, `EDL`, `EKEY`, `EMODEL`, `EFLAT`, `PENDING`, `ED1D`,
  `EFAIL`, `CLASSIC`, `VIEWEND`, `STATVIEW`, `HINTVIEW`, `CARETC`, `EDIFF`, `PAGEMAX`.
- `draw`: `ICACHE`, `ICACHE_BYTES`.

CASUX code assigns these only as ui/draw globals (`CASUI.X` after packing), as `key()`
already does.

### 9.2 `build/manifest.py`

**PACKS.** The CASUX tuple gains, by name:
- `'ui.emodel'`, `'ui.edkey'`, `'ui.picker'`, `'ui.edins'`, `'ui.eddel'`, `'ui.edmove'`,
  `'ui.edvert'`, `'ui.paste'`, `'ui.tidy'`, `'ui.structure'`, `'ui.empty_map'`,
  `'ui.epaint'`, `'ui.edslot'`, `'ui.edterm'`, `'ui.leave'`, `'ui.put'`, `'ui.wrapend'`
  (review, §0.8), and (milestone B)
  `'ui.bmatch'`, `'ui.spans'`, `'ui.keep'`, `'ui.blank'`, `'ui.PREFILL'`;
- `'ui.TMPL'`, `'draw.TPL'`, `'draw.TGAP'`, `'draw.MPREC'` (milestone A placed the draw
  names, `ui.tidy` and `ui.structure`);
- `'draw.MFNT'`, `'draw.mlayout'`, `'draw.mflat'`, `'draw.mcall'`, `'draw.mstop'`,
  `'draw.mlex'`, `'draw.mparse'`,
  `'draw.mpush'`, `'draw.mshut'`, `'draw.mreduce'`, `'draw.mbox'`, `'draw.tleaf'`,
  `'draw.mplace'`, `'draw.mmark'`, `'draw.mrender'`.

`status`, `panic` and `clear_cache` stay in CASUI (they are not listed anywhere, so their
home pack keeps them).

No other pack changes. There is no new module, so `lint.ALIASES`, `RESIDENT`, `UI_SIDE`
and the allowed imports are unchanged.

**MODULES.** These are estimates; set the final values to about 10 % over the
`build/release.py` measurement.

| Module | Today (lines / KB) | Estimated after | New budget |
|---|---|---|---|
| CVDRAW | 342/350, 10.5/13 KB | measured after milestone A: 973 lines, 24.4 KB; final (milestone D): 977 lines, 25.2 KB | `('draw', 'CVDRAW', 'R', 1075, 28)` (milestone D, ~10 % over the final measurement) |
| CVUI | 414/500, 14.1/16 KB | after milestone A: 498 lines, 15.9 KB; after milestone B: 1093 lines, 29.9 KB; after milestone C: 1284 lines, 34.0 KB; final (milestone D): 1287 lines, 34.1 KB | `('ui', 'CVUI', 'R', 1400, 37)` (milestone C; ~9 % over the final measurement) |
| CVMENU | 153/200 | +4 (setup row) | fits |
| CVMENUB | 42/150 | +6 (prefill) | fits |

**Pack bytecode.** The spec estimated 12.5 B per minified line; the final `build/release.py`
measurement (`dist/release.json`, `mpy_estimate` and `room`, milestone D) is well above it,
because the editor came out at about twice the estimated size (§0.7).

| Pack | Before MathPrint | Spec estimate | Measured (milestone D) |
|---|---|---|---|
| CASUX | 11,156 B | ~21 KB | **30,929 B** (PACKMAX 60,000: 29,071 B spare) |
| `room('layout')` reload (`ROOMCOST` 1.4 × bytecode + 512) | 16,130 B | ~30 KB | **43,812 B** |
| CASUI | 3,540 B | ~3.8 KB | **3,903 B** |

The engine is untouched, and CASUX is shed during family commands as today, so compute
speed and compute heap are unchanged. The cost is a heavier CASUX reload after heavy
commands. The gate is native `ui_calculus` at 189,776 (§12.9).

### 9.3 Heap

| Item | Size |
|---|---|
| Boot (CASUI + CASUX) | ~+10 KB estimated; measured +20.1 KB of bytecode (CASUX +19,773 B, CASUI +363 B), so about +28 KB of heap at `ROOMCOST` 1.4 (§9.2, §0.7). Boot still imports only CASUI and CASUX (`tests/test_release.py::test_boot_loads_only_the_ui`) |
| Typing transient, per 2D key | ~3–5 KB (CPython), ≤ ~25 KB at the cap; freed by the next GC |
| Flat key | ~0 |
| Retained while idle: `EDMAP`/`EDL` | ≤ 4 KB |
| Retained while idle: ICACHE | ≤ 3 KB |

All retained state is cleared before every job.

### 9.4 Code rules

- `tests/support/lint.py` subset: no comprehensions, generator expressions, lambdas,
  `with`, `key=`, recursion, nested functions or f-strings.
- Character classes use only `isalpha`/`isdigit`; `isalnum` is banned.
- `sort()` only on lists of tuples or ints.
- `bytearray` is allowed.
- Every loop is bounded by `len(s)`, the node cap or `PAGEMAX`.
- No stepped slices (`s[::-1]`; the lint rejects any non-unit step), no `reversed()`, no
  starred arguments or targets, no `format`; walk backwards with `range(n - 1, -1, -1)`.
- No iteration over a dict or set without sorting it or a `#@unordered-ok` marker (lint):
  `TPL` is only ever indexed (`name in TPL`, `TPL[name]`), never looped over.
- `try/except MemoryError` is allowed (today's `ui.engine` uses `except BaseException`);
  nothing in the editor catches a bare `Exception`, so bugs still reach `panic`.

---

## 10. Per-key cost budget

Counts are ti_draw calls per key when the status and hint rows are unchanged.

| Key class | set_color | fill_rect | draw_text | draw_line | Layout work |
|---|---|---|---|---|---|
| Today, any edit key | 4 | 3 | 2 | 1 | – |
| Typing on a flat line | **≤ 2** | 1 | 1 (+1 per scroll marker `<`/`>`) | 1 | `mflat` scan only |
| Typing on a 2D line, at the end | ≤ 2 (+1 if a box is right of `x0`) | 1 | runs right of `x0` (typically 1–2) | strokes right of `x0` + 1 | one `mlayout` (host 40–90 µs, text prototype; EVO ~3–7 ms est.) |
| Template insert (42, 51, picker) | ≤ 3 | 1 | ≤ 3 | ≤ 8 | one `mlayout` |
| ← → home end ↑ ↓ inside a 2D line (caret-only path, §6.4) | ≤ 2 (+1 if a box meets the old caret strip) | 1 (a 2 px strip) | text runs meeting the old caret strip (0–2) | strokes meeting the strip + 1 caret (typically 1–3) | **none** |
| ← → home end on a flat line | ≤ 2 | 1 | 1 (+1 per scroll marker) | 1 | **none** |
| 2nd / alpha | ≤ 3 | 1 (status) | ≤ 3 | 0 | none |
| No-op key | 0 | 0 | 0 | 0 | none |
| Hint row change | +1 SUB | +1 | ≤ +1 | | |
| Status change | +1 ACC if the chip shows | +1 | ≤ +2 | | |
| EH step, ENTER, menu return, history move | full redraw: ≤ 6 colors | ≤ 6 + bands | | | layouts from the caches |

**Device timing gate.** Host time ×75 is an estimate. `tests/test_mathprint_layout.py` pins a host
guard: one `mlayout` of a dense 160-character line < 400 µs. The EVO run times keys (§12.9).

**New pins in `tests/test_fastboot.py`**

| Test | Pin |
|---|---|
| `test_full_redraw_uses_few_colors` | Full ≤ 6 colors in both themes (kept). The second bare `u.redraw()` now makes **no** ti_draw call (`TD.CALLS == []`). Then `u.key(92)` gives fills `== [('fill_rect', -1, 169, 321, 21)]`, `set_color ≤ 2`, `draw_text == 1`, `draw_line == 1`. |
| `test_typing_costs_few_colors_per_key` | `typing.colors <= 2*30 + 6*2` (was `4*31 + 6*2`). The first assertion is kept. |
| New `test_first_key_after_answer_keeps_stage` | After `2/3{enter}`, key `1` makes no `fill_rect` with `y < 150` other than the status row. |
| New `test_modifier_repaints_status_only` | `u.key(21)`: fills `== [('fill_rect', -1, -1, 321, 20)]`, `set_color ≤ 3`. |
| New `test_arrows_do_no_layout` | On `1{frac}2{right}+x^3`, keys 24, 26, 25, 34 and 2nd 24 make 0 calls to `D.mlayout`/`D.mparse` (monkeypatched counters). |
| New `test_caret_move_cost_is_flat` | On `(1)/(2)+(1)/(3)+(1)/(4)+(1)/(5)`, each of 10 ← presses gives `fill_rect == 1` (the 2 px strip), `draw_text ≤ 2`, `set_color ≤ 3`, and no `D.mlayout` call; the frame buffer rows `EY..189` equal those of a forced full entry repaint. |
| New `test_2d_typing_cost` | After `1{frac}2{right}+1{frac}3{right}+`, each of `4`, `5`, `6` gives `set_color ≤ 3`, `fill_rect == 1`, `draw_text ≤ 3`. |
| `SCREENS` | Add `1{frac}2{enter}`, `{2nd,frac}{down}{down}{enter}x^2`, `{2nd,frac}{down}` ×8 `{enter}`, the template picker screen, `(1)/(2)+` repeated past the scroll, EH growth to 80 then CLEAR, and a history selection with 2D inputs. All existing invariants must hold: no OFFSCREEN, no OVERDRAW, ASCII ≤ 32 characters, fills ≥ 2×2. |

---

## 11. Compatibility

### 11.1 `tests/support/keyscript.py`

1. `KEYTEXT[42] = ('@frac', '@templates', 'b')`, so `/` is typed with 55.
2. `KEYTEXT[51] = ('^', '@surd', 'd')`, so text `surd(` is typed with alpha letters plus
   `(`. It is a plain call until its comma makes it a template, and `surd()` stays `surd()`.
3. `KEYTEXT[61]` is unchanged: `('^2', 'sqrt(', 'i')`.
4. `type_keys` handles `^` before the greedy table match (`e^(` and `10^(` are still
   matched as whole tokens):
   - `^2` not followed by a digit, `.` or `^` → 61.
   - Otherwise emit 51, then the operand: an optional `-`/`+`, then one of:
     - a `( … )` group through its match (the `(` is a no-op in the empty box, the `)`
       steps out, and no RIGHT is owed);
     - a number;
     - a name, or `name( … )`;
     - `pi`.

     A `^` right after the operand is typed inside, right-associatively.
   - Then emit one 26 per owed box, if more text follows in the run.
5. `decode` maps 51 to `^`. It keeps an `owed` count, incremented by a 51 whose next key is
   not 63. A 26 while `owed > 0` is dropped (and decrements it). `owed` is reset by 105 and
   by actions. 42 decodes as `{frac}` and 2nd 51 as `{surd}`. The round-trip test
   `decode(type_keys(s)) == s` stays exact.
6. New pins in `test_shims`:
   - `type_keys('x^3+1') == [32, 51, 94, 26, 85, 92]`
   - `type_keys('1/2') == [92, 55, 93]`
   - `type_keys('x^2') == [32, 61]` (kept)
   - `type_keys('e^(x)') == [21, 81, 32, 64]` (kept)

The docstring of `keyscript.py` and DESIGN 16.4 are updated.

**Native streams.** `micro_smoke` builds `ui_calculus` from `keyscript.parse`, so it is
regenerated automatically. Each `UI_CASES` input types back to the same text:
- `integrate(1/(2+cos(x)),x,0,2*pi)`: the `/` is inline, nothing is hidden.
- `arclen(x^(3/2),x,0,4)`: the `(` is a no-op and the `)` exits the box.
- `polararea(…)`, `paramarea(…)` and the nested integrate are plain text.

Only answers are asserted. The `ui` suite stream `(93,85,94,105,21,22)` is unaffected.
`check_release.py` scripts use `2+3`, `3*4` and `integrate(x^2,x,0,1)`; the last is now
typed as `x^(2)`, and `tidy` restores `x^2`.

### 11.2 Exact LINE/CUR assertions

| Test | Status |
|---|---|
| `test_ui.test_entry_and_repeat` (`'2+3'`) | holds (`structure` is the identity) |
| `test_atomic_ans_delete` | holds (DEL rule 1) |
| `test_empty_slot_never_evaluates` (`diff(,x)`) | **changes**: stage 1 finds the slot and the engine never loads, so `s.hist` is None; it asserts `not s.hist and 'run' not in s.mods` |
| `test_history_fraction_paste_is_parenthesized` (`'x^(2/3)'`) | holds: `x^(|)`, ↑ → history (§4.4), bare paste into the empty hidden slot |
| `test_evo_keys_forms_fraction_and_xroot` | holds: `(1)/(4)` → tidy `'1/4'`; `{2nd,x^n}8,3` → `surd(8,3)` = 2 |
| `test_help_example_paste` | holds: `diff(` types as `diff(|)` (autoclose), F5 finds `diff`, and the example `diff(x^3,x,2)` is inserted unchanged at CUR, giving `diff(diff(x^3,x,2))`, which contains it. Its bare `^3` follows the bare-power rule (§1.2). |
| `test_action_wrap_*` (256, `CUR == 255`) | hold: `put` checks the whole line; no empty slot, so PENDING keeps the offset |
| `test_empty_builtin_or_alias_keeps_editor_and_moves_caret` | holds for all 7: `sqrt()`, `abs()`, `exp()` → stage 1 (`CUR = len(name)+1`); `sin()`, `log()`, `surd()`, `d()` → stage 2 |
| `test_clear_history_while_selected` | holds (setup row appended last; `VIEWEND` is clamped after the menu, §2) |
| `test_decimal_form_…` | holds (footer strings, now at row 153) |
| `test_panic_works_without_ui_or_layout_phase` | holds; **extend** the deletion list with every new CASUX name of §9.2 |
| `test_panic_never_retries_failing_layout` | holds |
| `test_fastboot.test_boot_and_editing…` (`'1+2'`) | holds |
| `test_fastboot.test_keyscript_session_without_enter…` | **changes**: `LINE == 'sin(x'` becomes `'sin(x)'` (autoclose) |
| `test_fastboot.test_hint_line_works_before_the_engine_loads` | holds (hint row unchanged) |
| `test_fastboot.test_full_redraw_uses_few_colors`, `test_typing_costs…` | **change** (§10) |
| `test_shims.test_typing_round_trips…`, `test_keytext_matches_design_table` | hold with the new decode; add the §11.1 pins |
| `test_layout` | holds: `D.layout` and CACHE are unchanged |
| `test_menu.test_calculus_template` | holds (`diff(,x)`, offset 5 → `,`) |
| `test_menu` (new pins) | `insertion` of `sin(x)` → `('sin()', False, 4)`, of `surd(x,n)` → `surd(,)`, of `purge(x,...)` → `purge()`, of `paramarea(x,y,t,a,b)` → `paramarea(,,,,)` (position-0 `x` never prefilled); `diff(f,x,[n])` → `diff(,x)`; `sum(f,k,a,b)` → `sum(,k,,)`. Setup row 5 toggles `U.CLASSIC` on ENTER, `6` and ←/→, and row 4 still opens About. |

### 11.3 Other guarantees

| Area | Guarantee |
|---|---|
| `panic` | Stays in CASUI. Draws plain `LINE[max(0,CUR-29):+30]` at (10, 172) with the rule at 169. Touches no CASUX name. Resets `EH = 20`, `XOFF = EXOFF = 0`, `EDMAP = EDL = EKEY = PENDING = EMODEL = None`, `EFLAT = True`, `ED1D = False`, `VIEWEND = -1`, `STATVIEW = HINTVIEW = None`. Sets `EFAIL = LINE` for reasons 0 and 3. Reason 0 also follows an out-of-memory *computation* (LINE still holds the input), so that input is then shown 1D until it is edited: accepted, since the model cannot tell the causes apart and a retry loop is worse. |
| Cancel | `{clear@1}` during `R.go` is unchanged; the editor holds nothing during a job. |
| 256 limit | Checked on the buffer, including structure parens, in `put` and `insert`. `tidy` shortens HIST. ENTRY bypasses it as today, and `structure` falls back past 256. |
| Menus | `menu.open` signature and returns are unchanged. Results go through the existing wrap code and `insert`, then PENDING. |
| F4, help, recall, settings, history paste, ENTRY, empty-slot check, quit | Same control flow. |
| Hero view, answer scrolling | The hero is replaced by the focused history entry (newest, or `SEL` in MODE) with a view of up to 92 px. ←/→ (and 2nd ←/→) in MODE or on an empty line still step `DX` by 24; `DX` is clamped to `w - 300` in the full redraw and reset by ↑/↓ and by every edit (`put`/`insert`), as today; `<`/`>` mark more content. |
| Leading-operator Ans | Unchanged key set (less 95, which has no text: §0.5) and condition (`not LINE and R.ANS is not None and mod == 0`); the `ans()` insert goes through `put`, then the key's own action runs on the new LINE under the stale-map rule. |
| Boot | No new pack and no new module: CASEVO still imports only CASUI and CASUX before the first screen, and nothing on the boot path (`boot → emodel → redraw`) touches the engine (`LINE` is empty, so `emodel` does no layout). |
| `busy` / status during a job | `busy` and `engine` draw through `status`, which now also clears `STATVIEW`, so the status row is repainted after the job. |

---

## 12. Test plan

The new files `tests/test_mathprint_layout.py` (layout, `tidy`, `structure`),
`tests/test_mathprint_keys.py` (keys and sessions) and `tests/test_mathprint_screen.py` (rows,
redraw paths, pixel equivalence, history page) run in the source and `--bundled` tiers with
`--strict-depth`.

1. **Layout units** (engine-free; assert `'run' not in sys.modules`):
   - stops and `ORD` for every §3 template (§4.1 table);
   - hidden indices;
   - the `TGAP` distinctness;
   - `sin(x)+1` is one `draw_text`;
   - `mflat` true/false table;
   - degrade at 161 characters, at 25 nested groups, at h > 76 and under a forced
     `MemoryError` (each gives 1D with a linear map, and the next key works);
   - no OVERDRAW/OFFSCREEN for every template alone and nested 3 deep.
2. **Precedence agreement.** For each corpus input `P.rpn` accepts, the Q/W structure from
   `mparse(mode 1)` matches the RPN's `/` and `^` operands.
3. **Editing tables.** Every before/after row in §2, §2.1, §4.2, §4.3 and §4.4 as
   data-driven `(LINE, CUR, keys) → (LINE, CUR)` through `ui.key`, with no engine.
4. **Round trips.**
   - `tidy(structure(s))` and `tidy` of key-typed text give the same `run.go` record:
     300 random expressions from a small grammar, plus the 52 text-prototype cases and
     every catalog example.
   - Adversarial table: power followed by a digit, adjacent fractions, a fraction to a
     power, nested exponents, `-a/b`, `x^-1`.
5. **Navigation properties.**
   - A → walk from 0 visits every stop once and ends at `len`.
   - → then ← is the identity.
   - ↓ then ↑ returns to the same slot for a fraction, a power (§4.4 power rules), ⁿ√, ∫ab
     and Σ.
6. **Linear-typing invariant.** For 500 random balanced strings over the keyscript
   alphabet, `KS.run(s)` leaves `LINE == s` (strings with `^` compare after `structure`).
7. **Diff paint pixel equivalence.** For 200 random key sequences on 2D lines, after each
   key the entry box framebuffer rows `EY..189` (`TD.pixel`) and the visible texts there
   equal those of a forced full entry repaint (`EDIFF = False`). The sequences mix text
   keys (diff path) with ←/→/↑/↓/home/end (caret-only path) and `)`/`,` step-overs.
8. **Shell and recovery.**
   - Cost pins (§10).
   - EH growth costs exactly one full redraw, and none for linear typing.
   - `VIEWEND` scrolling.
   - Footer strings.
   - Same-row width guard.
   - Classic toggle: old behaviour, same LINE as the 1D editor; toggling with a 2D LINE
     rebuilds the model at once (`EMODEL`), in both directions.
   - `HERO` changes (first key after an answer, DEL to an empty line) repaint only the hint
     row, never the stage.
   - ENTER on `log(8,)` (picker 1.7 with the base left empty) evaluates `log(8)`; ENTER on
     a degraded (`EFAIL`/`ED1D`) line with `^()` or `/()` reports the empty slot without a
     layout.
   - A history answer with `w > 300` focused in MODE: `DX` clamps; a page of 5 answers
     makes no `D.layout` call on the second identical full redraw (one cache key per
     answer, §7.1).
   - Picker without the engine.
   - `panic` with every new CASUX name deleted, with and without the engine.
   - `EFAIL` no-retry.
   - `EDMAP`, `EDL` and both caches are empty inside `R.go` (assert in a fake family).
   - A view pack cut short, then 2nd MODE.
9. **Packaging and native.**
   - lint and framelint;
   - `pytest -m "not slow" --strict-depth` in source and bundled;
   - `build/release.py` (PACKMAX, budgets);
   - `check_release.py`, `test_release.py` (UI-only boot, depth ≤ 8);
   - CI: `micro_smoke` `ui` at 173,360 and `ui_calculus` at 189,776 with the regenerated
     streams, and 64-bit `all`.

   Hardware acceptance means an EVO run that times typing, arrows and a template insert.

When it ships, update DESIGN §16 (16.1, 16.4, 16.5, 16.6, 16.9), `docs/notes/UI.md`
(stale rows and keys) and `docs/STATUS.md`.

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| CASUX ~+10 KB (measured +19.8 KB bytecode, `room('layout')` +27.7 KB; §9.2) raises reload pressure; `ui_calculus` at 189,776 had under 2 KB spare | Measure first in CI (not yet run: the open gate of §0.7). Phase 3 option: lay answers out with `mparse(mode 1)` and drop `draw.tree/measure` (~−1.7 KB). Picker rows and menu code stay small. |
| EVO cost of `draw_text`/`draw_line`/`set_color` is unknown | Flat fast path; the diff paint; INK caret. `EDIFF`, `CARETC` and Classic are switches. Time keys on the device. |
| Diff paint leaves stale pixels | The pixel-equivalence property test (§12.7); full repaint on any geometry change; kill switch. |
| The display disagrees with the engine (`ti_rewrite` notation such as `sin^2(x)`, `xy`) | It is drawn as typed; the value is the engine's. Precedence-agreement test. |
| `tidy` or `structure` changes the meaning | One-token rule with neighbour checks; engine-equality round trips (§12.4). |
| The entry `(..)/(..)` rule flips when typing `(a)/(` with ÷ | Documented: identical text means an identical picture. 42 is the fraction key. |
| Heap spike on long 2D lines | 160 characters / 192 nodes / h 76 caps; `MemoryError` → 1D; rows built in place; `EFAIL`. |
| Key-semantics surprise (autoclose, `(` wraps to the slot end, ↑ moves inside a fraction first) | Nspire/FlowCE conventions; worked-example tests; Classic. |
| keyscript and native streams drift | Streams are generated from keyscript. The typist emits only real keys (26 for leaving an exponent). The round-trip and linear-typing tests (§12.6). |

**Not reproduced:** the Nspire gray temporary paren; Tab cycling (→ follows drawn order and
ENTER jumps to the first empty slot); selection; matrix, piecewise and system templates;
the nth-derivative template (`diff(f,x,n)` stays a call).
