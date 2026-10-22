# MicroCAS design

**Status:** the authoritative design for implementers, version 1.1, 2026-10-10. Version 1.1 applies
the first design review; the [Design review log](#design-review-log) records what changed and what
was rejected.

It replaces the three architecture proposals (memory-first, correctness-first, depth-first);
Appendix A scores them. Background material lives in `docs/reference/`:

| file | what it holds |
|---|---|
| `device-python.md` | device facts, the Python subset, the depth checker, the lint, probes |
| `algorithms.md` | algorithm survey with giac/FlowCE citations (cited here as "alg §n") |
| `flowce-answer-format.md` | FlowCE output rules (cited as "fmt §n") |
| `flowce-catalog.md` | FlowCE input rules, keys, catalog, themes (cited as "cat §n") |

Status tags, as in `device-python.md`:

| tag | meaning |
|---|---|
| [V] | verified on the EVO |
| [M] | measured on the desktop with a prototype (Appendix A lists the prototypes); `device-python.md` also uses it for desktop MicroPython v1.12 measurements |
| [T] | documented by a third party from the EVO (as in `device-python.md`) |
| [D] | documented by TI for the TI-84 Plus CE |
| [E] | estimate; the formula is given |
| [A] | assumption, to be settled by a named probe |

When a probe settles an item, change its tag here and in `device-python.md`.

**MUST** means a test or lint enforces it. **should** means the default unless a measurement says
otherwise.

## Contents

| part | sections |
|---|---|
| Overview | [0 Decisions](#0-decisions-in-one-screen) · [1 Overview](#1-overview-and-goals) · [2 Settled decisions](#2-settled-decisions-summary) · [3 Device constraints](#3-device-constraints) · [4 Repo and module map](#4-repository-layout-and-module-map) |
| Core | [5 Data representation](#5-data-representation) · [6 Number tower](#6-number-tower) · [7 Parser](#7-parser-and-input-preprocessing) · [8 Canonical form and simplifier](#8-canonical-form-and-simplifier) · [9 Rule engine](#9-rule-engine) · [10 Execution model](#10-execution-model-the-generator-trampoline) · [11 Algorithm plan](#11-algorithm-plan) |
| Output and UI | [12 Printer](#12-printer-1d-and-the-decimal-line) · [13 2D layout](#13-2d-layout-cvdraw) · [14 F4 forms](#14-answer-forms-f4-cvform) · [15 Registry and catalog](#15-command-registry-catalog-and-help) · [16 UI](#16-ui-architecture-cvui-cvdraw-cvmenu) |
| Budgets | [17 Frame budget](#17-frame-budget) · [18 Memory and lazy loading](#18-memory-budget-and-lazy-loading) · [19 Build](#19-build-and-bundling-build) |
| Process | [20 Testing](#20-testing-strategy) · [21 Milestones](#21-milestone-plan) · [22 Risks](#22-risks) |
| Appendices | [A Proposal scoring](#appendix-a-the-three-proposals-scoring-and-what-was-kept) · [B Probes](#appendix-b-probes-to-run-on-the-evo-m03) · [C Defaults to confirm](#appendix-c-defaults-chosen-here-confirm-with-the-user) · [Design review log](#design-review-log) |

---

## 0. Decisions in one screen

1. **Base: the memory-first proposal.**
   - Expressions are a hash-consed DAG of flat tuples with integer child ids.
   - The ids live in our own chained intern table: no dict, platform-independent hashes.
   - Sums and products are coefficient/exponent pair sequences (GiNaC style). There is no POW op.
   - Nodes never outlive a command: Ans, history and variables are stored as text.
   - Rules are input-language strings with letter wildcards.
   - One parser feeds both the CAS builder and the 2D layout engine.
2. **Grafted from correctness-first:**
   - Gaussian-rational numbers `(NUM, a, b, d)`; `i` is a number.
   - A per-node symbol bitmask `V[id]`, so `free_of` is O(1).
   - A **generator trampoline** runs all search and orchestration code. PROBE6 gates it; the
     fallback is the memory-first task machine.
   - A written branch/assumption policy.
   - An invariant checker over every node of every test.
   - Numeric verification of simplify candidates.
   - Per-rule self-match, soundness and measure tests, plus `lin`/`quad` binders.
   - `-(sum)` is distributed by the constructors.
3. **Grafted from depth-first:**
   - Per-function level annotations `#@L n`, checked statically (FRAMELINT) and per frame at
     run time.
   - A nesting-invariance test.
   - Resident modules are imported leaf-first.
   - A native `POLL` adapter for cancel.
   - Scripted key-sequence end-to-end tests.
   - An optional MicroPython unix-port test tier.
4. **Depth.** The deepest planned chain is 7 frames (entry 0, ..., `mk` 7). The test budget is 8,
   with strict penalties. The device limit is 10 [V].
5. **Heap.**
   - About 2,650 resident lines, about 58 KB [E].
   - Lazy modules are written as parts of at most `LAZYMAX` lines each (provisional 150, §4.3),
     loaded per command family and evicted LRU, never while one of their generators is live. The
     M0.5 memory gate measures the compile peak and the eviction mechanism, and fixes `LAZYMAX`,
     `PEAKB`, `NMAX` and the UI residency **before T1.1** (§18.7).
   - Node slots are preallocated at boot for `NMAX = 768` nodes (12 KB); each live node adds a
     tuple of about 32 B [E].
   - Every search runs in a releasable region.
6. **Device names.** The entry program is `CAS` (it was `CASEVO` until the QPL changes). Modules are `CV` plus up to 6 letters.

---

## 1. Overview and goals

MicroCAS is a computer algebra system for the TI-84 EVO, written in the calculator's Python. It is a
spiritual port of FlowCE, the giac-based CAS flash app for the TI-84 Plus CE. FlowCE is the model
for features, input habits and textbook-style answers. giac is an algorithm reference only, and none
of its code ships.

**Goals, in priority order:**

1. Correct answers, verified on the desktop against SymPy.
2. Fit the device: about 10 Python frames, about 173 KB of heap, a Python 3.4 subset, no native code.
3. A FlowCE-like experience: 1D input with TI conventions, 2D textbook output, a decimal line, F4
   forms and a command menu.
4. A code base that independent agents can build in parallel, test first, on the desktop.

**Non-goals for v1:** graphing, programming, matrices, number theory beyond what factoring needs,
persistence between runs, the 2D input editor (architected for, not built), Risch, Gruntz,
residues, RootOf.

**Data flow:**

```
key codes --> CVUI (1D editor, history, menus) --ENTER--> CVRUN.go(text)              depth 1
                                                   |  text passes: autoclose, Ans
                                                   |  CVPARSE: tokens -> RPN
                                                   |  trampoline: g_eval -> command generators
                                                   |     -> algorithms (CVALG, CVNORM, lazy modules)
                                                   |        -> constructors (CVNODE) -> mk
                                                   |  CVPRINT: node -> canonical 1D text + decimal
                                                   |  reset the node table
CVUI.show(record) <------ (kind, text, approx, flags)
   CVDRAW: text -> RPN -> boxes -> display list -> ti_draw (shipped; see §16)
```

---

## 2. Settled decisions (summary)

These were settled with the user. Do not reopen them.

| area | decision |
|---|---|
| project | Personal tool, published on GitHub, no license yet. A spiritual port of FlowCE; faithfulness is not required. giac is a reference only. |
| scope | v1 = T1 + T2 + T3, built as milestones T1 -> T2 -> T3. T3 may be cut at its milestone if it does not fit memory or speed. |
| T1 | Exact arithmetic (big rationals, simplified radicals, exact pi and e, complex numbers with i); simplify, expand, factor (polynomials); solve (linear, quadratic, rational-root polynomials); Ans, variable store (sto->), history. |
| T2 | Derivatives; limits (one-sided, "does not exist" with the one-sided values); integrals (table, u-substitution, by parts, partial fractions, +C); definite integrals; Taylor series. |
| T3 | Improper integrals (divergence reported); series sums; Riemann sums; ODEs (separable, 1st-order linear, 2nd-order constant-coefficient homogeneous plus common right-hand sides, with initial conditions); gradients; multiple integrals; polar and parametric areas. |
| graphing | None in v1. |
| input | 1D line editor (FlowCE style: implicit multiplication, Ans, a leading operator applies to the last answer). Architected so that a 2D editor can be toggled in later. |
| output | 2D textbook rendering, with a 10-significant-digit decimal line under exact numeric answers. Scientific notation when \|x\| >= 1e10 or \|x\| < 1e-4. F5 (and < >) cycles the forms simplified / one fraction / factored / expanded / decimal. |
| menus | The F1 command menu pastes the command and shows a one-line example/help hint (a lite FlowCE catalog). Command names follow giac, plus short aliases (`int`, `d`, `lim`, ...). |
| conventions | `log` is base 10 and `ln` is natural. Radians by default, with a degree mode. Exact trig at special angles. `+C` on antiderivatives. Polynomials in descending powers. `i` is the imaginary unit. |
| failure | A failed indefinite integral is shown unevaluated. A failed definite integral falls back to a numeric value labelled ≈. Limits behave the same way. |
| keys | F1-F4 the command menu's Algebra, Calculus, Trig and More tabs, F5 cycle forms; with 2nd lit the row relabels to All, Tmpl (template picker), Test, Setup (rad/deg), Help for the current command (v1.0.0, MATHPRINT.md 0.13; F2 was the history scroll). math opens the tab used last. Up/down walk the history, left/right pick its input or answer, enter copies it, [clear] deletes it (v1.0.1). Left/right scroll wide answers. sto-> stores. [clear] clears the line or cancels a computation. |
| themes | One light palette (v1.0.0 removed the Night theme and its setting). |
| robustness | [clear] cancels long computations (poll `ti_system.escape()`/`get_key`). MemoryError is caught and shown as a message. |
| architecture | Flat n-ary expression trees; an explicit-stack parser and printer; a data-driven rule engine run by an explicit-stack loop (derivatives, integral tables, simplification identities); iterative algorithms for factoring, partial fractions, limits and ODEs. Only the UI layer imports `ti_*`; desktop shims stand in. Tests: pytest, a SymPy oracle, golden files, a call-depth checker. |
| layout | `src/` (device code), `shim/`, `tests/`, `build/` (bundler), `docs/`. Python venv at `.venv`. Desktop CPython 3.14; device code is the Python 3.4 / MicroPython subset. |
| process | Design doc -> test-first desktop core T1, T2, T3 (one commit per milestone) -> UI + build script -> on-device tests. |

**Decisions made in this document.** Each is a default that is cheap to change; Appendix C lists
them for confirmation.

| # | default | where |
|---|---|---|
| D1 | `d/dx tan(u)` prints `sec(u)^2` (one template string) | §9.3 |
| D2 | Trig equations return the solutions in one period, `[0, 2π)` (giac's default; `[0, 360)` in degree mode), not a general family | §11.2 |
| D3 | `solve` works in real mode (`x^2+1=0` gives `no solution`). `csolve` is optional. | §11.2 |
| D4 | Left/right move the caret when the edit line has text. On an empty line, or in history mode, they scroll the shown answer. | §16.6 |
| D5 | Wide answers scroll; v1 does not wrap them | §13.5 |
| D6 | `alpha` + `.` types `'` (the prime for `y'`) | §16.4 |
| D7 | T3 conveniences `polararea`, `paramarea`, `arclen`, `riemann` and `grad` exist as commands. Typed set-up integrals work too. | §15.2 |
| D8 | Decimals typed by the user are approximate (floats), as on a TI | §6.3 |
| D9 | The single-letter alias `d` means `diff` only when it is called with 2 or more arguments and `d` is not a stored variable | §7.5 |
| D10 | History inputs are drawn as 1D text in v1; results are 2D | §13.1 |
| D11 | ENTER on an empty line repeats the last input (TI habit) | §16.5 |
| D12 | The F4 trig forms are optional (T2); the settled five forms are required | §14 |
| D13 | Device gates run inside the desktop phases: the M0.5 memory gate before T1.1, the PROBE6 gate before T1.6, and the bundle-lite plus PRBMEM recalibration at the end of T1 (T1.14, T1.15). The settled process puts device tests after the UI. | §21 |
| D14 | Only `E` (the EE key) starts a float exponent; `2e-1` is `2·e-1`. FlowCE also accepts `e`. | §7.2 |
| D15 | Arguments of odd and even functions are sign-normalized: `sin(1-x)` becomes `-sin(x-1)` (giac does the same) | §6.4 |
| D16 | 2nd math opens a TEST picker (`= != < <= > >= !`), as on the TI-84 | §16.4 |
| D17 | Lazy modules over `LAZYMAX` lines are split into parts at fixed seams from the start (§4.3); M0.5 may merge them back | §4.3 |

---

## 3. Device constraints

The full detail is in `device-python.md`. This summary lists what drives the design.

| fact | tag | consequence |
|---|---|---|
| Frames at depths 1..10 run; entering depth 11 raises `RuntimeError`. Every Python call counts (functions, methods, generators, mutual recursion); locals do not. | V | No recursion anywhere. Every function has a fixed level (§17). Search code nests through a trampoline, which costs no frames. |
| Comprehensions, lambdas, `key=` functions, dunders, properties and `with` probably cost hidden frames | A (PROBE5) | All of them are banned in `src/` (§17.4). Sorts use decorated flat tuples with no `key=`. |
| Native code may recurse in C on nested containers (`==`, `hash`, `repr`, quicksort) | A (PROBE5 nest) | Every container that holds node ids is flat. Children are ids, never nested tuples. |
| If the cap is a C-stack check (device-python §2.2), native work at our deepest levels draws on the same budget: the compiler under `need` (depth 3-4), `list.sort` in `add_` (depth 6, worst on sorted input), exception creation and `gc.collect` in `mk` (depth 7) | A (PROBE6 depth section) | PROBE6 measures each at or beyond its planned depth (Appendix B). Fallbacks in §17.2. |
| `math` domain errors may return nan instead of raising; float overflow gives inf without raising | A (PROBE6 `math`) | `nrun` checks every value for nan and inf whatever the probe shows (§6.6) |
| `sys.version` is 3.4.0 (MicroPython family). No f-strings. `eval`/`exec` work. | V | The subset lint (§20.3). `%`-formatting only. |
| No `math.gcd/isqrt/log10`, `int.bit_length`, `functools`, `itertools`, `re`, `fractions`, `cmath`, `decimal` | V/A | We write our own: gcd loops, Newton isqrt, complex helpers, a decimal formatter. |
| About 185 KB free at program start (PROBE3: 185,296 B); 173 KB after a probe imported `ti_plotlib`, `ti_graphics`, `ti_image` and more, which MicroCAS does not import. Bytecode, compile transients, qstrs and data all share this heap. | V | Resident code about 58 KB. Lazy families, eviction, regions, node caps (§18). |
| The GC is non-moving and mark-sweep | A | Allocate long-lived buffers early. No large dict growth (the intern table is our own). |
| Module names are `[A-Z][A-Z0-9]{0,7}`, in a flat namespace. User modules can import each other. A program runs as `from NAME import *`. | V | `CAS` plus `CVxxxxxx`. No `__main__` guard. The entry body is depth 0. |
| A 20k-iteration loop takes 0.066 s (about 3.3 µs per simple iteration) | V | Step budgets on every search. Numeric pre-checks before exact work. |
| Keys arrive as TI-BASIC `getKey` codes; 2nd (21) and alpha (31) are separate presses | V | The UI keeps its own modifier state (§16.4). |
| `ti_system.escape()` returns True once after [clear] was pressed | D (CE) | Probe it on the EVO (PROBE6); the fallback is `get_key() == 45` |
| The Python screen is about 320x210 | V/A | Layout constants come from PROBE7 (§16.1) |
| Dict and set order are not portable; floats print differently; `round`/`sum` differ | A/C | Own hash, own formatter, sort with total keys, never iterate a dict for output order |

---

## 4. Repository layout and module map

```
src/            device code. Flat; desktop module names; one module per row of the table below
shim/           ti_system.py, ti_draw.py (ti_graphics.py for the probes): desktop stand-ins that record calls and replay key scripts
tests/          pytest suites (§20)
  support/      evodepth.py, framelint.py, lint.py, invariants.py, oracle.py, keyscript.py, gen.py
  golden/       *.txt golden files
  corpus/       t1.tsv, t2.tsv, t3.tsv: oracle corpora
  depth_shapes/ calibration shapes (PROBE4, PROBE6)
build/          manifest.py (name map, residency, budgets), bundle.py, sizes.py
probe/          device probes (PROBE*.py, PRBMEM.py, CVTEST.py)
docs/           DESIGN.md (this file), reference/
dist/           bundler output (gitignored): dist/device/*.py, dist/linemap.json, dist/sizes.txt
```

### 4.1 Module map

**Lines** are minified code-line targets. **KB** is the estimated RAM after import, at 22 B per
line [E]: 12.5 B of `.mpy` per line [M] times a RAM factor of 1.8 [A]. The M0.5 memory gate
replaces the factor before T1.1, and T1.15 re-measures it on the real T1 modules (§18.7).

The line targets are estimates and may be 1.5-2× low for the algorithm-heavy modules (CVINT2,
CVPOLY, CVSOLVE). The bundler's per-module size gate (§19.2) catches an overrun when the module is
written, and §18.8 says what to do then.

**Lazy-module cap.** A lazy device module has at most `LAZYMAX` lines, because its compile peak must
fit in `RESERVE` (§18.1). `LAZYMAX` is provisionally 150 and is fixed by the M0.5 gate before any
lazy module is written. The rows below are logical modules; every lazy row over 150 lines is
written as parts (§4.3).

**Residency classes:**

| class | meaning |
|---|---|
| **R** | resident, imported at start |
| **L** | lazy, loaded when a command needs it |
| **U** | lazy UI module |

**Alias** is the fixed import alias that every module uses for that module.

| src | device | class | alias | role | lines | KB | tier |
|---|---|---|---|---|---|---|---|
| `casevo.py` | `CAS` | entry | – | Imports resident modules leaf-first. Runs the event loop at module level. | 30 | 1 | UI |
| `node.py` | `CVNODE` | R | `K` | Intern table, regions, number kernels, constructors (`add_`, `mul_`, `fn_`, `rel_`, `neg_`, `absn`), radicals, special values, the ∞ folding table, exceptions, `ESC` poll hook | 520 | 11 | T1 |
| `nodeb.py` | `CVNODEB` | R | `KB` | Powers too large to fold (§6.1): the fold rule, `huge`, `nval`, the sum, ln and kernel rules. Imported by `node`; on the calculator an aux pack (`CASBIG`) loaded on first use | 320 | 8 | T1 |
| `parse.py` | `CVPARSE` | R | `P` | Lexer, TI rewrite, name cutter, implicit `*`, token-level macro/variable expansion, shunting-yard, `inst`, `g_eval` | 420 | 9 | T1 |
| `printer.py` | `CVPRINT` | R | `PR` | 1D printer, display order, decimal formatter, messages | 330 | 7 | T1 |
| `alg.py` | `CVALG` | R | `A` | `postorder`, `subst`, predicates (`linear`, `quadratic`, `split_const`, `degree`, `simplify_candidate`), `size`, numeric evaluator `nev`, numeric zero probe | 300 | 7 | T1 |
| `run.py` | `CVRUN` | R | `R` | `go` (runner + trampoline), loader/evictor, command registry, session store (Ans, history, VARS, FUNCS), settings, result records | 300 | 7 | T1 |
| `draw.py` | `CVDRAW` | R | `D` | Layout boxes, display list, renderer, the palette, glyph strokes | 350 | 8 | UI |
| `ui.py` | `CVUI` | R | `U` | Key handling, modifier state, editor, history view, hero, status | 400 | 9 | UI |
| `rules.py` | `CVRULE` | L | `RU` | Rule-set compiler and cache, matcher, `rebuild`, `g_rewrite`, guards | 250 (2 parts) | 6 | T1 |
| `poly.py` | `CVPOLY` | L | `PO` | Dense Z[x] lists, division, PRS gcd, Yun, Bezout, rational roots, Gauss-Jordan over Q, sparse multivariate dicts | 350 (3 parts) | 8 | T1 |
| `norm.py` | `CVNORM` | L | `NO` | `expand`, `normal`/`together`, `iszero`, `g_simplify` candidates, answer polish | 300 (2 parts) | 7 | T1 |
| `ident.py` | `CVIDENT` | L | `ID` | Identity rule sets (strings), one-level denesting | 120 | 3 | T1 |
| `factor.py` | `CVFACT` | L | `FA` | Factor pipeline, integer factoring, numeric real roots | 280 (2 parts) | 6 | T1 |
| `solve.py` | `CVSOLVE` | L | `SO` | Solve worklist, inverse table, linear systems | 330 (3 parts) | 7 | T1 |
| `forms.py` | `CVFORM` | L | `FO` | F4 forms: orders, offer predicates, dedupe | 150 | 3 | UI |
| `diff.py` | `CVDIFF` | L | `DF` | Derivative fold, templates, n-th order, partials, gradient, FTC | 150 | 3 | T2 |
| `series.py` | `CVSER` | L | `SE` | Truncated power-series engine, `taylor` | 300 (2 parts) | 7 | T2 |
| `limit.py` | `CVLIM` | L | `LI` | Limit strategy chain, growth classes, numeric limits | 300 (2 parts) | 7 | T2 |
| `integ.py` | `CVINT` | L | `IN` | Integration driver, S0-S2, antiderivative check | 300 (2 parts) | 7 | T2 |
| `itab.py` | `CVITAB` | L | `IT` | Integral table rules (strings) | 100 | 3 | T2 |
| `integ2.py` | `CVINT2` | L | `I2` | S3 tabular parts, S4 rational and Hermite, S5 trig powers, `partfrac` | 300 (2 parts) | 7 | T2 |
| `integ3.py` | `CVINT3` | L | `I3` | S6 by parts, S7 radicals (Ostrogradsky), S8 Weierstrass | 250 (2 parts) | 6 | T2 |
| `defint.py` | `CVDEF` | L | `DI` | Definite and improper integrals, tanh-sinh, Gauss-Legendre, multiple integrals | 300 (2 parts) | 7 | T2/T3 |
| `sums.py` | `CVSUM` | L | `SU` | Finite and infinite sums, convergence tests, Riemann sums | 300 (2 parts) | 7 | T3 |
| `ode.py` | `CVODE` | L | `OD` | ODE classifier and solvers, initial conditions | 320 (3 parts) | 7 | T3 |
| `menu.py` | `CVMENU` | U | `M` | F-key menus (catalog tabs), TEST picker, vars, setup, help screens | 250 (2 parts) | 6 | UI |
| `catalog.py` | `CVCAT` | U | `CA` | Catalog entries and help text (data) | data | 7 | UI |

Resident total: about 2,650 lines, about 58 KB [E].

### 4.2 Import rules

- A module imports another as `import node as K`, always with the alias from the table. `from X
  import y` and `import *` are banned in `src/`. The bundler rewrites `import node as K` to
  `import CVNODE as K`.
- Resident modules may import resident modules at module level. The import graph MUST be acyclic.
  `casevo.py` imports in leaf-first order: `node, alg, parse, printer, run, draw, ui`. Each module's
  own imports then only bind modules that are already loaded, so import bodies never nest (§18.4).
- Lazy modules may import resident modules at module level. They MUST NOT import other lazy modules
  at module level, so the import order of lazy modules never matters.
  - From a generator, use `M = R.need('poly')`. `need` also loads the module's family (§4.3) and
    its `DEPS` closure, and pins them while the calling generator is on the stack (§18.4).
  - From a plain function, use `M = R.MODS['poly']`. The command's registry entry must list that
    module as a dependency (§18.4).
- Module bodies only define functions, constants and tables. They make no calls other than builtins
  such as `array(...)` and `tuple(...)`.
- Only `ui.py`, `draw.py`, `menu.py` and `casevo.py` import `ti_*`. Core modules receive natives
  by injection: `K.ESC`, `K.MEMFREE` and `R.BUSY` are set by the UI at start.

### 4.3 Parts (compile units, D17)

A lazy logical module longer than `LAZYMAX` lines is written from the start as **parts**: separate
source files of at most `LAZYMAX` lines each. Splitting does not change the steady memory; it caps
the compile peak at the size of one part, because each part compiles on its own.

- **Names.** `poly.py`, `polyb.py`, `polyc.py`; device `CVPOLY`, `CVPOLYB`, `CVPOLYC`; aliases `PO`,
  `POB`, `POC` (the module's alias plus `B`, `C`, or `D`; `factord` uses `FAD`). The runtime keys
  used by `need`, `MODS`, `DEPS` and `STRATS` are the family key plus `b`, `c`, or `d`:
  `int`, `intb` for `integ.py`, `integb.py`; the
  name map `DEV` (§18.4) turns a key into the module name. The bundler treats a part as an ordinary
  module.
- **Families.** Parts that call each other form a family, listed in `R.PARTS = {'poly': ('poly',
  'polyb', 'polyc'), ...}`. `need` loads a family as a unit, one part (one compile) at a time, and
  evicts it as a unit. `DEPS` and the registry name families. `R.need('polyb')` loads the whole
  `poly` family and returns the part `polyb`.
- **Cross-part calls.** A part reaches a sibling as `R.MODS['polyb'].f(...)`: a dict lookup, no
  frame. Module-level imports between parts are banned, as between any two lazy modules (§4.2).
- **Independent strategies** go in separate one-part families, so that only the strategy being
  tried is loaded (ladder step 5, §18.8).
- **The seams below are provisional** for `LAZYMAX = 150`. Owners may move them; the size gate
  (§19.2) enforces the cap. If M0.5 raises `LAZYMAX`, parts of one family may be merged.

| logical module (lines) | parts | families |
|---|---|---|
| CVRULE (250) | `rules`: compiler, cache, `guard_ok`, `rebuild`, `g_rewrite`; `rulesb`: `match`, `check`, `view` | one |
| CVPOLY (350) | `poly`: dense Z[x] arithmetic, division, PRS gcd, Yun; `polyb`: Bezout, rational roots, Gauss-Jordan over Q; `polyc`: sparse multivariate dicts | one |
| CVNORM (300) | `norm`: `expand`, `normal`, `together`, Kronecker gcd; `normb`: `g_iszero`, simplify candidates, `g_autosimp`, `g_polish` | one |
| CVFACT (515 implemented) | `factor`: command and node/polynomial conversion (131); `factorb`: univariate factoring and Kronecker (121); `factorc`: multivariate recombination and product check (129); `factord`: integer factoring, binomial shapes and numeric real roots (134) | one, four parts |
| CVSOLVE (330) | `solve`: worklist, polynomial and radical cases, root checks; `solveb`: inverse table, trig windows, exponentials, `a·sin u + b·cos u`; `solvec`: linear and nonlinear systems | one |
| CVSER (300) | `series`: substitution, ADD/MUL folds, powering; `seriesb`: function recurrences, `g_series` retries, `g_taylor` | one |
| CVLIM (300) | `limit`: strategies 1-4 and L'Hôpital; `limitb`: growth classes, oscillation, numeric limits | one |
| CVINT (300) | `integ`: driver, S0, S1, the check; `integb`: S2 u-substitution | one (`int`) |
| CVINT2 (300) | `integ2`: S3 tabular, S5 trig powers; `integ2b`: S4 rational and Hermite, `partfrac` | two (`int2`, `int2b`) |
| CVINT3 (250) | `integ3`: S6 by parts; `integ3b`: S7 radicals, S8 Weierstrass | two (`int3`, `int3b`) |
| CVDEF (300) | `defint`: singularities, F, jumps, symmetry; `defintb`: quadrature, improper pieces, multiple integrals | one |
| CVSUM (300) | `sums`: finite and symbolic sums, Riemann; `sumsb`: infinite-series tests, known-series table, numeric | one |
| CVODE (320) | `ode`: classifier, 1st-order linear, separable, Bernoulli; `odeb`: 2nd order with constant coefficients; `odec`: initial conditions, implicit answers | one |
| CVMENU (250) | `menu`: catalog menu, TEST picker; `menub`: vars, setup, help | two (UI) |
| CVCAT (data, about 7 KB) | `catalog`: the Algebra and Trig entries; `catalogb`: Calculus and More. A data module has a compile peak too: at least one parse node per literal. | two (UI); the All tab and help load both |

---

## 5. Data representation

### 5.1 The node table (CVNODE)

```
N   = [None] * NMAX           list: id -> flat tuple (op, ...); id 0 is "null"
H   = [0] * NMAX              list: id -> 25-bit structural hash (always a small int)
NX  = [0] * NMAX              list: id -> next id in the same hash bucket (0 = end)
V   = [0] * NMAX              list: id -> symbol bitmask (bits 0..28; bit 29 = overflow)
NN  = BASE                    the table length: ids 0 .. NN-1 are in use
B   = array('i', [0] * 1024)  bucket -> newest id in its chain (allocated once, 4 KB)
SYMN, SYMI                    per-command symbol bit table: bit -> name, name -> bit
```

- **Preallocated slots.** `N`, `H`, `NX` and `V` are allocated once at boot with `NMAX = 768`
  slots (4 lists × 768 × 4 B = 12 KB), and the module global `NN` is the length. The lists never
  grow, so no reallocation transient (old and new block alive together, four lists at once) happens
  in the non-moving heap at the moment memory is lowest. `NMAX` comes from the memory model
  (§18.1) and the M0.5 gate. Other modules read the length as `K.NN`, never `len(K.N)`.
- **Ids are a topological order.** A child is always older than its parent, so a smaller id can
  never contain a larger one.
- **Equality is `a == b` on ids.** This holds within a command only.
- **No dict is used for interning.** A MicroPython dict holding 2,000 entries needs a contiguous
  table of about 20 KB, plus a rehash transient of the same size [E]. The chained table uses one
  preallocated slot per node. It truncates in O(tail) (§5.9), and its hash is identical on every
  platform.
- **Lists are used rather than `array`** for `H`, `NX` and `V`. A list slot holding a small int
  costs 4 B on the device, the same as an array slot [A], and a list can also hold the `N` tuples.
  Released `N` slots are set to `None` so that the GC can reclaim the dead tuples.

### 5.2 Op codes

| range | op | tuple | notes |
|---|---|---|---|
| leaves (payload, no ids) | `NUM` 0 | `(NUM, a, b, d)` | Gaussian rational (a + b·i)/d; Python ints; d >= 1; gcd(a, b, d) = 1 (§6.1) |
| | `FLT` 1 | `(FLT, re, im)` | approximate complex number; floats; finite; `-0.0` stored as `0.0` |
| | `SYM` 2 | `(SYM, 'name')` | ASCII name. `y'` and `y''` are symbol names. `C1`, `C2` are symbols. Internal fresh symbols start with `_`. |
| | `CON` 3 | `(CON, k)` | k: 0 π, 1 e, 2 +∞, 3 undef, 4 true, 5 false. `true` and `false` are the values of decided relations; they are never numbers (§8.2). |
| | `WILD` 4 | `(WILD, slot, cons)` | exists only in rule patterns (§9) |
| composites (slots after `op` are ids); `COMP = 8` | `ADD` 8 | `(ADD, c, t1, k1, ...)` | §5.3 |
| | `MUL` 9 | `(MUL, k, b1, e1, ...)` | §5.3 |
| | `CALL` 10 | `(CALL, f, a1, ...)` | `f` is a SYM id: unevaluated command results (`integrate`, `sum`, `limit`, `diff`), undefined functions `f(x)`, conditions `y(0)` |
| | `LST` 11 | `(LST, a1, ...)` | lists, vectors, solution sets; order matters |
| | `EQ` 12, `NE` 13, `LT` 14, `LE` 15 | `(op, a, b)` | `a>b` is built as `LT(b, a)`; `a>=b` as `LE(b, a)` |
| | `BIGO` 16 | `(BIGO, u)` | the series remainder `O(u)` |
| | `DNE` 17 | `(DNE, l, r)` | result sentinel: a limit does not exist; `l`, `r` are the one-sided values (`UNDEF` for an oscillating side) (§10.5) |
| | `DIVG` 18 | `(DIVG, w)` | result sentinel: diverges; `w` is a small NUM id giving the reason (0 infinite bound, 1 unbounded integrand, 2 terms do not go to 0) |
| | `HOLD` 19 | `(HOLD, m)` | a display-only product that the constructors would fold, such as `factor(360) = 2^3*3^2*5`. `m` is a MUL built with `mk` directly (§11.2). |
| functions; `FN0 = 24` | `SIN` 24, `COS` 25, `TAN` 26, `SEC` 27, `CSC` 28, `COT` 29, `ASIN` 30, `ACOS` 31, `ATAN` 32, `SINH` 33, `COSH` 34, `TANH` 35, `LN` 36, `ABS` 37, `SIGN` 38, `FLOOR` 39, `CEIL` 40, `FACT` 41 | `(op, a)` | one argument. `FACT` is `n!`. `asec`, `acsc` and `acot` are rewritten by the builder (`asec(u) = acos(1/u)`, ...). |

### 5.3 Sums and products: pair sequences

**`ADD = (ADD, c, t1, k1, ..., tn, kn)`** means `c + k1·t1 + ... + kn·tn`.

- `c` is a NUM or FLT id. It may be `ZERO`.
- Each `ki` is a NUM or FLT id other than zero.
- Each `ti` is not a number, not an ADD, and not a MUL whose coefficient is not 1. A term's
  coefficient always lives in its `ki`.
- The `ti` are pairwise distinct; like terms are collected.
- The pairs are sorted by `(H[ti], structural tie-break)` (§5.7).
- There is at least 1 pair, and `n >= 2` or `c != 0`. Anything smaller collapses: to a number, to
  `t1`, or to the product `k1·t1`.

**`MUL = (MUL, k, b1, e1, ..., bn, en)`** means `k · b1^e1 · ... · bn^en`.

- `k` is a NUM or FLT id other than zero.
- Each `ei` is a nonzero id, either a number or any expression.
- The `bi` are pairwise distinct; the exponents of equal bases are summed.
- A `bi` is a number only in three cases:
  - a positive integer >= 2 that is s-th-power-free, under a rational exponent r/s with 0 < r/s < 1
    (a radical, §6.2);
  - a power **kept whole** because it is too large to fold (§6.1), `KB.huge(b, e)` (which also
    asks for a weight `4·|floor(e)|·hexlen(b)` over `MAXBITS/16`, so the small powers of a HOLD's
    display product are not taken for one): a squarefree
    integer >= 2 under a rational exponent outside [0, 1) (`2^100000`, `10^(10^6)`,
    `2^(200001/2)`, `2^-100000`), primes with equal exponents sharing one base as radicals do
    (`6^100000`, not `2^100000*3^100000`). Non-real numeric integer powers beyond the fold
    limit are rejected (§6.1). The coefficient `k` has no prime factor
    of a real base kept whole, and neither has the coefficient of an ADD term containing one, so
    `2*2^100000` is `2^100001`;
  - any number under a non-numeric exponent (`2^x`).
- A `bi` is never a MUL under an integer exponent; such products are flattened.
- `bi == E` means the exponential `e^ei`.
- `n == 1` with `e1 == 1` requires `k != 1`. If `b1` is also an ADD, then `k` is not 1 or −1:
  `-(x+1)` becomes `-x-1`, while `2(x+1)` and `(x+1)/2` are kept (giac-like; §8.2).
- The pairs are sorted like ADD pairs.

**There is no POW op.** A power is a one-pair MUL.

### 5.4 Derived forms

| math | node |
|---|---|
| `x - y` | `ADD(0, x, 1, y, -1)` |
| `x / y` | `MUL(1, x, 1, y, -1)` |
| `x^2` | `MUL(1, x, 2)` |
| `3x^2` alone / as a term of a sum | `MUL(3, x, 2)` / the pair `(MUL(1, x, 2), 3)` |
| `sqrt(u)` | `MUL(1, u, 1/2)`; `sqrt(2)` is `MUL(1, 2, 1/2)` |
| `e^u`, `exp(u)` | `MUL(1, E, u)` |
| `ln(u)` | `LN(u)` |
| `log(u)` (base 10) | `MUL(1, LN(u), 1, LN10, -1)`. The printer shows `log(u)` (§12.4). `d/dx log` needs no template. `log(100) = 2` because `ln(10^2)` becomes `2·ln(10)` on construction. |
| `x^(1/3)`, `surd(x,3)` | `MUL(1, x, 1/3)`. Numeric odd roots of negatives are real (§6.2). |
| `3 + 4i` | `NUM(3, 4, 1)`, a single number |
| `-∞` | `MUL(-1, OO, 1)` |
| `y'`, `y''` | `SYM("y'")`, `SYM("y''")` |
| unevaluated `∫ f dx` | `CALL(SYM('integrate'), f, x)` |

### 5.5 Preallocated ids

These are interned at startup, in this order. Their ids are identical in every command [M]:

| id | name | tuple |
|---|---|---|
| 1 | `ZERO` | `(NUM, 0, 0, 1)` |
| 2 | `ONE` | `(NUM, 1, 0, 1)` |
| 3 | `MONE` | `(NUM, -1, 0, 1)` |
| 4 | `TWO` | `(NUM, 2, 0, 1)` |
| 5 | `HALF` | `(NUM, 1, 0, 2)` |
| 6 | `I` | `(NUM, 0, 1, 1)` |
| 7 | `PI` | `(CON, 0)` |
| 8 | `E` | `(CON, 1)` |
| 9 | `OO` | `(CON, 2)` |
| 10 | `UNDEF` | `(CON, 3)` |
| 11 | `TEN` | `(NUM, 10, 0, 1)` |
| 12 | `LN10` | `(LN, 11)` |
| 13 | `TRUE` | `(CON, 4)` |
| 14 | `FALSE` | `(CON, 5)` |

`BASE = 15`. Everything at `BASE` or above is per-command scratch.

### 5.6 Worked example: `x^2+3x/2-sin(x)` [M]

This dump was produced with the scratch validation code (Appendix A), before `TRUE` and `FALSE`
took ids 13 and 14. With the current table, add 2 to every id of 13 or more.

```
RPN    : x 2 ^ 3 x * 2 / + x sin/1 -          (the * after 3 was inserted by the implicit-* pass)
build  : 8 new nodes (ids 13..20)
  13  H=002a0d8  V=1  (SYM, 'x')
  14  H=050bf11  V=1  (MUL, 2, 13, 4)              x^2
  15  H=0000019  V=0  (NUM, 3, 0, 1)               3      (garbage after folding)
  16  H=000001a  V=0  (NUM, 3, 0, 2)               3/2
  17  H=050f309  V=1  (MUL, 16, 13, 2)             3x/2   (garbage: becomes a pair in the sum)
  18  H=002a3d8  V=1  (SIN, 13)                    sin(x)
  19  H=1abfcf6  V=1  (MUL, 3, 18, 2)              -sin(x) (garbage)
  20  H=1a26583  V=1  (ADD, 1, 13, 16, 18, 3, 14, 2)
                           c=0  x*3/2  sin(x)*(-1)  x^2*1     (pairs in hash order)
same id from "-sin(x) + 3/2*x + x*x" : 20
after keep(BASE, 20): 5 live nodes; the root becomes id 17 = (ADD, 1, 13, 15, 16, 3, 14, 2)
printed: x^2+3*x/2-sin(x)            (display order comes from the printer, §12.3)
```

### 5.7 Hashing, equality and canonical order

- **The hash is computed once, in `mk`, from the children's hashes:**
  `h = op; for each child c: h = ((h << 5) ^ (h >> 20) ^ H[c]) & 0x1FFFFFF`.
  - Leaves hash from their payload, exactly as in the `mk` sketch (§5.10):
    - NUM: `((a % 33554393) << 3) ^ ((b % 1048573) << 1) ^ (d % 65521)`, masked to 25 bits;
    - SYM: a char loop from 5381;
    - FLT: start from `h = FLT`; for `re`, then `im`: `m, x = math.frexp(v)`, then
      `h = ((h << 5) ^ (h >> 20) ^ (int(m * 1048576) & M25) ^ ((x & 255) << 17)) & M25`;
    - CON and WILD: `((op << 12) ^ (t[1] << 4) ^ t[-1]) & M25`.
  - Every intermediate value stays below 2^30, so on the device it is a small int and never
    allocates.
  - `hash()` is never used, so `H` is the same on the device and the desktop under any
    `PYTHONHASHSEED`. `H` is part of the platform contract: golden node dumps (§20.6) pin it.
- **Canonical order of ADD and MUL pairs:**
  1. Decorate each pair as `(H[t], t, coef)`.
  2. Sort with `list.sort()` and no `key=`. Native comparison of flat int tuples makes no Python
     calls.
  3. Run `tiefix` (L7, iterative). It reorders each run of equal `H` by an id-independent
     structural key:
     - first `(op, len(t))`, then the leaf payload (NUM `(a, b, d)`, SYM name, FLT `(re, im)`, CON
       `k`) or, for a composite, the tuple of its children's `H` values;
     - a remaining tie (every child hash equal) is broken by an explicit-stack walk of both nodes
       in parallel, preorder, which compares the first differing `(op, len)` or leaf payload.

     The order is a pure function of structure; `nodes.txt` (§20.6) pins it.

  The same expression therefore gets the same id whatever order it was built in [M].
- **Display order is separate.** The printer computes it (§12.3). No algorithm may give meaning to
  the internal pair order.
- **Flat-container rule (MUST):**
  - Anything that holds node ids is a flat tuple, a list of ints, or a dict keyed by int.
  - Sorts compare only flat tuples of ints and strings.
  - The layout boxes and series also store children as indices.
  - No native `==`, `hash`, `repr` or sort ever recurses through nested node data.

### 5.8 Symbol masks and `free_of`

`mk` ORs the children's masks into `V[id]`. A SYM gets bit `SYMI[name]`. There are 29 bits
(0..28); bit 29 means "overflow symbol", and 2^29 is still a small int.

- `free_of(e, x)` (L7) is `not (V[e] & V[x])`.
- If either mask has the overflow bit, it walks `e` with a stack instead. This is written inline,
  because an L7 function may not call another function. With 29 or fewer symbols per command the
  walk never runs.
- `free_of(e, x)` for a set of variables `x` is `not (V[e] & mask)`.

### 5.9 Memory lifecycle and regions

- **Per command.** `R.go` resets the table to `BASE` and clears `SYMN`/`SYMI` at the end of every
  command. The UI receives only text. **No id ever crosses a command boundary.**
- **Regions.** `mark = K.NN` is cheap, so any computation can be run in a region:
  - `keep(m, y)` (L4) releases every node `>= m` that is not reachable from `y` and compacts the
    survivors. `y` is `None`, an id, or a flat tuple of ids. It returns `y` with ids remapped.
  - `release(m)` (L7) drops everything `>= m`.
  - Because ids are topological and the newest node is always at the head of its bucket chain,
    both run in O(tail) with no dict deletions.
- **Who may hold ids across a region.** When a region starts, its owner is suspended (§10.3). Only
  ids `< m` can be held outside the region. The region's result comes back remapped. The
  following per-command caches hold ids:
  - `RULECACHE`: compiled rule patterns (§9.4);
  - `TCACHE`: template RPN, which holds no ids;
  - memo dicts.

  Rule sets are compiled at command start, before any region opens. A rule set compiled later is
  registered in `RULECACHE`; `keep` treats `RULECACHE` as extra roots and rewrites it in place.
  Memo dicts are local to one plain function call, and a call never spans a region boundary.
- **Caps.**
  - Hard cap: `NMAX = 768` live nodes per command (the preallocated slots, §5.1). Reaching it
    raises `CasError('expression too complex')`. Regions compact garbage, so the cap bounds live
    nodes, not nodes created.
  - Soft check: every 256 new nodes, `mk` calls `MEMFREE()` (native `gc.mem_free`, 0 frames
    [A]). Below `LOWMEM = 24 KB` it calls `gc.collect()`; if memory is still low, it raises
    `CasMemory`, which is handled like `MemoryError` (§16.10).

### 5.10 Code sketch: `mk` and `keep`

The [M] prototype appended to growing lists. This version, with preallocated slots and the length
`NN` (§5.1), compacts in place; T1.1 re-tests it with the same properties.

```python
def mk(t):                                                      #@L 7
    global NN
    op = t[0]
    v = 0
    if op >= COMP:
        h = op
        for j in range(1, len(t)):
            c = t[j]
            h = ((h << 5) ^ (h >> 20) ^ H[c]) & M25
            v |= V[c]
    elif op == NUM:
        h = (((t[1] % 33554393) << 3) ^ ((t[2] % 1048573) << 1)
             ^ (t[3] % 65521)) & M25
    elif op == SYM:
        h = 5381
        for ch in t[1]:
            h = ((h << 5) ^ (h >> 20) ^ ord(ch)) & M25
        bit = SYMI.get(t[1])
        if bit is None:
            bit = len(SYMN)
            SYMN.append(t[1])
            SYMI[t[1]] = bit
        v = (1 << bit) if bit < 29 else OVF
    else:                                    # FLT (frexp-based, omitted), CON, WILD
        h = ((op << 12) ^ (t[1] << 4) ^ t[-1]) & M25
    b = h & (NB - 1)
    i = B[b]
    while i:
        if H[i] == h and N[i] == t:          # flat tuple compare: ints and str only
            return i
        i = NX[i]
    i = NN
    if i >= NMAX:
        raise CasError(M_COMPLEX)            # preallocated message text
    if not i & 255 and MEMFREE() < LOWMEM:   # native call, 0 frames
        gc.collect()                         # native
        if MEMFREE() < LOWMEM:
            raise CasMemory()
    N[i] = t
    H[i] = h
    NX[i] = B[b]
    V[i] = v
    B[b] = i
    NN = i + 1
    return i


def keep(m, y):                                                 #@L 4
    # Release nodes >= m not reachable from y (None, id or flat tuple of ids);
    # survivors move down in id order, in place, with remapped children.
    global NN
    n = NN
    if y is None:
        release(m)
        return None
    if n == m:
        return y
    roots = y if type(y) is tuple else (y,)
    live = bytearray(n - m)
    st = []
    for r in roots:
        if r >= m:
            st.append(r)
    # (also push the RULECACHE ids >= m here: an inline loop, usually empty)
    while st:
        i = st.pop()
        if live[i - m]:
            continue
        live[i - m] = 1
        t = N[i]
        if t[0] >= COMP:
            for j in range(1, len(t)):
                if t[j] >= m:
                    st.append(t[j])
    for i in range(n - 1, m - 1, -1):        # the newest id is always its chain's head
        B[H[i] & (NB - 1)] = NX[i]
    rm = [0] * (n - m)
    k = m                                    # next free slot; k <= i, so nothing unread
    for i in range(m, n):                    # is overwritten
        if live[i - m]:
            t = N[i]
            if t[0] >= COMP:                 # children are older: already remapped
                u = [t[0]]
                for j in range(1, len(t)):
                    c = t[j]
                    u.append(rm[c - m] if c >= m else c)
                t = tuple(u)
            h = H[i]
            N[k] = t
            H[k] = h
            V[k] = V[i]
            NX[k] = B[h & (NB - 1)]
            B[h & (NB - 1)] = k
            rm[i - m] = k
            k += 1
    for i in range(k, n):                    # drop dead tuples so the GC can reclaim them
        N[i] = None
    NN = k
    # (rewrite RULECACHE ids >= m through rm here: an inline loop, usually empty)
    if type(y) is tuple:
        out = []
        for r in y:
            out.append(rm[r - m] if r >= m else r)
        return tuple(out)
    return rm[y - m] if y >= m else y
```

### 5.11 Memory per node [E]

| part | bytes |
|---|---|
| tuple of 2..6 items (16-byte GC blocks: 16 or 32), per live node | 32 (typical) |
| `N`, `H`, `NX`, `V` list slots (small ints are immediate), preallocated for all `NMAX` slots at boot | 16 per slot, 12 KB in total |
| **per live node** | **about 32**, plus big-int payloads |

The prototype's commands peaked at 13-31 live nodes for diff plus simplify [M], and a second
derivative of a large product needed 45 [M]. Integration searches should stay in the low hundreds,
because failed attempts are released [E]. PRBMEM measures the real per-node cost (§18.7).

---

## 6. Number tower

### 6.1 Gaussian rationals (the only exact numbers)

`(NUM, a, b, d)` stands for (a + b·i)/d. All arithmetic is integer-only: `/` on ints is banned in
the exact modules. The kernels are L7 leaves on tuples. `num(a, b, d)` (L6) returns an id.

```python
def nmul(x, y):                                                 #@L 7
    # x, y: (NUM, a, b, d) tuples -> normalized product tuple; no calls
    if x[2] == 0 and y[2] == 0:               # real fast path
        a = x[1] * y[1]
        b = 0
    else:
        a = x[1] * y[1] - x[2] * y[2]
        b = x[1] * y[2] + x[2] * y[1]
    d = x[3] * y[3]
    g = a if a >= 0 else -a                   # inline gcd(a, b, d)
    h = b if b >= 0 else -b
    while h:
        g, h = h, g % h
    h = d
    while h:
        g, h = h, g % h
    if g > 1:
        a //= g
        b //= g
        d //= g
    return (NUM, a, b, d)
```

- The kernels are `nnorm`, `nadd`, `nmul`, `ninv` (`1/((a+bi)/d) = d(a-bi)/(a²+b²)`; zero raises
  `Undefined`), `npowi` (square and multiply; negative n inverts first), `nneg`, `nsign` (real
  only) and `ncmp` (real only).
- `i^2 = -1`, `1/(1+i) = (1-i)/2` and `(2i)^3 = -8i` all fold inside the constructors [M].
- "Real" means `b == 0`. Ordering and `nsign` raise `Undefined` on non-real numbers.
- Big integers are Python ints. Printing caps a result at 4,000 characters; a longer result is
  shown as the message `Done`, as FlowCE does.
- **Size guards** (big-int work is otherwise unbounded and cannot be cancelled):
  - `npowi` estimates the result size as `|n| × 4 × len('%x' % base)` bits (hex conversion is
    linear; `int.bit_length` is absent) and raises `CasError('number too large')` above
    `MAXBITS = 65,536` bits. For a real base, a power too large to fold stays
    **written as a power** (CalcPlex's giant numbers), exact and immediate, so `2^(10^6)`,
    `3^(2^20)` and `7^7^7` are answers, not errors.
  - **The fold rule:** first try the original whole-base `npowi` rule. Thus `4^9000`,
    `9^10000`, and `(2^8193)^2` retain their previous exact integer values. Ordinary products
    of integers stay numbers, even if the resulting integer is itself a giant power.
  - Only a real power beyond that limit goes to the radical table prime by prime (§6.2).
    Each prime power folds when its weight `4·|n|·hexlen(q)` is at most `MAXBITS`;
    otherwise its exponent stays whole. A coefficient gives its factors of those primes to
    the exponent, so `2^100000*2 = 2^100001`. Equal exponents share one base. If the folding
    weights above `MAXBITS/16` total more than `2·MAXBITS`, those primes also stay whole.
    A base above 4,000 bits is factored only below 256; the remainder stays one cofactor.
  - **Conservative limits:** non-real numeric powers beyond the original `npowi` limit
    raise `number too large`. Distinct giant-power terms are not independent algebraic
    variables: treating them as such gave false nonzero tests and roots. Until bounded
    collection is implemented, sums with more than one surviving giant-power term, or a
    large ordinary coefficient (over 4,096 estimated bits) alongside one, raise that same
    error. Identical terms can cancel or combine, and a single giant term can coexist with
    small constants and ordinary symbols. Coefficient normalization that crosses back into
    the fold range also raises instead of leaving an invalid node. The zero test never
    claims exact nonzero merely because a polynomial in giant-power kernels is nonempty.
  - The original arithmetic representation is preferred over equivalence of independently
    built giant and folded forms: `2^10000*2^10000` remains an integer, while `2^20000`
    remains a power. Both denote the same exact value; mixing their additive forms beyond
    the supported bounds fails safely. No rounded result is substituted.
  - Other hard ceilings remain: oversized exponents, float overflow, and expansion of
    polynomial coefficients beyond `MAXBITS` produce `number too large`.
  - A power kept whole has no float value: `nprog` raises `Undefined` for it (§6.6), so there is
    no decimal line (§12.6), `approx` keeps it exact, and the numeric probe skips it. `simplify`
    therefore keeps an expression holding one as built (its candidates cannot be verified, §8.7);
    `expand`, `normal`, `together`, `factor` treat each such power as one kernel.
  - **Where the code lives.** Giant powers are rare, so their rules are in `nodeb.py` (alias
    `KB`), an aux pack on the calculator that loads the first time a command meets one; `node`
    keeps only cheap tests in its hot paths. `mul_` calls `KB.hpow` for a number to an integer
    power when `16·|n|·len('%x%x%x' % (a, b, d))` exceeds `MAXBITS` (a bound on every case the
    rule above can send to the radical table or keep whole), and `KB.hfold` at the end of the
    product when `20·hexlen(k) + Σ 4·|n|·hexlen(q)` over the radical table exceeds `MAXBITS` (a
    bound on the weights once the coefficient's primes join them, so below it the rule always
    folds everything, as the plain loop does). Every other hook (`add_`, `absn`, `fn_` for `ln`,
    `mul_`'s `(Π B^X)^e`, and `huge` in `nprog`, `normal`, `kinds`, `factor`) first reads
    `K.HUGE`, which is 1 once the command has kept a power whole; a power kept whole exists only
    after that. So `2^1000`, radicals and every command without a giant power never load the
    pack.
  - `nodeb` cannot import `node` (`node` imports it, and the import graph is acyclic, §4.2): its
    `K = None  #@lazy node` is bound by node's module body, `KB.K = __import__(__name__)`, and
    the pack compiler turns that into plain references to node's pack (`build/packs.py`). `add_`
    is level 6 and the leaves it would need (`mk`, `ifac`, `tiefix`, `nadd`) are level 7, so its
    rule, `KB.hsum` (level 7), calls nothing: it puts each call it needs on a list that `add_`
    carries out, and is run again with the answers so far until it is done.
  - The printer never calls `str()` on an integer whose estimated decimal length
    (`1.21 × hex length`) is over 4,000 digits, because `str()` of a big int is quadratic and has
    no cancel poll. The record becomes `Done` at once.
- **Fast paths:** integers (`b == 0`, `d == 1`) skip the gcd. Equal denominators skip the
  cross-multiplication.

### 6.2 Radicals

- **Canonical form:** the MUL pair `(r, p/s)` with `r >= 2` an s-th-power-free integer and
  `0 < p/s < 1`. The coefficient carries everything rational: `3√2 = MUL(3, 2, 1/2)`.
- **Normalization in `mul_`,** for a real numeric base `q` under a rational exponent `n + p/s`:
  1. Prime by prime: `(u/v)^x` puts `f·x` for every prime `r^f` of `u`, and `-f·x` for every
     prime of `v`, into the radical table; the sign `(-1)^n` and the odd-root rule (step 5) go to
     the coefficient. No power is computed here, so `(1/3)^(1/100000)` costs nothing.
  2. At the end of the product each prime's integer part folds into the coefficient (unless it
     is kept whole, §6.1) and the fractional part in (0, 1) stays. This is the rationalization
     `(u/v)^(p/s) = (u·v^(s-1))^(p/s) / v`: `1/√2 = √2/2`, `(2/3)^(1/2) = √6/3`.
  3. Run `rootsplit(N, s)` (L7): trial division up to `min(10^4, N^(1/3))`, then a perfect s-th
     power test on the cofactor with an integer Newton root. It returns `(outside, inside)`. A
     cofactor with a large prime factor stays partly reduced; that is documented and still correct.
  4. Merge pairs with equal exponents: `√2·√3 = √6`, then split again. Pairs with equal bases add
     their exponents, through the general rule: `2^(1/2)·2^(1/3) = 2^(5/6)`.
  5. **Negative radicands.**
     - With an odd `s`, the result is real and negative (TI convention): `(-8)^(1/3) = -2`.
     - With `s = 2`: `√(-r) = i·√r`.
     - With an even `s >= 4`, the pair is kept as typed.
  6. Non-real Gaussian bases with fractional exponents are kept as pairs.
- **Only `simplify` does more:**
  - `√(p+q√r)` is denested when `p² - q²r` is a rational square (alg §2.2).
  - Binomial denominators `1/(a+b√r)` are rationalized.
  - Neither is done in the constructors, because both cause swell.

### 6.3 Constants, infinity, floats

- **`π` and `e`** are `CON` leaves with `V = 0`. `e^u` is the pair `(E, u)`. `mul_` applies
  `e^(ln u) = u` and `e^(k·ln u) = u^k` for integer k.
- **`∞` and `undef`.** The constructors fold the extended reals with a small table, so that
  substituting `oo` gives a value. Here `c` is a nonzero real number, `k` a real constant (V = 0)
  whose sign the constructor can see (a real NUM, or a positive constant as in `absn`, §6.4):

  | where | rule |
  |---|---|
  | `add_` | `∞ + finite = ∞`, `∞ - ∞ = undef` |
  | `mul_` | `c·∞` keeps the sign of `c`; `0·∞ = undef`; `∞·∞ = ∞`; `∞^p = ∞` (p > 0), `= 0` (p < 0); `1/∞ = 0` |
  | `mul_`, base `k` under exponent `±∞` | `k^∞ = ∞` when k > 1, `0` when 0 <= k < 1; `k^(-∞)` the reverse; `1^∞` and k <= -1 give `undef`. `e^∞ = ∞`, `e^(-∞) = 0`. |
  | `fn_` | `ln ∞ = ∞`, `ln 0` raises `Undefined`; `atan(±∞) = ±π/2`; `tanh(±∞) = ±1`; `abs(±∞) = ∞`; `sign(±∞) = ±1`; `sin`, `cos`, `tan` of `±∞` give `undef`; `floor(±∞) = ±∞` |
  | everywhere | `undef` absorbs everything |

  Limits and sums do their real work in their own sign domain (§11); this table only stops
  `1/oo` from staying unevaluated.
- **Floats.**
  - A decimal typed by the user (`0.5`, `2.5E-3`) is a FLT (D8). FLT arithmetic is native.
  - A FLT meeting a NUM produces a FLT: contagion inside `add_`/`mul_`.
  - If the input contains any FLT (`ctx.approx`), every command runs **exactly** (FlowCE runs
    `exact()` before `solve`): `g_eval` passes each FLT through `exact()`, which turns it into the
    rational of its 15-significant-digit decimal text (`0.25` -> `1/4`). The runner then passes the
    final result through `approx()`, which evaluates every constant subexpression numerically
    (giac `has_num_coeff`). So `factor(x^2-0.25)` gives `(x-0.5)*(x+0.5)`.
  - Exact values never meet floats elsewhere. The only place floats are compared with exact values
    is `nev` (§6.6).

### 6.4 Special values (in `fn_`)

- **The argument test:** the argument is `0`, `PI`, or `MUL(q, PI, 1)` with q a real rational. In
  degree mode the builder has already turned degrees into a multiple of π (§6.5).
- **Coverage:**
  - `sin`, `cos`, `tan`, `sec`, `csc` and `cot` at kπ/12 for all k: 24 slots, using symmetry.
  - Multiples of π/5, π/8 and π/10 (the values `(√5±1)/4`, `√(2±√2)/2`, ...).
  - The inverse functions over the same values: the inverse table is keyed by the structural hash
    `H` of the value, which is stable across commands, then confirmed with an id compare.
- **Storage:** tables of small int tuples. Each value is a list of terms `(p, q, r)` meaning
  `Σ (p/q)·√r`. Nested radicals (π/8 multiples) are a second small table.
  - `fn_` builds results directly: radical pairs with `mk`, and sums with `add_`.
  - It never calls `mul_`, which keeps `fn_` at L5 (§17).
  - The `sec`, `csc` and `cot` tables are precomputed in rationalized form. `tan(π/2)` raises
    `Undefined`.
- **Sign normalization (D15).** One canonical sign rule serves odd functions, even functions and
  `abs`, so that `sin(1-x)` and `-sin(x-1)` are the same node:
  - `negfirst(u)` (L7, no calls) says whether `-u` is the canonical representative: for an ADD,
    the coefficient of its first pair (canonical order, §5.7) is negative; for a MUL, its
    coefficient is negative; for a number, it is negative. It depends only on structure.
  - `neg_(u)` (L6) negates without `add_`: it negates the constant and every pair coefficient of an
    ADD (the pair order does not depend on coefficients), or the coefficient of a MUL, and calls
    `mk`.
  - Odd functions (`sin tan csc cot asin atan sinh tanh`): if `negfirst(u)`, `f(u) = -f(-u)`.
    Even functions (`cos sec cosh`): if `negfirst(u)`, `f(u) = f(-u)`. So `sin(1-x)` becomes
    `-sin(x-1)` (as giac does), and `cos(1-x)` becomes `cos(x-1)`.
- **`absn(u)` (L6)** builds every canonical `abs` node; `fn_(ABS, u)` and `mul_` rule 7 (§8.2)
  both use it:
  - a number gives its modulus (`abs(3+4i) = 5`; a non-square modulus becomes a radical);
  - `±∞` gives `∞`;
  - a provably positive constant (V = 0: positive numbers, `π`, `e`, positive radicals, and sums
    and products of these, checked by an inline stack walk) gives `u`; a provably negative one
    gives `neg_(u)`;
  - otherwise the numeric content comes out: `abs(c·w) = |c|·abs(w)` for a real coefficient `c`,
    and the rational content of a sum likewise (`abs(2x+2) = 2·abs(x+1)`);
  - then the sign rule: `abs(u) = abs(-u)` when `negfirst(u)`, so `abs(-x-1) = abs(x+1)`;
  - `abs(w^(2k)) = w^(2k)`.
- **Other `fn_` rules,** in order:
  - inverse cancellation: `sin(asin u) = u`, `tan(atan u) = u`, and so on;
  - `ln(1) = 0`, `ln(e) = 1`, `ln(e^u) = u` (u real, §8.3);
  - `ln(b^k) = k·ln b` for an integer b written as a perfect power with the smallest base
    (`ln 8 = 3 ln 2`, `ln 100 = 2 ln 10`);
  - `ln(p/q) = ln p - ln q`;
  - `ln(-n) = ln n + iπ`;
  - the ∞ rules of §6.3;
  - `sign(number)`, `floor(number)`, `ceil(number)`, and `n!` for an integer n <= 1000.

### 6.5 Degree mode (a boundary conversion)

The core is radian-only. The conversion is done with the constructors in both directions, never by
pattern matching, so it survives `expand`, `normal_args` and F4.

- **Builder.** In degree mode, `g_eval` builds a trig argument `u` as `u·π/180`. If `u` is a sum,
  the factor is distributed term by term (`add_` of one `mul_` per term), so `sin(x+30)` is built
  as `sin(π·x/180 + π/6)`: the same node that `expand` produces. Inverse-trig results are
  multiplied by `180/π`.
- **Printer** (§12.4), in degree mode only:
  - a trig node `f(v)` prints its argument as `v·180/π`, computed with the constructors (term by
    term when `v` is a sum). `sin(π·x/180 + π/6)` prints `sin(x+30)`;
  - before printing, `PR.record` substitutes each inverse-trig node `F(u)` by
    `(π/180)·CALL(SYM('asin'), u)` (the CALL is an inert print-only atom that prints `asin(u)`),
    built with the constructors. `180·asin(u)/π + 30` then prints `asin(u)+30`.

  Both maps are exact inverses of the builder's (each term maps to one term, and `mul_` cancels
  the π factors), so `parse(print(e)) == e` holds in degree mode too (§12.5).
- Derivatives pick up the `π/180` factor through the chain rule with no special case. In degree
  mode `d/dx sin(x)` prints `π*cos(x)/180`, as on a TI-89.
- Solve windows are in the user's unit: `[0, 2π)` in radian mode, `[0, 360)` in degree mode
  (§11.2).

### 6.6 Numeric evaluation `nev` (CVALG)

The decimal line, the numeric zero test, checks, quadrature and every numeric fallback all use
`nev`.

- **Compile.** `nprog(root, xs)` (L4) turns the postorder list into a flat program. `xs` is the
  tuple of variable ids, which become slots. Each instruction is
  a flat tuple of indices into a value list:
  - `(P_ADD, c, i1, k1, ...)`
  - `(P_MUL, k, i1, e1, s1, ...)`
  - `(P_POW, ib, ie)`
  - `(P_FN, op, i)`
  - `(P_VAR, slot)`
  - `(P_CONST, value)`
- **Run.** `nrun(prog, xs)` (L4) is one loop.
  - Values are floats. An operation leaves the reals (`math.log` of a negative, `sqrt` of a
    negative, a non-integer power of a negative) only by switching to Python `complex`. The
    complex helpers `cexp`, `clog`, `csin`, `ccos` and `cpow` (L5) are built from `math`; `cmath`
    is absent.
  - Errors (`ZeroDivisionError`, `OverflowError`, a `ValueError` that has no complex meaning) are
    caught by `nev` and raised as `Undefined`. `nprog` raises `Undefined` for a power kept
    whole (§6.1), which is beyond the float range either way.
  - **Every value is checked for nan and inf** (`v - v != 0`), whatever PROBE6 shows: float
    overflow gives inf without raising, and some MicroPython builds return nan from `asin(2)` or
    `log(0)` instead of raising. A nan from a native function first retries the complex helper (the
    same path as a `ValueError`); any remaining nan or inf raises `Undefined`.
  - `nrun` sets `LEFTREAL[0] = 1` when a value first becomes complex while every input was real.
    The numeric zero probe and simplify verification use it to skip points where the input is not
    real (§8.3).
  - `PR.record` computes the decimal line inside its own `try`: `Undefined`, or any other
    `Exception` (an `OverflowError` from a huge value, say), means "no decimal line" and never
    escapes (§12.6).
- **Cost.** There is no `eval`/`exec` compile. That saves code and the transient compile heap.
  Cost is about 30 nodes × about 10 µs per point [E].
- **Optimization path (only if profiling shows a need):** generate flat straight-line source (one
  statement per node) and `exec` it (depth-first proposal, §5.3).

```python
def nrun(prog, xs):                                             #@L 4
    r = [0.0] * len(prog)
    for i in range(len(prog)):
        ins = prog[i]
        op = ins[0]
        if op == P_CONST:
            v = ins[1]
        elif op == P_VAR:
            v = xs[ins[1]]
        elif op == P_ADD:                    # (P_ADD, c, i1, k1, i2, k2, ...)
            v = ins[1]
            j = 2
            while j < len(ins):
                v += ins[j + 1] * r[ins[j]]
                j += 2
        elif op == P_MUL:                    # (P_MUL, k, i1, e1, s1, ...): e int or float;
            v = ins[1]                       # s = (-1)^p when e = p/q with q odd, else 0
            j = 2
            while j < len(ins):
                b = r[ins[j]]
                e = ins[j + 1]
                if type(e) is int or (type(b) is float and b >= 0.0):
                    v *= b ** e              # stays real (0.0 ** -1 raises ZeroDivisionError)
                elif type(b) is float and ins[j + 2]:
                    v *= ins[j + 2] * (-b) ** e     # TI real odd root: (-8)^(1/3) = -2
                else:
                    v *= cpow(b, e)          # L5 helper: complex principal value
                    LEFTREAL[0] = 1          # (only when every input was real; detail omitted)
                j += 3
        elif op == P_POW:                    # (P_POW, ib, ie): a symbolic exponent
            b = r[ins[1]]
            e = r[ins[2]]
            if type(b) is float and type(e) is float and b > 0.0:
                v = b ** e
            else:
                v = cpow(b, e)
        else:                                # P_FN
            a = r[ins[2]]
            v = NAN
            if type(a) is float:
                try:
                    v = FNUM[ins[1]](a)      #@calls 7  natives such as math.sin
                except ValueError:
                    pass
                if v != v:                   # domain error: ValueError, or nan on the device
                    a = complex(a, 0.0)
            if v != v:
                v = FCPX[ins[1]](a)          #@calls 5  complex helpers
        if v - v != 0:                       # inf or nan: overflow does not raise
            raise Undefined()
        r[i] = v
    return r[-1]
```

`nprog` compiles numeric exponents as follows:

- An integer exponent becomes an int.
- Any other rational `p/q` becomes a float, with a sign flag `s = (-1)^p` when `q` is odd. This
  keeps `nev` consistent with the exact real-odd-root convention (§6.2).
- A non-numeric exponent becomes a separate `P_POW` instruction, whose result enters the product
  with exponent 1.

---

## 7. Parser and input preprocessing

### 7.1 Pipeline

The history keeps the text as typed (FlowCE). All rewrites run at evaluation time, and every stage
is a loop: no recursion and no `eval`.

| # | stage | function | module | level | what it does |
|---|---|---|---|---|---|
| 1 | autoclose | inline in `R.go` | CVRUN | L1 | Appends the missing `)` and `]` (at most 64 open). FlowCE `console_autoclose`. |
| 2 | Ans | inline in `R.go` | CVRUN | L1 | Replaces each `ans()` with `(` + `ANS` + `)`, at most 8 times. `ANS` is the last answer that was not a message (§7.11). With no answer yet, the message is `no answer yet`. |
| 3 | lex | `lex(s)` | CVPARSE | L6 | Text to tokens (§7.2); sets `F_CALL` on whole names |
| 4 | paper notation | `ti_rewrite(toks)` | CVPARSE | L6 | Port of FlowCE `ti_rewrite` (cat §5.5) |
| 5 | name cut + implicit `*` | `ti_implicit(toks)` | CVPARSE | L6 | Port of FlowCE `ti_implicit_mult` with `im_cut` (cat §5.6) |
| 6 | context | `expand_names(toks)` | CVPARSE | L5 | Renames the sum index `i`; expands stored variables, user functions and macros at token level (§7.6) |
| 7 | shunting-yard | `rpn(toks)` | CVPARSE | L7 | Tokens to an RPN list (§7.7) |
| 8 | consumers | `g_eval(code, ctx)` / `inst(code, env)` / `D.measure(code)` / `untok(toks)` | | L2 / L4 / L3 / tests | CAS builder for user input / builder for templates and patterns / 2D layout / golden tests |

`P.tokens(text, ctxt)` (L3) chains stages 3-6; with `ctxt = 0` it skips stage 6, so stored
variables, user functions and macros are not expanded. `R.start` (L2) calls it, then `rpn`.

**Which paths run which stages:**

| path | stages | why |
|---|---|---|
| user input | 1-7, then `g_eval` | |
| F4 forms, the round-trip test (§12.5) | 3-5 and 7, then `g_eval` in inert mode (§7.8) | old answers must not change when a variable is stored later |
| rule strings and templates (`tcode`) | 3 and 7 | rule strings use explicit `*` (rule lint, §20.3) |
| 2D layout of an answer | 3 and 7 | printer text has explicit `*` |

Calls still parse on the short paths, because `lex` sets `F_CALL` itself (§7.2).

### 7.2 Tokens

A token is the flat tuple `(kind, value, start, end, flags)`. `start` and `end` are source offsets;
the layout engine uses them to map a caret (§13.8).

| kind | value |
|---|---|
| `K_NUM` | `(p, q)` for an exact decimal-free number, or a float for a decimal |
| `K_NAME` | the name |
| `K_OP` | `+ - * / ^ = != < <= > >= =>` |
| `K_LP`, `K_RP`, `K_LB`, `K_RB`, `K_COMMA` | brackets and separators |
| `K_POST` | postfix `!` or `'` |

- **`flags`:** bit `F_IMPL` marks a `*` inserted by stage 5. The layout draws it as a 1 px gap.
  Bit `F_CALL` marks a name whose `(` opens a call:
  - `lex` sets it on a whole name directly followed by `(` when `classify` gives FUNCTION or
    USERFN, or when the name is a call letter (§7.5). So `tcode` and the 2D layout, which skip
    stage 5, still parse `sin(x)` as a call.
  - `ti_implicit` sets it on the pieces it cuts (`xsin(x)` -> `x*sin(x)`) and clears it where it
    inserts `*` before `(`.
- **Numbers:** `[0-9]+(\.[0-9]*)?(E[+-]?[0-9]+)?` or `\.[0-9]+...`. **Only uppercase `E`**, which
  the EE key types, starts an exponent (D14), and only if a digit follows: `2E10` and `2E-3` are
  floats, while `2e` is `2*e` and `2e-1` is `2*e-1`, because `e` is the constant key (2nd ÷). This is an
  intentional deviation from FlowCE: the ported golden case `2.5e-3x` is changed to `2.5E-3x`, and
  `2.5e-3x` gets its own golden line (`2.5*e-3*x`). Integers are exact. Anything with `.` or an
  exponent is a float (D8).
- **Names:** `[A-Za-z][A-Za-z0-9]*`, plus `'` primes directly after `y` (`y'`, `y''`). `π` (from
  the UI glyph) lexes as `pi`, and `θ` as `theta`. Underscore names are reserved for internal fresh
  symbols, and user input rejects them.
- **Relations:** `!=` is one token, so `n!=1` means `n != 1`; a factorial equation is typed
  `(n!)=1`.

### 7.3 The classifier

`classify(name)` (L7) returns one of FlowCE's five classes:

| class | members |
|---|---|
| FUNCTION | function names (`sin`, ..., `ln`, `log`, `exp`, `sqrt`, `surd`, `abs`, ...), `O` (the series remainder, so `O(x^6)` in an answer is not cut to `O*(x^6)`), command names, aliases, macros, `purge` |
| VALUE | `pi e i oo inf infinity undef theta true false`, the Riemann methods `left right mid trap` (so `mid` is not cut into `m*i*d`), and the stored variable names (`R.VARS`) |
| USERFN | the defined function names (`R.FUNCS`) |
| KEYWORD | none in v1 (no programming) |
| UNKNOWN | anything else |

The tables are module globals of CVRUN, read directly with no call. Stages 4 and 5 depend on the
class: `2pir` becomes `2*pi*r` only because `pi` is VALUE.

### 7.4 Paper notation (`ti_rewrite`)

This is an exact port of the rules in cat §5.5. In summary:

- `f(x)=...` becomes a definition.
- `xsinx` becomes `x*sin(x)`.
- `sin2x` becomes `sin(2x)`.
- `sin^2x` and `sin^2(x)` become `sin(x)^2`.
- `sin^-1(x)` becomes `asin(x)`.
- `sin x+1` becomes `sin(x)+1`.

FlowCE's only recursion, `ti_rewrite` on the argument of `sin^2(...)`, becomes a splice: the
rewritten argument tokens are pushed onto an explicit work queue and processed by the same loop. A
paren counter finds the argument's end.

### 7.5 Name cutting and implicit multiplication (`ti_implicit`)

This is an exact port of cat §5.6.

- **`im_cut`:** a fewest-pieces dynamic program over at most 32 letters. Greek names stay whole.
  There are at most 3 pieces, and ties go to the longest first piece.
- **The `lend`/`lcall` state machine:** the call letters are `f`, `g` and `h`, plus `y`, `y'`,
  `y''` and `u` on a line containing `desolve`. So `y'(0)=0` is the condition `CALL(y', 0) = 0`,
  not `y'*(0)`.
- **`*` is the only thing inserted,** so the pass is idempotent.
- **MicroCAS addition (D9):** the 1-letter alias `d` is FUNCTION only when it is not a stored
  variable and its argument list has a top-level comma. So `d(x^2,x)` is a derivative and `d(x+1)`
  is `d*(x+1)`.

### 7.6 Context expansion (`expand_names`, L5)

All of these work on the token list with a work queue, in one loop. The loop is capped at 64
expansions, and nested definitions at depth 16 (it reports "definition too deeply nested").

1. **Sum index.** In `sum(` and `riemann(` calls whose index argument is the bare letter `i`, every
   standalone `i` inside the call becomes the first of `k`, `j`, `m` that the call does not use
   (FlowCE `sum_index_i`).
2. **Stored variables.** A VALUE name stored in `R.VARS` is replaced by `(` + `lex(stored text)` +
   `)`. Stored text is canonical printer output, which already has explicit `*`, so it needs only
   `lex`. Expansion repeats until no stored names remain or the cap is hit.
3. **User functions.** `f(a1,...)`, with `f` in `R.FUNCS = {name: (params, body text)}`, is
   replaced by `(` + the body tokens with each parameter token replaced by `(ai)` + `)`. The
   argument split uses a depth counter.
4. **Macros.** Registry macros such as `polararea(r,t,a,b)` -> `integrate((#1)^2/2,#2,#3,#4)` are
   expanded the same way (§15.1).

### 7.7 Operators and the shunting-yard (`rpn`, L7)

Precedence, from lowest to highest:

| level | operators | notes |
|---|---|---|
| 1 | `=>` | store; right-associative. The runner handles a top-level `=>` before `rpn` (§7.9). |
| 2 | `,` | separator. A comma outside every bracket makes the whole line a list: `x=1,x=2` is the list of two equations, so printed solutions re-parse (§12.1). |
| 3 | `= != < <= > >=` | relations |
| 4 | binary `+ -` | |
| 5 | `*`, `/`, implicit `*` | |
| 6 | prefix `-` | so TI's `-x^2` is `-(x^2)` |
| 7 | `^` | right-associative |
| 8 | postfix `!` and `'` | |
| 9 | call | |

| input | RPN |
|---|---|
| `-x^2` | `x 2 ^ neg` |
| `2^-3` | `2 3 neg ^` |
| `1/2x` | `1 2 / x *` (TI: ½·x) |
| `a^b^c` | `a b c ^ ^` |
| `diff(sin(x)^2,x,2)` | `x sin/1 2 ^ x 2 diff/3` |

**RPN items** are flat tuples ending in the token index `ti`:

| item | meaning |
|---|---|
| `('n', value, ti)` | number |
| `('s', name, ti)` | name |
| `('w', slot, ti)` | wildcard (pattern mode) |
| `('o', op, ti)` | operator; `op` is `'neg'` for prefix minus |
| `('F', name, nargs, ti)` | call |
| `('L', n, ti)` | list or tuple; `ti = -1` is a bare top-level list, drawn without brackets |
| `('P', ti)` | group: the CAS builders ignore it; the layout uses it for hidden parentheses |

**Code sketch** (tested on 25 cases [M], including the error cases `f(a,,b)`, `(a]`, `()` and
`x+`, before the review added the top-level list; T1.3 re-tests it):

```python
def rpn(toks):                                                  #@L 7
    out = []
    ops = []
    argc = []
    top = 1                                  # items of a bare top-level list
    val = False
    for i in range(len(toks)):
        tk = toks[i]
        k = tk[0]
        if k == K_NUM or k == K_NAME and not tk[4] & F_CALL:
            if val:
                raise CasError('missing operator', tk[2])
            out.append(('n' if k == K_NUM else 's', tk[1], i))
            val = True
        elif k == K_NAME:
            ops.append(('f', tk[1], i))
            val = False
        elif k == K_LP or k == K_LB:
            if len(argc) >= MAXNEST:
                raise CasError('too deeply nested', tk[2])
            ops.append(('(', k, i))
            argc.append(1)
            val = False
        elif k == K_COMMA or k == K_RP or k == K_RB:
            while ops and ops[-1][0] == 'o':
                out.append(ops.pop())
            if k == K_COMMA and not ops:     # top-level comma: the line is a list
                if not val:
                    raise CasError('empty argument', tk[2])
                top += 1
                val = False
                continue
            if not ops or ops[-1][0] != '(':
                raise CasError('unbalanced', tk[2])
            if k == K_COMMA:
                if not val:
                    raise CasError('empty argument', tk[2])
                argc[-1] += 1
                val = False
                continue
            o = ops.pop()
            n = argc.pop()
            if (o[1] == K_LB) != (k == K_RB):
                raise CasError('mismatched bracket', tk[2])
            if not val:                                      # () [] f()
                if n > 1:
                    raise CasError('empty argument', tk[2])
                n = 0
            if o[1] == K_LB:
                out.append(('L', n, i))
            elif ops and ops[-1][0] == 'f':
                out.append(('F', ops.pop()[1], n, i))
            elif n == 1:
                out.append(('P', i))
            elif n > 1:
                out.append(('L', n, i))
            else:
                raise CasError('empty ()', tk[2])
            val = True
        elif k == K_POST:
            if not val:
                raise CasError('missing operand', tk[2])
            out.append(('o', tk[1], i))
        else:
            o = tk[1]
            if not val:
                if o == '-':
                    ops.append(('o', 'neg', i))
                elif o != '+':
                    raise CasError('missing operand', tk[2])
                continue
            p = PREC[o]
            while ops and ops[-1][0] == 'o':
                q = PREC[ops[-1][1]]
                if q > p or (q == p and o != '^' and o != '=>'):
                    out.append(ops.pop())
                else:
                    break
            ops.append(('o', o, i))
            val = False
    while ops:
        o = ops.pop()
        if o[0] != 'o':
            raise CasError('missing )')
        out.append(o)
    if not val and toks:
        raise CasError('missing operand')
    if top > 1:
        out.append(('L', top, -1))           # bare top-level list (solutions)
    return out
```

### 7.8 Builders

**`inst(code, env)` (L4, CVPARSE).** Builds templates and patterns. One loop over the RPN with a
value stack of ids. It calls only constructors: `mul_`, `fn_` and `rel_` (L5), and `add_` (L6).

| mode | what wildcards become |
|---|---|
| pattern, `env=None` | uppercase rule letters become `WILD` leaves (§9.2) |
| template, `env` a slot list | a wildcard becomes its bound id |

- `x` is bound to the focus variable in both modes.
- Template strings are compiled once per command, through `tcode(s)` (L5): `lex` then `rpn`,
  cached in `TCACHE`. There is no implicit `*` on this path, so rule strings write every `*`
  (rule lint, §20.3).
- `inst` has no angle mode and runs no commands. It is never used to re-parse answer text; the
  round-trip test uses `g_eval` in inert mode.

**`g_eval(code, ctx)` (L2 generator, CVPARSE).** Evaluates user input.

- **Operators:**
  - `+` goes to `add_`. `-` is `add_([a, add_([b], -1)])`: two sequential calls, not nested.
  - `*`, `/` and `^` go to `mul_`. `neg` is `add_([a], -1)`.
  - `!` is `fn_(FACT)`. `'` is allowed only on `y` (`y'`) and is folded into the name by the lexer.
  - A relation goes to `rel_`, which may fold it to `TRUE` or `FALSE` (§8.2).
  - An arithmetic operator with a `TRUE`/`FALSE`, `DNE`, `DIVG` or `HOLD` operand raises
    `CasError('invalid use of a result')`; relations, lists and calls accept them.
- **Names:**
  - `pi`, `e`, `i`, `oo`, `undef`, `true`, `false` become their constants.
  - `theta` becomes the symbol θ. Anything else becomes a symbol (including `left`, `right`,
    `mid`, `trap`, which `riemann` reads by name).
- **Calls:**
  - Elementary functions go to `fn_`. The builder rewrites `log(u)` to `ln(u)/LN10`, `log(u,b)`
    to `ln(u)/ln(b)` (so `log(8,2) = 3`), `exp(u)` to `E^u`, `sqrt(u)` to `u^(1/2)`, `surd(u,n)`
    to `u^(1/n)` (real odd roots, §6.2), `O(u)` to `BIGO(u)`, and `asec(u)` to `acos(1/u)`.
  - **Degree mode** wraps trig arguments as `u·π/180` (distributed over a sum) and multiplies
    inverse-trig results by `180/π` (§6.5).
  - A **command** becomes a generator: its arguments are already evaluated (innermost first), and
    `r = yield CMD(name, args)`. The registry maps the name to a module and a generator (§15.1);
    `R.go` has preloaded the module (§18.4).
  - An unknown call becomes `CALL(SYM(name), args...)`.
- **Inert mode** (`ctx.inert`). Commands build `CALL(SYM(name), args...)` instead of running, and
  nothing is simplified. F4 and the round-trip test (§12.5) re-parse answer text this way, with the
  answer's angle mode.
- **Lists:** `[...]`, `{...}` and a bare top-level list (§7.7) become `LST`.
- **Floats:** a FLT anywhere in the input sets `ctx.approx`. Each FLT is then built through
  `exact()`, the command runs exactly, and the runner applies `approx()` to the result (§6.3).
- **Default result path.** At the end, if `A.simplify_candidate(r)` holds (L7, resident in CVALG,
  §8.7), `g_eval` runs `M = R.need('norm')` and then `r = yield M.g_autosimp(r)`.
  A plain expression that is not a candidate loads no lazy module.

### 7.9 Runner-level input rules (FlowCE `answer_before`)

`R.go` applies these rules to the token list, in this order:

0. `purge(name, ...)`, checked before stage 6 so that the names are not expanded: remove each name
   from `VARS` and `FUNCS`. The message is `x deleted` (`x purged` before v1.0.1).
1. `f(x)=body` or `f(x):=body` (detected by stage 4): store `FUNCS[f] = (params, body text)`. The
   message is `f(x) defined`.
2. `expr=>name`: evaluate `expr`, store its printed text in `VARS[name]`, and show the value. An
   invalid name gives the message `Invalid variable name`.
3. `name=expr` or `name:=expr`, where `name` is a valid variable name that does not occur in `expr`
   (FlowCE `equaltosto`): store `name` and show the value.
4. A lone equation `lhs=rhs` with exactly one unknown symbol (not counting `pi`, `e`, `i` and `oo`)
   becomes `solve(lhs=rhs, unknown)`. The equation `x=(-x/2)^2` falls here.
5. Otherwise, evaluate.
6. `+C` flag: the input is a top-level `integrate(` or `int(` call with 1 or 2 arguments (FlowCE
   `is_antideriv`).

Valid variable names are `[a-z][a-z0-9]*`, other than a command, function or constant name, or a
VALUE word (§7.3).

**Storing into a working variable.** `x=3` (rule 3) stores into `x`, after which every `diff` or
`integrate` in `x` sees the number 3. When rules 2 or 3 store into `x`, `y`, `t`, `z`, `n`, `k` or
`theta`, the record sets `F_PURGEHINT`, and the status strip shows `x is now 3: purge(x) clears
it` (§16.1).

### 7.10 Golden and property tests for the input side

- Port all of FlowCE `tests/host/test_tiinput.cc` (about 200 cases) as
  `tests/golden/tiinput.txt`, compared through `untok(ti_implicit(ti_rewrite(lex(s))))`. The
  `e`-exponent cases change as D14 says (§7.2).
- Review cases (§20.12): `2e-1`, `3e-2x`, `2E-1`, `riemann(x^2,x,0,1,4,mid)`,
  `desolve([y''+y=0,y(0)=1,y'(0)=0],y)`, `O(x^6)` after `ti_implicit`, and `sin(x)` through
  `lex` + `rpn` alone (no stage 5).
- Properties:
  - stage 5 inserts only `*`;
  - running stages 4 and 5 twice changes nothing;
  - `classify` is called only on real names.

### 7.11 Session state (CVRUN): text only

| name | contents |
|---|---|
| `ANS` | The text of the last answer that was not a message, or `None`. A message never becomes Ans and never clears it: FlowCE detects messages by the space in them, while we use the record kind. |
| `HIST` | A list of entries `[input, output, kind, approx, flags, forms]`. At most 40 entries and 8 KB of text; the oldest is dropped first. `forms` is `None` until F4 computes it (§14). |
| `VARS` | `{name: canonical text}` |
| `FUNCS` | `{name: (params tuple, body text)}` |
| `SET` | settings: `deg` (0/1) |

Re-parsing stored text is cheap, and **`parse(print(e)) == e` is a tested invariant** (§12.5). It
is what makes text-only session state safe.

---

## 8. Canonical form and simplifier

### 8.1 Four levels

| level | entry | when | what |
|---|---|---|---|
| 0, construction | `add_`, `mul_`, `fn_`, `rel_` (CVNODE) | always | The rules of §8.2 and §6. Each constructor runs once per node; its children are already canonical. |
| 1, expand | `NO.expand(e)` (L3) | `expand`, F4 *expanded*, and inside algorithms | A fold into sparse polynomials over atoms. Positive integer powers of sums are multiplied out. Negative and non-integer powers are atoms. Capped at `MAXTERMS = 400` terms (§8.5). |
| 2, normal | `NO.normal(e)`, `NO.together(e)` (L3) | zero tests, *one fraction*, simplify candidates | Kernels become variables. Numerator and denominator become sparse polynomials, the gcd is cancelled, and the result is rebuilt (§8.6). |
| 3, simplify | `NO.g_simplify(e)` (L2) | the `simplify` command, F4 *simplified*, the default result path | Candidates, each in its own region. The smallest by measure wins, after numeric verification (§8.7). |

### 8.2 Constructor rules

**`add_(terms, k=None)` (L6).** Returns the canonical `k·Σ terms`.

1. Flatten nested ADDs: each pair's coefficient is multiplied in.
2. Fold numbers into the constant. Gaussian arithmetic; FLT contagion.
3. Split a MUL term with coefficient `c != 1` into `c` and `MUL(1, rest)`. A term `c·S`, with `S` a
   sum, is distributed (flattened) into the outer sum, so `2(x+1)+x` gives `3x+2` [M].
4. Collect like terms in a dict `term id -> coefficient tuple` and drop zero coefficients.
   Once the command has built a power kept whole (`K.HUGE`, §6.1), a term holding one gets its
   coefficient's factors of that power's primes moved into the exponent (regrouped as rule 11),
   and terms that then coincide are collected again: `2^100000+2^100000 = 2^100001`.
   The conservative limits in §6.1 reject unsupported sums and fold-boundary normalization.
   This is `KB.hsum`, which asks `add_` for the level-7 calls it needs (§6.1).
   `absn` keeps the content of such a sum (`abs(x/2+2^99999)`), since scaling it would undo this.
5. Sort the pairs by `(H, id)` and run `tiefix`.
6. Collapse: no pairs gives the constant; one pair with a zero constant gives the product `k·t`.
7. Infinity: `∞ + finite = ∞`, `∞ - ∞ = undef`.

**`mul_(k, pairs)` (L5).** Returns the canonical `k·Π b^e`. Rules, in order, for each `(b, e)` on
the work stack:

1. `e == 0`: skip. `0^0` is 1 (alg §2.1).
2. A numeric `b` and an integer `e`: fold into `k` (`npowi`), unless the result could be too
   large to fold (§6.1): then a real `b` goes to the radical table prime by prime, and a
   non-real one beyond the fold limit raises `number too large`. `0^n` is 0 and `0^(-n)`
   raises `Undefined`, at once.
3. A real numeric `b` and a rational non-integer `e`: radical normalization (§6.2).
4. A non-real numeric `b` and a non-integer `e`: keep the pair.
5. `b` a MUL and `e` an integer: distribute. The coefficient goes back on the stack under `e`
   (rule 2), and each pair becomes `(bj, ej·e)` (`ej·e` through `add_` when it is symbolic).
6. `b` a MUL with a positive real rational coefficient `c` and a non-integer `e`: pull out `c^e`
   (§8.3). Then a MUL of real powers kept whole under a real rational `e` distributes:
   `(Π B^X)^e = Π B^(X·e)`, as every such `B` is positive (`(2^100000)^(1/2) = 2^50000`).
7. `b = MUL(1, u, m)`, a single pair, with `m` an even integer, `e` non-integer, and `m·e` an
   integer: gives `absn(u)^(m·e)` (§6.4: `absn` is L6, so `mul_` never calls `fn_`). If `m·e` is
   even it gives `u^(m·e)` (§8.3). So `sqrt((-x-1)^2)` and `sqrt((x+1)^2)` are both `abs(x+1)`.
8. `b = E` and `e = LN(u)`: gives `u`. `e = MUL(n, LN(u), 1)` with n an integer: gives `u^n`.
9. `b = ABS(u)` and `e` an even integer: gives `u^e`.
10. Merge equal bases by summing exponents: numbers inline, otherwise with `add_`. For example
    `e^x·e^(2x) = e^(3x)` [M].
11. Merge radicals with the same rational exponent (§6.2); the end of the product first applies
    the fold rule of §6.1 to every prime of the radical table, and powers kept whole merge the
    same way by their whole exponent.
12. Infinity: the `mul_` rows of the ∞ table (§6.3).
13. Assembly:
    - `k == 0` gives `ZERO`; no pairs gives `k`;
    - one pair `(b, 1)` with `k == 1` gives `b`;
    - `k == -1` with the single pair `(S, 1)`, `S` a sum, gives `add_([S], -1)`;
    - otherwise sort, run `tiefix`, and call `mk`.

**`fn_(op, a)` (L5).** Special values and function rules (§6.4). It calls only `add_`, `neg_`,
`absn` (L6) and the leaves.

**`rel_(op, a, b)` (L5).**

- When `a - b` is a number, it folds to `TRUE` or `FALSE`, which are `CON` leaves and never numbers
  (§5.2). EQ and NE fold for any number; LT and LE fold for a real number and raise `Undefined`
  for a non-real one. So `2<3` gives `true`, `x-x=1` gives `false` and `x+1=x+1` gives `true`.
- Otherwise it returns `mk((op, a, b))`. `>` and `>=` are swapped into `<` and `<=`.
- Rule guards need more than this exact fold; `guard_ok` (§9.2) decides the rest.
- `solve` maps `TRUE` to "every x" and `FALSE` to "no solution" (§11.2). The printer prints
  `true` and `false`.

### 8.3 Branch and assumption policy

**Every symbol is assumed real.** Complex values come only from `i` or from operations on numbers.
Numeric values follow §6: principal values, except that a rational power with an odd denominator
of a negative real is the real root (TI convention). `nev` uses the same convention for symbolic
bases (§6.6).

**The policy (one rule):**

- A rewrite of an expression with symbols must give the same value as its input at **every real
  point where every subexpression of the input is real**. Where the input is not real, the rewrite
  may do anything; extending the domain is allowed (`x/x = 1`).
- A rewrite of numbers alone (V = 0) must be an exact identity under the §6 conventions.

Each row below follows from the rule, and each has a property test (§20.7) that samples real points,
including negative ones, keeps only the points where the input is real (`LEFTREAL`, §6.6), and
checks the two sides there (correctness-first §3.3).

| rewrite | in constructors? | why it is allowed |
|---|---|---|
| `x^a·x^b = x^(a+b)`, a and b rational | yes | With odd denominators, the real-root convention is multiplicative (the parity of the numerator survives reduction). With an even denominator in the input, the input is real only at x >= 0, where the merge holds. So `x^(1/2)·x^(1/3) = x^(5/6)` and `x^(1/6)·x^(1/6) = x^(1/3)` (a domain extension) are both allowed. |
| `x^a·x^b = x^(a+b)`, symbolic exponents | yes | the input is real only at x > 0 (or for integer values) |
| `(x^a)^n = x^(a·n)` | yes | n an integer |
| `(x·y)^n = x^n·y^n` | yes | n an integer |
| `(c·u)^r = c^r·u^r` | yes | c a positive real rational |
| `(u^2)^(1/2) = \|u\|`, `\|u\|^2 = u^2` | yes | holds for real u |
| `ln(e^u) = u` | yes | holds for real u |
| `e^(ln u) = u`, `sin(asin u) = u` | yes | the input is real only where it holds |
| real odd roots of negative numbers | yes | the §6 convention |
| `√a·√b = √(a·b)` | numbers only | a, b > 0 (an exact identity is required for numbers: `√-2·√-3 = -√6`) |
| `ln a + ln b = ln(a·b)`, `n·ln u = ln(u^n)` (`lncollect`) | no; rule set only | the input is real only for a, b, u > 0, where it holds; no guard needed |
| `ln(a·b) = ln a + ln b`, `ln(u^n) = n·ln u` (`lnexpand`) | no; rule set only | the input is also real for a, b < 0, so the guard requires `a > 0` and `b > 0` (`u > 0`) to be proved (§9.2) |
| `x/x = 1`, `0·u = 0` | yes | a domain extension (giac does the same) |
| `asin(sin u) = u`; `(x^a)^b` with b non-integer | never | false at real points where the input is real |

Integration results use `ln(abs(u))` in real mode (§11.3).

### 8.4 Code sketch: `add_` (tested [M])

```python
def add_(terms, k=None):                                        #@L 6
    # canonical k * sum(terms); terms: list of ids; k: NUM tuple or None
    c = Q0                                   # (NUM, 0, 0, 1)
    acc = {}                                 # term id -> coefficient tuple
    st = []
    m0 = Q1 if k is None else k
    for e in terms:
        st.append((e, m0))
    while st:
        e, m = st.pop()
        t = N[e]
        op = t[0]
        if op == NUM:
            c = nadd(c, nmul(t, m))
            continue
        if op == ADD:                        # flatten nested sums
            st.append((t[1], m))
            j = 2
            while j < len(t):
                st.append((t[j], nmul(N[t[j + 1]], m)))
                j += 2
            continue
        if op == MUL and t[1] != ONE:        # split the numeric coefficient
            m = nmul(N[t[1]], m)
            if len(t) == 4 and t[3] == ONE:
                e = t[2]
                if N[e][0] == ADD:           # c*(sum) inside a sum: distribute
                    st.append((e, m))
                    continue
            else:
                e = mk((MUL, ONE) + t[2:])
        if e in acc:
            acc[e] = nadd(acc[e], m)
        else:
            acc[e] = m
    lst = []
    for e in acc:                            #@unordered-ok (sorted below)
        m = acc[e]
        if m[1] or m[2]:
            lst.append((H[e], e, mk(m)))
    cid = mk(c)
    if not lst:
        return cid
    lst.sort()                               # flat (int, int, int) tuples, no key=
    tiefix(lst)
    if len(lst) == 1 and cid == ZERO:        # k*t is a product, not a sum
        e, kk = lst[0][1], lst[0][2]
        if kk == ONE:
            return e
        t = N[e]
        if t[0] == MUL:
            return mk((MUL, kk) + t[2:])
        return mk((MUL, kk, e, ONE))
    out = [ADD, cid]
    for r in lst:
        out.append(r[1])
        out.append(r[2])
    return mk(tuple(out))
```

(FLT contagion and infinity are omitted. The real code checks `op == FLT` next to `op == NUM`.)

### 8.5 expand

`NO.expand(e)` (L3) is a fold over `postorder(e)`. Each node maps to a sparse polynomial: a dict
from an exponent tuple over atoms to a coefficient tuple.

- **Atoms** are symbols, constants and kernels. Function arguments are expanded first, so
  `sin(2(x+1))` becomes `sin(2x+2)`, as giac does.
- **A sum** merges its children's dicts. **A product** convolves them.
- **An integer power `>= 0`** uses binary powering. **A negative or non-integer power** is an atom:
  its base is expanded, but the power stays a quotient.
- The result is rebuilt with the constructors.
- **Cap:** more than `MAXTERMS = 400` terms raises `CasError('too large')`. The cap comes from the
  memory model, not from taste: each term costs about 60-80 B of transient memory (its `acc` dict
  entry, its exponent tuple, its sort tuple and, at the end, its pair in the result tuple) [E],
  so 400 terms are about 30 KB, the whole working set (§18.1). A 2,000-term expansion would need
  more than 100 KB. The loops also check `MEMFREE() < LOWMEM` every 64 terms and raise
  `CasMemory` early rather than fail in the middle of a native allocation. `(a+b)^200` is refused
  at once: the term count of a power of a sum is estimated (`C(n+k-1, k-1)`) before expanding.
- **Fast path:** a univariate polynomial with rational coefficients goes through dense int lists
  (CVPOLY).

### 8.6 normal, together, iszero

**`NO.normal(e)` (L3)** returns a canonical `num/den`.

1. **Kernels.** In postorder, a fold normalizes function arguments first and collects the maximal
   non-rational subterms. A pair `u^(p/q)` with `q > 1` becomes the kernel `u^(1/q)`, raised to the
   power p. For an integer radicand there is the relation `t^q = r`, applied while multiplying.
   Kernels are ordered by `(H, tiefix)` and numbered.
2. **Rational function.** Numerator and denominator become sparse multivariate polynomials, dicts
   `{exponent tuple: coefficient tuple}`. A sum adds fractions; a product multiplies; an integer
   power uses binary powering.
3. **gcd.**
   - The univariate case uses the dense PRS (CVPOLY).
   - The multivariate case uses Kronecker substitution `v_i -> x^(D_i)` with degree bounds,
     then a univariate PRS over Z, maps back, and verifies by exact division.
   - **The Kronecker degree is capped:** the univariate degree after substitution, about
     `Π (d_i + 1)` for variable degrees `d_i`, must be at most `KRONMAX = 64`. Three variables of
     degree 20 would otherwise give a dense PRS of degree about 9,000. Above the cap, the gcd is the
     content only, plus the monomial gcd.
   - If verification fails, or there are Gaussian coefficients, `gcd = content only`. The result is
     still correct, only less cancelled.
4. **Rebuild.** The denominator's leading coefficient is made positive and the integer content is
   divided out.
5. **Caps.** At most 6 kernels, a total degree of at most 60, and at most `MAXTERMS = 400` terms,
   with the same `MEMFREE` checks as `expand`. Beyond that, `normal` returns `e` unchanged and sets
   `NORMAL_GAVE_UP`.

**`NO.together(e)`** is *one fraction*: `normal`, with the denominator factored when that is not
bigger (FlowCE).

**`NO.g_iszero(e)` (L2 generator)** returns `YES`, `NO` or `LIKELY`.

1. `e == ZERO` gives YES. A nonzero NUM gives NO.
2. Rewrite with the identity set `ZBASIS` (in a scoped `g_rewrite`):
   - `tan`, `sec`, `csc` and `cot` become sin and cos;
   - `sin(u)^2` becomes `1 - cos(u)^2`, and integer multiples of a common argument are expanded
     (T2);
   - `e^(a+b)` becomes `e^a·e^b`;
   - `ln` of a positive rational becomes a sum of `ln p` over primes.
3. If the `normal` numerator is 0, YES.
4. If the remaining kernels are all of independent kinds (symbols, π, e, an exp basis, prime
   radicals) and the numerator is nonzero, NO.
5. **Numeric probe** with `nev` at 3 points. Each symbol gets a distinct value from a fixed LCG: in
   (0.31, 2.7) at the first two points and in (-2.7, -0.31) at the third, so that a rewrite valid
   only for positive values (`sqrt(x^2) -> x`, `ln(x^2) -> 2ln(x)`) is caught. A point that raises
   `Undefined`, or where the expression leaves the reals although every input is real
   (`LEFTREAL`, §6.6), is skipped; up to 8 points are tried, alternating signs.
   `|value| > 1e-9 · scale` at any point gives NO, where `scale` is the largest absolute term value
   or 1. Otherwise LIKELY.

Checks (antiderivatives, solve roots, F4 dedupe) accept LIKELY as zero. Tests assert YES where the
math guarantees it.

### 8.7 simplify and the default result path

**When it runs** (FlowCE `auto_simplify`). Every command result and plain expression passes through
`g_autosimp`, but only if `simplify_candidate(e)` holds:

- a sum together with a negative power, or
- `tan`/`sec`/`csc`/`cot`, or
- a numeric radical other than a single `√n`.

`diff` results always qualify. Commands that ask for a specific form (`expand`, `factor`,
`partfrac`, `together`) skip it.

**Candidates.** Each runs as `yield scoped(...)` with its own step budget:

| candidate | when |
|---|---|
| A: the input as built | always |
| `keep_factored` | a product of numbers and at least 2 polynomial factors, one of them a sum: the numbers are multiplied and each base normalized |
| `normal` with the denominator factored | otherwise |
| `trigsin`, `trigcos`, `tlin` rule sets | trig present |
| `merge_sqrt`, `collect_rational`, `power_sums` | always (FlowCE) |
| `lncollect`, `expmerge`, denesting, rationalizing binomial denominators, `abs` factoring | explicit `simplify()` only |

**Measure:** tree size counted with multiplicity (iterative), plus 2 per radical pair, plus 1 per
negative exponent. The smallest wins; ties go to A.

**Verification (MUST).** A winner other than A is compared with A by `nev` at 3 points before it is
accepted: two positive points and one negative point, as in the numeric probe of §8.6, skipping
points where A is not real. A mismatch discards it and increments `SIMPBUG`; every test asserts
`SIMPBUG == 0` afterwards. If no real point is found in 8 tries, the candidate is discarded
without counting a bug.

**`simplify_candidate`** lives in CVALG (resident, L7), so a plain expression that is not a
candidate loads no lazy module (§7.8).

### 8.8 Answer polish (FlowCE `answer_after` subset; CVNORM `g_polish`, T2)

These are small passes that pick which of several equal forms to show. The reference is fmt §2-§3.

| pass | effect | applies to |
|---|---|---|
| `normal_args` | function arguments in lowest terms: `atan((2x-1)/√3)` | all results |
| `textbook_powers` | `e^(x·ln 2)` becomes `2^x` | all results |
| `drop_constants` | numerator terms that are constant in x are dropped | antiderivatives from non-table strategies |
| `ln_conjugate` | `ln\|√P - Q\|` becomes `-ln\|√P + Q\|` when `P - Q²` is constant | antiderivatives |
| `sec_only` | `1/cos(u)^n` becomes `sec(u)^n` | when the input contained sec, csc or cot |
| `factor_sum_result` | `n(n+1)/2` | finite sums to n |
| `exp_factor` | `e^x(sin x+cos x)/2` | when smaller and no radical is added |

Sign and order rewrites (`positive_first`, `sum_content`, the quotient sign) belong to the printer
(§12.3), not here.

### 8.9 Invariant checker (`tests/support/invariants.py`)

This runs after every test, as a scan over `N[1:K.NN]`, so it costs the code under test no
frames. It checks:

- `NUM` is normalized and `FLT` is finite.
- The ADD and MUL invariants of §5.3, including the pair order (it recomputes the sort and
  `tiefix`). The MUL inside a `HOLD` is exempt: it is display-only (§5.2).
- Powers kept whole (§6.1), from an independent factorization: squarefree bases, one base per
  exponent, every kept prime over `MAXBITS` by its weight (or, in the `MAXFOLD` case, over
  `MAXBITS/16` with a total over `MAXFOLD`), the exponent within `MAXBITS`, and no coefficient
  of the MUL or of an ADD term sharing a kept prime. The absolute-value and even-power
  shortcuts require independently proven real bases; a complex base with a real symbol
  is not thereby real.
- `H` and `V` equal a recomputation.
- No `WILD` exists outside `RULECACHE`.
- `fn_` normal forms: there is no `SIN(0)`, no `LN(1)`, no `LN(E)`, and no `MUL(1, E, LN u)`.
- Sign normalization (§6.4): no odd or even function, and no `ABS`, has an argument `u` with
  `negfirst(u)`; no `ABS` has a provably positive constant argument or a numeric coefficient.
- `TRUE`, `FALSE`, `DNE`, `DIVG` and `HOLD` never occur inside an ADD, MUL or function node.
- After a command ends, `K.NN == BASE`.
- `SIMPBUG == 0`.

---

## 9. Rule engine

### 9.1 Rules or code?

Following alg §0.3, the matcher stays small and bounded. Rules are used where a table of
*shape → result* is the natural form. Everything else is procedural code.

| use | mechanism | module |
|---|---|---|
| derivative of each function op | template strings keyed by op (instantiation only, no matching) | CVDIFF |
| integral table: `f(L)` forms, FlowCE `table0` (sec, csc, sec², sec³, ...), quadratic forms | match + instantiate | CVITAB |
| identities: `trigsin`, `trigcos`, `tan2sincos`, `tlin`, `lncollect`, `lnexpand`, `expmerge`, `pyth`, `ZBASIS` | `g_rewrite` with a declared measure | CVIDENT |
| solve inverse table (`sin` -> `asin`/`π-asin`, `e^` -> `ln`, ...) | templates keyed by op | CVSOLVE |
| ODE right-hand-side shapes (`P·e^(αx)·sin/cos(βx)`) | match | CVODE |
| catalog macros (`polararea`, ...) | token macros (§7.6) | CVRUN |
| special values, Taylor recurrences, shape predicates (`linear`, `quadratic`, `split_const`), factoring, partial fractions, the limit chain, tabular integration, Hermite, the ODE classifier | **code** | various |

### 9.2 Rule format

Rules are tuples of strings in the input language: `lhs, rhs, guard`. A rule costs only its
string bytes.

```python
# CVITAB. The integrand reaching S1 has had its constant factor removed (split_const).
ITAB = (
    'L^N',          'L^(N+1)/(A*(N+1))',                       'N!=-1',
    'L^(-1)',       'ln(abs(L))/A',                            '',
    'e^L',          'e^L/A',                                   '',
    'K^L',          'K^L/(A*ln(K))',                           'K>0',
    'sin(L)',       '-cos(L)/A',                               '',
    'cos(L)',       'sin(L)/A',                                '',
    'sec(L)^2',     'tan(L)/A',                                '',
    'sec(L)',       'ln(abs(sec(L)+tan(L)))/A',                '',   # FlowCE textbook string
    'sec(L)*tan(L)', 'sec(L)/A',                               '',
    'Q^(-1)',       '2*atan((2*A*x+B)/sqrt(4*A*C-B^2))/sqrt(4*A*C-B^2)', '4*A*C-B^2>0',
)
# CVIDENT: identity set = (measure, lhs, rhs, guard, ...)
TRIGSIN = (('count', COS), 'cos(U)^2*R', '(1-sin(U)^2)*R', '')
LNCOLLECT = (('count', LN), 'ln(U)+ln(V)+R', 'ln(U*V)+R', '')
```

**Wildcard letters,** in pattern mode only. Uppercase letters are reserved for rules; the
rule-lint test rejects any other uppercase name in a rule string.

| letter | slot | constraint | notes |
|---|---|---|---|
| `U V W` | 0 1 2 | ANY | |
| `A B C` | 3 4 5 | FREE: free of x | also bound by `L` and `Q` |
| `K` | 6 | FREE | |
| `M N` | 7 8 | NUMB: a NUM node | |
| `P` | 9 | INT: an integer NUM | |
| `L` | 10 | LIN: `a·x + b` with `a != 0` and `a`, `b` free of x | binds `A := a`, `B := b` |
| `Q` | 11 | QUAD: `a·x² + b·x + c` with `a != 0` | binds `A`, `B`, `C` |
| `R` | 12 | REST | only as a unit pair of an AC pattern: takes the leftover pairs and the constant or coefficient |
| `x` | 13 | the focus variable | bound by the engine before matching |

`NSLOT = 14`. Lowercase names in rules are literal (`e`, `pi`, `sin`, ...).

- **Binders (from correctness-first).** `L` and `Q` exist because canonical forms defeat structural
  patterns. `(2x)^2` is stored as `4x^2`, so a pattern `(A*x)^2` could never match. The self-match
  test (§9.8) reports any rule of that kind.
- **Guards** are relation strings, decided by `RU.guard_ok(guard, env)` (L3):
  1. `inst` builds the relation with the bindings. `rel_` folds it to `TRUE` or `FALSE` when the
     difference of the two sides is a number.
  2. Otherwise, if the difference `d` is constant (`V[d] == 0`), it is evaluated with
     `nprog`/`nrun`: a value clearly away from 0 (`|v| > 1e-9 · scale`) decides the relation, so
     `abs(sqrt(2)/2)<=1` and `pi>0` hold. A non-real value, or `Undefined`, fails the guard.
  3. A constant value near 0 returns `(NEAR, op, d)`. The calling generator (L2) then runs the
     exact test `NO.normal(d)` (L3; a plain L3 helper could not): a zero numerator decides `=`,
     `<=`, `>=` as true and `<`, `>`, `!=` as false; anything else fails the guard (§9.7).
  4. A difference with free symbols fails the guard.

  A rule fires only if its guard holds. A failed or undecided guard moves on to the next rule, so an
  undecided guard can only miss a rule, never give a wrong answer. Guards do not backtrack into
  other bindings. Rule authors write AC patterns so that the first binding is the intended one.
- **Measures.** Every identity set declares one, and `measure(rhs) < measure(lhs)` must hold:
  - `('size',)`: tree size;
  - `('count', OP, ...)`: the number of nodes with one of these ops;
  - `('excess', OP, ...)`: summed over products, the total integer exponent of the factors with
    one of these ops, minus 1 (certifies `tlin`: `sin(a)·cos(b)` has excess 1, `sin(a+b)/2 +
    sin(a-b)/2` has 0);
  - `('pow', OP, ...)`: the total positive integer exponent on bases with these ops;
  - `('lex', m1, m2, ...)`: the tuple of measures, compared lexicographically (certifies `ZBASIS`
    as `('lex', ('count', TAN, SEC, CSC, COT), ('pow', SIN))`).

  Integration and solve tables need none, because they produce results rather than rewrite to a
  fixpoint.
- **Identity LHS shapes (lint).** An ADD- or MUL-headed identity LHS must contain `R`, so that it
  matches inside a larger sum or product: `cos(U)^2*R` matches `3cos(x)^2` and `cos(x)^2*sin(x)`
  (§9.8 test 5). A LHS must not use `A`, `B` or `C` together with `L` or `Q`, because the binders
  write those slots; the RHS and the guard may read them.
- **Rule strings use explicit `*`.** They are compiled by `lex` and `rpn` only (§7.1), with no
  implicit multiplication, and the rule lint rejects a missing `*`.

### 9.3 Template tables (no matching)

```python
# CVDIFF: d/du f(u); the fold multiplies by du/dx                (D1: tan -> sec^2)
DT = {SIN: 'cos(U)', COS: '-sin(U)', TAN: 'sec(U)^2', SEC: 'sec(U)*tan(U)',
      CSC: '-csc(U)*cot(U)', COT: '-csc(U)^2', ASIN: '1/sqrt(1-U^2)',
      ACOS: '-1/sqrt(1-U^2)', ATAN: '1/(1+U^2)', SINH: 'cosh(U)', COSH: 'sinh(U)',
      TANH: '1-tanh(U)^2', LN: '1/U', ABS: 'abs(U)/U', SIGN: '0', FLOOR: '0', CEIL: '0'}
# CVSOLVE: f(u) = T  ->  u in INV[f] (one period, D2); guard on T
INV = {SIN: (('asin(T)', 'pi-asin(T)'), 'abs(T)<=1'),
       COS: (('acos(T)', '2*pi-acos(T)'), 'abs(T)<=1'),
       TAN: (('atan(T)', 'atan(T)+pi'), ''),
       LN: (('e^T',), ''), ABS: (('T', '-T'), 'T>=0')}
```

(`T` is the right-hand-side slot of the solve table. `e^u = T` and `b^u = T` are handled in code,
because they need `ln` with a positivity check.)

### 9.4 Compilation and caching

- **`RU.rset(name)` (L3)** compiles a rule set:
  - each LHS through `inst(tcode(lhs), None)` in pattern mode;
  - the rules are bucketed into `RULECACHE[name] = {op: ((lhs_id, rhs_str, guard_str), ...)}`.
    **Buckets are view-aware:** the matcher views any subject as an ADD or a MUL (§9.5), so an
    ADD-headed, MUL-headed or wildcard-headed LHS can match a subject of any head (`x` meets
    `L^N` with `N = 1`). Such rules go into every bucket, and into the bucket `VIEW` used for a
    head that has no bucket of its own. The lookup is `rs.get(op, rs[VIEW])`, one tuple;
  - within a bucket, rules stay in file order, so results are deterministic.
- **RHS strings** compile to RPN only when a rule fires (`tcode`, cached in `TCACHE` for the
  command).
- **Command start.** The registry entry of each command lists its rule sets (§15.1). `R.go`
  compiles them before the trampoline starts, so pattern ids sit below every region mark and
  regions never touch them. A set compiled later (by a soft dependency) is remapped by `keep`
  (§5.9).
- **Command end.** `RULECACHE` and `TCACHE` are dropped with the node table. Recompiling a set of
  about 40 rules costs about 40 × 2 ms [E].

### 9.5 Matcher (`RU.match`, L3)

This is the memory-first matcher. It was tested on AC backtracking [M]: `sin(U)*cos(U)*R` against
`sin(x)cos(2x)sin(2x)` binds `U=2x` after one backtrack, and a failed match leaves `env` clean.

- **State:** a goal stack of `(pattern, subject)` pairs, a **trail** of bound slots for undo, and
  **choice points** `(goals snapshot, trail length, AC goal to resume)`. There is no recursion.
- **AC nodes** (ADD, MUL):
  - The subject is *viewed* as the pattern's op (`view`, L4), so identity elements act as defaults:
    `x` matches `x^N` with `N=1`, and `3·sin x` is seen as `ADD(0, sin x, 3)`.
  - Pattern pairs match **distinct** subject pairs (sub-multiset matching).
  - Concrete heads are tried before wildcard heads, and candidates are filtered by head op.
  - A `REST` slot takes the leftover pairs, rebuilt with `add_`/`mul_`.
- **Termination:** at most `MAXSTEP = 400` steps per match. Running out counts as failure, and
  every binding is undone.
- **Limits (lint-checked):** an AC pattern has at most 3 non-`REST` pairs and at most one `REST`.

```python
def match(p, s, env, x):                                        #@L 3
    goals = [(p, s)]
    trail = []
    cps = []
    steps = 0
    while True:
        steps += 1
        ok = True
        if steps > MAXSTEP:
            ok = False
            cps = []
        elif not goals:
            return True
        else:
            g = goals.pop()
            if len(g) == 2:                              # plain goal
                pp, ss = g
                tp = N[pp]
                op = tp[0]
                if pp == ss:
                    pass
                elif op == WILD:
                    sl = tp[1]
                    if env[sl]:
                        ok = env[sl] == ss
                    else:
                        ok = check(tp[2], ss, env, x, trail)     # L4: FREE/NUMB/INT/LIN/QUAD
                        if ok:
                            env[sl] = ss
                            trail.append(sl)
                elif op == ADD or op == MUL:
                    c, sp = view(op, ss)                 # L4: (coef or const id, pairs tuple)
                    pps = []
                    rest = -1
                    j = 2
                    while j < len(tp):
                        b = N[tp[j]]
                        if b[0] == WILD and b[2] == REST and tp[j + 1] == ONE:
                            rest = b[1]
                        elif b[0] == WILD:
                            pps.append((tp[j], tp[j + 1]))       # wildcard heads last
                        else:
                            pps.insert(0, (tp[j], tp[j + 1]))
                        j += 2
                    if rest < 0:
                        goals.append((op, tuple(pps), sp, 0, -1, ZERO))
                        goals.append((tp[1], c))                 # coefficient / constant
                    elif tp[1] == (ZERO if op == ADD else ONE):
                        goals.append((op, tuple(pps), sp, 0, rest, c))
                    else:
                        ok = False
                elif op >= COMP:                         # fixed-arity node
                    ts = N[ss]
                    if ts[0] != op or len(ts) != len(tp):
                        ok = False
                    else:
                        for j in range(len(tp) - 1, 0, -1):
                            goals.append((tp[j], ts[j]))
                else:
                    ok = False                           # different leaves
            else:                                        # AC goal
                op, pps, sps, j0, rest, c = g
                if not pps:
                    if rest < 0:
                        ok = not sps
                    else:
                        if op == ADD:                    # rebuild the leftovers
                            ts = [c]
                            for b, k in sps:
                                ts.append(mul_(k, [(b, ONE)]))
                            r = add_(ts)
                        else:
                            r = mul_(c, list(sps))
                        if env[rest]:
                            ok = env[rest] == r
                        else:
                            env[rest] = r
                            trail.append(rest)
                else:
                    pb, pe = pps[0]
                    hb = N[pb][0]
                    j = j0
                    while j < len(sps) and hb != WILD and N[sps[j][0]][0] != hb:
                        j += 1
                    if j >= len(sps):
                        ok = False
                    else:                                # try pair j; remember j+1
                        cps.append((tuple(goals), len(trail),
                                    (op, pps, sps, j + 1, rest, c)))
                        goals.append((op, pps[1:], sps[:j] + sps[j + 1:], 0, rest, c))
                        goals.append((pe, sps[j][1]))
                        goals.append((pb, sps[j][0]))
        if not ok:
            if not cps:
                while trail:
                    env[trail.pop()] = 0
                return False
            gl, tl, acg = cps.pop()
            while len(trail) > tl:
                env[trail.pop()] = 0
            goals = list(gl)
            goals.append(acg)
```

(`mul_`, at L5, may raise `Undefined`. The matcher lets it propagate as a soft failure.)

### 9.6 Instantiation

`inst(tcode(rhs), env)` (L4) with the bound slot list. `x` and the `L`/`Q` coefficient slots are
already in `env`.

### 9.7 Rewriter (`RU.g_rewrite`, L2 generator) and termination

The rewriter makes bottom-up passes. Each pass visits `postorder(root)`, rebuilds a node if a child
changed (`rebuild`, L4), and fires the first matching rule of the node's (view-aware) bucket. It is
a generator so that each pass can poll and run in a region.

```python
def g_rewrite(root, rs, x, budget):                             #@L 2
    MT = R.MODS['rulesb']                            # the matcher part (section 4.3)
    NO = R.MODS['norm']                              # in every rule user's DEPS closure
    view = rs[VIEW]
    seen = [root]
    for npass in range(MAXPASS):                     # MAXPASS = 8
        m0 = K.NN
        new = {}
        fired = 0
        for n in A.postorder(root):                  # L7: ids sorted, children first
            t = K.N[n]
            m = n
            if t[0] >= K.COMP:
                for j in range(1, len(t)):
                    if new[t[j]] != t[j]:
                        m = rebuild(m, new)          # L4
                        break
            for lhs, rhs, guard in rs.get(K.N[m][0], view):     # one tuple, file order
                env = [0] * NSLOT
                env[XSLOT] = x
                if not MT.match(lhs, m, env, x):     # L3
                    continue
                ok = guard_ok(guard, env)            # L3: 1, 0, or (NEAR, op, d)
                if type(ok) is tuple:                # constant and near 0: exact test here,
                    ok = (NO.normal(ok[2]) == K.ZERO     # at L2, so normal (L3) is legal
                          and (ok[1] == K.EQ or ok[1] == K.LE))
                if ok:
                    m = P.inst(P.tcode(rhs), env)    # L4
                    fired += 1
                    break
            new[n] = m
        if fired > budget:
            raise CasSoft('rewrite budget')
        r = K.keep(m0, new[root])                    # drop this pass's garbage
        if r == root or r in seen:                   # fixpoint or cycle
            break
        seen.append(r)
        root = r
        yield TICK                                   # let the driver poll [clear]
    yield root
```

**Termination** is guaranteed by five things:

1. Each set's declared measure strictly decreases. This is tested on random instances (§9.8) and
   asserted in debug runs.
2. A repeated root id means a fixpoint or a cycle. Hash-consing makes the check an int comparison.
3. Caps: `MAXPASS`, `MAXSTEP`, the fire budget, and the node cap.
4. Each pass releases its garbage.
5. `simplify` never keeps a rewritten form without comparing sizes (§8.7).

### 9.8 Rule tests (`tests/test_rules.py`)

These run for **every** rule in every table and set, with sampled bindings that satisfy the
constraints and guards:

1. **Self-match.** Build the LHS from the sampled bindings through the canonical constructors; the
   pattern must match it. The LHS must also survive `inst` in pattern mode with its intended shape.
2. **Soundness,** checked by `nev` and mpmath at 30 digits on random real points, plus negative and
   complex points for the policy rows (§8.3):
   - integral rules: `d/dx rhs ≡ lhs`;
   - identities: `lhs ≡ rhs`;
   - derivative templates: equal to `sympy.diff`;
   - inverse templates: `f(rhs) ≡ T`.
3. **Measure.** For identity sets, `measure(rhs) < measure(lhs)` on 20 random instances.
4. **Coverage.** The corpus run reports rules that never fired (a warning, not a failure).
5. **Context match.** The sampled LHS instance must also fire through `g_rewrite` when it is
   multiplied by 3, multiplied by another factor (`sin(x)`), added to another term, and when its
   head differs from the pattern's (a bare `x` against `L^N`). This catches rules that the bucket
   lookup or a missing `R` would skip silently.

Adding a rule costs one line of data and gets all five tests automatically. The rule lint (§20.3)
checks the letters, the AC limits, explicit `*`, `R` in ADD/MUL identity LHS, and no `A`/`B`/`C`
next to `L`/`Q` in a LHS.

---

## 10. Execution model: the generator trampoline

### 10.1 Why

Search code is naturally recursive: integrate a sub-integrand, take the limit of a derivative,
solve a factor. A plain call costs one frame per level, and we have about 4 frames left after the
runner and the constructors.

The trampoline runs **one generator at a time** from a single driver loop. Logical nesting is a
list of suspended generators on the heap, so it costs no frames. Every orchestration generator
runs at depth 2, whatever its logical depth. The scratch validation (Appendix A) measured this: 32
logical levels with a maximum device depth of 6 [M].

- **On the device:** PROBE4 showed that a native driving a generator costs 0 extra frames [V] for
  `list(gen)`. PROBE6 confirms the same for `gen.send` before T1 coding.
- **Fallback, if PROBE6 fails:** the memory-first task machine. That is explicit continuation tuples
  plus handler functions, with the same strategy decomposition (§10.8).

### 10.2 Protocol (MUST)

| construct | meaning |
|---|---|
| `r = yield g_sub(args)` | Virtual call. `r` is the child's result, or `None` if it failed. |
| `r = yield scoped(g_sub(args))` | The same, but the child runs in a node region. On return, everything it created is released except its result, which comes back remapped (§10.3). A scoped child returns `None`, an id, or a flat tuple of ids. |
| `yield value` | Return. `value` must not be a generator, a `scoped` pair or `TICK`. The driver never resumes the generator after this. |
| bare `return`, or the end of the generator | Return `None` (failure / not applicable). |
| `raise CasSoft(...)` | Soft failure. The driver pops the generator, releases its region, records the exception in `LASTSOFT`, and returns `None` to the parent. `Undefined` (for example a division by zero during a substitution) is a `CasSoft`. |
| `yield TICK` | Nothing, except that the driver polls cancel and counts a step. Long generator loops do this every iteration. |
| any other exception | Hard error. It aborts the whole command (§10.5). |
| a result sentinel (`DNE`, `DIVG`, an empty `LST`, `TRUE`/`FALSE`) | A normal return value. Only the top-level record turns it into a message (§10.5), so a caller such as `g_defint` can test it and go on. |

- Generator functions are named `g_*`.
- A `g_*` call may appear only as the operand of `yield` or `scoped(...)`, or in `R.go`, which
  creates the root generator from what `R.start` returns.
- Plain functions never call or reference `g_*` functions. A plain function that needs a search
  result restructures as a generator.
- **Banned inside `g_*` (lint):**
  - `yield from`: it would nest frames;
  - `return value`: it is legal Python 3, but the driver reads it as a failure (`None`), silently;
    a generator returns with `yield value`;
  - bare `except:` and `finally`: when a suspended generator is dropped (cancel, an error), CPython
    throws `GeneratorExit` into it and runs these clauses, while the device may not. Desktop and
    device would then behave differently. `except SomeError:` with a named class is allowed.

### 10.3 Regions in the trampoline

- When a `scoped` child is pushed, the driver records `mark = K.NN`.
- The parent is suspended, so every node at or above `mark` belongs to the child and its
  descendants.
- When the child returns `y`, the driver calls `y = K.keep(mark, y)`. A failed attempt (returning
  `None`) releases everything it built.
- Siblings run one after another. An earlier sibling's result sits below the later sibling's mark,
  so it is safe.
- Rule: a generator must not stash ids in shared mutable state (module globals, dicts passed to
  children). Results travel only through `yield`. The debug arena (§20.4) catches violations.

### 10.4 The driver (in `R.go`, L1; tested [M])

The trampoline loop was tested on the prototype [M]. The error paths and live pins added by
review 1 were run against stubs on CPython: a normal nested run with `need` pins, `CasError`,
`Undefined` from `start`, `MemoryError`, a `KeyError` in a generator, `RuntimeError`, an
`OverflowError` in the printer, and `KeyboardInterrupt` (re-raised after the reset) [M]. T1.6
re-tests them on the real modules.

```python
def _g():
    yield
GEN = type(_g())
SCOPE = ['scope']                    # unique sentinels, compared with 'is'
TICK = ['tick']


def scoped(g):                                                  #@L 7
    return (SCOPE, g)


def go(job):                                                    #@L 1
    # job: ('eval', text) | ('form', hist_index); returns a result record (text only).
    # Never raises, except KeyboardInterrupt, which is re-raised after the reset.
    rec = None
    err = None
    stack = g = val = None
    try:
        code, ctx = start(job)       # L2: text passes, P.tokens (L3), rpn, preload, rule sets
        if job[0] == 'eval':         # the root generator is created here, never in a helper
            g = P.g_eval(code, ctx)
        else:
            g = MODS['form'].g_form(code, ctx)
        stack = [g]
        marks = [-1]
        NEEDED.append([])            # per stack slot: families pinned through need() (18.4)
        val = None
        steps = 0
        while stack:
            steps += 1
            if not steps & 31:
                if K.ESC():          # native ti_system.escape (or get_key()==45): 0 frames
                    raise Cancel()
                if steps > BUDGET:
                    raise CasError(M_TOO_LONG)
                if not steps & 511:
                    BUSY(steps)      # UI hook at depth 2: "Calculating..." animation
            top = stack[-1]
            try:
                y = top.send(val)
            except StopIteration:
                y = None
            except CasSoft as e:
                LASTSOFT[0] = e
                y = None
            else:
                if y is TICK:
                    val = None
                    continue
                if type(y) is GEN:
                    if len(stack) >= MAXGEN:                 # 64
                        raise CasError(M_COMPLEX)
                    stack.append(y)
                    marks.append(-1)
                    NEEDED.append([])
                    val = None
                    continue
                if type(y) is tuple and len(y) == 2 and y[0] is SCOPE:
                    stack.append(y[1])
                    marks.append(K.NN)
                    NEEDED.append([])
                    val = None
                    continue
            stack.pop()
            for f in NEEDED.pop():   # this generator no longer keeps its families live
                LIVE[f] -= 1
            m = marks.pop()
            if m >= 0:
                y = K.keep(m, y)
            val = y
        rec = PR.record(val, job)    # L2: text (L3), decimal line, sentinel messages, flags
    except Cancel:
        err = M_INTERRUPTED
    except CasError as e:
        err = e.args
    except CasSoft:                  # Undefined from start() or the printer: outside the loop
        err = M_UNDEFINED
    except (MemoryError, CasMemory):
        err = M_OOM
    except RuntimeError:             # depth: should never fire if the tests pass
        err = M_TOO_COMPLEX
    except KeyboardInterrupt:
        err = KBI                    # re-raised below, after the reset
    except Exception as e:           # a bug: report it, never lose the session
        err = (M_INTERNAL, type(e).__name__)
    stack = g = val = None           # every path: drop the generator frames first,
    del NEEDED[:]                    # then reset (section 18.6), then build the message
    LIVE.clear()
    del PINNED[:]
    K.reset()                        # node table, SYMN/SYMI, RULECACHE, TCACHE
    if err is M_OOM:
        evict_all()                  # L2: every lazy module, then gc.collect()
    if err is KBI:
        raise KeyboardInterrupt()
    if err is not None:
        rec = msg_rec(err)           # L2: built on the empty table; preallocated texts
    return rec
```

(`start`, `msg_rec` and `evict_all` are L2 helpers. `start` returns `(code, ctx)` and never creates a
generator. `KBI` is a unique sentinel like `TICK`.)

### 10.5 Exceptions

Since v1.0.1 every message a user sees starts with a capital letter, as on the TI-Nspire
(`Undefined`, `No solution`, `Missing operand`, `Internal error: TypeError`); the text keeps its
meaning. The sections below quote the earlier lowercase spellings where they describe history;
`src/` holds the current texts (MATHPRINT.md 0.15).

| class | base | raised by | effect |
|---|---|---|---|
| `CasSoft` | `Exception` | strategies, `Undefined` from constructors and `nev` | the child returns `None` (§10.2). Raised outside the driver loop (`start`, `PR.record`), it gives `undefined`. |
| `Undefined` | `CasSoft` | `0^-1`, `tan(π/2)`, `ln(0)` | as above. At top level (the root generator returns `None` and `LASTSOFT` is `Undefined`) the message is `undefined` |
| `CasError` | `Exception` | syntax errors, bad arguments, caps (`Too long to compute`, `Too many terms`, `Number too large`) | aborts the command and shows the message. **Never used for a mathematical result.** |
| `Cancel` | `BaseException` | the cancel poll | `Interrupted` |
| `CasMemory` | `BaseException` | `mk` and `need` low-memory checks | `Out of memory` (§18.6) |
| `MemoryError` | builtin | anywhere | `Out of memory` |
| `RuntimeError` | builtin | the device depth cap | `Expression too complex` (a bug: the tests should prevent it) |
| `KeyboardInterrupt` | builtin | `[on]` (if the EVO raises it) | `R.go` resets, then re-raises; the event loop shows `Interrupted` (§16.2) |
| any other `Exception` | builtin | a bug (`TypeError`, `KeyError`, `OverflowError`, ...) | `Internal error: TypeError`. The session survives; tests fail on any such record. |

**Result sentinels are values, not exceptions.** An algorithm returns them, and its caller decides:

| sentinel | meaning | message when it is the top-level result |
|---|---|---|
| empty `LST` (from `g_solve`) | no solution | `No solution` |
| `TRUE` (from `g_solve`) | every x is a solution | `Every x is a solution` |
| `DNE(l, r)` | a limit does not exist | `Does not exist: l from the left, r from the right`, or `No limit (it oscillates)` when a side is `UNDEF` |
| `DIVG(w)` | an improper integral or a series diverges | `Diverges (the improper integral does not converge)`, `Diverges (the integrand is unbounded on the interval)`, `Diverges (the terms do not go to 0)` |

So `integrate(1/(x^2+1),x,0,1)`, whose denominator has no real root, gets an empty list from its
singularity search and goes on to `π/4`. `PR.record` prints the one-sided values of a `DNE`
before `K.reset()`, like any other result. Arithmetic on a sentinel raises
`CasError('invalid use of a result')` (§7.8).

### 10.6 Strategy sketch: the integration driver (CVINT)

```python
STRATS = (('int', 'g_table'), ('intb', 'g_usub'), ('int2', 'g_tabular'),
          ('int2b', 'g_rational'), ('int2', 'g_trigpow'), ('int3', 'g_parts'),
          ('int3b', 'g_radical'), ('int3b', 'g_weier'))       # parts, section 4.3


def g_int(f, x, depth):                                         #@L 2
    # returns (F, R) with f = F' + R; R != 0 means "partly unevaluated"
    if K.free_of(f, x):
        yield (K.mul_(K.ONE, [(f, K.ONE), (x, K.ONE)]), K.ZERO)
        return
    c, g = A.split_const(f, x)               # L5: f = c*g, c free of x
    t = K.N[g]
    if t[0] == K.ADD:                        # S0 linearity: one virtual call per term
        Fs = [K.mul_(t[1], [(x, K.ONE)])]
        Rs = []
        j = 2
        while j < len(t):
            r = yield g_int(t[j], x, depth)
            if r is None:                    # a soft failure inside: keep the term unevaluated
                r = (K.ZERO, t[j])
            Fs.append(K.mul_(t[j + 1], [(r[0], K.ONE)]))
            Rs.append(K.mul_(t[j + 1], [(r[1], K.ONE)]))
            j += 2
        yield (scale(c, K.add_(Fs)), scale(c, K.add_(Rs)))
        return
    for mod, name in STRATS:                 # S1 .. S8, first success wins
        M = R.need(mod)                      # soft dependency: lazy import at depth 3,
                                             # pinned while this g_int is on the stack
        r = yield scoped(getattr(M, name)(g, x, depth))      #@calls 2
        if r is not None:
            ok = yield scoped(g_check(r[0], r[1], g, x))      # d/dx F + R - g == 0 ?
            if ok is not None:
                yield (scale(c, r[0]), scale(c, r[1]))
                return
    yield (K.ZERO, f)                        # S9: unevaluated remainder
```

(`scale(c, e)` stands for `K.mul_(K.ONE, [(c, K.ONE), (e, K.ONE)])`. The `need` pin means that a
nested `g_int`, started from inside `g_parts`, can never evict CVINT3 while `g_parts` is suspended
(§18.5).)

### 10.7 Budgets and polling

| what | limit |
|---|---|
| engine steps per command | `BUDGET = 20000` (calibrated on the device: a warning above 5 s, a failure above 20 s) |
| generator stack | `MAXGEN = 64` |
| rewrite | `MAXPASS = 8`, `MAXSTEP = 400` per match |
| integration | u-substitution depth <= 3, parts depth <= 4 |
| L'Hôpital | 5 rounds |
| series retries | order + 2, + 4, + 8 |

Plain loops that can run long poll the cancel hook inline every 256 iterations:
`if not i & 255 and K.ESC(): raise Cancel()`. Such loops include `expand`, `normal`, polynomial
loops, Kronecker, quadrature, `nev` sampling and sums. A plain loop cannot animate the busy
indicator; only the driver does that.

### 10.8 Fallback if PROBE6 fails

Each `g_*` becomes a handler `h_*(task)` that pushes continuation tuples onto `TASKS` and values
onto `VALS` (memory-first §5.1). The strategy order, regions (`nmark` saved in the continuation),
budgets and module layout stay as they are. Only the orchestration code changes, which is roughly
25% of CVINT, CVLIM, CVSOLVE, CVSUM and CVODE. This decision must be made before T1.6 starts.

---

## 11. Algorithm plan

alg §n has the algorithms with giac/FlowCE citations. This section fixes how each one is built
here.

### 11.1 Feature table

| feature | tier | module | entry | pattern | data | verification | caps | fallback |
|---|---|---|---|---|---|---|---|---|
| exact arithmetic, radicals, constants, special values | T1 | CVNODE | constructors | construction | special-value tables | invariants, oracle | radicand trial division to 10^4 | a partly reduced radical |
| expand | T1 | CVNORM | `g_expand` | fold | – | oracle | `MAXTERMS = 400` terms, `MEMFREE` checks | `too large` |
| simplify | T1 | CVNORM, CVIDENT | `g_simplify` | candidates | identity sets | numeric check per candidate | 400 steps per match, 8 passes | the A-form |
| factor | T1 | CVFACT, CVPOLY | `g_factor` | pipeline (loops) | cyclotomic and binomial shapes | the product expands back exactly | divisor, odometer and step budgets | a partial factorization, no "irreducible" claim |
| solve | T1 | CVSOLVE | `g_solve` | worklist | `INV` templates | substitute every root (`g_iszero`) | per-item budget, 24 roots | numeric roots labelled ≈ |
| linear systems | T1 | CVSOLVE, CVPOLY | `g_solve([eqs],[vars])` | Gauss-Jordan over Q | – | substitution | 8 variables | empty list (`no solution`) / parametric |
| Ans, store, history, functions | T1 | CVRUN | §7.9 | text | – | round trip | 40 entries | – |
| derivatives, partials, n-th order, FTC | T2 | CVDIFF | `g_diff` | fold with memo | `DT` | SymPy | n <= 20 | – |
| Taylor series | T2 | CVSER | `g_taylor` | fold with truncated series | – (recurrences are code) | SymPy coefficients | order <= 20 | unevaluated `taylor(...)` |
| limits | T2 | CVLIM (+SER, DIFF) | `g_limit` | strategy chain | growth-class data | numeric cross-check | budget, 5 L'Hôpital rounds | ≈ estimate; the `DNE` sentinel (§10.5) |
| antiderivatives | T2 | CVINT, CVITAB, CVINT2, CVINT3 | `g_integrate` | strategy chain S0-S9 | `ITAB` | `d/dx F ≡ f` | depth guards, budget | unevaluated `∫ f dx` + C |
| partial fractions | T2 | CVINT2 (`integ2b`) | `g_partfrac` | linear system | – | `together(result) ≡ input` | denominator degree <= 12 | unevaluated |
| definite integrals | T2 | CVDEF | `g_defint` | singularities -> F -> limits + jumps | – | tanh-sinh cross-check | 400 evaluations | ≈ value |
| improper integrals | T3 | CVDEF | `g_defint` | split pieces | – | quadrature | – | the `DIVG` sentinel, ≈ |
| sums and series | T3 | CVSUM | `g_sum` | closed forms + tests | known-series table | partial sums | 1,000 direct terms | ≈ / the `DIVG` sentinel |
| Riemann sums | T3 | CVSUM | `g_riemann` | loop or symbolic sum + limit | – | equals ∫ in the limit | – | numeric table |
| ODEs | T3 | CVODE | `g_desolve` | classifier | RHS shapes | substitute into the ODE | order <= 2 | `no closed form found` |
| gradient | T3 | CVDIFF | `g_grad` | list of partials | – | SymPy | – | – |
| multiple integrals | T3 | CVDEF | nested `integrate` | inner first | – | Gauss-Legendre product | – | ≈ |
| polar/parametric area, arc length | T3 | macros -> CVDEF | `polararea`, `paramarea`, `arclen` | build the integrand, then definite | macros | quadrature | – | ≈ |

### 11.2 T1 notes

- **factor** (alg §2.8), all loops:
  1. Integer content and sign; `x^k`.
  2. Yun (CVPOLY).
  3. For each square-free part:
     - shapes: binomials `a·x^n + b` (cyclotomic split when `|a| = |b|`, differences of n-th
       powers), and an exponent gcd `d` (substitute `X = x^d`, factor, then retry each factor in
       x);
     - rational roots, with candidates pruned by `P(1)` and `P(-1)`, testing `q^n·P(p/q)` by exact
       Horner;
     - Kronecker quadratic factors by an odometer over signed divisor tuples, with a step budget.
       Degree 3 factors only if the degree is at least 6 and there is budget left.
  4. Multivariate: content per variable, monomial content, homogeneous dehomogenization, binomial
     shapes.
  5. Rational expressions: factor the numerator and denominator separately.

  Factoring is over Q only: `x^2-2` stays as it is. The result is a MUL of `(factor, multiplicity)`
  pairs; the printer orders them (§12.3).

  **Integers.** `factor(n)` for an integer (and the integer content of a polynomial, when it is
  not 1) uses trial division by 2, 3 and 6k±1 up to `min(√n, 10^6)`, polling cancel. A cofactor
  above the bound stays as one base. The constructors would fold `2^3·3^2·5` back to 360, so the
  result is `HOLD(m)`, where `m` is the MUL `(MUL, sign, 2, 3, 3, 2, 5, 1)` built with `mk`
  directly (§5.2). It prints `2^3*3^2*5`; re-parsing that text gives 360, which is the intended
  value (§12.5).
- **solve** (alg §2.10). A worklist of `(expr, var)` items, processed in one generator:
  0. A decided relation: `TRUE` (the equation folded, as `x+1=x+1` does) yields `TRUE`, "every x
     is a solution"; `FALSE` (`x-x=1`) yields the empty `LST`, "no solution" (§8.2, §10.5).
  1. `normal` -> `N/D`; drop roots where `D = 0`.
  2. If `free_of(N, var)`: `TRUE` when `N = 0`, otherwise no root from this item.
  3. A product: push each factor.
  4. A polynomial in `var`:
     - Yun, then rational roots;
     - degree <= 2 by formula (exact radicals; a negative discriminant gives no real roots, D3);
     - **symbolic coefficients** (`x^2+a=0`, `a·x=b`) give the generic solution, as giac does:
       the leading coefficient is assumed nonzero and both formula roots are returned
       (`x=-sqrt(-a),x=sqrt(-a)`) unless the discriminant is a constant whose sign is known
       (V = 0: decided as in `guard_ok`, §9.2). The root check is symbolic for these roots;
     - biquadratic and `P(x^k)` through `t = x^k`;
     - otherwise numeric real roots (bisection and Newton on sampled sign changes), labelled ≈.
  5. A single kernel `f(u)`: solve for `t = f(u)` (push), then push `u - inv` for each inverse
     template whose guard holds (`guard_ok`, so `sin(x)=sqrt(2)/2` gives `π/4` and `3π/4`).
     - Periodic families (D2) list every solution `x` in the window `[0, P)` when
       `u = a·x + b` with rational `a`, at most 24. `P` is `2π` in radian mode and `360` in
       degree mode, because the window is on `x`, which is typed in the user's unit (§6.5).
     - Exponentials: `b^u = T` gives `u = ln T / ln b`. The `ln(b^k)` canonical form makes
       `2^x = 8` give 3.
  6. One radical `P + Q·√A = 0`: square to `P² - Q²·A = 0`, solve, and check every root.
  7. `a·sin u + b·cos u = c` -> `R·sin(u + φ)`.
  8. Otherwise numeric, labelled ≈.

  Every root is checked: `g_iszero(subst(expr))` must not be NO, and the denominators must not be
  0. Roots are deduplicated by id and sorted by numeric value (symbolic roots by `H`). Output:
  `LST(EQ(x, r1), ...)`; no root gives the empty `LST`, a sentinel that only the top-level record
  turns into `no solution` (§10.5). Systems: if linear in the unknowns, Gauss-Jordan over Q;
  otherwise eliminate one variable by substitution, at most 2 equations.
- **Implicit solve and store** are handled by the runner (§7.9).

### 11.3 T2 notes

- **diff** (alg §3.1). A fold over `postorder` with memo `d[id]` (memory-first prototype [M]):
  - ADD gives `Σ k·d(t)`.
  - A MUL pair `(b, e)`:
    - power rule when `e` is free of x;
    - `b^e·(e'·ln b + e·b'/b)` otherwise.
  - A function: `d(arg)·inst(DT[op], {U: arg})`.
  - `CALL integrate` with variable bounds: FTC, `f(b)·b' - f(a)·a'`.
  - Higher order: loop with `g_autosimp` between steps.
  - Partial derivatives use another variable. Degree mode needs nothing special (§6.5).
- **Series engine** (alg §3.2). `series_fold(e, x, a, n)` (L3, CVSER):
  - Substitute `x = a + h`, or `x = 1/h` at ∞.
  - Fold over `postorder` with one truncated series per node: a flat tuple `(v, c0, c1, ..., cN)`
    meaning `h^v·Σ ci·h^i`, with **coefficient ids**.
  - ADD: align and add. MUL pairs:
    - an integer exponent: binary powering with truncated convolution;
    - another constant exponent: the Miller recurrence;
    - `E^u`: the exp recurrence times `e^(u0)`.
  - Functions:
    - `ln`: the leading term plus the derivative recurrence;
    - `sin` and `cos`: a coupled recurrence;
    - `tan = sin/cos`;
    - `atan` and `asin`: the series of the derivative, integrated term by term.
  - Every loop is O(N²) with no recursion.
  - `g_series` (L2) retries with order + 2, + 4, + 8 while the leading coefficient is zero (checked
    by `normal`).
  - `taylor(f, x=a, n)` defaults to `n = 5`. The output is the polynomial plus `BIGO((x-a)^(n+1))`.
- **limit** (alg §3.3). `g_limit` tries these strategies in order, each in a scoped region; the
  first success wins:
  0. **Piecewise functions.** If f contains `floor`, `ceil`, `sign` or `abs` of an argument that
     vanishes or is an integer at the point, a two-sided limit is always computed as the two
     one-sided limits (each with steps 1-7 below, the function evaluated with `x = a ± ε` in its
     argument's sign), and plain substitution is never trusted. So `limit(floor(x),x,1)` gives
     `DNE(0, 1)` rather than 1.
  1. Substitute (with the ∞ folding table of §6.3, so `1/oo` gives 0). One-sided handling of
     `abs`, `sign`, `floor` and `ceil` by the side.
  2. Rational in x: cancel, then substitute. At ±∞, compare degrees.
  3. Series at the point (or at ∞). The leading term `c·h^v` decides: `v > 0` gives 0, `v = 0`
     gives c, `v < 0` gives ±∞ by `sign(c·side^v)`. A two-sided limit with odd `v` gives
     `DNE(-∞, ∞)` (signs as computed).
  4. Rewrite the indeterminate form: `0·∞` -> a quotient, `∞-∞` -> `together`, `1^∞`, `0^0`,
     `∞^0` -> `exp(lim g·ln f)`. Then up to 5 rounds of L'Hôpital. The inner limits use steps 1-3
     only, so the depth stays bounded.
  5. Growth classes at ±∞: triples (exp degree, power, log power) for products and quotients.
  6. Bounded times vanishing gives 0. Bounded and oscillating gives `DNE(UNDEF, UNDEF)`, printed
     `no limit (it oscillates)`.
  7. Numeric: `f(a ± 10^-k)` for k = 2..8 (or `f(10^k)`), with Richardson extrapolation, labelled ≈.

  If the one-sided values differ, the result is the sentinel `DNE(L, R)` (§10.5), printed at top
  level as `does not exist: L from the left, R from the right`. Callers (L'Hôpital, improper
  integrals, the n-th term test) test for `DNE` and carry on.
- **integrate** (alg §3.4). `g_int` (§10.6) with the (F, R) contract:

  | step | strategy | notes |
  |---|---|---|
  | S0 | linearity | |
  | S1 | `ITAB` match on the integrand | |
  | S2 | u-substitution | Candidates: kernels innermost first, their arguments, the bases of powers, denominators. Numeric pre-check of `f/u'` as a function of `u` at x = 0.3271 and 0.7193 (FlowCE), then exact: substitute a fresh `_t`, `normal`, `free_of(x)`. Depth <= 3. |
  | S3 | tabular parts | for `poly·{e^(ax), sin, cos}` and `e^(ax)·sin/cos(bx)` |
  | S4 | rational functions | Division, Yun, Hermite reduction, partial fractions through the CVPOLY linear solve, `ln\|·\|`, and `atan` plus the `I_k` reduction loop for irreducible quadratics. Real irrational roots use giac's ln-ratio form. |
  | S5 | trig powers | FlowCE substitutions; even powers by linearization with integer coefficient arrays |
  | S6 | by parts (LIATE) | depth <= 4; repeated `x^n·ln(x)^m` loops |
  | S7 | radicals | `(ax+b)^(p/q)` by substitution; `P/√(ax²+bx+c)` by the Ostrogradsky linear system |
  | S8 | Weierstrass `t = tan(x/2)` and `t = e^x` | last resort |
  | S9 | fail | the remainder R |

  - **Check:** `d/dx F + R - f` must pass `g_iszero` (anything but NO). A failed check discards the
    attempt.
  - **Output:** `ln|u|` in real mode, then `g_polish` (§8.8). `+C` is a view decoration (§13.6).
    `R != 0` prints `F + ∫R dx`. Total failure shows `∫f dx` (a `CALL`).
- **definite integrals** (alg §3.5-§3.6). `g_defint` runs in three phases, so that only one
  family set is loaded at a time (§18.5):
  1. **Singularities** (soft `R.need('solve')`, dropped after): the singularities of f in `[a, b]`,
     from `g_solve` on denominators, `ln` arguments and `cos` for tan/sec. An empty `LST` means
     none (`1/(x^2+1)` on `[0, 1]`); a `TRUE` (an identically zero denominator) is an error. If
     exact solving fails (`None`), isolate numerically.
  2. An interior or endpoint singularity makes the integral improper (T3).
  3. **Antiderivative** (the preloaded `int` family): get F from `g_int`. If `R != 0`, go numeric.
     Then `R.drop(('int', 'int2', 'int2b', 'int3', 'int3b', 'itab'))`.
  4. **Limits** (soft `R.need('lim')`): total = `F(b⁻) - F(a⁺) + Σ jumps of F` inside. One-sided
     limits are used only where plain substitution fails. This catches Weierstrass jumps. A `DNE`
     or infinite one-sided value at a jump makes the result numeric (or `DIVG` for T3).
  5. Cross-check against tanh-sinh (relative error 1e-6). On a mismatch, show the numeric value
     labelled ≈ and not the exact one.
  6. An odd integrand on a symmetric interval gives 0, after a numeric check at 3 points.

  Quadrature: tanh-sinh, levels <= 6, at most 400 evaluations, polling every 64. The cross-check
  uses Gauss-Legendre with 12 points on 3 uneven panels (FlowCE). Domain errors at a node move the
  node inward.

### 11.4 T3 notes

- **Improper integrals** (alg §4.1). Split into pieces, each improper at one end. Each piece gets F
  plus a one-sided limit.
  - A piece whose one-sided limit is ±∞ or a `DNE` makes the result the sentinel `DIVG(w)`
    (§10.5), printed at top level as:
    - `diverges (the improper integral does not converge)` for an infinite bound (`w = 0`);
    - `diverges (the integrand is unbounded on the interval)` for an interior or endpoint
      singularity (`w = 1`).

    A multiple integral or a macro that meets `DIVG` in an inner piece passes it up unchanged.
  - No principal values.
  - With no F, go numeric, with a growth heuristic over I(R), I(2R), I(4R).
- **Sums** (alg §4.2).
  - Finite with numeric bounds and at most 1,000 terms: an exact loop that polls CLEAR
    each term. The accumulator's numeric fields (real numerator, imaginary numerator,
    denominator), including ADD/MUL coefficients, are capped at 3,300 hex digits
    (about 13,200 bits, near the printer's 4,000-character limit). On exceeding that
    budget, the loop releases its temporary nodes and returns no result; the caller
    keeps `sum(...)` or `riemann(...)` formal. It never silently rounds an exact sum.
  - With a symbolic bound:
    - Faulhaber: `P(k) - P(k-1) = Q(k)` as a triangular system;
    - geometric series;
    - `Q(k)·r^k`: `r·P(k+1) - P(k) = Q(k)`;
    - telescoping after partial fractions, pairing shifted denominators.

    The result is factored, e.g. `n(n+1)/2`.
  - Infinite, in order:
    1. the n-th term test (numeric first, then `g_limit`);
    2. geometric;
    3. telescoping limit;
    4. the known-series table: ζ(2k) for k <= 4, the alternating harmonic, Leibniz, `r^n/n!`,
       `r^n/n`, `n·r^n`;
    5. p-series;
    6. integral test and comparison;
    7. numeric: 200 terms plus the tail integral, or averaged partial sums, labelled ≈.
  - A divergent rational-term series returns `+∞`, like FlowCE. A failed n-th term test gives
    `DIVG(2)`, printed `diverges (the terms do not go to 0)`. A `DNE` from the inner `g_limit` of
    the n-th term test (oscillating terms) is also a failed test.
- **Riemann sums** (alg §4.3). `riemann(f, x, a, b, n, method)` with method `left`, `right`, `mid`
  or `trap`.
  - A numeric `n`: a loop, exact when f is rational.
  - A symbolic `n`: build the sum, apply Faulhaber to get a rational function of n, and show it.
    `limit(...)` of it must equal `∫`; a test checks that.
- **ODEs** (alg §4.4).
  - `y`, `y'` and `y''` are symbols, so linearity tests reuse `linear` and `free_of`.
  - The classifier tries these checks in order, each a generator:
    1. 1st-order linear: integrating factor `e^(∫p)`, with abs and constant factors cleaned;
    2. separable: split the factors by `free_of`, then two `g_int` calls, `R.drop` of the
       integration families, and a `g_solve` for y (soft `R.need('solve')`, §18.5); an empty
       `LST` or `None` keeps the implicit answer. Record lost solutions (`y = 0`); constants are
       absorbed (`ln|y| = F + C` gives `y = C·e^F`);
    3. Bernoulli: through `v = y^(1-n)`;
    4. 2nd-order with constant coefficients: characteristic roots by formula, in the three cases;
       the particular solution by the operator series `e^(λx)·[1/L(D+λ)]P(x)` with Gaussian pairs
       for sin and cos (correct under resonance).
  - Initial conditions: differentiate, substitute, Gauss-Jordan for C1 and C2, substitute back.
  - The constants print as `C1` and `C2`. An implicit answer prints as `G(y) = F(x) + C1` when
    `solve` fails.
  - Syntax: `desolve(y''+y=0, y)`, or with conditions in a list,
    `desolve([y''+4y=0, y(0)=1, y'(0)=0], y)`.
- **Gradient.** `grad(f, [x, y, z])` gives an `LST` of partials. Bare `grad(f)` uses the symbols of
  f in name order.
- **Multiple integrals.** Nested `integrate` calls evaluate innermost first; inner bounds may
  depend on outer variables. If any level leaves `R != 0`, the **whole** integral goes numeric
  with an n×n Gauss-Legendre product (n = 10) on the mapped region, labelled ≈.
- **Polar and parametric area, arc length** (alg §4.7). The macros build the set-up integral:
  - `polararea(r, t, a, b)` = `integrate((r)^2/2, t, a, b)`;
  - `paramarea(x, y, t, a, b)` = `integrate(y*diff(x,t), t, a, b)`;
  - `arclen(f, x, a, b)` = `integrate(sqrt(1+diff(f,x)^2), x, a, b)`;
  - the 6-argument parametric form of `arclen` uses `sqrt(diff(x,t)^2+diff(y,t)^2)`.

  For arc length, the radicand is normalized and perfect squares are pulled out (`√(u²) = |u|`).
  The sign of u on the interval is fixed by a midpoint check, then the abs is dropped. A radicand
  with an odd-power factor of degree above 2 goes numeric at once (FlowCE `hard_radicand`).

---

## 12. Printer (1D) and the decimal line

### 12.1 Output contract

`PR.text(e, ctx)` (L3, CVPRINT) returns **canonical, re-parseable input-language text**. That text
*is* the answer: history, Ans, variables, F4 and the 2D renderer all use it (FlowCE fmt §0). The
text uses:

| element | text |
|---|---|
| multiplication | explicit `*` |
| `u^(1/2)` | `sqrt(u)` |
| exponentials | `e^(u)`, or `e^x` for an atomic exponent |
| base-10 log | `log(` |
| absolute value | `abs(` |
| constants | `i`, `pi`, `oo`, `undef` |
| decided relations | `true`, `false` (§8.2) |
| relations | the main variable on the left: `x>3`, not `3<x` (§12.4) |
| series remainder | `O(...)` |
| unevaluated results | calls: `integrate(f,x)`, `limit(...)`, `sum(...)` |
| solutions | `x=a,x=b`, a bare top-level list that `rpn` re-parses as a list (§7.7), in Ans, the F4 re-parse, the 2D layout and `=>` stores. Ans also wraps it in parentheses. Systems print as `x=2,y=1`. |
| floats | 15 significant digits, so Ans keeps precision. The renderer draws float literals with at most 10 (§13.2). |

**Sentinels become messages.** When the top-level result is a sentinel (§10.5), `PR.record` makes a
message record instead of an answer: `no solution`, `every x is a solution`, `does not exist: l
from the left, r from the right`, `no limit (it oscillates)`, or `diverges (...)`. A message never
becomes Ans (§7.11). The empty list and `TRUE` are messages only as the result of an `F_SOLN`
command (solve, or an equation turned into solve by §7.9 rule 4); elsewhere `2<3` is the answer
`true` and `[]` is an empty list.

A result longer than `MAXTEXT = 4,000` characters becomes the message `Done`. `text` stops as soon
as it has emitted that many characters, and the printer never converts a huge integer with `str()`
(§6.1), so building the text of a huge result costs no more than the cap.

### 12.2 Driver (explicit stack)

```python
def text(root, ctx):                                            #@L 3
    # returns the text, or None when it would exceed MAXTEXT (the record becomes Done)
    out = []
    n = 0
    st = [(root, 0)]                     # (node id, minimum precedence) or a literal str
    while st:
        it = st.pop()
        if type(it) is str:
            out.append(it)
            n += len(it)
            if n > MAXTEXT:              # stop at once: no 30k-digit text is ever built
                return None
            continue
        seq = items(it[0], it[1], ctx)   # L4: display sequence for one node; None for an
        if seq is None:                  # integer over the str() size guard (section 6.1)
            return None
        for i in range(len(seq) - 1, -1, -1):
            st.append(seq[i])
    return ''.join(out)
```

- **`items(n, need, ctx)` (L4)** returns a list of literal strings and `(child, precedence)` pairs
  in display order. It adds `(` and `)` when the node's own precedence is below `need`.
- **Memory** is O(output); there are no per-subtree string copies.
- **Temporary nodes.** The display passes may build temporary nodes through the constructors. For
  example, a negated difference `-(P)·rest` is printed as `(-P)·rest`, and a coefficient `|k|·t` is
  built per term. The table is reset after the command in any case.

### 12.3 Display order (FlowCE `positive_first`, fmt §1, as precomputed keys)

**Main variable:** the command's variable; otherwise `x`, then `t`, then `θ`; otherwise the first
symbol in name order. `deg(n, mv)` and `xpow(n, mv)` are L7 leaves.

**Sums.** The terms are decorated with keys and sorted as flat tuples, with no `key=`.

| case | order |
|---|---|
| polynomial in `mv` with more than 2 terms | descending degree, the constant last |
| non-polynomial | descending key `x_power` = floor(60 × the rational exponent of `mv` in the term), others 0. So `2x^(3/2)-3x+6sqrt(x)` and `x^2*e^x-2x*e^x+2e^x`. |
| exactly 2 terms | the positive term first (`4-x^2`, `ln\|x-2\|-ln\|x+2\|`) |
| complex number | the real part first (`1+i*sqrt(3)`) |

- **Tie-breaks:** the term's `H`, then the id. `H` is platform independent, and ids are
  deterministic within a command.
- **Flip negated differences:** `-(P)·rest`, where P has a negative lead, prints as `(-P)·rest`.
  So `2x*cos(x)+(x^2-2)*sin(x)`.
- **A long polynomial over an integer** (text over 70 characters) is printed term by term
  (fmt §1.4).

**Products.**

- The pairs are split by the sign of the exponent into numerator and denominator.
- Factor rank, then tie-breaks:

  | rank | factor kind |
  |---|---|
  | 0 | numbers |
  | 1 | `π` |
  | 2 | variables and their powers |
  | 3 | `e^...` |
  | 4 | functions and sums |

  - **Trig factors:** the smaller argument first, then sin < cos < sec < csc < tan < cot.
  - **Polynomial factors:** by `poly_key`: lower degree, then smaller absolute constant, then a
    negative constant first. So `(x-2)(x+2)(x^2+4)`.
  - **Polynomials before non-polynomials:** `(x^2-2)*sin(x)`.
- `sum_content`: the rational content of a sum factor is pulled out:
  `e^(2x)(2sin(3x)-3cos(3x))/13`.
- The coefficient prints as `p*m/q`, so `x^3/6` and `3*x^5/40`, never `1/6*x^3`.
- The minus goes in front of a quotient: `-3/(16*(x-1))`. `-1·rest` prints as `-rest`.
- An exponent of ±1/2 prints as `sqrt`.

### 12.4 Names and special printing

| node | printed |
|---|---|
| `MUL(k, LN(u), 1, LN10, -1)` | `k*log(u)`. More generally, `LN10^-n` with LN factors whose positive integer exponents sum to n prints each as `log(u)^m`. Otherwise it prints raw (`ln(u)/ln(10)`). |
| pair `(E, u)` | `e^x`, or `e^(u)` |
| `MUL(k, u, 1/2)` / `(u, -1/2)` | `k*sqrt(u)` / `.../sqrt(u)` |
| `ASIN` / `ACOS` / `ATAN` | `asin(` / `acos(` / `atan(`. The renderer shows `arcsin`, as FlowCE does. |
| degree mode | Never by pattern. A trig node `f(v)` prints its argument as `v·180/π`, computed with the constructors, term by term; inverse-trig nodes are first replaced by `(π/180)·CALL(SYM('asin'), u)` (a print-only atom). Both maps are exact inverses of the builder's, so they survive `expand`, `normal_args` and F4 (§6.5). |
| `TRUE`, `FALSE` | `true`, `false` |
| `LT(a, b)`, `LE(a, b)` | `a<b`, `a<=b`; but when the main variable occurs in `b` and not in `a`, `b>a`, `b>=a`. So `x>3` prints `x>3`, and `3<x` also prints `x>3`. |
| `HOLD(m)` | the pairs of `m` in order, `b^e` joined by `*`, with no folding: `2^3*3^2*5` |
| `BIGO(u)` | `O(u)` |
| `SYM('C1')` | `C1` |
| `FLT(re, im)` | `fdec(re, 15)` (+ the imaginary part) |
| `NUM(a, b, d)` | `a/d`, `a/d+b/d*i`, `i`, `-i`, `3*i` |

### 12.5 Round-trip invariant (MUST)

For every corpus result and every fuzz case, in both angle modes: re-parsing `text(e)` through the
answer path of §7.1 (stages 3-5 and 7, then `g_eval` in inert mode with the answer's angle mode)
gives `e` again, in the same table. `inst` is never used for this, because it has no angle mode
and runs no commands. This is what makes text-only session state safe. Floats compare within
1e-14 relative. The only exception is `HOLD`, which re-parses to its value (`2^3*3^2*5` gives
360); the test compares values there.

### 12.6 The decimal line

- **When it is shown** (FlowCE `result_approx`, fmt §5.1):
  - only for an exact result with no free symbols;
  - never for integers, Gaussian integers, floats, lists or solution sets, messages, results of
    size >= 64, or results containing an unevaluated `sum(`;
  - never when the result contains `OO`, `UNDEF`, `TRUE`, `FALSE`, a sentinel (`DNE`, `DIVG`,
    `HOLD`) or a `CALL` (one scan of the result's nodes). So `limit(1/x^2,x,0)`, which gives `oo`,
    shows no decimal line;
  - never for a result holding a power kept whole (§6.1): `nprog` raises `Undefined` for it,
    since it overflows or underflows a float (`2^-100000` would print `0`). A logarithmic
    estimate would not give the exact, platform-identical digits this line promises, so the
    answer is shown exact only, like an integer, and `approx` keeps it exact.
- **How it is computed:**
  - an exact rational uses `dec10(p, q)` directly;
  - anything else uses `nev`, then `fdec10` on each part (`nrun` has already rejected nan and
    inf, §6.6);
  - a complex value prints as `a+bi`;
  - the whole computation runs inside a `try` in `PR.record`: any exception (`Undefined`,
    `OverflowError`, ...) means "no decimal line" and never reaches `R.go`.
- **Format:** 10 significant digits, rounded half-up. Scientific notation `d.dddE±n` when
  |x| >= 1e10 or |x| < 1e-4. `str(float)`, `round` and `%g` are never used. The digits are
  identical on the device and the desktop by construction [M]: tested exact on 20,000 random
  rationals.
- **Storage and visibility:** the line is computed before `K.reset()` and stored in the history
  entry. It is shown only while the entry shows its original text: after F4 the `≈` line hides,
  as in FlowCE.

```python
def dec10(p, q, nd=10):                                         #@L 7
    # p/q (q > 0) -> text with nd significant digits, half-up, integers only.
    if p == 0:
        return '0'
    s = ''
    if p < 0:
        s = '-'
        p = -p
    e = len(str(p)) - len(str(q))          # 10^e <= p/q < 10^(e+1), maybe e-1
    if e >= 0:
        if p < q * 10 ** e:
            e -= 1
    elif p * 10 ** (-e) < q:
        e -= 1
    k = nd - 1 - e
    if k >= 0:
        m, r = divmod(p * 10 ** k, q)
        den = q
    else:
        den = q * 10 ** (-k)
        m, r = divmod(p, den)
    if 2 * r >= den:
        m += 1
        if m == 10 ** nd:
            m //= 10
            e += 1
    dg = str(m)
    j = len(dg)
    while j > 1 and dg[j - 1] == '0':
        j -= 1
    dg = dg[:j]
    if e >= 10 or e < -4:                  # scientific: d.ddddE+-n
        t = dg[0]
        if len(dg) > 1:
            t = t + '.' + dg[1:]
        return s + t + 'E' + str(e)
    if e < 0:
        return s + '0.' + '0' * (-e - 1) + dg
    if len(dg) <= e + 1:
        return s + dg + '0' * (e + 1 - len(dg))
    return s + dg[:e + 1] + '.' + dg[e + 1:]


def fdec10(x, nd=10):                                           #@L 6
    # exact binary value of a double -> dec10 (math.frexp is native: 0 frames)
    if x == 0.0:
        return '0'
    m, ex = math.frexp(x)                  # x = m * 2**ex, 0.5 <= |m| < 1
    p = int(m * 9007199254740992.0)        # m * 2**53, exact
    ex -= 53
    if ex >= 0:
        return dec10(p * 2 ** ex, 1, nd)
    return dec10(p, 2 ** (-ex), nd)
```

Examples [M]: `1/3` gives `0.3333333333`, `22/7` gives `3.142857143`, `π` gives `3.141592654`,
`1/100000` gives `1E-5`, `9999999999.5` gives `1E10`, and `0.1+0.2` gives `0.3`.

---

## 13. 2D layout (CVDRAW)

> **Shipped implementation (2026-10-11).** The UI draws through `ti_draw`, not
> `ti_graphics` (`setColor` takes one positional argument on the EVO), with one
> 10-pixel font and 31 columns. The device semantics and the layout contract are
> in [notes/FASTBOOT.md](notes/FASTBOOT.md) and `shim/ti_draw.py`; where they
> differ from this section, they win.

### 13.1 Pipeline

```
answer text -> P.lex (L6) -> P.rpn (L7) -> level pre-pass -> measure (L3) -> place (L3)
            -> display list -> render (L3) -> ti_graphics
```

- One engine renders results and messages' math. In v1, history *inputs* are drawn as plain small
  1D text, and the edit line is a 1D text editor (§16.5).
- The answer text skips stages 4-6 (§7.1): `lex` sets `F_CALL` on calls, printer text has explicit
  `*`, and stored variables are not expanded. A bare top-level list (solutions, `x=1,x=2`) draws as
  a comma row without brackets; `O(x^6)` draws as a call.
- The same engine becomes the 2D editor later (§13.8).
- A text that fails to parse is drawn as plain text. A test parses and lays out every golden answer,
  including solve and taylor results, and fails if any of them falls back to plain text (§20.12).

### 13.2 Boxes

Boxes are flat tuples in a list `BX`, appended in postorder, so children always have smaller
indices:

```
(kind, w, asc, desc, lvl, a, b, c, payload, ti)
```

| field | meaning |
|---|---|
| `a`, `b`, `c` | child box indices, or -1 |
| row children | stored as `(start, count)` in a flat list `KID` |
| `payload` | text, a glyph code, or a style flag |
| `ti` | the RPN item's token index (§7.7), for future caret mapping |

| kind | built from | layout rule (fmt §9) |
|---|---|---|
| `TEXT` | number, name, operator glyph | Variables italic; numbers and function names upright. Float literals are drawn with at most 10 significant digits (§12.1). |
| `ROW` | `+ - * =`, commas, call arguments | Same-level operators flattened. `opgap` around binary operators. `*` is a centered dot, hidden (1 px gap) before a letter or `(`. |
| `FRAC` | `/` | Numerator and denominator lose their `P` parentheses. The bar sits on the math axis (asc/3), width `max(w) + 2·gap`. Same size as the parent. |
| `SUP` | `^` | The exponent at script level and loses its `P`. Its baseline puts the bottom at 45% of the base's ascent. `e^u` draws as an italic e with a superscript. |
| `SQRT` | `sqrt(u)` | Width `rad + content + 2`; a stroked radical sign (§13.7) |
| `NROOT` | `surd(u,n)` | A radical with the index in script font |
| `PAREN` | a `P` item kept by its parent | Stretched delimiters, drawn as strokes when taller than 1.15 × the font |
| `ABS` | `abs(u)` | Vertical bars |
| `CALL` | other calls | An upright name, `(`, arguments, `)`; `asin` drawn as `arcsin` |
| `INTEG` | `integrate(f,x)` / `(f,x,a,b)` | A stroked ∫, bounds at script level, then `f`, a gap, `d` and `x` |
| `DERIV` | `diff(f,x)` | `d/dx` as a fraction on the axis, then `f` (parenthesized if it is a row) |
| `SUMB` | `sum(f,k,a,b)` | A stroked Σ, `k=a` below and `b` above |
| `LIMB` | `limit(f,x,a)` | `lim` with `x→a` below |
| `LISTB` | `[...]` | Brackets |

The special calls must have exactly the FlowCE argument counts; any other count draws as a plain
`CALL`.

### 13.3 Levels and metrics

- **Script levels.** The RPN is postorder, so a child is measured before anyone knows that it sits
  in an exponent. A **pre-pass** fixes this:
  1. A stack builds `parent[i]` and `role[i]`.
  2. One reverse loop sets `level[i] = level[parent[i]] + 1` for exponent and bound roles.

  No recursion is needed (depth-first proposal §6.3).
- **Font sizes.** `ti_graphics` offers only a few font sizes (PROBE7). Level 0 uses the large font,
  and levels 1 and above use the small one. A script of a script stays small.
- **Metrics per font,** in a table filled from PROBE7. The formulas are FlowCE's (fmt §9.1):

  | metric | value |
  |---|---|
  | `adv` | 0.5 s |
  | `opgap` | 0.22 s |
  | `bar` | 1 px (2 px at s >= 26) |
  | `gap` | max(2, 0.13 s) |
  | `rad` | 0.56 s |
  | `isw` | 0.5 s |

  Text widths come from `string_size` (native), cached per string for the command.
- **Fallback** if `string_size` is missing: FlowCE's fixed metrics, big `{adv 8, asc 14, desc 4}`
  and small `{adv 6, asc 9, desc 3}`.

### 13.4 Measure and place (sketch)

```python
def measure(code, lvl):                                         #@L 3
    BX = []
    KID = []
    st = []                                  # stack of box indices
    for i in range(len(code)):
        it = code[i]
        k = it[0]
        if k == 'n' or k == 's':
            st.append(leaf(BX, it, lvl[i]))                  # L5: TEXT box, metrics
        elif k == 'P':
            st.append(boxn(BX, PAREN, (st.pop(),), lvl[i], it))   # L5
        elif k == 'o' and it[1] == '/':
            b = unparen(BX, st.pop())                        # L4: drop a P wrapper
            a = unparen(BX, st.pop())
            st.append(boxn(BX, FRAC, (a, b), lvl[i], it))
        elif k == 'o' and it[1] == '^':
            e = unparen(BX, st.pop())
            st.append(boxn(BX, SUP, (st.pop(), e), lvl[i], it))
        elif k == 'o':                                       # + - * = neg ! ...
            row_op(BX, KID, st, it, lvl[i])                  # L4: flattens rows; calls boxn (L5)
        elif k == 'F':
            args = st[len(st) - it[2]:]
            del st[len(st) - it[2]:]
            st.append(call_box(BX, KID, it, args, lvl[i]))   # L4: INTEG/DERIV/...; calls leaf (L5)
        else:                                                # 'L'
            args = st[len(st) - it[1]:]
            del st[len(st) - it[1]:]
            st.append(list_box(BX, KID, args, lvl[i], it))
    return BX, KID, st[-1]
```

`place(BX, KID, root, x, y)` (L3) walks an explicit stack of `(box, x, baseline)` top-down. It
emits the **display list**, a flat list of flat tuples:

| item | meaning |
|---|---|
| `('t', x, y, text, font, style)` | text |
| `('l', x1, y1, x2, y2)` | line |
| `('r', x, y, w, h)` | filled rectangle |
| `('g', glyph, x, y, w, h)` | stroked glyph |

`render(dl, dx, clip)` (L3) draws the list with `ti_graphics` calls only. It applies the horizontal
scroll offset `dx` and the clip rectangle. Colors come from the palette (§16.8).

### 13.5 Fitting and scrolling

- Try the levels from largest to smallest. Width scales linearly, so the search jumps straight to
  an estimate.
- If the answer is still too wide at the smallest level, it **scrolls** horizontally with
  left/right (D5) and shows the edge markers `◀` / `▶`. v1 has no wrapping.
- **Boxes:**
  - hero: 300 px wide, about 110 px tall;
  - history result: 300 × 36 px (§16.1).
- **FlowCE's robustness caps** apply: a nesting deeper than 24, or more than 400 RPN items, is
  drawn as plain text.

### 13.6 Decorations (view only, never part of the answer text)

| decoration | placement |
|---|---|
| `+ C` | on the answer's row, right after it and spaced like its operators, in the answer's color, when the record flag `F_PLUSC` is set (§7.9): the view lays out the answer text with `+C` appended, so alignment and scrolling count it (MATHPRINT.md 0.10, 7.1). The history text stays the bare answer |
| `≈ value` | under the hero, from the stored decimal |
| form label | `exact`, or the current form name, at the top right of the status row, left of the modifier chip (v1.0.0; it was a footer chip with `F4`) |
| `≈` prefix | before an answer that is itself a numeric fallback (record flag `F_APPROX`) |

### 13.7 Glyphs

- `π`, `√`, `∫`, `Σ`, `∞`, `≈`, `≤`, `≥`, `≠`, `→`, `θ` and the multiplication dot are drawn as
  strokes from a small vector table: tuples of line segments in a unit box, scaled per font.
  This needs no font support.
- If an EVO probe confirms that `ti_draw.draw_text` renders these code points in a usable
  size, the table can map some glyphs to text instead. PROBE7 targets the older graphics API.
- Source files stay ASCII. Glyph code points are built with `chr()` in CVDRAW.

### 13.8 Hooks for the future 2D editor

- Every RPN item, and so every box, keeps its token index. A token keeps its source span.
- A caret position in the text therefore maps to a box. A 2D editor can reuse `measure` and
  `place` unchanged and add structure-aware keys (cat §5.2).

---

## 14. Answer forms (F4, CVFORM)

FlowCE fmt §6 is the reference. The forms key is F5 (and < >) since the F-key row of
MATHPRINT.md 0.13; this section calls it F4, its key until then.

**Orders.** These are data in CVFORM; the original answer is position 0, labelled `exact`.

| result kind | cycle after the original |
|---|---|
| exact number (it has a `≈` line) | decimal, simplified, one fraction, factored, expanded |
| any other expression | simplified, one fraction, factored, expanded, decimal |
| expression with sin, cos or tan (optional, T2) | trig combined, in terms of sin, in terms of cos, then the plain order |

**Operations.** Each form is computed from the **original** answer text, re-parsed, never from the
previous form. The re-parse uses the answer path of §7.1 (no context expansion, inert `g_eval`,
the entry's angle mode), so a variable stored later never changes an old entry's forms:
`expand((a+1)^2)`, then `a=3`, then F4 still shows forms of `a^2+2*a+1`.

| form | operation |
|---|---|
| simplified | `g_simplify` (explicit mode) |
| one fraction | `together` |
| factored | `g_factor` |
| expanded | `g_expand` |
| decimal | `approx` |
| trig forms | `trigsin`, `trigcos`, `tlin` rule sets |

**Opaque function nodes.** For the algebra forms, non-arithmetic function nodes are first replaced
by fresh symbols `_f1`, `_f2`, ... and put back afterwards (FlowCE `function_nodes`). "Factored"
therefore factors the algebra around `ln|...|`.

**When a form is offered.** These follow FlowCE fmt §6.4 and are implemented as predicate
functions in CVFORM:

| form | skipped when |
|---|---|
| simplified | the result has radicals, or the text is not strictly shorter |
| one fraction | the top level is not a sum with a denominator |
| factored | the top level is not a product of 2 or more variable factors or a power of a sum, or factoring added radicals |
| expanded | the top level is not a sum that still contains a sum factor |
| decimal | there is a variable exponent, the size is over 40, or there is no irrational constant |
| any form | the text is 90 characters or longer with no top-level `+`/`-` |
| all forms | unevaluated `integrate`/`sum`/`limit` results, messages |

**Cycling.**

- Each F4 press computes the next offered form that is **new in this round**. "New" means its
  sorted character multiset differs from every text shown earlier in the round, so `2cos(x)sin(x)`
  equals `2sin(x)cos(x)`.
- Computed forms are cached in `HIST[i].forms` as `(name, text)`.
- After the last form, the cycle returns to the original.
- F4 runs as `R.go(('form', i))`, so [clear] cancels it and MemoryError is handled. Either one
  returns to the original form.
- The entry's displayed output text **is replaced** by the form, so Ans uses the form shown
  (FlowCE). The `≈` line hides unless position 0 is shown.

---

## 15. Command registry, catalog and help

### 15.1 Registry (CVRUN, resident, about 2 KB)

```python
# name: (module, generator, min args, max args, flags, rule sets compiled at start)
CMDS = {
    'simplify':  ('norm', 'g_simplify', 1, 1, 0, ('trigsin', 'trigcos', 'tlin', 'lncollect')),
    'expand':    ('norm', 'g_expand', 1, 1, F_NOAUTO, ()),
    'factor':    ('fact', 'g_factor', 1, 2, F_NOAUTO, ()),
    'together':  ('norm', 'g_together', 1, 1, F_NOAUTO, ()),
    'approx':    ('norm', 'g_approx', 1, 1, F_NOAUTO, ()),
    'solve':     ('solve', 'g_solve', 1, 2, F_SOLN, ()),
    'diff':      ('diff', 'g_diff', 1, 3, F_ALWAYSAUTO, ('trigsin', 'trigcos')),
    'integrate': ('int', 'g_integrate', 1, 4, 0, ('itab',)),
    'limit':     ('lim', 'g_limit', 2, 4, 0, ()),
    'taylor':    ('ser', 'g_taylor', 1, 4, F_NOAUTO, ()),
    'partfrac':  ('int2b', 'g_partfrac', 1, 2, F_NOAUTO, ()),
    'sum':       ('sum', 'g_sum', 2, 4, 0, ()),
    'riemann':   ('sum', 'g_riemann', 5, 6, 0, ()),
    'desolve':   ('ode', 'g_desolve', 1, 3, 0, ()),
    'grad':      ('diff', 'g_grad', 1, 2, 0, ()),
}
ALIAS = {'int': 'integrate', 'd': 'diff', 'deriv': 'diff', 'lim': 'limit',
         'series': 'taylor', 'ratnormal': 'together', 'dsolve': 'desolve',
         'gradient': 'grad', 'evalf': 'approx'}
DEPS = {'norm': ('poly', 'rules', 'ident'), 'fact': ('poly', 'norm'),
        'solve': ('poly', 'norm', 'fact', 'rules'), 'diff': ('norm', 'poly', 'rules', 'ident'),
        'int': ('itab', 'rules', 'diff', 'norm', 'poly'), 'lim': ('ser', 'diff', 'norm', 'poly'),
        'ser': ('norm', 'poly'), 'int2': ('poly', 'norm'), 'int2b': ('poly', 'norm', 'fact'),
        'int3': ('diff', 'norm', 'poly'), 'int3b': ('norm', 'poly'),
        'def': ('int',),                 # soft: 'solve', then 'lim', one phase at a time (11.3)
        'sum': ('poly', 'norm', 'lim'),
        'ode': ('int', 'poly', 'norm')}  # soft: 'solve' after the integration phase (11.4)
PARTS = {'rules': ('rules', 'rulesb'), 'poly': ('poly', 'polyb', 'polyc'),
         'norm': ('norm', 'normb'), 'fact': ('fact', 'factb'),
         'solve': ('solve', 'solveb', 'solvec'), 'ser': ('ser', 'serb'),
         'lim': ('lim', 'limb'), 'int': ('int', 'intb'), 'def': ('def', 'defb'),
         'sum': ('sum', 'sumb'), 'ode': ('ode', 'odeb', 'odec')}   # keys, section 4.3
MACROS = {'polararea': (4, 4, 'integrate((#1)^2/2,#2,#3,#4)'),
          'paramarea': (5, 5, 'integrate((#2)*diff(#1,#3),#3,#4,#5)'),
          'arclen':    (4, 6, None)}     # None: arity-dependent macro built in code
HINT = {'diff': 'diff(f,x,[n])', 'integrate': 'integrate(f,x,[a,b])',
        'limit': 'limit(f,x,a,[dir])', 'solve': 'solve(eq,[x])',
        'purge': 'purge(x,...)'}         # ... one per command
```

- **Generator signature:** `g_name(args, ctx)`. `args` is a tuple of evaluated ids. `ctx` is
  `(angle, mainvar, approx flag)`.
- **Dependencies:** `R.go` preloads the module's family and the closure of `DEPS` (§18.4) and
  compiles the listed rule sets (§9.4). A definite `integrate` (4 arguments) also preloads `def`.
  Soft dependencies (the comments in `DEPS`) are loaded by the generator when its phase starts, so
  that the phase eviction of §18.5 can free the earlier phase first.
- **The result** of an `F_SOLN` command is an `LST` of equations, or a sentinel (§10.5).
- **Flags:**

  | flag | meaning |
  |---|---|
  | `F_NOAUTO` | skip the default simplify path |
  | `F_ALWAYSAUTO` | always run it |
  | `F_SOLN` | the result is a solution list |

- `limit` accepts both `limit(f,x,a,[dir])` (giac) and `limit(f,x=a,[dir])` (FlowCE catalog). `dir`
  is `1` for the right side and `-1` for the left.
- `taylor` accepts both `taylor(f,x=a,[n])` and `series(f,x,a,n)`.

### 15.2 v1 command list

| command | aliases | signature | tier |
|---|---|---|---|
| `simplify` | | `simplify(e)` | T1 |
| `expand` | | `expand(e)` | T1 |
| `factor` | | `factor(e,[x])` | T1 |
| `together` | `ratnormal` | `together(e)` (one fraction) | T1 |
| `solve` | | `solve(eq,[x])`, `solve([eqs],[vars])` | T1 |
| `approx` | `evalf` | `approx(e)` | T1 |
| `purge` | | `purge(x,...)`: forget stored variables and functions (§7.9) | T1 |
| functions | | `sqrt surd abs ln exp sin cos tan sec csc cot asin acos atan`, `log(u,[b])` (base 10, or base b) | T1 |
| relations | | `= != < <= > >=` (TEST picker, §16.7); a decided relation gives `true`/`false` | T1 |
| `diff` | `d`, `deriv` | `diff(f,x,[n])` | T2 |
| `integrate` | `int` | `integrate(f,x,[a,b])` | T2 (infinite bounds: T3) |
| `limit` | `lim` | `limit(f,x,a,[dir])` | T2 |
| `taylor` | `series` | `taylor(f,x=a,[n])` | T2 |
| `partfrac` | | `partfrac(e,[x])` | T2 |
| `sum` | | `sum(f,k,a,b)` | T3 |
| `riemann` | | `riemann(f,x,a,b,n,[left\|right\|mid\|trap])` | T3 |
| `desolve` | `dsolve` | `desolve(eq or [eq,conds],[y])` | T3 |
| `grad` | `gradient` | `grad(f,[x,y,z])` | T3 |
| `polararea`, `paramarea`, `arclen` | | macros (§15.1) | T3 |
| optional, if space allows | | `sinh cosh tanh floor ceil round sign re im conj arg subst numer denom csolve ifactor gcd lcm` | opt |

### 15.3 Catalog (CVCAT, lazy, about 7 KB)

```python
# (signature, insert, one-line help, example, categories)
CAT = (
    ('diff(f,x,[n])', 'diff(', 'Derivative of f with respect to x (n-th order).',
     'diff(x^3,x,2)', 'C'),
    ('integrate(f,x,[a,b])', 'integrate(', 'Antiderivative, or definite integral from a to b.',
     'integrate(x*sin(x),x)', 'C'),
    ('solve(eq,[x])', 'solve(', 'Exact solutions of an equation (real).',
     'solve(x^2-x-1=0,x)', 'A'),
    # ...
)
```

- **Categories:** `A` algebra, `C` calculus, `T` trig, `S` sums and series, `D` differential
  equations, `V` vectors, `N` numbers, `F` functions and symbols.
- **The menu tabs** are Algebra (A), Calculus (C), Trig (T), More (S, D, V, N, F) and All (A-Z);
  F1-F4 open the first four, 2nd F1 the All tab (MATHPRINT.md 0.13).
  The help text is written fresh: FlowCE's English catalog has gaps (cat §7.4).
- **Templates and labels** follow the TI-Nspire (MATHPRINT.md 0.10, 3): nothing is
  prefilled. In MathPrint a command with a 2D template inserts that template with every box
  empty (`diff(` → d/d□(□) as `diff(,)`, `integrate(` → `integrate(,,,)`, `limit(` →
  `limit(,,,)`, `log(` → `log(,)`) and the caret in the first box in drawn order; any other
  command inserts one empty box per required argument (FlowCE's required-argument rule, cat
  §1.3). (v1.0.0 removed the Classic 1D entry setting; MathPrint is the only editor.)

### 15.4 Help line and help (2nd F5)

- **Help line** (`ui.ARGPH` and `draw.ARGS`, in the UI view pack). Since the QPL changes it
  explains the argument the caret is in and whether it is required ("Expr. to simplify
  (required)", "Base (empty: 10)"), for every command and 2D slot; it was the
  command's signature (MATHPRINT.md §0.11).
- **2nd F5** (F5 until MATHPRINT.md 0.13) loads CVCAT and shows the full entry for the command
  around the caret: its name (as the Nspire's menus show it), help, example. ENTER on the help
  screen pastes the example. With no command at the caret, it shows the key summary page
  (FlowCE *Shortcuts*).

---

## 16. UI architecture (CVUI, CVDRAW, CVMENU)

> **Shipped implementation (2026-10-11).** The shell boots without the engine:
> `ui.engine()` loads it on the first ENTER or a menu that needs it, and boot and
> engine load times show in the status row. Drawing uses `ti_draw` on a 320 x 210
> screen with the row layout in `src/ui.py`. See
> [notes/FASTBOOT.md](notes/FASTBOOT.md); where it differs from this section, it
> wins.

### 16.1 Screen layout

All coordinates live in one table in CVUI. PROBE7 confirms the drawable size, assumed to be
320 × 210.

```
y   0..13   status strip: left RAD|DEG; middle status text (Calculating..., "fill in the
            empty slot", "Stored; purge(name) deletes" for a record with F_PURGEHINT,
            section 7.9); right the focused answer's form label (exact, decimal, ...; gray)
            and the modifier chip 2nd | a | A | a-lock | A-LOCK. A status message that needs
            the room hides the form label until it clears (v1.0.0)
y  14..157  stage: history entries, newest at the bottom; the newest entry is drawn as the
            HERO (large, with the footer "≈ value") while the edit line is empty
y 158..169  help line: signature of the command around the caret (gray, small)
y 170..189  edit line: 1D text, caret, horizontal scroll with edge markers
y 190..209  F-key bar: 5 tabs x 64 px: Alg | Calc | Trig | More | Forms; while the 2nd
            chip is lit: All | Tmpl | Test | Setup | Help (MATHPRINT.md 0.13). The row is
            repainted (one fill, the four gaps, the labels) only when the layer changes
```

- **A history entry** is the input as small gray 1D text on the left, then the result
  right-aligned in 2D at the history size (box 300 × 36). A message entry is drawn in the secondary
  color, clipped with `...`.
- **The hero** (box 300 × 110) is the newest entry: input small, result large and centered, and the
  footer. When the user starts typing, it becomes a normal history row (FlowCE behavior).

### 16.2 Event loop (`casevo.py`, depth 0)

```python
import ti_system as TS
import node as K                  # leaf-first: each later import only binds loaded modules
import alg as A
import parse as P
import printer as PR
import run as R
import draw as D
import ui as U
U.boot()                          # inject natives (K.ESC, K.MEMFREE, R.BUSY), buffers, draw
while True:
    try:
        k = TS.wait_key()
        a = U.key(k)              # L1: editor, menus; returns None, U.QUIT or a job tuple
        if a is U.QUIT:
            break
        if a is not None:         # U.key has emptied CACHE before returning a job (16.3)
            r = R.go(a)           # L1: runner + trampoline (section 10.4); never raises,
            U.show(a, r)          # except KeyboardInterrupt after its reset
    except MemoryError:
        U.panic(0)                # L1: drop display caches, gc.collect(), message, redraw
    except KeyboardInterrupt:
        U.panic(1)
    except RuntimeError:
        U.panic(2)
    except Exception:             # a UI bug (layout, menus): keep the session alive
        U.panic(3)
```

There is no `main()` function: it would waste a frame. The entry module is never imported by
others. Every `Exception` and `KeyboardInterrupt` is caught here, so the session (history, Ans,
variables) survives any bug; only a `U.panic` that itself fails can end the program.

### 16.3 UI state (CVUI module globals)

| name | meaning |
|---|---|
| `LINE`, `CUR`, `XOFF` | edit text, caret index, horizontal scroll of the edit line |
| `MOD` | 0 none, 1 2nd, 2 alpha, 3 alpha-lock lowercase, 4 alpha-lock uppercase |
| `MODE` | `EDIT` or `HIST` |
| `SEL` | the selected history index in `HIST` mode |
| `SELC` | the selected cell of that entry: 0 the input (left), 1 the answer (right; v1.0.0) |
| `HERO` | True while the newest entry is shown large (the edit line is empty in `EDIT` mode) |
| `DX` | horizontal scroll offset of the shown answer |
| `ENTRYPOS` | ENTRY recall position |
| `DIRTY` | bit flags: `D_LINE`, `D_STAGE`, `D_STATUS`, `D_BAR` |
| `CACHE` | `{(entry, form position, size): (display list, width)}`: at most 5 entries and 4 KB (estimated as 24 B per display-list item; the oldest entry goes first). `U.key` empties it before it returns a job, so it holds nothing while `R.go` runs (§18.1). |

### 16.4 Keys and modifier state

The codes are TI-BASIC `getKey` codes: row and column of the key matrix. [V] means verified by
PROBEK; the rest are the standard TI-84 codes [D]. The TI-84 Evo moved keys within that matrix
[T]: TI's Evo key map (education.ti.com/84evo-key-map) puts x^n left of sin (51), the fraction
template on the CE's apps key (42), ÷ × − + one row up (55, 65, 75, 85: alpha H, M, R, W, as on
the CE matrix) and a new < > key in the CE's + place (95). CalcPlex, which runs on the Evo, uses
the same plain codes. TI's Evo keypad notes add xRoot as 2nd x^n and make < > switch
representations (fraction and decimal). The 2nd and alpha layers stay positional. PROBEK2
confirms the rest.

| code | key | plain | 2nd | alpha |
|---|---|---|---|---|
| 11-15 [V] | y= window zoom trace graph (F1-F5) | menu tabs Algebra, Calculus, Trig, More; F5 forms (nothing without an answer) | All tab, template picker, TEST picker, setup, help (the row relabels while 2nd is lit) | as plain |
| 21 [V] | 2nd | modifier | | |
| 22 [V] | mode | setup (2nd F4) | **quit** | |
| 23 [V] | del | backspace (`ans()` as one unit) | – | |
| 24, 26 [V] | left, right | caret, or scroll the answer (D4) | home, end | |
| 25, 34 [V] | up, down | history navigation (§16.6) | page | |
| 31 [V] | alpha | modifier; alpha alpha or 2nd alpha = lock | | |
| 32 | X,T,θ,n | `x` | `t` | `theta` |
| 41 [V] | math | menu on the tab used last (`ui.TAB`; Algebra at first) | TEST picker: `= != < <= > >= !` (D16, §16.7; also 2nd F3) | `a` |
| 42 | fraction template (Evo; apps on the CE) | fraction template with term capture, `(x)/(□)` | template picker (MathPrint; also 2nd F2) | `b` |
| 43 | prgm | – | – | `c` |
| 44 [V] | vars | Ans, variables, functions | | |
| 45 [V] | clear | clear / back / hide hero; in the history, delete the selected entry; cancel while computing | | |
| 51 | x^n (Evo; x⁻¹ on the CE) | exponent box `^(□)` | `surd(□,)` (xRoot) | `d` |
| 52, 53, 54 | sin cos tan | `sin(` `cos(` `tan(` | `asin(` `acos(` `atan(` | `e` `f` `g` |
| 55 | ÷ (Evo; ^ on the CE) | `/` | `pi` | `h` |
| 61 | x² | `^(2)` | `sqrt(□)` | `i` |
| 62 | , | `,` | `E` (EE) | `j` |
| 63, 64 | ( ) | `(` `)` | `{` `}` | `k` `l` |
| 65 | × (Evo; ÷ on the CE) | `*` | `e` | `m` |
| 71 | log | `log(` | `10^(` | `n` |
| 72-74 | 7 8 9 | digits | | `o` `p` `q` |
| 75 | − (Evo; × on the CE) | `-` | `[` | `r` |
| 81 | ln | `ln(` | `e^(` | `s` |
| 82-84 | 4 5 6 | digits | | `t` `u` `v` |
| 85 | + (Evo; − on the CE) | `+` | `]` | `w` |
| 91 [V] | sto→ | `=>` | | `x` |
| 92-94 | 1 2 3 | digits | | `y` `z` `theta` |
| 95 | < > (Evo; + on the CE) | the answer's forms, as F5 (the Evo key switches representations) | | |
| 102 | 0 | `0` | menu, All tab (catalog; also 2nd F1) | space |
| 103 | . | `.` | `i` | `'` (prime; D6) |
| 104 [V] | (−) | `-` | `ans()` | |
| 105 [V] | enter | evaluate | ENTRY (recall inputs) | |

- **Modifiers.** 2nd and alpha are one-shot. A locked alpha types lowercase; 2nd toggles the case
  while alpha is locked (FlowCE). The status chip shows the state.
- **Dispatch** goes through dict tables `code -> text or action code` (one per modifier), then one
  `if/elif` chain over the action codes in `U.key`. There is no function per key, which saves
  frames and code.
- **MathPrint** (the default entry; docs/notes/MATHPRINT.md 2): `U.edkey` handles the editing
  keys. Table texts ending in `(` are closed at once (`sin(□)`), `)` steps over a closer or
  closes the nearest visible group, 42/51/61 and 2nd 51 insert templates, and DEL, the arrows and
  up/down follow the 2D caret map. It is the only editor since v1.0.0 (the `Entry: Classic`
  setting is gone); a line over the layout caps, out of memory or after a panic is still edited
  flat (MATHPRINT.md 5.3), which is not a user mode.

### 16.5 Editor (1D, FlowCE habits, cat §5)

- **Insert:** `LINE = LINE[:CUR] + t + LINE[CUR:]`. A function key inserts `name(`. The line is at
  most 256 characters.
- **Leading-operator rule.** On an empty line with a result available (hero shown, or an entry
  selected), the keys `+ − × ÷ ^ x² x⁻¹ sto→` insert `ans()` first. `(−)` is always a minus sign.
- **ENTER:**
  1. **Empty-slot check** (cat §1.3): `(,`, `,,`, `,)`, or `()` after a known function, or a line
     ending in an operator or `(`, moves the caret there, shows `Fill in the empty box`, and does
     not evaluate.
  2. **Empty line:** re-evaluates the last input (TI habit).
  3. **Otherwise** returns `('eval', LINE)`. The history stores the line with autoclose applied.
- **ENTRY** (2nd ENTER) recalls earlier inputs, one further back per press, while the line still
  equals the last recall.
- **Help line.** `ui.argpos` finds the slot at the caret (the 2D caret map, or a backward scan
  with a paren-depth counter) and `ui.arghelp` its argument help (MATHPRINT.md §0.11).

### 16.6 History, hero and navigation

| key | in `EDIT` mode | in `HIST` mode |
|---|---|---|
| up | enter `HIST` mode, selecting the newest entry's answer | previous entry (2nd: 5) |
| down | – | next entry (2nd: 5); past the newest, back to `EDIT` |
| left/right | move the caret when the line is non-empty; scroll the hero when it is empty (D4) | left selects the **input** cell, right the **answer** cell (TI-Nspire); a selected answer wider than the view scrolls first (right to its end, left back to its start, then left selects the input) |
| ENTER | evaluate (§16.5) | copy the selected cell at the caret, then return to `EDIT`. An answer is wrapped in `(...)` unless it is a single atom: a name, an unsigned number without `/`, or one call `f(...)` (never with its `+ C`). So `2/3` pasted after `x^` gives `x^(2/3)`, and `x=2` pasted after `3*` gives `3*(x=2)`. An input comes back as 2D text, as ENTRY gives it; a message entry always gives its input. |
| 2nd ENTER | ENTRY recall | as ENTER |
| F5, < > | forms of the hero | forms of the selected entry |
| clear | clear the line; on an empty line, hide the hero | delete the selected entry (input and answer) from the history and select the older one, or the newer one if it was the oldest; an empty history goes back to `EDIT`. Ans and variables are kept (v1.0.1, MATHPRINT.md 0.14) |

The selection band covers only the selected cell (v1.0.0; it was the whole row).

The stage scrolls so that the selected entry stays visible.

### 16.7 Menus (CVMENU; modal screens with their own `wait_key` loop at L2)

**Command menu** (F1-F4 open its first four tabs, 2nd F1 and 2nd 0 the All tab, `math` the tab
used last; MATHPRINT.md 0.13):

- Tabs Algebra / Calculus / Trig / More / All. `left`/`right` switch tabs; the tab shown is
  remembered in `ui.TAB` for the next `math`.
- Rows show the signature and the one-line help (CVCAT). `up`/`down` select, `1`-`9` pick, and
  alpha letters filter by prefix (search).
- **ENTER** inserts the template, with the caret in the first slot. FlowCE's action rule
  (cat §1.4):
  - with the caret at the end of a non-empty line, `solve factor expand simplify partfrac
    integrate diff limit taylor` wrap the whole line as the first argument;
  - on an empty line with a result available, they apply to `ans()`.
- `clear` or F1 closes the menu.

**TEST picker** (2nd math or 2nd F3, D16): a one-row menu `=  !=  <  <=  >  >=  !`, as the TI-84 TEST
menu. `1`-`7` or left/right and ENTER insert the operator at the caret; `clear` closes it. It lives
in the `menu` part with the F1 menu.

**vars** (v1.0.0; F2 was recall, then the history scroll, now the Calculus tab; up scrolls the
history, §16.6): `Ans`, `name = value` for
each variable, and the defined functions. ENTER inserts `ans()` or the name.

**Setup** (2nd F4, also `mode`):

- Angle RAD/DEG: toggled by ENTER or left/right, applied at once. (v1.0.0 removed the theme and
  the Classic entry rows.)
- Clear history, Clear variables: each asks for confirmation.
- About: version, `gc.mem_free()`, the loaded modules.

**F5 forms** (§14). **2nd F5 help** (§15.4).

When a menu is closed, CVMENU, CVMENUB, CVCAT and CVCATB are evicted if memory is low (§18.5).

Menu screens run at L2 and draw through `D.measure`, `D.place` and `D.render` (L3) directly, never
through `D.layout` (L2), so that every call edge goes down a level (§17.1).

### 16.8 Palette

One light palette (`draw.COLORS`; v1.0.0 removed the Night theme, its setting and the unused
slots), drawn with `ti_draw.set_color(r, g, b)`:

| slot | color | used for |
|---|---|---|
| BG | `#F7F8FA` | stage |
| INK | `#111419` | results, edit line |
| SUB | `#6C7581` | inputs, hints, `≈`, messages, the form label |
| LINE | `#DBE0E7` | separators, empty boxes |
| ACC | `#245CCC` | caret, chip text, F-key labels |
| ACCSOFT | `#E2EAFA` | selected cell, F-key tabs |

### 16.9 Redraw policy

- **Edit keys** redraw only the edit line, the help line and the status chip: a few `fill_rect` and
  `draw_text` calls.
- **Full redraws** happen only after an evaluation, F5, a history move or cell change, or a menu
  closing. The 2nd and alpha keys repaint the status row, and the F-key row only when the layer
  changes (2nd on or off).
- **Display lists** are cached per visible entry (`CACHE`, §16.3), so scrolling history does not
  lay out again. The cache is capped at 4 KB and emptied before every computation, so it never
  competes with the working set.
- Each region is cleared with `fill_rect` in BG, then drawn.

### 16.10 Busy indicator, cancel and errors

- **Busy.** `R.BUSY = U.busy` (L2). The driver calls it every 512 steps. After 0.4 s
  (`time.monotonic` if PROBE6 finds it, otherwise a step count), it draws `Calculating` with dots
  animating at 4 Hz in the status strip.
- **Cancel.** `K.ESC = ti_system.escape` if PROBE6 shows that it reports [clear] on the EVO. That is
  a native call at 0 frames, so it can be used anywhere. Otherwise, a 1-line Python adapter
  `esc()` returns `get_key() == 45`.
  - The adapter costs 1 frame, so polls happen only at L1-L4: the driver and plain loops, never
    `mk`.
  - `get_key` consumes keys typed during a computation; that is acceptable.
  - A cancel shows `Interrupted`, and a cancelled F4 returns to the original form.
- **Errors.**
  - `R.go` turns every computation error into a record: `Interrupted`, `Out of memory`,
    `Expression too complex`, `undefined`, `internal error: <type>`, or a CAS message. It resets
    the node table on every path before it builds a message (§10.4).
  - UI-level `MemoryError`, for example while laying out a huge answer, is caught in the entry loop
    by `U.panic`. It drops `CACHE`, calls `gc.collect()`, draws the answer as clipped plain text,
    and shows the message. Any other UI exception gets the same treatment, with the message
    `internal error` (§16.2).

---

## 17. Frame budget

### 17.1 Layers

The **level** of a function is the deepest device depth at which it may run. Callers must have a
smaller level (§17.3).

| L | layer | evaluation path | UI path | may call |
|---|---|---|---|---|
| 0 | entry | `CAS` body: imports and the event loop | the same | L1 |
| 1 | runner / dispatch | `R.go` (runner and trampoline) | `U.key`, `U.show`, `U.boot`, `U.panic` | >= L2 |
| 2 | orchestration | all `g_*` generators; `R.start` (returns `(code, ctx)`, never a generator), `PR.record`, `msg_rec`, `evict_all` | `U.busy`; menu screens (`M.*`, which call L3 drawing directly); editor helpers; `D.layout`, `D.draw_entry` | >= L3 |
| 3 | algorithms | `diff` fold, `subst`, `expand`, `normal`, `series_fold`, factor and solve loops, `RU.match`, `RU.rset`, `RU.guard_ok`, quadrature, `nev`, `P.tokens`, `PR.text`, `R.need`, `R.drop` | `D.measure`, `D.place`, `D.render` | >= L4 |
| 4 | helpers | `inst`, `K.keep`, `check`, `view`, `rebuild`, `nprog`, `nrun`, `PR.items`, polynomial drivers, `ps_*` series ops, Gauss-Jordan | `row_op`, `call_box`, `list_box`, `unparen` | >= L5 |
| 5 | constructors | `mul_`, `fn_`, `rel_`, `linear`, `quadratic`, `split_const`, `tcode`, `expand_names`, complex helpers (`cpow`, ...), polynomial kernels that call | `D.leaf`, `D.boxn`, metrics | >= L6 |
| 6 | sum constructor, lexer | `add_`, `neg_`, `absn`, `num`, `fdec10`, `lex`, `ti_rewrite`, `ti_implicit` | `lex` | L7 |
| 7 | leaves | `mk`, number kernels, `tiefix`, `negfirst`, `rootsplit`, `release`, `free_of`, `postorder`, `classify`, `simplify_candidate`, `rpn`, `dec10`, `deg`/`xpow` keys, `scoped`, polynomial leaf loops (`prem`, `pcont`, `peval`) | `rpn`, `classify` | builtins and natives only |
| 8 | test budget | nothing planned | | |
| 9-10 | device reserve | unmeasured native, dunder and import costs | | |

### 17.2 Deepest planned paths

| scenario | chain | max |
|---|---|---|
| antiderivative check | 0 loop > 1 `R.go` > 2 `g_check` > 3 `diff` > 4 `inst` > 5 `mul_` > 6 `add_` > 7 `mk` | 7 |
| table or identity rewrite | 1 > 2 `g_rewrite` > 3 `match` > 4 `check` > 5 `linear` > 6 `add_` > 7 `mk` | 7 |
| rule guard | 1 > 2 `g_rewrite` > 3 `guard_ok` > 4 `inst` > 5 `rel_` > 6 `add_` > 7 `mk` | 7 |
| numeric guard | 1 > 2 `g_rewrite` > 3 `guard_ok` > 4 `nrun` > 5 `cpow` > natives | 5 |
| normal | 1 > 2 `g_simplify` > 3 `normal` > 4 `from_poly` > 5 `mul_` > 6 `add_` > 7 `mk` | 7 |
| series | 1 > 2 `g_series` > 3 `series_fold` > 4 `ps_mul` > 5 `mul_` > 6 `add_` > 7 `mk` | 7 |
| print | 1 > 2 `PR.record` > 3 `text` > 4 `items` > 5 `mul_` > 6 `add_` > 7 `mk` | 7 |
| decimal line | 1 > 2 `PR.record` > 3 `nev` > 4 `nrun` > 5 `cpow` > natives | 5 |
| quadrature | 1 > 2 `g_defint` > 3 `quad` > 4 `nrun` > 5 `cpow` > natives | 5 |
| soft lazy import | 1 > 2 `g_int` > 3 `R.need` > the compiler (C) > 4 module body (+1 [A]) | 5 |
| layout | 1 `U.show` > 2 `D.layout` > 3 `measure` > 4 `call_box` > 5 `leaf` > natives | 5 |
| menu | 1 `U.key` > 2 `M.menu` > 3 `D.render` > natives | 3 |
| busy | 1 `R.go` > 2 `U.busy` > natives | 2 |

The scratch validation measured the first row's shape at 6 [M] (§10.1). The memory-first
prototype measured 7 with strict penalties [M].

**Native costs at the deepest levels [A].** If the cap is a C-stack check (device-python §2.2),
native work also spends it. The unmeasured cases sit exactly at the deepest levels, so PROBE6
measures each one beyond its planned depth (Appendix B), and each has a fallback:

| native work | where | probe | fallback if it fails |
|---|---|---|---|
| `list.sort` (MicroPython's quicksort recurses in C; older versions recurse on one side, so sorted input recurses O(n) deep) | `add_`, `mul_` at depth 6; printer keys at 4 | `sort9`: 3,000 tuples at depth 9, random, ascending and descending | `K.isort` (L7): insertion sort up to 16 items, an iterative bottom-up merge sort above, replaces every `list.sort` below L3 |
| creating and raising an exception instance | `mk` at depth 7 (`CasError`, `CasMemory`), constructors at 5-6 (`Undefined`) | `exc10`: raise and catch a user exception at depth 10 | raise instances preallocated at boot (`raise E_COMPLEX`), so nothing is constructed deep |
| `gc.collect()` | `mk` at depth 7 | `gc10`: collect at depth 10 with a full heap of tuples | `mk` only sets a flag; the driver collects at depth 1 |
| the compiler | `need` at depth 3 (soft loads), 2-3 (preload) | `imp6`: import a 300-line generated module from depth 6 | `need` moves to the driver: a generator yields `NEED(name)` and receives the module, so every import runs from depth 1 |

The test budget of 8 leaves two levels for these costs; the probes show whether they need more.

### 17.3 Annotations and FRAMELINT (static, `tests/support/framelint.py`)

- **Annotations:**
  - `#@L n` on the module's first line sets the default level.
  - `#@L n` as a trailing comment on a `def` line overrides it.
  - Dynamic calls need `#@calls k` on the call line, where `k` is the level the callees are
    declared at, and `k` must exceed the caller's level. Examples: `getattr(M, name)(...)`,
    `FNUM[op](a)`, `R.BUSY(...)`.
  - Tables of functions need `#@table k`, and every function placed in them must have level >= k.
- **FRAMELINT checks:**
  - Every resolvable call edge satisfies `L(callee) > L(caller)`. This covers same-module names and
    `ALIAS.f` through the fixed aliases of §4.1. That proves there are no cycles and no recursion.
  - Generators (`g_*`) are exactly L2. A `g_*` call appears only as the operand of `yield`, inside
    `scoped(...)`, or in `R.go` (the root generator). A plain function never references `g_*`.
  - Inside a `g_*`: no `yield from`, no `return value`, no bare `except:` and no `finally`
    (§10.2).
  - Imports inside functions appear only in `R.need`, `R.go` and `U.boot`. Module bodies contain
    only `import`, `def`, assignments of literals and builtin calls.
  - **Report:** the longest declared chain per entry point. It is printed by
    `python tests/support/framelint.py --report` and pasted into §17.2 when it changes.
- The bundler strips the annotations after linting. Framelint also runs on the bundled output,
  using a level table renamed alongside any minified names.

### 17.4 Banned constructs in `src/` (lint)

| construct | reason |
|---|---|
| list, set and dict comprehensions; generator expressions | a hidden frame each on the device |
| `lambda`, `key=` arguments, `map`/`filter` with Python callables | a frame per call, plus a native trampoline |
| classes other than empty `Exception` subclasses; `property`; `__slots__` | dunders cost frames; attribute maps cost heap |
| `with`, `yield from`, `async` | hidden frames, or not Python 3.4 |
| inside a `g_*`: `return value`, bare `except:`, `finally` | a silent failure, or desktop/device divergence under `GeneratorExit` (§10.2) |
| recursion (cycles in the call graph) | the depth cap |
| `from X import ...`, `import *` | bundling and eviction |
| dict or set iteration without a `#@unordered-ok` marker | order is not portable |
| `/` on ints in exact modules; `str()`/`repr()`/`%g`/`round` of floats in output code | exactness and portability |
| the subset bans of device-python §13: f-strings, annotations, keyword-only parameters, PEP 448, banned modules, attributes and builtins, non-ASCII, the `__main__` guard | the device |

### 17.5 Dynamic check (`tests/support/evodepth.py`)

This is device-python §12 with three additions (§20.2):

1. `gen_penalty = 0` for frames resumed by `gen.send`, `throw` or `__next__`. This is calibrated by
   the PROBE4 `gen` shape [V] and confirmed by PROBE6.
2. A per-frame assertion `actual depth <= declared level`, using `build/levels.json` from
   FRAMELINT. It runs in the default mode (`gen_penalty = 0`), where the levels are exact.
3. The emulated hard limit is 10, and the violation budget is 8. **The whole suite also passes
   with both penalties at 1** (the strict setting). In strict mode every generator frame counts one
   level deeper than declared (a `g_*` runs at 3), so the per-frame level assertion is off there;
   strict mode checks only the budget of 8. The deepest chain is then 7 + 1 = 8.

### 17.6 When a new chain does not fit

FRAMELINT names the offending edge, for example:
`norm.py:212 normal (L3) -> expand (L3): callee must be > 3`. There are three local fixes:

1. **Hoist:** the caller's caller calls both, one after the other.
2. **Promote:** make the outer step a generator and `yield` the inner one as a sub-generator.
3. **Sink:** move a small helper to a deeper level, if its own callees allow it.

None of these needs a design change.

---

## 18. Memory budget and lazy loading

> **Shipped implementation (2026-10-11).** The calculator loads compiled packs
> (`build/manifest.py` `PACKS`), not compiled-on-device parts: each family is one
> pack, eviction is LRU at pack granularity, and soft, view and aux packs give way
> when memory runs short. The ledger below is the original estimate. Measured
> heap and the loader tables are in [notes/FASTBOOT.md](notes/FASTBOOT.md) and
> [notes/PACKAGING.md](notes/PACKAGING.md).

### 18.1 Heap ledger [E unless marked]

| item | KB |
|---|---|
| free after importing `ti_system` and `ti_graphics` | **173** [V] |
| resident code (8 modules, about 2,650 lines at 22 B/line) | −58 |
| boot buffers: node slots `N`/`H`/`NX`/`V` 12 (§5.1), bucket array 4, history <= 8, VARS/FUNCS <= 2, misc 2 | −28 |
| display cache (`CACHE`, at most 4 KB between commands, emptied before every `R.go`, §16.3) | 0 |
| **available for lazy code plus the command working set** | **≈ 87** |
| command working set: <= `NMAX` = 768 live node tuples × 32 B ≈ 24 KB, plus tokens, generators, polynomial dicts (<= `MAXTERMS` = 400 terms), stacks ≈ 8 KB | −32 |
| reserve `RESERVE`: the compile peak of the largest part, `LAZYMAX × PEAKB` = 150 lines × 80 B = 12 KB, plus fragmentation `FRAG` = 3 KB | −15 |
| **lazy code budget at any moment** | **≈ 40** |

**The compile peak [E].** MicroPython builds the parse tree of a whole module before it emits
bytecode, at roughly `8 + 4n` bytes per parse node with n children, which is about 60-150 B per
source line. So a 300-line module needs 18-45 KB of transient memory, more than its steady size;
this is why lazy code comes in parts of at most `LAZYMAX` lines (§4.3). `PEAKB = 80` B per line is
provisional; the M0.5 gate measures it (§18.7). The ledger counts the reserve and the full working
set together, which is conservative: preloads run before the node table grows, so only soft loads
(§18.4) compile while a working set is live.

### 18.2 Lazy load sets per command family [E]

The KB column comes from §4.1. A command family loads its `DEPS` closure; soft dependencies load
per phase or per strategy (§18.5), so the table gives the largest phase.

| command | modules (closure of `DEPS`) | KB | fits 40? |
|---|---|---|---|
| plain evaluation that is a simplify candidate (§8.7), `simplify`, `expand`, `together` | NORM POLY RULE IDENT (the NORM set) | 24 | yes |
| `factor` | + FACT | 30 | yes |
| `solve` | + FACT SOLVE | 37 | yes (tight) |
| `diff`, `grad` | DIFF + NORM set | 27 | yes |
| `taylor` | SER + NORM set | 31 | yes |
| `limit` | LIM SER DIFF + NORM set | 41 | **no** (−1) |
| `integrate` through S2 | INT ITAB DIFF + NORM set | 37 | yes (tight) |
| `integrate` through S8 | + one strategy family at a time; the largest is `int2b` + FACT | 47 | **no** (−7) |
| definite / improper integral | DEF + the solve phase (44), then the integrate phase (54), then the limit phase (48), with phase eviction (§18.5) | 54 | **no** (−14) |
| `sum` | SUM LIM SER DIFF + NORM set | 48 | **no** (−8) |
| `desolve` | ODE + the integrate phase (54), then the solve phase (44) | 54 | **no** (−14) |
| menus and help | MENU CAT | 13 | yes (evicted on close when low) |

The rows marked "no" use the mitigation ladder (§18.8). The figures are estimates with about ±50%
error, and the line targets themselves may be 1.5-2× low (§4.1). **The M0.5 gate replaces the
factors before T1.1, and PRBMEM on the real T1 bundle re-measures them at T1.15** (§18.7). T2
integration work starts only after that recalibration.

### 18.3 Working-set caps

| cap | value |
|---|---|
| nodes | hard cap `NMAX = 768` live nodes (preallocated slots, §5.1); soft check every 256 new nodes against `LOWMEM = 24 KB` free |
| generator stack | 64 |
| expand / normal | `MAXTERMS = 400` terms, with `MEMFREE` checks every 64 terms (§8.5) |
| Kronecker gcd | univariate degree <= `KRONMAX = 64` (§8.6) |
| integer powers | `MAXBITS = 65,536` bits, estimated before `npowi` (§6.1) |
| result text | `MAXTEXT = 4,000` characters, enforced while printing (§12.1) |
| history | 40 entries, 8 KB |
| edit line | 256 characters |
| layout | 400 RPN items, nesting 24 |
| display cache | 5 entries and 4 KB; empty while a command runs |

### 18.4 Loading protocol

- **Startup.** `casevo.py` imports the resident modules leaf-first (§4.2), so import bodies never
  nest.
- **Families and closures.** `need(key)` loads the key's family (§4.3) and every family in its
  `DEPS` closure. The closures are precomputed as leaf-first tuples (`CLOSURE[family]`, built by the
  bundler from `DEPS`), so `need` loops instead of recursing.
- **Preload** (`R.start`, L2, called by `R.go`):
  1. Scan the RPN for command names.
  2. Take the closure of their `DEPS`.
  3. Load each family with `R.need`. Module bodies run at depth 3 or 4.
  4. Compile the declared rule sets.
  5. Mark these families `PINNED` for the command.

  This happens before the node table grows, which limits fragmentation.
- **Soft dependencies.** A generator calls `M = R.need('int2')` when a strategy or a phase needs a
  family outside the declared set (§10.6, §11.3).
- **Live pins.** `need`, called from a generator, records the family in that generator's stack
  slot (`NEEDED[-1]`) and increments `LIVE[family]`. The driver decrements the counts when the
  generator is popped (§10.4). A family with `LIVE > 0` is never evicted: some generator on the
  stack obtained it, and a generator created from a lazy module is always created by a parent that
  obtained the module, so the module of every suspended generator is live.
- **Plain functions** never import. They use `R.MODS['poly']`, which must be in the command's
  declared closure; a `KeyError` is a bug caught by tests.
- **Name map.** On the desktop `DEV = {'poly': 'poly', 'int': 'integ', 'intb': 'integb', ...}`.
  The bundler rewrites it to `{'poly': 'CVPOLY', 'int': 'CVINT', 'intb': 'CVINTB', ...}` (§19).

```python
def need(key):                                                  #@L 3
    fam = FAMILY.get(key, key)                    # part key -> family key (section 4.3)
    for f in CLOSURE[fam]:                        # leaf-first families; the last is fam
        USE[f] = STEPS[0]                         # LRU stamp
        if f in LOADED:
            continue
        for p in PARTS.get(f, (f,)):              # one compile at a time
            want = COST[p] + PEAKB * LINES[p] + FRAG      # manifest numbers (section 18.7)
            while MEMFREE() < want:               # natives: 0 frames
                v = None                          # inline LRU victim: not pinned, not live
                for n in LOADED:
                    if n not in PINNED and not LIVE.get(n, 0) and (
                            v is None or USE[n] < USE[v]):
                        v = n
                if v is None:
                    raise CasMemory()
                for q in PARTS.get(v, (v,)):
                    del sys.modules[DEV[q]]
                    del MODS[q]
                LOADED.remove(v)
                gc.collect()
            MODS[p] = __import__(DEV[p])          # body runs one level deeper; defines only
        LOADED.append(f)
    if NEEDED and fam not in NEEDED[-1]:          # pin while this generator is on the stack
        NEEDED[-1].append(fam)
        LIVE[fam] = LIVE.get(fam, 0) + 1
    return MODS[key]
```

(`FAMILY`, `PARTS`, `CLOSURE`, `COST`, `LINES` and `DEV` come from `build/manifest.py` through the
bundler. `MEMFREE` is `gc.mem_free`, injected by the UI. This sketch was run against stubs on
CPython: an LRU victim that is live is skipped, and the next one is evicted [M].)

### 18.5 Eviction protocol

- **Between commands:** families stay loaded, which saves recompile time. If `gc.mem_free()` is
  below 40 KB after a command, the LRU lazy families are evicted until it is at least 40 KB.
- **Inside a command:** `need` evicts LRU families that are neither `PINNED` nor live
  (`LIVE > 0`). So the scenario "`g_parts` (CVINT3) is suspended while a nested `g_int` needs
  CVINT2" can never evict CVINT3 and import it a second time: the outer `g_int` pinned `int3` when
  it called `need`, and it is still on the stack.
- **Phase eviction.** A multi-phase command calls `R.drop(keys)` (L3, like `need`) when a phase
  is done. `drop` removes those families from the caller's own `NEEDED` slot (decrementing
  `LIVE`), unpins them, and evicts each one whose `LIVE` count is now 0; a family that is still
  live is left for `need` to evict later. Phases load their next families as soft dependencies,
  so the earlier phase is gone first:
  - `g_defint`: `solve` (singularities), dropped; the preloaded `int` set (antiderivative),
    dropped with `int2`, `int2b`, `int3`, `int3b` and `itab`; then `lim` (limits and jumps)
    (§11.3);
  - `g_desolve`: the `int` set, dropped; then `solve` for y (§11.4);
  - `g_int`: a strategy family (`int2`, `int2b`, `int3`, `int3b`) whose attempt failed is
    dropped before the next strategy's `need`.
- **Safety.** With live pins, no module is evicted while a generator from it is suspended, so no
  module is ever imported twice at once. Module state is only constant tables, so re-importing a
  module later is correct, though it costs time. Tests count imports per module per command and
  assert at most 2 (one re-import after a phase drop), and exactly 1 for a family that was live
  throughout.
- **Evicting** means `del sys.modules[dev]` and `del MODS[key]` for every part, then
  `gc.collect()`. There are no other references, because `from X import` is banned and module
  objects are never stored in globals (a generator's local `M` is covered by the live pin).
- **If eviction does not free memory** (`sys.modules` is missing or not writable, or PRBMEM `kept`
  is close to `cost`; device-python §14.2 lists this as [A]), the M0.5 gate chooses a fallback:
  1. clear the module's globals before deleting it (`m.__dict__.clear()`, also probed in M0.5),
     which frees the function objects and their bytecode even if the module object stays;
  2. if nothing frees code: eviction is off. Lazy families load at most once per session and stay;
     lazy modules are merged into fewer, larger family modules; the T3 cut decision (§18.8 step 7)
     moves forward to T1.15, and T2 families may be trimmed. When memory runs out, the message
     asks the user to restart `CAS`.

### 18.6 MemoryError protocol (in `R.go`, L1)

1. Set `stack`, `g` and `val` to `None`. The generator frames go with them.
2. Reset: clear `NEEDED`, `LIVE` and `PINNED`; `K.reset()` truncates the node table and clears
   `SYMN`, `RULECACHE` and `TCACHE`.
3. Evict every lazy module (every key in `MODS`, including a family whose import was cut short)
   and clear `MODS` and `LOADED`.
4. `gc.collect()`.
5. Only then build the record `('msg', 'Out of memory')`. The text is preallocated, so building the
   message allocates almost nothing, and it is never built with the node table still full.

`R.go` follows the same order on every error path: drop references, reset, then build the message
(§10.4). `U.panic` does the UI-side equivalent (§16.10).

### 18.7 Calibration: the M0.5 gate (before T1.1) and T1.15

**Status (M0.5, 2026-10-10): device run pending.** `build/genprobe.py` and `probe/PRBL100.py`,
`PRBL200.py`, `PRBL300.py` exist; the user has not run PRBMEM yet (`probe/README-MEM.md`). Until
then every number of §4.1 and §18 stays provisional, and `build/manifest.py` says so
(`CALIBRATION = 'provisional'`, with `FACTOR 1.8`, `PEAKB 80`, `LAZYMAX 150`, `NMAX 768`,
`EVICT 'modules'` and CVDRAW resident). T1.1 and T1.2 proceed on these numbers (D13 relaxed for
this run); T1.15 measures the real T1 bundle in any case. `python build/genprobe.py --derive
FILE --apply` turns the transcript into the manifest values; `docs/notes/M0.5.md` lists the
rest of the follow-up.

**M0.5 memory gate (before T1.1).** The design's code-size factors are assumptions, and every lazy
module's size depends on them, so they are measured before any module is written.
`build/genprobe.py` generates three modules of 100, 200 and 300 lines (`PRBL100`, `PRBL200`,
`PRBL300`) from code shaped like ours: the prototype's functions (loops over flat tuples, `if`
chains, tuple and string tables), minified by the M0.4 bundler. PRBMEM (device-python §14.3), with
`MODS` set to these modules, reports per module:

| column | meaning |
|---|---|
| `cost` | steady RAM after import |
| `kept` | RAM not freed by eviction |
| `peak` | compile transient |

It also reports the bytes per node shape. A short addition to PRBMEM checks that `sys.modules`
exists and that `del sys.modules[name]` works, and measures `kept` again with
`m.__dict__.clear()` before the deletion.

The gate fixes, in `build/manifest.py` and this document:

- `FACTOR = cost / .mpy bytes` (replaces the 1.8 assumption) and the steady B per line;
- `PEAKB = peak / lines`, and so `LAZYMAX`: the largest part whose `LAZYMAX × PEAKB + FRAG` fits
  the reserve the ledger can afford (§18.1). If `LAZYMAX` comes out at 300 or more, parts of one
  family may be merged; below 150, the seams of §4.3 move;
- `NMAX` from the bytes per node shape;
- the eviction mechanism: `sys.modules` deletion, `__dict__` clearing, or no eviction (§18.5);
- the UI residency: whether CVDRAW stays resident or becomes evictable during computation (ladder
  step 4), from the measured cost of `draw.py`-sized code;
- the KB column of §4.1 and the tables of §18.1-§18.2.

**T1.15 recalibration.** PRBMEM runs again on the bundled T1 modules (resident and lazy) and
replaces the factors with measurements of the real code. Go/no-go notes for T2 are recorded.

- If `kept` is above 2 KB per module, eviction is not worth it. Merge the lazy modules into fewer
  family modules, loaded per session.
- If `.mpy` imports work on the EVO (PROBE7), switch the bundler to `.mpy` output: no compile peak,
  and `LAZYMAX` no longer matters.

### 18.8 Mitigation ladder (apply in order until the budget closes)

1. Calibrate (§18.7). If the real cost is at most 16 B/line (with the line targets of §4.1), every
   row of §18.2 fits.
2. Minify module-level names and attributes (bundler phase 2). qstrs are never freed.
3. Phase eviction in `defint`, `desolve` and `sum` (§18.5).
4. Make CVDRAW evictable during computation (decided at M0.5). CVUI then reaches it through
   `R.MODS['draw']`, and it is re-imported for `U.show`, which costs compile time [A].
5. Strategy families one at a time: `g_int` drops each failed strategy family before the next
   `need` (they are separate families already, §4.3).
6. Lower the working-set target to 512 live nodes (`NMAX`), freeing about 12 KB.
7. **T3 cut decision** (milestone T3.8), based on the CVTEST measurements.

---

## 19. Build and bundling (`build/`)

> **Shipped implementation (2026-10-11).** After bundling, `build/packs.py`
> merges device modules into packs and `build/archive.py` compiles them with
> MicroPython v1.12 `mpy-cross`; the calculator receives 21 `CAS*` packs and two
> launchers. See [notes/FASTBOOT.md](notes/FASTBOOT.md) and
> [notes/PACKAGING.md](notes/PACKAGING.md) for the pipeline and current manifest.

### 19.1 Manifest (`build/manifest.py`)

```python
ENTRY = ('casevo', 'CAS')
MODULES = (
    # src      device     class  max lines  KB budget
    ('node',   'CVNODE',  'R',   520,       12),
    ('alg',    'CVALG',   'R',   300,       7),
    ('parse',  'CVPARSE', 'R',   440,       10),
    ('poly',   'CVPOLY',  'L',   150,       3),
    ('polyb',  'CVPOLYB', 'L',   150,       3),    # parts of one family (section 4.3)
    # ... one row per module or part of sections 4.1 and 4.3
)
FAMILY = {'polyb': 'poly', 'polyc': 'poly', 'intb': 'int'}    # ... part key -> family key
FACTOR = 1.8      # RAM bytes per .mpy byte; set by the M0.5 gate (section 18.7)
PEAKB = 80        # compile peak in bytes per source line; set by the M0.5 gate
LAZYMAX = 150     # lines per lazy part; set by the M0.5 gate
FRAG = 3072       # fragmentation allowance per import, bytes
```

The bundler derives `CLOSURE` (leaf-first family tuples from `DEPS`), `COST` and `LINES` per part,
and writes them, with `FAMILY`, `PARTS` and the `DEV` map, into `run.py`'s tables.

### 19.2 `python build/bundle.py` steps

1. **Lint** `src/` with the subset lint (§20.3) and FRAMELINT. Any error stops the build.
2. **Per module:**
   - tokenize with the stdlib `tokenize` (desktop only);
   - drop comments, docstrings and the `#@` annotations;
   - rewrite `import x as Y` to `import DEV as Y`;
   - rewrite the `DEV` table literal in `run.py` to the device names;
   - convert indentation to 1 space; drop blank lines;
   - phase 2: rename module-level names from a short alphabet, consistently across modules, with a
     reserved-name list.
3. **Write** `dist/device/<DEV>.py` (ASCII, LF), `dist/linemap.json` (device file:line ->
   src:line) and `dist/sizes.txt`.
4. **Check:**
   - names match `[A-Z][A-Z0-9]{0,7}` and are unique;
   - each file is within its line budget, and each lazy part within `LAZYMAX` lines;
   - `compile()` succeeds on each output;
   - the subset lint passes on the output;
   - if `mpy-cross` is installed (`pip install mpy-cross` in the venv), `.mpy` bytes × `FACTOR`
     is within the KB budget. Otherwise the size gate is skipped with a warning.
5. **Bundled tests:** `python -m pytest --bundled`. The conftest puts `dist/device` first on
   `sys.path` and maps desktop names to device names (§20.1).

### 19.3 Device install and debugging

- Copy `dist/device/*.py` to the calculator with TI's transfer tool [A: the EVO transfer path is
  unverified]. Run `CAS` from the Python app.
- Probes (`probe/*.py`) are transferred separately. `CVTEST` is a developer probe: the release
  builds it to `dist/dev/CVTEST.py` for the native CI suites, and it does not ship.
- A device error reports a file and a line. `python build/linemap.py CVNODE 123` prints the source
  location.

---

## 20. Testing strategy

### 20.1 Layout and how to run

```
.venv/Scripts/python -m pytest -q                    # everything, under the depth checker
.venv/Scripts/python -m pytest -q -m "not slow"      # fast loop: skips oracle corpora and fuzz
.venv/Scripts/python -m pytest -q tests/test_node.py -k radical
.venv/Scripts/python -m pytest --update-golden       # regenerate golden files (review the diff!)
.venv/Scripts/python -m pytest --bundled             # run the suite against dist/device (section 19)
.venv/Scripts/python tests/support/framelint.py --report   # longest declared chains
.venv/Scripts/python build/bundle.py                 # lint + bundle + size report
```

**`tests/conftest.py`:**

- Puts `src`, `shim` and `tests/support` on `sys.path`, and calls `sys.set_int_max_str_digits(0)`.
- Runs every test's call phase under the depth checker (§20.2).
- After each test:
  - runs the invariant scan (§8.9);
  - checks `SIMPBUG == 0`;
  - checks `K.NN == K.BASE` when the test ran a full command;
  - fails on any record of kind `internal error` (a bug that `R.go` caught, §10.4).
- Registers the markers `device_base(n)`, `slow`, `oracle` and `bundled`.

`PYTHONHASHSEED` is left random, so that order bugs show up.

### 20.2 Depth checker (`tests/support/evodepth.py`)

The base is device-python §12.2, which is tested. This design adds three things.

1. **Generator resume (`gen_penalty`, default 0).** On CPython 3.12+, a `CALL` event for
   `top.send(v)` passes the **unbound** `send` descriptor as `func` and the generator as `arg0`.
   The check must therefore look at both [M]. Without this fix the trampoline is charged one frame
   too many.

   ```python
   _GENOP = object()

   def _call(self, code, offset, func, arg0):           # CALL, in device code only
       if not self._is_dev(code):
           return _M.DISABLE
       f = sys._getframe(1)
       if hasattr(func, '__code__'):
           self._native.pop(f, None)
       elif getattr(func, '__name__', '') in ('send', 'throw', '__next__') and (
               type(getattr(func, '__self__', None)).__name__ == 'generator'
               or type(arg0).__name__ == 'generator'):
           self._native[f] = _GENOP                      # generator resume: gen_penalty
       else:
           self._native[f] = func                        # builtin calling back: native_penalty

   # in _start():
   #     if caller in self._native:
   #         depth += (self.gen_penalty if self._native[caller] is _GENOP
   #                   else self.native_penalty)
   ```
2. **Automatic base.** A device frame with no live device ancestor (a test calling into `src/`
   directly) starts at its **declared level** from `build/levels.json`, not at `base + 1`. So
   `K.add_` called from a test is measured as running at depth 6, its real worst case.
   `@pytest.mark.device_base(n)` overrides this. End-to-end tests call `R.go` or drive the
   key-script loop, and their depths are real.
3. **Level assertion.** Each frame's actual depth must be <= its declared level. A frame without an
   annotation inherits its module's level. The assertion runs with `gen_penalty = 0` only; strict
   runs check the budget of 8 instead (§17.5).

**Calibration tests** (`tests/test_depth_calibration.py`):

- The PROBE4 shapes give plain 9, mutl 9, meth 9, gen 8 and nest3 6 with zero penalties.
- In strict mode, `list(gen)` gives 7.
- A trampoline shape driving 200 logical generator levels never exceeds depth 2 [M].
- When PROBE5 and PROBE6 report, their numbers are added and the default penalties updated.

### 20.3 Static checks

| check | file | runs on |
|---|---|---|
| subset lint: device-python §13, plus `/` on ints in exact modules, the §17.4 bans, the `ti_*` import rule, ASCII | `tests/support/lint.py` | `src/`, `dist/device/` |
| FRAMELINT (§17.3) | `tests/support/framelint.py` | `src/`, `dist/device/` |
| rule lint: only the listed wildcard letters; AC patterns with at most 3 pairs plus at most one `R`; explicit `*` (rule strings get no implicit multiplication); `R` in every ADD- or MUL-headed identity LHS; no `A`/`B`/`C` next to `L`/`Q` in a LHS (§9.2) | `tests/test_rules.py` | rule tables |
| generator lint: no `yield from`, `return value`, bare `except:` or `finally` inside a `g_*` (§10.2) | `tests/support/framelint.py` | `src/` |
| `compile()` on every bundled file, and optionally `mpy-cross` | `build/bundle.py` | `dist/device/` |

### 20.4 Invariants and the debug arena

- **Invariant scan:** §8.9.
- **Debug arena.** The test flag `K.DEBUG_ARENA = True` changes `release` and `keep`: released ids
  are never reused. Their `N` slot becomes `(DEAD,)`, and `keep` appends survivors at fresh ids.
  Any constructor or algorithm that reads a `DEAD` node raises `AssertionError`. This catches ids
  that leak across a region boundary (§10.3). The flag is off on the device, and `NMAX` is raised
  in this mode.

### 20.5 SymPy oracle (`tests/support/oracle.py`)

**Conversion.** Our canonical text is converted to SymPy: `^` becomes `**`, `ln` becomes `log`,
`log` becomes `log(·,10)`, `e` becomes `E`, `i` becomes `I`, `abs` becomes `Abs`, and the `asin`
family is mapped by name. The result is parsed with `sympify` and an explicit locals dict, with no
implicit multiplication (our output always has explicit `*`).

**Real odd roots.** SymPy's `x**(1/3)` is the principal root, so `(-8)^(1/3)` would be
`1+i·√3` there and `-2` here (§6.2). The converter therefore maps every power `u^(p/q)` with a
rational exponent and an odd `q` to `real_root(u, q)**p`, and `surd(u,n)` to `real_root(u, n)`.
Branch-policy checks (§8.3) sample only real points where the input is real, including negative
ones.

**Equivalence:** `sympy.simplify(a - b) == 0` when that is fast. Otherwise numeric agreement with
mpmath at 30 digits on 5 domain-aware points (with complex points for `i`). Strings are never
compared.

| area | check |
|---|---|
| arithmetic, simplify, expand, together | equivalence with the input |
| factor | the product expands to the input exactly; factor degrees match `sympy.factor_list` over Q |
| solve | substitute every root; compare root counts with `sympy.solveset` over the reals |
| diff | equivalence with `sympy.diff` |
| integrate | `d/dx(ours) - f ≡ 0`; definite integrals against `sympy.integrate` or mpmath quadrature |
| limit | `sympy.limit`, including one-sided values for DNE cases |
| taylor | coefficients against `sympy.series` |
| sums | `sympy.summation`, or numeric partial sums |
| ODE | the residual is 0 and the initial conditions hold |

**Corpora:** `tests/corpus/t1.tsv`, `t2.tsv`, `t3.tsv`, one case per line:
`input <TAB> check <TAB> reference <TAB> note`. `check` is one of `eq`, `text`, `antideriv`,
`limit`, `roots`, `ode`, `sum`, `msg` or `approx`. Sources:

- the seeds of alg §6 (all of them; these are the milestone acceptance sets);
- the inputs of FlowCE `tools/emu/cases/*.tsv`;
- the inputs of FlowCE `tools/hostgiac/corpus_calc*` (about 720 problems), with references computed
  by SymPy.

The corpora are marked `slow` and `oracle`.

### 20.6 Golden files (`tests/golden/`)

| file | contents |
|---|---|
| `tiinput.txt` | the FlowCE input passes (§7.10) |
| `print_t1.txt`, `print_t2.txt`, `print_t3.txt` | input -> canonical text: textbook order, signs, quotients, `log`, `e`, `sqrt`, degree mode |
| `messages.txt` | every message string |
| `forms.txt` | F4 sequences for a set of answers |
| `decimal.txt` | decimal lines |
| `layout/*.txt` | display-list dumps at fixed metrics (the recording shim) |
| `nodes.txt` | node-table dumps for canonical-form cases: they pin `H` and the pair order, the platform contract of §5.7 |

`--update-golden` rewrites them, and the diff is reviewed in the commit.

### 20.7 Properties

These use the seeded random expression generator in `tests/support/gen.py`.

- **Canonicity:** random permutations and regroupings of the build order give the same id.
  Rebuilding a node from its children gives the same id.
- **Round trip:** `parse(print(e)) == e` (§12.5), in both angle modes.
- **Determinism:** a subprocess runs the golden suite under 3 `PYTHONHASHSEED` values, and the
  outputs are byte-identical.
- **Regions:** random sequences of `mark`, build and `keep` under the debug arena. Text and ids
  stay stable, and re-interning finds the same id [M].
- **Matcher undo** leaves `env` clean. **Rewrite** reaches a fixpoint within `MAXPASS` on generated
  inputs.
- `dec10` agrees with the `decimal` module (§12.6).
- **Nesting invariance** (depth-first proposal). Every command family runs on inputs nested 1, 8
  and 32 deep: `sin(sin(...x))`, `((x+1)^2+1)^2...`, nested fractions. **The maximum measured depth
  must be identical across the three.** Any hidden recursion breaks this, even through a
  mis-annotated dynamic call.

### 20.8 Memory and performance counters

- **Memory, per corpus item:**
  - node high-water mark (live, and created) and the generator stack peak;
  - the modeled bytes, `32 × live nodes` plus 70 per term held by `expand`/`normal` dicts, must
    stay <= 32 KB, the working set of §18.1. A 2,000-term expansion must be refused by the cap or
    the `MEMFREE` check before the model passes 32 KB (§8.5);
  - after the command, the table is back at `BASE`;
  - each lazy module is imported at most twice per command, and once if its family stayed live
    (§18.5).
- **Performance, per item:** engine steps, `mk` calls, matcher steps and `nev` points.
  Multiplying them by per-operation costs from the CVTEST calibration gives a device-time
  estimate. Over 5 s warns; over 20 s fails.

### 20.9 End-to-end key scripts (`tests/support/keyscript.py`)

- `shim/ti_system.wait_key` replays a list of key codes and raises `StopScript` at the end.
  `get_key` and `escape` can inject [clear] after N polls, to test cancel.
- `shim/ti_graphics` records draw calls as a display transcript.
- Tests run `casevo.py` itself, so the depths are real, and assert on the history, Ans and the
  screen-text dump.
- Ported FlowCE cases: `ansop`, `entry` and the leading-operator cases; FlowCE's Calc 1-3 sessions.

### 20.10 Bundled and MicroPython tiers

- `pytest --bundled` runs the suite against `dist/device`.
- **Optional CI job:** a smoke script on the MicroPython unix port, with
  `micropython -X heapsize=170K`, over `dist/device`. It catches syntax and builtin gaps, dict
  order, unstable sorts, float repr and a real `MemoryError`. It cannot emulate the frame cap; the
  checker does that. Its availability on our CI is [A].

### 20.11 On the device

`probe/CVTEST.py` runs about 50 commands across T1-T3. For each it prints pass or fail, the time,
and `gc.mem_free()` before and after. It runs at every milestone after B.1, and its measurements
drive the T3 cut decision (§21).

It also repeats the device checks of PROBE6 on the real bundle: importing the largest lazy part
from depth 6, `add_`-style sorts of 3,000 tuples at depth 9 (random, ascending, descending),
raising and catching `CasError` at depth 10, `gc.collect()` at depth 10, and the `math` edge cases
(`asin(2)`, `log(0)`, `sqrt(-1)`, `0.0**-1`, `(-8.0)**(1/3)`, `1e308*10`) through `nrun`.

### 20.12 Review cases

These come from the design reviews. Each is a named test, so that a regression points at the
section it breaks.

| area | cases | section |
|---|---|---|
| `R.go` never raises | fuzz 2,000 seeded random input lines (`tests/support/gen.py`); inject `MemoryError` at the k-th allocation in `mk`, `keep`, `text` and the layout for every k up to the command's count; inject a `TypeError` in a generator. Each gives a record and leaves `K.NN == BASE` and an empty `LIVE`. | §10.4 |
| decimal line | `limit(1/x^2,x,0)` (`oo`), `undef`, `-oo`, `2<3`: no decimal line and no exception | §12.6 |
| relation folding | `x-x=1` gives `no solution`, `x+1=x+1` gives `every x is a solution`, `2<3` gives `true` | §8.2 |
| internal results | `integrate(1/(x^2+1),x,0,1)` gives `pi/4`; an improper integral whose inner limit is a `DNE`; a separable ODE whose `g_solve` for y returns the empty list | §10.5 |
| branch policy | each §8.3 row at negative points; `sqrt(x^2)` never simplifies to `x`; the oracle maps `(-8)^(1/3)` to `-2` | §8.3, §20.5 |
| guards | `solve(sin(x)=sqrt(2)/2)` gives `pi/4` and `3*pi/4`; `integrate(pi^x,x)` uses the `K^L` rule; a guard whose constant difference is exactly 0 after `normal` | §9.2 |
| rule engine | each identity in context (×3, ×`sin(x)`, inside a sum, a bare `x` against `L^N`) | §9.8 |
| degree mode | `sin(x+30)` in DEG round-trips after `expand`, F4 and Ans; `solve(sin(x)=1/2)` in DEG gives `x=30,x=150` | §6.5, §11.2 |
| lexer | `2e-1` is `2*e-1`; `3e-2x` is `3*e-2*x`; `2E-1` is `0.2`; `riemann(x^2,x,0,1,4,mid)`; `desolve([y''+y=0,y(0)=1,y'(0)=0],y)`; `O(x^6)`; `sin(x)` through `lex` and `rpn` alone | §7.2, §7.10 |
| answer text | the 2D layout and the round trip of solve results (`x=-1,x=1`) and taylor results (`...+O(x^6)`); `factor(360)` prints `2^3*3^2*5` | §12.1, §13.1 |
| printing | `x>3` prints `x>3`; `log(8,2)` gives 3; `2^(10^6)` gives `number too large` at once; a 30,000-digit result gives `Done` without building its text | §12.4, §6.1 |
| eviction | a suspended `g_parts` with a nested `g_int` that needs CVINT2 under a tiny fake heap: no double import, no eviction of a live family; `R.drop` of a still-live family | §18.5 |
| memory model | a 2,000-term `expand` is refused by the cap before the modeled bytes pass 32 KB; `normal` of three variables of degree 20 stays under `KRONMAX` | §8.5, §8.6 |
| session | `expand((a+1)^2)`, then `a=3`, then F4 keeps the old forms; `x=3` sets `F_PURGEHINT`; `purge(x)` | §14, §7.9 |
| history paste | pasting `2/3` after `x^` gives `x^(2/3)`; pasting `x=2` after `3*` gives `3*(x=2)` | §16.6 |
| device | the CVTEST depth and `math` checks above | §20.11 |

---

## 21. Milestone plan

### 21.1 Rules for implementers (human or agent)

- **Test first.** Write the failing tests for a task, then the code. Every test runs under the
  depth checker and the invariant scan.
- **File ownership.** Each task lists the files it owns. Two tasks that run in parallel never own
  the same file. Shared files (`run.py` tables, `parse.py`) have one owner; the others request
  changes through that owner. A task that owns `src/x.py` also owns its parts `src/xb.py`, ...
  (§4.3).
- **Interfaces are frozen before parallel work** (§21.2). An interface change after the freeze
  needs a short note in this document and must update the contract tests in the same commit.
- **Definition of done** for every task:
  - acceptance tests pass;
  - `pytest -q -m "not slow"` passes;
  - lint and FRAMELINT are clean;
  - new public functions are annotated `#@L n`.
- **One commit per milestone,** with a message such as `T1: exact core`, after the full suite
  passes (the user's process). Work-in-progress commits on branches are fine.

### 21.2 Interfaces frozen at the end of T1.1/T1.3 (contract tests: `tests/test_api.py`)

| module | public API |
|---|---|
| `node.py` | op codes and preallocated ids (§5.2, §5.5); `N`, `H`, `V`, `NN`, `NMAX`; `mk(t)`; `num(a, b=0, d=1)`; `flt(re, im=0.0)`; `sym(name)`; `add_(ids, k=None)`; `mul_(k, pairs)`; `fn_(op, a)`; `rel_(op, a, b)`; `neg_(u)`; `absn(u)`; `negfirst(u)`; the number kernels `nadd nmul ninv npowi nneg nsign ncmp` on NUM tuples; `free_of(e, x)`; `keep(m, y)`; `release(m)`; `reset()`; the exceptions `CasError CasSoft Undefined Cancel CasMemory`; the hooks `ESC`, `MEMFREE` |
| `alg.py` | `postorder(e)` -> sorted id list; `subst(e, x, v)`; `linear(e, x)` -> `(a, b)` or None; `quadratic(e, x)`; `split_const(e, x)` -> `(c, g)`; `degree(e, x)`; `size(e)`; `nprog(e, xs)`; `nrun(prog, vals)`; `nev(e, env)` |
| `parse.py` | `tokens(text)`; `lex(s)`; `rpn(toks)`; `inst(code, env)`; `tcode(s)`; `g_eval(code, ctx)` |
| `run.py` | `go(job)` -> record `(kind, text, approx, flags)`, never raising except `KeyboardInterrupt`; `start(job)` -> `(code, ctx)`; `need(key)`; `drop(keys)`; `MODS`; `scoped(g)`; `TICK`; `CMDS ALIAS DEPS PARTS MACROS HINT`; `ANS HIST VARS FUNCS SET` |
| `printer.py` | `text(e, ctx)`; `record(val, job)`; `dec10(p, q, nd)`; `fdec10(x, nd)` |
| `rules.py`, `rulesb.py` | `rset(name)`; `guard_ok(guard, env)` -> 1, 0 or `(NEAR, op, d)`; `g_rewrite(root, rs, x, budget)`; in `rulesb`: `match(p, s, env, x)` |

### 21.3 M0: Foundations

| id | task | owns | depends | acceptance | parallel |
|---|---|---|---|---|---|
| M0.1 | Test harness | `tests/conftest.py`, `tests/support/{evodepth,lint,framelint,invariants,gen}.py`, `tests/depth_shapes/`, `tests/test_depth_calibration.py`, `tests/test_lint.py`, `tests/test_framelint.py`, `pytest.ini` | – | Calibration as in §20.2. Lint and FRAMELINT unit tests on good and bad snippets, including a generator called without `yield` and an L4 -> L4 edge. | first |
| M0.2 | Shims | `shim/ti_system.py`, `shim/ti_graphics.py`, `tests/support/keyscript.py` | – | Key replay, `escape` injection, a draw transcript | with M0.1 |
| M0.3 | Probes | `probe/PROBE5.py`, `PRBIMP.py` (device-python §14.1), `PROBE6.py` (Appendix B, including the depth and `math` sections), `PROBE7.py` (including the interactive drawing loop), `PROBEK2.py`, `PRBMEM.py` (with the `sys.modules` checks of §18.7) | – | Desktop dry runs pass. **The user runs them on the EVO.** Results go into `device-python.md` and here. **Gate:** PROBE6 decides trampoline or task machine (§10.8) before T1.6, and the §17.2 native-cost fallbacks. | with M0.1 |
| M0.4 | Build skeleton | `build/manifest.py`, `build/bundle.py` (strip and rename imports only), `build/linemap.py` | M0.1 | Bundles a sample module; name checks; line map | after M0.1 |
| M0.5 | Memory gate | `build/genprobe.py`, `probe/PRBL100.py`, `PRBL200.py`, `PRBL300.py` (generated), the §18 numbers, `build/manifest.py` constants | M0.3, M0.4 | `genprobe` writes the three modules from prototype-shaped code through the M0.4 bundler. **The user runs PRBMEM on the EVO.** `FACTOR`, `PEAKB`, `LAZYMAX`, `NMAX`, the eviction mechanism and the CVDRAW residency are fixed as in §18.7, and §4.1, §4.3 and §18 are updated. **Gate: before T1.1.** | after M0.4 |

### 21.4 T1: Exact core (commit `T1`)

| id | task | owns | depends | acceptance | group |
|---|---|---|---|---|---|
| T1.1 | Node core | `src/node.py`, `tests/test_node.py`, `test_numbers.py`, `test_radicals.py`, `test_special.py`, `tests/golden/nodes.txt` | M0.1, the M0.5 gate | §5-§6 invariants; Gaussian arithmetic; alg §6 seeds 2.2 and 2.3; canonicity; `keep`/`release` properties; debug arena. **API freeze.** | A |
| T1.2 | Polynomials | `src/poly.py`, `tests/test_poly.py` | M0.1, the M0.5 gate (part sizes) | PRS gcd, Yun, division, Bezout, rational roots, Gauss-Jordan over Q, sparse dicts. Random agreement with SymPy. No node dependency. | B |
| T1.3 | Token passes | `src/parse.py` (`lex`, `ti_rewrite`, `ti_implicit`, `classify` hook, `rpn`), `tests/golden/tiinput.txt`, `tests/test_tokens.py`, `test_rpn.py` | M0.1 | All FlowCE `test_tiinput.cc` cases and properties; the §7.7 RPN table | C |
| T1.4 | Decimal formatter | `src/printer.py` (`dec10`, `fdec10` only), `tests/test_dec10.py` | M0.1 | Exact against `decimal` on 20,000 random cases; the scientific thresholds | D |
| T1.5 | Builders | `src/parse.py` (`inst`, `tcode`, `expand_names`, `g_eval`, `tokens`), `tests/test_eval.py` | T1.1, T1.3 | Arithmetic seeds; degree mode; variables, functions and macros at token level; floats and `approx` | C |
| T1.6 | Runner and session | `src/run.py`, `tests/test_run.py` | T1.1, T1.5, the PROBE6 gate | Trampoline protocol (§10.2) incl. `CasSoft` -> None, `TICK`, `MAXGEN`; regions; budget and cancel; `need`/`drop`/eviction with fake sizes, live pins and families; §7.9 rules incl. `purge`; text-only session; records; `R.go` never raises (the §20.12 fuzz and injection cases, `KeyboardInterrupt` re-raised after the reset); the MemoryError path (simulated by patching `mk`) | E |
| T1.7 | Printer | `src/printer.py` (`text`, `items`, order keys, `record`), `tests/test_print.py`, `tests/golden/print_t1.txt`, `tests/test_roundtrip.py` | T1.1, T1.5 | fmt §1 ordering cases; §12.4 names incl. relations and `HOLD`; sentinel messages; `MAXTEXT`; the round-trip property through inert `g_eval`; the decimal-line rules | D |
| T1.8 | Algorithm core | `src/alg.py`, `tests/test_alg.py` | T1.1 | `postorder`, `subst`, predicates, `size`, `nprog`/`nrun` (real, complex, the odd-root rule), numeric probe | F |
| T1.9 | Rule engine | `src/rules.py`, `src/ident.py`, `tests/test_rules.py` | T1.5, T1.8 | Matcher cases (incl. the AC backtrack); `g_rewrite` termination; the §9.8 suite for every rule | A |
| T1.10 | Normal, expand, simplify | `src/norm.py`, `tests/test_norm.py` | T1.2, T1.9 | Expand cap; normal with gcd; `g_iszero` YES/NO/LIKELY; simplify candidates with verification and `SIMPBUG == 0`; alg §6 seeds 2.4 and 2.5 | B |
| T1.11 | Factor | `src/factor.py`, `tests/test_factor.py` | T1.10 | alg §6 seeds 2.8 (incl. `x^5-x+1` with no false claim); product check; budgets | B |
| T1.12 | Solve | `src/solve.py`, `tests/test_solve.py` | T1.11 | alg §6 seeds 2.10; linear systems; root checks; the empty-list and `TRUE` sentinels; symbolic coefficients; one-period trig (D2) in both angle modes; guards with radicals | G |
| T1.13 | T1 integration | `tests/corpus/t1.tsv`, `tests/test_corpus_t1.py`, `test_nesting.py`, `test_determinism.py`, `test_memory.py` | T1.1-T1.12 | The whole T1 corpus passes the oracle; strict depth; invariants; determinism; memory model. **Commit `T1`.** | E |
| T1.14 | Bundle-lite | `build/*` | T1.13, M0.4 | `dist/device` for the resident and T1 modules; `.mpy` size report; `pytest --bundled` passes | D |
| T1.15 | Memory recalibration | §4.1, §18 numbers, `build/manifest.py` | T1.14 + the user's PRBMEM run on the T1 bundle | The M0.5 numbers replaced by measurements of the real code; the budget re-evaluated, with go/no-go notes for T2 | user + E |

Parallel groups: T1.3 and T1.4 may start before the M0.5 gate; T1.1 and T1.2 start when it has
reported. The four then run together. After the T1.1 and T1.3 freeze: T1.5 (C),
T1.7 (D) and T1.8 (F); then T1.6 (E) and T1.9 (A). T1.10 to T1.12 run in sequence (B, then G).

### 21.5 T2: Calculus (commit `T2`)

| id | task | owns | depends | acceptance | group |
|---|---|---|---|---|---|
| T2.1 | Derivatives | `src/diff.py`, `tests/test_diff.py` | T1 | alg §6 seeds 3.1 incl. FTC and `x^x`; the `DT` soundness tests | A |
| T2.2 | Series engine | `src/series.py`, `tests/test_series.py` | T1 | Seeds 3.2 incl. Laurent and the retry on cancellation | B |
| T2.3 | Limits | `src/limit.py`, `tests/test_limit.py` | T2.1, T2.2 | Seeds 3.3; the `DNE` sentinel and its messages; `floor`/`ceil`/`sign` one-sided rule; ∞ folding; ≈ numeric | B |
| T2.4 | Integration driver, S1-S2 | `src/integ.py`, `src/itab.py`, `tests/test_integ12.py` | T2.1 | Table and u-substitution seeds; the check; the unevaluated form | C |
| T2.5 | S3-S5 and `partfrac` | `src/integ2.py`, `tests/test_integ345.py`, `test_partfrac.py` | T2.4 | Tabular, rational and trig-power seeds; `partfrac` seeds | D |
| T2.6 | S6-S8 | `src/integ3.py`, `tests/test_integ678.py` | T2.4 | Parts and radical seeds; Weierstrass | E |
| T2.7 | Definite integrals and quadrature | `src/defint.py`, `tests/test_defint.py` | T2.3, T2.4 | Seeds 3.5 and 3.6 incl. the `1/(2+cos x)` jump; cross-check; ≈ fallback | F |
| T2.8 | Polish and T2 integration | `src/norm.py` (`g_polish`), `tests/corpus/t2.tsv`, `tests/test_corpus_t2.py` | T2.1-T2.7 | The T2 corpus; depth and memory as in T1.13. **Commit `T2`.** | A |

### 21.6 T3: Advanced calculus (commit `T3`, or a documented cut)

| id | task | owns | depends | acceptance | group |
|---|---|---|---|---|---|
| T3.1 | Improper integrals | `src/defint.py` | T2 | alg §6 seeds 4.1; the `DIVG` sentinel and its messages | F |
| T3.2 | Sums and series | `src/sums.py`, `tests/test_sums.py` | T2 | Seeds 4.2 | B |
| T3.3 | Riemann sums | `src/sums.py` | T3.2 | Seeds 4.3; the limit equals `∫` | B |
| T3.4 | ODEs | `src/ode.py`, `tests/test_ode.py` | T2 | Seeds 4.4 incl. resonance and initial conditions | C |
| T3.5 | Gradient | `src/diff.py` | T2.1 | Seeds 4.5 | A |
| T3.6 | Multiple integrals, polar/parametric area, arc length | `src/defint.py`, `run.py` `MACROS` (through E) | T3.1 | Seeds 4.6 and 4.7 | F |
| T3.7 | T3 integration | `tests/corpus/t3.tsv`, `tests/test_corpus_t3.py` | T3.1-T3.6 | The T3 corpus. **Commit `T3`.** | E |
| T3.8 | Cut gate | – | T3.7 and D.1 numbers | Decide per §18.8 which T3 families ship; record the decision | user |

### 21.7 UI, build, device (after T3, per the settled process)

| id | task | owns | depends | acceptance | group |
|---|---|---|---|---|---|
| U.1 | Layout engine | `src/draw.py`, `tests/test_layout.py`, `tests/golden/layout/` | T1 | Display-list goldens at fixed metrics for every box kind; robustness caps; fitting and scrolling | A |
| U.2 | UI core | `src/ui.py`, `src/casevo.py`, `tests/test_ui.py` | U.1, T1.6 | Key scripts: edit, leading operator, `ans()` delete, ENTRY, empty slot, history navigation and paste, scroll, F4, cancel, MemoryError, themes | B |
| U.3 | Menus and catalog | `src/menu.py`, `src/catalog.py`, `tests/test_menu.py` | U.2 | F1 insert and action rule, F2 recall, F3 settings, F5 help; catalog entries for every command | C |
| U.4 | F4 forms | `src/forms.py`, `tests/test_forms.py`, `tests/golden/forms.txt` | T1.10 | The orders, offer predicates, dedupe and cancel of §14 | D |
| B.1 | Full bundler | `build/*` | U.1-U.4 | Phase-2 minify; the size gate; `pytest --bundled` passes | E |
| B.2 | MicroPython tier (optional) | `ci/` | B.1 | The smoke script runs under `-X heapsize=170K` | E |
| D.1 | CVTEST | `probe/CVTEST.py` | B.1 | Runs on the device; reports time and memory per command; the depth and `math` checks of §20.11 | E |
| D.2 | Device tuning | §10.7, §18 numbers | D.1 | `BUDGET`, `LOWMEM`, `NMAX` and the module splits tuned on the device; T3 cut confirmed | user |

U.1 to U.4 own disjoint files and can run in parallel once their dependencies are met.

---

## 22. Risks

| # | risk | impact | mitigation |
|---|---|---|---|
| 1 | Code plus nodes exceed the heap (the "no" rows of §18.2); the compile peak of a lazy module | OOM on limits, integrate, definite integrals, `sum`, `desolve` | the M0.5 gate before T1.1 and PRBMEM again at T1.15; parts of at most `LAZYMAX` lines (§4.3); the size gate; the §18.8 ladder; the T3 cut gate |
| 2 | The generator trampoline behaves differently on the EVO | the orchestration design | PROBE6 gate before T1.6; task-machine fallback (§10.8) |
| 3 | Hidden frames or native C recursion (the compiler, quicksort, exception creation, `gc.collect` at our deepest levels) | `RuntimeError` or a crash deep in a search | §17.4 bans; flat containers; the strict checker; nesting invariance; PROBE5 (including the risky nested-tuple section); the PROBE6 depth section and the §17.2 fallbacks; `MAXNEST = 32` |
| 3a | `sys.modules` deletion is missing or frees little | lazy loading cannot evict | an explicit M0.5 check; the `__dict__.clear()` and no-eviction fallbacks (§18.5) |
| 3b | An unexpected exception (a bug) | the program exits and the session is lost | `R.go` and the event loop catch every `Exception` (§10.4, §16.2); tests fail on any `internal error` record |
| 4 | Heap fragmentation (non-moving GC) | MemoryError with free memory | buffers allocated at boot; no dict intern table; preload before the node table grows; caps |
| 5 | Device speed (about 3 µs per simple operation) | slow integrals, limits and factoring | step budgets; numeric pre-checks before exact work; dense int-list fast paths; counters plus the CVTEST calibration |
| 6 | Canonical-form bugs (order dependence, non-idempotence) | wrong equality, duplicate terms | invariant scan; canonicity and round-trip properties; golden node dumps; multi-seed determinism |
| 7 | Unsound rewrites (branches, domains) | wrong answers | the §8.3 policy table with property tests; per-rule soundness; candidate verification; derivative checks on antiderivatives |
| 8 | Patterns that cannot match canonical forms | silent rule misses | `L`/`Q` binders; the self-match test; the coverage report |
| 9 | Desktop/device divergence (dict order, float repr, `round`, sort stability, missing builtins) | tests pass on the desktop only | own hash and formatter; lint bans; `#@unordered-ok`; bundled and MicroPython tiers; CVTEST |
| 10 | Fonts, glyphs or the screen size differ from assumptions | ugly or broken 2D output | PROBE7; stroked glyphs; a metrics table with fixed-metric fallback |
| 11 | `escape()`/`get_key()` misbehave during busy loops | no cancel | PROBE6; the `POLL` adapter (§16.10) |
| 12 | Integration and limit coverage below FlowCE | user-visible gaps | FlowCE corpora; the (F, R) contract; ≈ fallbacks; coverage reports |
| 13 | Startup compile time of about 2,600 resident lines | slow app start | measured in CVTEST; minify; move the UI menus and help lazy (already done); `.mpy` if supported |
| 14 | Session text loses information | wrong Ans or variables | the round-trip invariant on every golden and fuzz case; 15-digit floats |
| 15 | Parallel agents conflict | integration churn | the interface freeze (§21.2); file ownership; contract tests |

---

## Appendix A. The three proposals: scoring and what was kept

### A.1 Scores (1-10)

The depth-first proposal reached the judge only from its §5.2 onward, so it was scored on the
sections available.

| criterion | memory-first | correctness-first | depth-first |
|---|---|---|---|
| Device feasibility (depth cap, heap, Python 3.4 subset) | **9**: prototype measured at depth 7 under the strict checker; measured `.mpy` sizes; own intern table with no rehash transients; region compaction | 6: dict `INDEX` (rehash transients, tombstones); an unverified trampoline; symbol bit 30 is a boxed int; pre-baked rule tuples cost heap; 82 KB resident plus warm | 7: a rigorous level system, but it plans all 8 levels (zero test margin); SSA `exec` compile; leaf-first imports |
| Mathematical soundness | 6: `i` as a constant with a mod-4 counter and an ad hoc conjugate rule; no branch policy; unverified simplify candidates | **9**: Gaussian rationals; a written branch policy; N-form zero oracle; verified candidates; per-rule soundness (minus 1: id tie-breaks in the canonical order) | 6: conventional; little visible detail |
| Extensibility for T2/T3 | 6: continuation-passing handlers are awkward for nested strategies | **8**: generator strategies read like recursive code; scoped regions | 7: task combinators (`SEQ`/`TRY`/`MAP`); hoist and promote |
| Testability | 7: depth checker, layer lint, memory model, `.mpy` gate, prototype | **9**: an invariant on every node; rule self-match, soundness and measure tests; multi-seed determinism; debug arena | **9**: per-function levels; per-frame assertion; nesting invariance; end-to-end key scripts |
| Simplicity | **6**: custom table and pair encoding to learn, but strings-as-rules and one parser | 5: N-form kernel basis, tiers, pre-baking, generator `throw` protocol | 5: annotation-heavy; combinators; zero slack |
| **Total (device feasibility weighted ×2)** | **43** | 42 | 41 |

### A.2 Why memory-first is the base

- Device feasibility is the binding constraint, and memory-first scored best there.
- It is also the only proposal backed by a working prototype measured under the depth checker.
- Its weaknesses, soundness and extensibility, are exactly what the correctness-first grafts fix:
  Gaussian numbers, the policy, verification, generators and rule tests. None of those grafts
  touches the representation's feasibility properties.
- The reverse would not work. Fixing correctness-first's feasibility issues means replacing its
  core: the intern table, the order keys and the residency plan.

### A.3 What was kept from each

| from | kept |
|---|---|
| memory-first | DAG with ids; chained intern table; pair sequences with no POW; `log` as `ln/ln10`; regions with `keep`; text-only session; one parser, two consumers; rule strings and letter wildcards; the iterative AC matcher; strict-checker layering; the module map; the `.mpy` size gate |
| correctness-first | Gaussian `NUM`; symbol masks; the generator trampoline with scoped regions; the branch policy; the invariant checker; candidate verification; rule self-match, soundness and measure tests; `L`/`Q` binders; `-(sum)` distribution; multi-seed determinism; the debug arena; PROBE6 |
| depth-first | per-function `#@L` annotations with FRAMELINT and the per-frame assertion; the nesting-invariance test; leaf-first imports; the level pre-pass for 2D layout; key-script end-to-end tests; the MicroPython tier; hoist/promote fixes |
| rejected | dict-based interning; id tie-breaks; pre-baked rule tuples on the device; SSA `exec` numerics as the default (kept as an optimization path); the full N-form kernel basis (reduced to `ZBASIS` plus `normal`); planning on level 8 |

### A.4 Validation done for this document [M]

These ran on desktop CPython 3.14.7, in scratch code outside the repo:
`%TEMP%\casdesign\` (this document) and `%TEMP%\casproto\` (memory-first).

- **Trampoline plus regions plus Gaussian core.** 32 logical generator levels and nested `scoped`
  regions ran with a maximum device depth of 6 under the strict checker, with `gen_penalty = 0`.
  The garbage of failed strategies was released (23 nodes remained of a larger tail). `i^2 = -1`,
  `1/(1+i) = (1-i)/2`, `-(x+1) == -x-1`, and `2(x+1)` was kept.
- **Checker finding.** On CPython 3.12+, the `CALL` event for `gen.send` passes the unbound
  descriptor plus `arg0`. Generator-resume detection must check `arg0` (§20.2).
- **The shunting-yard of §7.7:** 25 cases, including the error cases.
- **`dec10`:** 0 mismatches against `decimal` on 20,000 random rationals.
- **The worked node dump of §5.6,** including order independence and `keep` compaction.
- **PROBE6:** dry-run on CPython 3.14. Plain 999 and in-generator 995 show that `send` adds no
  frame on CPython (the difference of 4 is `tryit`, the lambda, `tramp` and the generator). The
  depth section (`exc9`, `exc10`, `gc10`, `sort9`, and `imp6` with a stand-in 300-line module)
  runs clean on CPython, which says nothing about the device; it checks that the probe itself is
  correct.

---

## Appendix B. Probes to run on the EVO (M0.3)

| probe | purpose | source |
|---|---|---|
| PROBE5 + PRBIMP | frame costs of comprehensions, `key=`, `map`, `eval`, dunders, `__init__`, imports; missing builtins and methods; float, round, sort and dict behavior; nested-tuple native recursion (**risky last section: back up first**) | device-python §14.1 |
| PROBE6 | the generator trampoline (the T1.6 gate); `throw`; `StopIteration.value`; bytes per suspended generator; `del a[m:]` on lists and arrays; `bytearray`; `time` names; `math` domain errors and overflow; native costs at depth (exception creation at 9 and 10, `gc.collect` at 10, importing a 300-line module from 6, sorting 3,000 tuples at 9); `escape()`/`get_key()` during a 3-second busy loop. **The sort section is last and risky: back up first.** `imp6` needs `PRBL300` from M0.5; before that it reads `E:ImportError` and is re-run later. | below |
| PROBE7 | screen size (`getPixel`/`setPixel` at the edges), `setFont` sizes, `string_size` results per font, whether `drawString` renders `chr(0x3c0)` `chr(0x221a)` `chr(0x222b)` `chr(0x3a3)` `chr(0x221e)` `chr(0x2248)`, `dir(ti_graphics)` in pages, the `setColor` signature, and whether a `.mpy` module imports (transfer `PRBMPY.mpy` built by `mpy-cross`). **An interactive loop:** draw a frame with `ti_graphics`, wait with `wait_key`, redraw a region with `fillRect` and `drawString`, repeat 5 times, then `print` a line: does the drawing stay visible between keys, does `wait_key` or `print` clear or scroll it, how long does a full redraw take, and does `ti_system.disp_clr()` erase it. | written in M0.3 |
| PROBEK2 | the code of every key (extends PROBEK); fills the [D] rows of §16.4 | written in M0.3 |
| PRBMEM | bytes per object shape; `cost`/`kept`/`peak` per module; `sys.modules` deletion and `m.__dict__.clear()` (§18.7) | device-python §14.3, with `MODS` = `PRBL100`, `PRBL200`, `PRBL300` at M0.5, and the T1 bundle at T1.15 |

**Reading PROBE6 on the EVO:**

| line | expected |
|---|---|
| `plain` | 10 (it starts from module level) |
| `ingen` | **6** means resuming a generator with `send` costs no extra frame: the trampoline design holds. 5 means `send` costs 1: subtract one level from L2-L7 and re-run FRAMELINT, or take the fallback. |
| `tramp` | `200 201`, with no error |
| `throw` | `1 2` |
| `ret` | `val=7`, or `noattr` (we do not depend on it) |
| `genB` | bytes per suspended generator (one generator per sample, no child) |
| `del` | list and array slice deletion, and array append |
| `math ...` | for each case, the exception name or the value. `nrun` checks for nan and inf in any case (§6.6); a `nan` here confirms that check is needed. `(-8.0) ** (1 / 3)` shows whether float power returns a complex number, raises, or gives nan. |
| `exc9`, `exc10` | `ok`: creating and raising an exception costs no frame. `E:RuntimeError` at 10 only: it costs one, still within the budget of 8. At 9: use preallocated exception instances (§17.2). |
| `gc10` | `ok`: `gc.collect()` is safe at depth 10 with a deeply nested chain alive |
| `imp6` | `ok` and the bytes kept: compiling a 300-line module from depth 6 works. An error means the compiler spends the depth budget: move `need` into the driver (§17.2). |
| `poll` | `esc` hits and `keys` seen while [clear] was held for 3 s, and the loop count `n` (iterations in 3 s). `esc 0` with key 45 in `keys` means the `get_key` adapter is needed (§16.10). |
| `free` | free heap at the end |
| `sort9` | `ok ok ok` (random, ascending, descending): `list.sort` is safe at depth 9. `RT` for a mode, or a crash after the line `sort mode 1` or `2`, means the quicksort recurses deeply on sorted input: use `K.isort` (§17.2). |

**PROBE6 listing** (dry-run tested on CPython 3.14; the `imp6` line also with a stand-in
`PRBL300`):

```python
# PROBE6: generator trampoline, native costs at depth, list/array facts for cas-evo DESIGN.md.
# Prints short lines; press a key after each screenful. The sort section runs LAST and may
# crash the calculator if the native sort overflows its stack: back up first.
import gc
import math
try:
    from ti_system import wait_key as _wk, escape as _esc, get_key as _gk
except ImportError:
    _wk = input
    _esc = None
    _gk = None
_n = [0]


def out(s):
    print(s)
    _n[0] += 1 + len(s) // 30
    if _n[0] >= 9:
        _wk()
        _n[0] = 0


def memfree():
    gc.collect()
    try:
        return gc.mem_free()
    except AttributeError:     # desktop dry run
        return 0


cnt = [0]


def plain():
    cnt[0] += 1
    plain()


def gchild(d):
    cnt[0] += 1
    if d > 0:
        r = yield gchild(d - 1)
        yield r + 1
    else:
        yield 0


GEN = type(gchild(0))


def tramp(g):
    st = [g]
    val = None
    while st:
        try:
            y = st[-1].send(val)
        except StopIteration:
            y = None
        if type(y) is GEN:
            st.append(y)
            val = None
            continue
        st.pop()
        val = y
    return val


def deep_in_gen():
    # one generator at trampoline depth, then plain recursion inside it
    cnt[0] = 0
    try:
        plain()
    except RuntimeError:
        pass
    yield cnt[0]


def t_tramp():
    cnt[0] = 0
    r = tramp(gchild(200))
    return "%d %d" % (r, cnt[0])


def gthrow():
    try:
        yield 1
    except ValueError:
        yield 2


def t_throw():
    g = gthrow()
    a = g.send(None)
    b = g.throw(ValueError("x"))
    return "%d %d" % (a, b)


def gret():
    yield 1
    return 7


def t_ret():
    g = gret()
    g.send(None)
    try:
        g.send(None)
    except StopIteration as e:
        return "val=%s" % (getattr(e, "value", "noattr"),)
    return "nostop"


def gone():
    yield 1
    yield 2


def t_mem():
    keep = [None] * 100       # allocated before the measurement
    a = memfree()
    for i in range(100):
        g = gone()
        g.send(None)          # suspended at its first yield; it has no child generator
        keep[i] = g
    g = None
    return (a - memfree()) // 100


def t_del():
    L = list(range(10))
    del L[4:]
    from array import array
    A = array('i', range(10))
    r = "list %d" % len(L)
    try:
        del A[4:]
        r += " arr %d" % len(A)
    except Exception as e:
        r += " arr E:" + type(e).__name__
    try:
        A.append(5)
        r += " app ok"
    except Exception as e:
        r += " app E:" + type(e).__name__
    return r


def t_ba():
    b = bytearray(4000)
    b[3999] = 1
    return "%d %d" % (len(b), b[3999])


def t_time():
    import time
    names = []
    for n in ("monotonic", "time", "ticks_ms", "perf_counter"):
        if hasattr(time, n):
            names.append(n)
    return " ".join(names)


def tryit(label, f):
    try:
        out(label + " " + str(f()))
    except BaseException as e:
        out(label + " E:" + type(e).__name__)


# --- native costs at depth: deep(n, f) runs f as the frame at depth n ----------------------


def deep(n, f):
    if n > 2:
        return deep(n - 1, f)
    return f()


class PErr(Exception):
    pass


def t_exc():
    try:
        raise PErr("x")
    except PErr:
        return "ok"


def t_gc():
    gc.collect()
    return "ok"


def t_imp():
    # PRBL300 is the 300-line module that build/genprobe.py writes (M0.5)
    a = memfree()
    __import__("PRBL300")
    return "ok %d" % (a - memfree())


def t_sort():
    # 3,000 flat 2-tuples, sorted at the caller's depth: random, ascending, descending
    r = ""
    for mode in (0, 1, 2):
        print("sort mode %d" % mode)     # the last line printed names a crash
        L = []
        for i in range(3000):
            if mode == 0:
                k = (i * 7919) % 3001
            elif mode == 1:
                k = i
            else:
                k = 3000 - i
            L.append((k, i))
        try:
            L.sort()
            r += " ok"
        except RuntimeError:
            r += " RT"
        except MemoryError:
            r += " MEM"
        L = None
        gc.collect()
    return r


def t_math():
    # how math reports domain errors and overflow: an exception name, or the value
    for src in ("math.asin(2.0)", "math.log(0.0)", "math.sqrt(-1.0)", "0.0 ** -1",
                "(-8.0) ** (1 / 3)", "1e308 * 10"):
        try:
            v = eval(src)
            r = repr(v)
        except Exception as e:
            r = type(e).__name__
        out("math %s %s" % (src, r))
    return "done"


def t_poll():
    # escape() hits and get_key() codes while [clear] is held for 3 s
    if _esc is None:
        return "no ti_system"
    import time
    clk = None
    for n in ("monotonic", "time"):
        if hasattr(time, n):
            clk = getattr(time, n)
            break
    _n[0] = 0
    print("POLL: press ENTER, then")
    print("hold CLEAR for 3 seconds")
    _wk()
    hits = 0
    keys = []
    i = 0
    left = 3
    t0 = clk() if clk else 0
    while left > 0:
        i += 1
        if not i & 255:
            if _esc():
                hits += 1
            k = _gk()
            if k and len(keys) < 6:
                keys.append(k)
            if clk:
                e = int(clk() - t0)
                if 3 - e < left:
                    left = 3 - e
                    print(left)               # countdown, once per second
            elif i >= 900000:
                left = 0
    while _gk():                              # drain queued [clear] presses
        pass
    return "esc %d keys %s n %d" % (hits, keys, i)


cnt[0] = 0
try:
    plain()                    # from module level: device expects 10
except RuntimeError:
    pass
out("plain %d" % cnt[0])
# tryit(1) > lambda(2) > tramp(3) > gen(4) > plain x N:
# N = 6 -> resuming a generator with send() costs no extra frame
tryit("ingen", lambda: tramp(deep_in_gen()))
tryit("tramp", t_tramp)
tryit("throw", t_throw)
tryit("ret", t_ret)
tryit("genB", t_mem)
tryit("del", t_del)
tryit("bytea", t_ba)
tryit("time", t_time)
tryit("math", t_math)
CHAIN = None
for i in range(2000):          # a deeply nested chain for the collector to mark
    CHAIN = (CHAIN, i)
for lab, d, f in (("exc9", 9, t_exc), ("exc10", 10, t_exc), ("gc10", 10, t_gc),
                  ("imp6", 6, t_imp)):
    try:
        out(lab + " " + str(deep(d, f)))
    except BaseException as e:
        out(lab + " E:" + type(e).__name__)
CHAIN = None
tryit("poll", t_poll)
out("free %d" % memfree())
try:                           # RISKY, last: native quicksort at depth 9
    out("sort9" + deep(9, t_sort))
except BaseException as e:
    out("sort9 E:" + type(e).__name__)
```

---

## Appendix C. Defaults chosen here: confirm with the user

| # | default | alternative | cost to change |
|---|---|---|---|
| D1 | `d/dx tan(u) = sec(u)^2` | `1+tan(u)^2` | one template string |
| D2 | Trig equations: every solution in `[0, 2π)` (`[0, 360)` in degree mode) | a general family with an integer `n` | `INV` data plus a print rule |
| D3 | `solve` in real mode (`x^2+1=0` gives `no solution`) | complex roots by default | a flag; `csolve` is optional anyway |
| D4 | left/right: the caret when the line has text, otherwise scroll the answer | dedicated scroll keys | the UI key table |
| D5 | Wide answers scroll; no wrapping in v1 | FlowCE 6-line wrapping | a layout pass, about 60 lines |
| D6 | `alpha .` types `'` for `y'` | another key | the key table |
| D7 | T3 helper commands `polararea`, `paramarea`, `arclen`, `riemann`, `grad` | typed set-up integrals only | registry data |
| D8 | Typed decimals are floats (approximate answers) | exact decimals | one lexer rule |
| D9 | `d(f,x)` is `diff` only with 2+ arguments and no stored `d` | no `d` alias | the classifier |
| D10 | History inputs drawn as 1D text in v1 | 2D inputs (as FlowCE) | comes with the 2D editor |
| D11 | ENTER on an empty line repeats the last input (TI habit) | no-op | one line |
| D12 | The F4 trig forms (`in terms of sin/cos`) are optional in T2 | required | CVFORM data plus rule sets |
| D13 | Device gates inside the desktop phases: the M0.5 memory gate before T1.1, the PROBE6 gate before T1.6, bundle-lite and PRBMEM again at T1.14-T1.15. The settled process puts device tests after the UI. | all device work after the UI, as settled; then the memory and depth assumptions stay unverified until T3 is written | the §21 task order |
| D14 | Only `E` (the EE key) starts a float exponent; `2e-1` is `2·e-1` | FlowCE: `e` also starts an exponent (`2.5e-3x` is `0.0025x`) | one lexer rule and its golden lines |
| D15 | Arguments of odd and even functions are sign-normalized: `sin(1-x)` becomes `-sin(x-1)` | keep the argument as typed (`sin(1-x)` and `-sin(x-1)` are then different nodes) | `negfirst` in `fn_` |
| D16 | 2nd math opens a TEST picker (`= != < <= > >= !`) | relations on alpha keys | the key table and CVMENU |
| D17 | Lazy modules over `LAZYMAX` lines are written as parts from the start (§4.3) | write whole modules and split only if the size gate fails | file layout; merging parts later is easy |

---

## Design review log

### Review 1 (2026-10-10, applied in version 1.1)

The review checked version 1.0 against `docs/reference/` and `probe/`; its line numbers refer to
1.0. It found no declared chain deeper than 7, and 36 issues plus a list of missing tests. **No
item was rejected.** Every item was applied; the few that were adapted are listed after the table
with the reason.

| # | issue | resolution | where |
|---|---|---|---|
| 1 | Uncaught exceptions end the program | `R.go` catches `CasSoft`, `KeyboardInterrupt` (re-raised after the reset) and any `Exception` (`internal error`); it resets on every path before it builds a message; the event loop catches `Exception`; the decimal line excludes `oo`/`undef`/sentinels and runs in its own `try`; `nrun` rejects nan and inf | §10.4, §10.5, §16.2, §12.6, §6.6, §18.6 |
| 2 | Booleans were the numbers 1 and 0 | `TRUE`/`FALSE` `CON` leaves; solve maps them to "every x" / "no solution"; printed `true`/`false` | §5.2, §8.2, §11.2, §12.4 |
| 3 | Result messages were `CasError`s | sentinels: empty `LST`, `TRUE`, `DNE(l, r)`, `DIVG(w)`; only the top-level record makes messages | §5.2, §10.2, §10.5, §11 |
| 4 | Heap plan rests on an unmeasured compile peak; calibration too late | compile-peak model in the ledger; `LAZYMAX = 150` provisional with parts (D17); the M0.5 gate before T1.1 fixes `FACTOR`, `PEAKB`, `LAZYMAX`, `NMAX`, eviction and CVDRAW residency; T1.15 re-measures | §4.1, §4.3, §18.1, §18.2, §18.7, §21.3 |
| 5 | Guards folded only numeric differences | `guard_ok` (L3) decides constant relations numerically, with an exact `normal` test near 0 done by the calling generator; `absn` folds positive constants | §9.2, §9.7, §6.4 |
| 6 | Branch policy contradicted itself; verification blind to branch errors | one policy rule; the table aligned with it; a negative sample point in `g_iszero` and in simplify verification; the oracle uses `real_root` | §8.3, §8.6, §8.7, §20.5 |
| 7 | Short parse paths missed calls; solution text did not re-parse | `lex` sets `F_CALL`; rule strings use explicit `*` (linted); `rpn` builds a list from a top-level comma; `O` is a FUNCTION | §7.1, §7.2, §7.3, §7.7, §9.2, §9.3 |
| 8 | Degree mode stripped π/180 by pattern | conversions through the constructors both ways; the solve window is `[0, 360)` in degrees | §6.5, §12.4, §11.2 |
| 9 | Lowercase `e` started an exponent | only `E` does (D14) | §7.2, Appendix C |
| 10 | Eviction vs suspended generators and preloading | live pins through `need`; `R.drop` semantics; `lim`, `solve` soft dependencies of `def` and `ode` | §18.4, §18.5, §15.1, §10.4 |
| 11 | Table growth; unreachable term caps | preallocated node slots; `MAXTERMS = 400` with `MEMFREE` checks | §5.1, §8.5, §8.6, §18.3 |
| 12 | Native C-stack use and `math` behavior unprobed | PROBE6 depth and `math` sections; fallbacks per native cost; CVTEST repeats them | §3, §17.2, Appendix B, §20.11 |
| 13 | PROBE6 cancel test too short; `genB` counted two generators | a 3-second timed loop after a key press; a single-generator sample | Appendix B |
| 14 | Extended reals under-specified; `floor` limits | the ∞ folding table; piecewise functions force one-sided limits | §6.3, §11.3 |
| 15 | `y'(0)` and `mid` broke | desolve call letters; `left right mid trap` are VALUE | §7.3, §7.5 |
| 16 | Silent rule misses | view-aware buckets; `R` required in ADD/MUL identity LHS; context-match test; `excess`/`pow`/`lex` measures; the `A`/`B`/`C` rule | §9.2, §9.4, §9.8, §20.3 |
| 17 | Canonical-form gaps (`abs`, signs) | `absn`, `negfirst`, `neg_`; sign normalization (D15); invariants | §6.4, §8.2, §8.9 |
| 18 | Kronecker gcd unbounded | `KRONMAX = 64` | §8.6 |
| 19 | Unbounded big-int work | `MAXBITS` before `npowi`; no huge `str()`; `text` stops at `MAXTEXT` | §6.1, §12.1, §12.2 |
| 20 | Display cache over budget | 4 KB cap; emptied before `R.go` | §16.3, §18.1 |
| 21 | Test-infrastructure contradictions | level assertion only at `gen_penalty = 0`; level slips fixed (`guard_ok` L3, layout L4/L5, menus avoid `D.layout`, `R.start` returns code); round trip through inert `g_eval`; FLT hash and `tiefix` specified | §17.1, §17.5, §20.2, §12.5, §5.7 |
| 22 | Generator protocol lint | no `return value`, bare `except:` or `finally` in `g_*` | §10.2, §17.4, §20.3 |
| 23 | F4 re-parsed through `expand_names` | answer text skips stage 6 | §7.1, §14 |
| 24 | `sys.modules` deletion unverified | an explicit M0.5 check with two fallbacks | §18.5, §18.7, §22 |
| 25 | No interactive drawing probe | added to PROBE7 | Appendix B |
| 26 | Device gates reorder the settled process | listed for confirmation (D13) | §2, Appendix C |
| 27 | `x=3` hides the main variable | `purge` and `F_PURGEHINT` | §7.9, §15.2, §16.1 |
| 28 | `log(u,b)` unspecified | `ln(u)/ln(b)` | §7.8, §15.2 |
| 29 | `factor(360)` not representable | `HOLD` | §5.2, §11.2, §12.4 |
| 30 | Float coefficients in solve and factor | `exact()` then `approx()` | §6.3 |
| 31 | History paste wrapped too rarely | wrap unless a single atom | §16.6 |
| 32 | `ans()` rule contradicted "a message never becomes Ans" | one rule | §7.1, §7.11 |
| 33 | No way to type relations or `!` | TEST picker (D16) | §16.4, §16.7 |
| 34 | `x>3` printed `3<x` | the main variable goes left | §12.4 |
| 35 | Symbolic discriminants unspecified | the generic solution, as giac | §11.2 |
| 36 | Auto-simplify loaded the NORM set for every expression | `simplify_candidate` is resident | §7.8, §8.7, §18.2 |
| tests | missing tests | §20.12 review cases | §20.12 |

**Adapted, with reasons:**

- **#4, `LAZYMAX`.** The review suggested measuring first and expecting "≤150 lines". 150 is
  adopted now as the provisional cap, with parts written from the start (D17), because every lazy
  module is written after M0.5 anyway and merging parts later is cheaper than splitting modules.
- **#5, the exact zero test.** It cannot run inside `guard_ok`: `normal` is L3 like `guard_ok`, so
  the call would be an illegal L3 -> L3 edge. `guard_ok` returns `(NEAR, op, d)` and the calling
  generator (L2) runs `normal`. A guard that stays undecided fails, which can only miss a rule.
- **#10, counting live generators per module.** On the device a generator object does not name its
  module, so the count is kept per family through `need`, in the stack slot of the generator that
  obtained it. A generator is always created by a parent that obtained its module, so the pin
  covers every suspended generator; the guarantee is the one the review asked for.
- **#16, "forbid `A`/`B`/`C` next to `L`/`Q` in one rule".** Narrowed to the LHS. The RHS and the
  guard must be able to read the coefficients that `L` and `Q` bind (`'L^(N+1)/(A*(N+1))'`).
- **#1, `KeyboardInterrupt`.** Re-raised after the reset as suggested; the event loop already
  turns it into `Interrupted` (§16.2), so the user sees the same message as for [clear].


### Implementation follow-up: T1.11 completion (2026-10-11)

CVFACT uses four compile units, all below the provisional `LAZYMAX = 150`: 131, 121, 129 and
134 minified lines. Section 4.3 records the implemented seam; the manifest, loader and static
checkers support the `d` suffix. Cross-part helpers moved, but no section 21.2 frozen API or
function level changed. The total is 515 lines, still above the original 280-line estimate;
this split controls compilation peak only. Section 18's device memory estimates remain
provisional until T1.15. Rational `HOLD` answers display negative prime powers as denominators,
consistent with ordinary products; their exact value is unchanged.

### Single-file deployment and automatic builds (2026-10-11)

The user now explicitly requires one minified Python runtime file and automatic
GitHub Actions builds. This replaces the transfer layout in section 19; the
short-name module layout remains an intermediate build and test representation.
`build/release.py` emits `CASEVO.py`, with compressed ASCII code blocks and native
dictionary namespaces loaded through `exec`. No filesystem API or external
project module is required on the calculator. Identifier shrinking, LZ/Huffman
compression and UI/input/print eviction reduce footprint. Source modules and
their API contracts remain independently testable. See `notes/B.1.md`.

This change does **not** increase the measured Python heap. The latest provisional
model exceeds 173,360 bytes before several runtime costs; downloadable artifacts
are device test builds. Native 64-bit MicroPython compatibility with a 500,000-byte
heap is a separate gate and is not an EVO heap measurement. T1.15 and physical UI,
transfer, depth and memory acceptance are still open. A green action must not be
presented as proof of hardware readiness.

Native compatibility testing also banned stepped slices and replaced the
quadrature floating-key dictionary with a fixed dyadic sample grid. The lazy
loader collects reclaimable compilation buffers before rejecting admission.

### Transfer rejection and corrected size gate (2026-10-11)

The user could not transfer the generated CASEVO.py. Reproduction with TI
Connect Evo 7.1.0.792's actual converter established a **65,511-byte source
limit for CASEVO.py/CVTEST.py**, far below the 262,679/267,644-byte artifacts.
The Python object adds 18 bytes plus its module name under a 65,535-byte limit;
the 3.5 MB total-storage check did not cover this. See
`reference/transfer-limits.md` for the boundary tests.

Default builds enforce this limit for every generated Python file and remove
stale release outputs before validation.

### Authorized companion-file paging (2026-10-11)

The user subsequently allowed multiple files to preserve functionality. This
supersedes the single-file requirement above. The release keeps minification,
native dictionary namespaces and eviction phases, but stores each source block
in a separate importable CODE-string carrier. CASEVO/CVTEST load carriers on
demand, drop them from sys.modules immediately, and release source after exec.
No file API is required. The 110-file package has no resident compressed archive
or decoder; the largest file is 6,314 bytes and all passed TI's converter.

The provisional stage subtotal is now 139,442 bytes before excluded runtime
costs. The measured 173,360-byte heap remains the target. Physical acceptance
remains unverified. Complete files, checksums and the installation guide ship in
one deterministic ZIP, automatically built and tested by GitHub Actions.
