# Device Python reference: one code base for the TI-84 EVO and desktop CPython

This document describes the Python that runs on the TI-84 EVO and how cas-evo code
must be written so that it runs both there and in desktop CPython 3.14, where we
run the tests. It covers syntax, builtins, behaviour differences, memory, module
naming and bundling, and the desktop call-depth checker.

Every factual claim has a status tag:

| Tag | Meaning |
|---|---|
| **[V]** | Verified on the EVO by our probes (`probe/PROBE*.py`; the transcripts are in Appendix A). |
| **[R]** | Reported in the project brief from the first on-device session. The output is not in the screenshots I checked. |
| **[D]** | Documented by TI for the **TI-84 Plus CE** Python (guide for CE bundle 5.7, 2021). The CE build is "based on CircuitPython". It is probably the same on the EVO, but we have not checked. |
| **[C]** | Verified on desktop CPython 3.14.7 (the project venv) while writing this doc. |
| **[A]** | Assumed from knowledge of MicroPython/CircuitPython internals. It is not verified, and PROBE5 or PRBMEM (section 14) is meant to settle it. |

When a probe settles an [A] claim, change its tag here, so that this file stays the single source of truth.

---

## 0. The rules in one screen

1. **Keep the call stack shallow.** Code at the program's top level is depth 0. Frames at depth 1..10 run. Entering depth 11 raises `RuntimeError` **[V]**. Plan for depth 8 at most (section 2).
2. **No recursion, mutual recursion included.** Use explicit stacks. Also avoid hidden frames in deep code: comprehensions, generator expressions, lambdas and key functions, dunder methods, properties, and `with` blocks that use Python context managers.
3. **Python 3.4 syntax only.** No f-strings **[V]**, walrus, annotations, `match`, `async`, PEP 448 unpacking, `1_000`, keyword-only parameters or `raise ... from` (section 3). The lint in section 13 enforces this.
4. **Use only the builtins and modules listed in section 4.** No `math.gcd/isqrt/log10`, `int.bit_length`, `functools`, `itertools`, `re`, `fractions`, `cmath` **[V for re/fractions/cmath]**. Write them ourselves.
5. **Exact code never uses floats or `/`.** Rationals are integer pairs. Decimal output comes from our own integer-based formatter, never from `str(float)`, `repr`, `round` or `sum` (section 5).
6. **Never depend on dict or set iteration order, or on sort stability.** Sort with total keys (section 7).
7. **Expression data are tuples with small-int codes, not class instances.** Use interning and reset the intern tables between commands (section 10).
8. **Device module names are `[A-Z][A-Z0-9]{0,7}`** **[V]**, in a flat namespace. The bundler maps `src/` names to device names (section 11).
9. **There is no `if __name__ == "__main__":`.** The device runs a program as `from NAME import *` **[V]**.
10. **Every test runs under the call-depth checker** (section 12). Device-only behaviour that the desktop cannot see is listed in section 9.

---

## 1. Runtime identity and execution model

| Fact | Tag | Evidence / note |
|---|---|---|
| `sys.version` is exactly `"3.4.0"`, with nothing after it | V | PROBE3 printed `v 3.4.0` (it printed the first 28 characters) |
| The engine is a MicroPython-family interpreter. TI's CE Python is "based on CircuitPython" | D (CE), A (EVO) | guide p.40. The RuntimeError text matches MicroPython's stack check |
| Running a program shows `# Shell Reinitialized`, `# Running NAME`, `from NAME import *`. Each run gets a fresh interpreter and nothing persists | V | PROBEK, PROBE3 and PROBE4 screenshots. This is consistent with the "no persistence" decision |
| The running program's `__name__` is `"NAME"`, not `"__main__"` | A (follows from the line above) | PROBE5 prints it |
| f-strings raise SyntaxError | V | PROBE2 `fstr N` |
| `eval` and `exec` work, and `exec(src, globals())` can define functions | V | PROBE2, PROBE4 `chain` |
| 1-space indentation compiles | V | PROBE4 `exec`'d `"def f0():\n cnt[0]+=1\n f1()\n"` |
| User modules import each other, at top level and inside a function | V | PROBE `import PRBMOD`, PROBE2 `t_mod` |
| `dir(__builtins__)` raises | V | PROBE2 printed `exec? eval? ...`: every probe of `n in dir(__builtins__)` raised |
| `float` is an IEEE double (53-bit mantissa) | V/D | PROBE2 printed `0.06600000000003092` (16 significant digits, impossible for float32). The guide says "53 bits" |
| `int` has arbitrary precision | V | `len(str(3**2000))`, `(3**200)//(7**50)` |
| `complex` works. `cmath` is absent | V | PROBE3 `cxY`, mods line |
| set literals and operators, `divmod`, `round(x, n)`, `input`, `sorted(key=)`, `issubclass`, `hash(tuple)` and `"%.9g" %` all work | V | PROBE3 |
| A 5000-element list works. The CE had a 100-element limit | V / D | PROBE2 `list Y`, guide p.1 |
| Free heap is 185,296 B at the start of a small program and 173,360 B after importing several `ti_*` modules | V | PROBE3, PROBE |
| A 20,000-iteration module-level loop (`s += i*i`, which becomes a big int after about 1.5k iterations) takes 0.066 s | V | about 3.3 us per iteration with globals and big ints |
| `[on]` breaks a running program with KeyboardInterrupt | D (CE) | guide p.16. Not checked on the EVO |
| `ti_system.escape()` returns True once after `[clear]` was pressed, then resets | D (CE) | guide "escape()". Not checked on the EVO |

---

## 2. The call-depth cap

### 2.1 Measurements

In this table, depth 0 is the module-level code of the program the user runs. Each probe
shape counts how many bodies of the recursive function ran (`cnt`) before the
RuntimeError.

| Probe shape | Device result | Frames on the stack when it failed | Tag |
|---|---|---|---|
| PROBE4 `plain`: self-recursion, started by `measure()` | 9 | `measure`(1) + `plain`x9 (2..10). The 11th frame raised before its body ran | V |
| `biglc`: 8 parameters and 8 more locals | 9 | Same as `plain`, so **the number of locals and arguments does not matter** | V |
| `mutl`: ping and pong | 9 | Same, so **mutual recursion counts the same as plain recursion** | V |
| `meth`: `self.m()` | 9 | Same, so **method calls cost one frame, like functions** | V |
| `chain`: 41 *distinct* functions f0 -> f1 -> ... (defined with exec) | 8 | `measure`(1) + lambda(2) + f0..f7 (3..10). **This is a depth cap, not a recursion detector** | V |
| `gen`: `yield from` chain consumed by `list()` | 8 | `measure`(1) + lambda(2) + gen x8 (3..10). **Every active generator is a frame. The native `list()` driving them cost 0 frames** | V |
| `nest3`: 3 wrapper functions, then `plain` | 6 | `measure` + w1 w2 w3 (2..4) + plain x6 (5..10). **Frames used by callers reduce what callees get** | V |
| `lamb` | `AttributeError` | `cnt.__setitem__` does not exist. This says nothing about lambdas, but shows that **dunder methods of builtin types are not attributes** | V |
| `paren`: `eval` of 80 nested `(...)` | ok | The compiler handles redundant nesting. This is weak evidence, because the parser may collapse the parentheses | V |
| PROBE3 `rec(8)` from module level | ok (9 frames); `rec(12)` fails | Consistent with the above. Error text: `RuntimeError: maximum recursion depth ...` | V |
| PROBE3: 41-deep method recursion; PROBE2: `rec(25)` | RuntimeError | | V |

**Rule [V]:** frames at depths 1..10 run. A call that would create the frame at depth 11 raises
`RuntimeError("maximum recursion depth exceeded")` (the screen showed only the first 24
characters of the message) before the callee's body runs. The error can be caught: `measure()`
caught it, and the program went on with no problems.

### 2.2 What costs a frame

| Construct | Frame cost on the device | Tag |
|---|---|---|
| A call to a `def` function or method, including exec-defined functions | 1 | V |
| An active generator, and each `yield from` level | 1 while it runs | V |
| A native builtin that iterates a generator (`list(gen)`) | 0 extra | V |
| A lambda | 1 (it is a function) | A (PROBE5 `lamb`) |
| A list, set or dict comprehension | **+1**. MicroPython compiles each one into a hidden function. CPython 3.12+ inlines them, so the desktop shows no frame [C: the desktop PROBE5 run gives `lcomp 998`] | A (PROBE5 `lcomp`) |
| A generator expression | +1 while it runs | A (PROBE5 `genexp`) |
| A key function called by `sorted`/`min`/`max`; a function called by `map`/`filter` | 1 + the native trampoline cost (0 or 1?) | A (PROBE5 `sortk`, `minkey`, `map`) |
| Dunder methods invoked by syntax (`==`, `<`, `+`, `hash()`, `in`, `str()`), `__init__` on instantiation, property getters, `__enter__`/`__exit__` | 1 + the trampoline cost | A (PROBE5 `eq`, `init`, `hash`, `str`, `add`) |
| `eval("f()")` | 1 for `f` + the cost of eval itself | A (PROBE5 `eval`) |
| The body of a module imported with `import X` | +1 relative to the importer? | A (PROBE5 `imptop`/`impfn` with PRBIMP) |
| Class bodies (they run at import) | 1 | A |

**Likely mechanism [A]:** MicroPython raises exactly this RuntimeError from its C-stack check
(`MP_STACK_CHECK`). So the cap is most likely a small *C-stack* limit, and the frame-count
behaviour comes from each Python call using about the same amount of C stack. All the [V] data
fit this model. The consequence is that **native code that recurses in C can use up the same
budget, or, where it is unchecked, overflow the real stack**. Examples are comparing, hashing,
printing or `repr`-ing deeply nested tuples and lists, `sort` (a recursive quicksort in
MicroPython), and compiling deeply nested source in `eval`. PROBE5's last section measures how
deep nested tuples can be for native `==`, `hash`, `repr` and `<`.

### 2.3 Design rules

1. **No recursion anywhere in `src/`, direct or mutual.** Parser, printer, simplifier, rule engine,
   polynomial algorithms, limits and ODE code all run as loops over explicit work stacks.
2. **Every module layer gets a fixed depth.** Proposed budget (the design doc may move the
   layers, but not the margin):

   | Depth | Layer | Notes |
   |---|---|---|
   | 0 | Entry program body, with the event loop at module level | A `main()` would spend a frame here |
   | 1 | Key handler or dispatcher | Catches CasError, MemoryError, RuntimeError, KeyboardInterrupt |
   | 2 | Command runner (evaluates one input line) | Lazy imports happen here, so module bodies run at 3 |
   | 3 | Command implementation (`integrate`, `solve`, ...) | |
   | 4 | Algorithm driver (rule-engine loop, partial fractions, ...) | |
   | 5 | Engine primitive (normalise node, polynomial division, ...) | |
   | 6 | Arithmetic kernel (rational ops, gcd, isqrt) | |
   | 7 | Leaf helper | Includes the leaf's comprehension and key function |
   | 8 | Test budget limit | Allowed, but nothing is planned here |
   | 9-10 | Reserve for unmeasured native and dunder costs | Never planned |
3. **Avoid hidden frames from layer 5 down:** no comprehensions, generator expressions, lambdas,
   `key=` functions, Python dunders, properties or `with`. Use plain `for`/`while` loops and
   decorate-sort-undecorate (section 7).
4. **Polling for cancel must not add a frame in deep loops.** The UI injects the native
   `ti_system.escape` or `get_key` as a global (for example `core.POLL = ti_system.escape`).
   Calling a native function costs 0 Python frames [A]. Deep loops call it every 256 iterations
   or so.
5. **Never parse user input with `eval`.** The parser uses an explicit stack. It also enforces
   `MAXNEST`, a nesting limit chosen from PROBE5 results (32 until then), so that native
   operations on nested data stay safe.
6. **The top-level handler catches `RuntimeError`** and reports "expression too complex". If the
   tests pass, it should never fire.

---

## 3. Syntax

### 3.1 Allowed (Python 3.4 as MicroPython implements it)

| Feature | Tag | Notes |
|---|---|---|
| `def`, `return`, default args, `*args`, `**kwargs`, keyword arguments in calls | A (core MicroPython) | |
| `lambda` | D | Costs a frame; avoid in deep code |
| `if/elif/else`, `while/for` (+`else`), `break`, `continue`, `pass` | D | |
| `try/except/else/finally`, `except E as e`, `raise E(...)`, `assert`, `del` | D/A | |
| `global`, `nonlocal` | D (keyword list) | |
| `class` with single inheritance, `@staticmethod`, `@classmethod`, `property` | D | Keep classes rare (section 8) |
| `yield`, `yield from` | V | |
| Conditional expressions, chained comparisons, `is`, `in`, augmented assignment | A | |
| List, dict and set comprehensions, generator expressions | A | Each costs a frame (section 2.2) |
| Set literals `{1, 2}` | V | |
| Tuple unpacking, starred assignment `a, *b = t` | A | PROBE5 `star=` |
| Slicing with a step (`s[::-1]`) | A | PROBE5 `slice` |
| `%`-formatting | V | Preferred over `str.format` |
| `str.format` (subset) | D | |
| `0x`/`0o`/`0b` literals, big-int literals, complex literals `2j`, `b''` | A/D | |
| `print(..., end=" ")` | V | |
| `with` + a context-manager class | A | Costs 2 dunder frames; avoid in deep code |
| Decorators | A | |
| 1-space indentation, `;` statement separators | V / A | The bundler may use both to shrink files |

### 3.2 Forbidden or unsafe

| Construct | Why | Tag | Use instead |
|---|---|---|---|
| f-strings | SyntaxError | V | `"%s=%d" % (a, b)` |
| `:=` (3.8) | Not 3.4 | A | Plain assignment |
| Parameter, return and variable annotations | Support is uncertain; variable annotations are 3.6 syntax | A | Comments |
| `match` (3.10), `async`/`await` (3.5), `except*` (3.11), `type X =` (3.12) | Not 3.4 | A | |
| Positional-only `/` (3.8) | Not 3.4 | A | |
| Keyword-only parameters `def f(a, *, b)` | Valid in 3.4, but MicroPython support is unverified | A (PROBE5 `kwonly`) | Plain defaults |
| PEP 448 unpacking: `[*a, *b]`, `{**d}`, `f(*a, *b)` (3.5) | Not 3.4 | A | `a + b`, `d2 = dict(d); d2.update(e)` |
| `@` matrix operator (3.5), `1_000` (3.6) | Not 3.4 | A | |
| `raise X from Y` | MicroPython parses it but drops the chaining | A | Plain `raise` |
| `raise StopIteration` inside a generator | CPython 3.7+ turns it into RuntimeError [C]; MicroPython ends the generator [A] | C/A | `return` |
| `if __name__ == "__main__":` | Never true on the device | V (derived) | The entry program runs its code at top level |
| `__slots__` | CPython enforces it [C]; MicroPython ignores it [A] | C/A | Don't use classes for data |
| Metaclasses, `__init_subclass__`, `__class_getitem__`, descriptors other than `property`, `__del__`, `__getattribute__`, complex multiple inheritance | Unsupported or partly supported | A | |
| `import functools`, `itertools`, `re`, `fractions`, `decimal`, `cmath`, `os`, `typing`, `dataclasses`, `enum`, `abc`, `copy`, `operator`, `string`, `io` | Absent | V (`re`, `fractions`, `cmath`, `os`, `micropython`), A (the rest) | Own code |
| Non-ASCII characters in source | The transfer path and encoding are unknown | A | `chr(0x3c0)` in the UI layer |
| `print(..., file=..., flush=...)` | Unverified | A | |

---

## 4. Builtins and modules

### 4.1 Builtins

* **Verified on the EVO [V]:** `print`, `len`, `range`, `list`, `str`, `type`, `getattr`, `hasattr`,
  `dir` (on modules), `__import__`, `eval`, `exec`, `globals`, `complex`, `set`, `divmod`, `round`,
  `input`, `callable`, `sorted(key=)`, `issubclass`, `hash`, `BaseException`, `Exception`,
  `RuntimeError`, `AttributeError`, and `type(e).__name__`.
* **Documented on the CE, so assumed present [D]:** `abs all any bin bool bytearray bytes callable chr
  classmethod dict dir divmod enumerate eval exec filter float getattr globals hasattr hash help
  hex id input int isinstance issubclass iter len list locals map max memoryview min next object
  oct ord pow print property range repr round set setattr slice sorted staticmethod str sum super
  tuple type zip __import__ __build_class__ Ellipsis`.
* **Not in the CE list, so treat as absent until PROBE5 shows them [A]:** `reversed`, `frozenset`,
  `compile`, `open`, `format` (the builtin; `str.format` exists), `vars`, `ascii`, `delattr`,
  `NotImplemented`, `breakpoint`, `exit`/`quit`, `RecursionError`.
  Replacements: `reversed(x)` becomes `x[::-1]` or an index loop; `frozenset` becomes `tuple(sorted(...))`.
* **Exceptions (CE) [D]:** `BaseException ArithmeticError AssertionError AttributeError EOFError
  Exception GeneratorExit ImportError IndentationError IndexError KeyboardInterrupt KeyError
  LookupError MemoryError NameError NotImplementedError OSError OverflowError RuntimeError
  StopIteration SyntaxError SystemExit TypeError UnicodeError ValueError ZeroDivisionError`,
  plus TI's `ReloadException`. **Missing:** `RecursionError`, `ModuleNotFoundError` (catch
  `ImportError`), `FloatingPointError`, `TimeoutError`, and the other 3.5+ classes.

### 4.2 Modules

| Module | Status | Contents we may use |
|---|---|---|
| `math` | present (D, R) | CE list [D]: `e pi sqrt pow exp log cos sin tan acos asin atan atan2 ceil copysign fabs floor fmod frexp ldexp modf isfinite isinf isnan trunc radians degrees`. `log(x, base)` works [D]. **Not listed, so write our own:** `gcd isqrt factorial log10 log2 sinh cosh tanh asinh acosh atanh hypot isclose fsum comb perm prod gamma erf`, and the constants `inf nan tau` (use `float('inf')`). `math.pow` converts to float [D], so never use it for exact powers |
| `sys` | present (V) | `version` [V]; `modules`, `implementation`, `maxsize` [A]; no `setrecursionlimit`, `settrace` or `getsizeof` [A] |
| `gc` | present (V) | `collect`, `mem_free` [V]; `mem_alloc` [R/A]; `threshold` [A] |
| `time` | present (V) | CE: `monotonic`, `sleep` [D]. On the EVO, which of `monotonic`/`time` exists is unverified |
| `array` | present (V) | Compact typed arrays for big tables of small numbers |
| `collections` | present (V) | `OrderedDict`, `namedtuple`, `deque` [A]. Avoid `deque`: the MicroPython API differs |
| `random` | D (CE), A (EVO) | `seed getrandbits randrange randint choice random uniform` |
| `ti_system` | present (V) | EVO names [V]: `disp_at disp_clr disp_cursor disp_wait escape getKey get_key recall_RegEQ recall_list sleep store_list wait wait_key`. On the EVO, `wait_key` returns TI-BASIC getKey codes, and 2nd/alpha arrive as separate presses [V] |
| `ti_graphics` | present (V) | Tail of the name list [V]: `...drawLine drawPolyLine drawRect drawString fillArc fillCircle fillPolygon fillRect getPixel hsv_to_rgb popImage pushImage setColor setFont setPen setPixel string_size` (earlier names scrolled off) |
| `ti_draw` | present (V) | CE API [D]: `draw_line draw_rect fill_rect draw_circle fill_circle draw_text draw_poly fill_poly poly_xy clear clear_rect set_color set_pen set_window show_draw`, with pixels 0..319 x 0..209 |
| `ti_plotlib` | present (V) | Not used in v1 (no graphing) |
| `ti_image` | unknown | PROBE2 tested it, but the line scrolled off |
| `cmath`, `re`, `fractions`, `os`, `micropython` | **absent (V)** | |
| `functools`, `itertools`, `decimal`, `struct`, `io`, `json`, `heapq`, `bisect`, `copy`, `operator` | absent (A) | |

Only `src/ui*` imports `ti_*`. The core receives native callables, such as the cancel poll, by injection.

---

## 5. Numbers

### 5.1 int

* Ints have arbitrary precision [V]. Small ints (|n| < 2^30 on a 32-bit build) are unboxed, so they
  cost no allocation. Larger ints are heap objects with 16-bit digits [A].
* `//`, `%` and `divmod` floor towards minus infinity, as in CPython [A] (PROBE5 `negmod`). 3-argument
  `pow(a, b, m)` is likely present [A] (PROBE5 `pow3`).
* `int.bit_length`, `to_bytes` and `from_bytes`, `math.gcd` and `math.isqrt` are **absent or
  unverified**. Write `ilog2`/`nbits` as a loop, Euclid's gcd, and Newton's isqrt. The desktop has
  all of these, so the lint bans them; otherwise tests would pass on the desktop only.
* **`/` on ints returns a float. Never use it in exact code.** Rationals are `(p, q)` with `q > 0`,
  normalised by gcd. The lint can ban `ast.Div` in exact-core modules.
* **Mixed int/float comparison:** CPython compares exactly (`(10**20+1) == 1e20` is `False` [C]).
  MicroPython converts the int to a float (`True`) [A]. Never compare exact values with floats.
* **`float(huge_int)`:** CPython raises OverflowError [C]. MicroPython probably returns `inf` [A], and
  its rounding of big-int-to-float may differ. Convert exact to approximate values with our own
  integer-scaled routine.
* **Digit limit:** CPython 3.11+ refuses `str(int)` beyond 4300 digits (ValueError [C]). The device
  has no such limit [A]. Call `sys.set_int_max_str_digits(0)` in `tests/conftest.py`, and cap the
  displayed digits in the CAS itself.

### 5.2 float

* Floats are IEEE doubles [V/D]. With double precision on a 32-bit build, every float is a 16-byte
  heap object, so float-heavy loops allocate [A].
* **`str`/`repr` differ:** the CE shows "up to 16 significant digits" [D]. CPython uses the shortest
  round-trip form, up to 17 digits: `repr(0.1+0.2)` is `'0.30000000000000004'` on CPython [C] and
  probably `'0.3'` on the device. **Never `str()` a float in user-visible output or golden files.**
* `"%.9g" %` works [V]. Correct rounding of the last digits is unverified [A], because MicroPython's
  float formatter is not always correctly rounded. **The 10-significant-digit decimal line comes
  from our own formatter.** For a rational `p/q`, produce the digits by integer division. For a
  float, take `m, e = math.frexp(x)` [D], scale `m` to a 53-bit integer, and round the decimal
  digits with integer arithmetic. The output is then identical on both platforms by construction.
  Apply scientific notation when |x| >= 1e10 or |x| < 1e-4.
* **`sum()` of floats:** CPython 3.12+ uses compensated summation. `sum([0.1]*10) == 1.0`, while a
  loop gives `0.9999999999999999` [C]. The device sums naively [A]. Use `sum()` only on ints, and
  accumulate floats in explicit loops (Riemann sums, numeric integration).
* **`round()`:** CPython rounds halves to even (`round(2.5) == 2` [C]). MicroPython uses
  `nearbyint`, and `round(x, n)` multiplies by 10^n, so edge cases may differ [A]. Never use
  `round` for display.
* `1.0/0.0` raises ZeroDivisionError [C, A on the device]. `math.sqrt(-1)` raises ValueError.
  `math.inf` is absent [D], so use `float('inf')`.

### 5.3 complex

* `complex` works [V], and `abs(3+4j)` works [A]. `cmath` is absent [V]. Exact complex numbers in
  the CAS are pairs of exact reals anyway, and numeric complex functions are written with `math`.
* `complex("1+2j")` works, but `complex("1 + 2j")` (with spaces) raises [D].

---

## 6. Strings

* **Safe methods [A, MicroPython core]:** `join split rsplit(sep) strip lstrip rstrip
  startswith endswith` (with a *single* string argument), `find rfind index rindex count replace
  lower upper isdigit isalpha isspace isupper islower partition rpartition format encode`, plus
  `in`, slicing, `*`, and `%`.
* **Avoid [A: absent in MicroPython]:** `ljust rjust center zfill` (use `' ' * n`), `title
  capitalize swapcase casefold isalnum isnumeric isdecimal isidentifier isprintable expandtabs
  translate maketrans format_map removeprefix removesuffix`, `startswith((a, b))` with a tuple, and
  `rsplit(None, n)`. PROBE5 `nostr`, `swtup` and `rsplitN` check these.
* **Formatting:** use `%d`, `%s` and `%.Ng`. `%*d` is unverified [A].
* **Text encoding:** keep internal strings ASCII. Glyphs such as pi, the square root sign, the integral sign and theta exist only in the UI drawing
  layer. MicroPython stores UTF-8, so indexing non-ASCII strings is O(n) [A].
* **Building output:** collect fragments in a list and `''.join` them once. `s += t` in a loop
  creates garbage.
* **Interned strings:** identifiers and short string literals (about 10 characters or fewer) in
  source become permanent interned "qstrs". They are never freed, even when their module is
  unloaded. Longer literals are ordinary heap strings, freed with their module. Runtime-built
  strings are not interned, and there is no `sys.intern` [A].

---

## 7. Containers, ordering and sorting

* **dict order:** CPython guarantees insertion order [C]. MicroPython iterates in hash-table slot
  order [A] (PROBE5 `dictord`; CPython prints `xambzcqe`). CPython also randomises `str` hashes per
  process, so the iteration order of sets of strings changes from one desktop run to the next [C].
  **No output, rule order or term order may depend on dict or set iteration.** Keep an explicit
  list of keys, or sort with a total key. Leave `PYTHONHASHSEED` random in CI, so that order
  bugs show up.
* **set** is present [V]. **frozenset** is not in the CE list [A]: use `tuple(sorted(s))` as a
  hashable key.
* **Sorting:** `sorted`/`list.sort` with `key=` works [V]. In MicroPython [A]:
  * the sort is an in-place quicksort, so it is **not stable** (PROBE5 `stable`; CPython prints
    `bdfhjlacegik`);
  * the **key function is called on every comparison**, not once per element (PROBE5 `kc`;
    CPython calls it 12 times), and each call costs a frame;
  * the quicksort recurses in C.

  Rules:
  * Make keys total by appending a unique index.
  * In deep layers, decorate-sort-undecorate: `dec = [(k(x), i) for ...]`, then `dec.sort()`, then
    reorder by `i`, with no `key=`. A loop instead of the comprehension saves the frame.
  * Never sort mixed incomparable types; that raises TypeError on both platforms.
* **list:** `append extend insert pop remove index count reverse sort` [D]. `copy`/`clear` are
  unverified [A], so use `L[:]` and `del L[:]`. A big list is one contiguous block, and the
  non-moving GC can fragment the heap, so allocate big buffers early [A].
* **tuple** is the default record type: immutable, one allocation, hashable.
* **dict views** do not support set operations in MicroPython [A]. Don't write `d.keys() & e.keys()`.
* **array** [V present]: use `array('i', ...)` and similar for large tables of small numbers.
  It cannot hold big ints.

---

## 8. Classes, introspection and exceptions

* User classes and methods work [V]. Every method call is 1 frame [V]. Operator dunders,
  `__init__` and property getters each cost a frame [A].
* **Supported special methods [A]:** `__init__ __repr__ __str__ __eq__ __ne__ __lt__ __le__ __gt__
  __ge__ __hash__ __len__ __getitem__ __setitem__ __iter__ __next__ __contains__ __call__ __add__`
  and the rest of the arithmetic dunders. Reflected operators such as `__radd__` depend on a
  build flag [A] (PROBE5 `radd`). `__getattr__` is probably supported, `__slots__` is ignored,
  and `__del__` is not supported.
* **Dunder methods of builtin types are not attributes:** `cnt.__setitem__` raises AttributeError [V].
  Never call `list.__getitem__`, `int.__add__`, `object.__setattr__` and similar directly.
* **Introspection is limited:** `dir(__builtins__)` fails [V]; `dir(module)` [V] and
  `type(x).__name__` [V] work; there are no `inspect` or `traceback` modules and no
  `sys.settrace` [A]; docstrings are discarded and `__qualname__` is absent [A]. Dispatch on
  small-int codes or `isinstance` against builtins; no reflection-based plugin systems.
* `bool` is a subclass of `int` on both platforms. Test for `bool` before `int` when it matters.
* **Exceptions:**
  * `str(e)` and `type(e).__name__` work [V]; `e.args` [A]. There are no tracebacks and no chaining.
  * `RecursionError` does not exist on the device [A]. In CPython it subclasses `RuntimeError`
    [C], so `except RuntimeError` works on both.
  * `KeyboardInterrupt` (`[on]` on the CE [D]) is a `BaseException`. Catch it explicitly at the
    top level.
  * In the `MemoryError` handler, stay shallow (depth 1). Set the big references to `None`,
    call `gc.collect()`, and only then build the message, from a preallocated string.
  * Lazy imports catch `ImportError`, not `ModuleNotFoundError`.

---

## 9. Where desktop CPython 3.14 hides device problems

All rows are verified on CPython [C]. The device column is [A] unless marked otherwise.

| Topic | CPython 3.14 | Device | Mitigation |
|---|---|---|---|
| List, set and dict comprehensions | Inlined, no frame (PEP 709): PROBE5 `lcomp 998` | One frame each | The checker adds +1 per comprehension (section 12) |
| Recursion limit | about 1000 | **10 frames [V]** | The checker emulates it |
| `sum()` of floats | Compensated | Naive | Loops |
| `str(int)` > 4300 digits | ValueError | Fine | `sys.set_int_max_str_digits(0)` in conftest |
| `raise StopIteration` in a generator | RuntimeError | Ends the generator | `return` |
| dict order | Insertion | Hash slot | Explicit order |
| `str` hash | Random per process | Fixed | Never depend on set order |
| `repr(float)` | Shortest form, up to 17 digits | Up to 16 digits [D] | Own formatter |
| `round(x, n)` | Correctly rounded, half-even | Multiply and `nearbyint` | Own rounding |
| `int == float` | Exact | Via float | Don't mix |
| `float(10**400)` | OverflowError | `inf`? | Own conversion |
| Sort stability and key calls | Stable, key once per element | Unstable, key per comparison | Total keys, pre-decorate |
| `math.gcd/isqrt/log10`, `int.bit_length`, `str.ljust`, `reversed`, `frozenset`, ... | Present | Absent [D/A] | Lint bans |
| `__slots__` | Enforced | Ignored | Don't use |
| `__name__` of the run program | `"__main__"` | `"NAME"` [V-derived] | No main guard |
| f-strings, annotations, `[*a]` | Accepted, even by `ast.parse(..., feature_version=(3, 4))` [C] | SyntaxError [V for f-strings] | Explicit lint checks (section 13) |

---

## 10. Memory

### 10.1 Budget

* There is about **185 KB of free heap** at program start, and about 173 KB after importing several `ti_*`
  modules [V]. Everything lives in this one heap: our compiled bytecode, compile-time
  transients, interned names, expression data and history.
* No precompiled `.mpy` support is known on TI [A]. Every module is compiled from source on
  every run, so the compile peak (parse tree plus bytecode under construction) and the compile
  time both count.
* The GC is mark-sweep and non-moving [A]. A collection on a heap of about 180 KB is cheap. Fragmentation can
  make a large contiguous allocation fail even when the total free memory looks sufficient.

### 10.2 Object sizes (32-bit MicroPython, 16-byte GC blocks): estimates [A], to be measured with PRBMEM

| Object | Approx. heap bytes | Note |
|---|---|---|
| Small int, `None`, `True`/`False`, interned short str | 0 | Immediate or shared |
| float | 16 | Boxed double |
| int around 2^64 | about 32 | Header + digit array; grows about 16 B per 128 bits |
| tuple of n items | 16 (n<=2), 32 (n<=6), 48 (n<=10) | **One allocation; the best record** |
| list of n items | 16 header + item array (at least 16, doubles as it grows) | Two allocations, over-allocated |
| Small dict | 48-80 | |
| Class instance with 2 attributes | 48-80 | Instance + attribute map; slower attribute access |
| Runtime str of 20 characters | about 48 | |
| Closure | 16-32 per creation, plus about 16 per captured variable | Re-created on every call of the outer function |
| Bound method `f = obj.m` | 16 per creation | `obj.m()` call syntax avoids it |
| Generator object | 32-100+ | Holds its frame state |

### 10.3 Idioms

1. **Expression nodes are tuples headed by a small-int op code**, for example `(ADD, c1, c2, c3)`.
   N-ary sums and products are flat, as the architecture decision says. Leaves are small ints or
   symbol ids. Don't create a class instance per node.
2. **Interning (hash-consing).** Keep `INTERN = {}` mapping each node to its canonical copy, so
   that equal subtrees are the *same* object. This removes duplicate subtrees, lets canonical
   forms be compared with `is`, and allows memo tables keyed by node.
   * **Caveat:** if children are nested tuples, every `hash` or `==` on a node walks the whole
     subtree natively. That is O(size) per intern lookup, and it uses unmeasured C stack
     (section 2.2). Tuples do not cache their hash.
   * **Recommended input for the design doc:** children are **integer node ids**.
     * `NODES` is a list of tuples. `INDEX` is a dict mapping a tuple of the form
       `(op, id1, id2, ...)` to its id.
     * Hashing and equality are then flat (O(arity)), node equality is int equality, and no
       native code recurses.
     * The price is about 12 bytes per node for the list slot and the dict entry.
     * Both tables must be **reset between commands**. Re-intern Ans, history and stored
       variables into the fresh tables with an explicit-stack copy, or keep them as source text.
   * If PROBE5 shows that native `==` and `hash` are safe to depth 128 or more, nested-tuple
     children (without ids) are a valid, simpler alternative, provided the parser enforces
     `MAXNEST`.
3. **Op codes and symbols are small ints**, with a symbol table of name to id. Small ints need no
   allocation, compare in one instruction and hash trivially.
4. **Prefer tuples to lists** for anything that is never mutated. Use lists for work stacks and
   accumulators, and reuse them with `del stack[:]`.
5. **No closures or lambdas in the core.** Use module-level functions with explicit arguments.
   Rule-engine actions are *data* (templates and op codes) that the engine loop interprets, not
   Python callables. That saves both frames and allocations.
6. **Avoid properties, namedtuple attribute access and per-node method calls in hot paths.**
7. **Large constant tables** (the integral table, the command catalog, help text) go in
   lazily imported modules as tuples of tuples. Long help strings are freed when their module
   is unloaded; short ones stay interned [A].
8. **Drop temporaries explicitly** (`big = None`) before the next stage, and call `gc.collect()` at
   command boundaries.
9. **Allocate long-lived buffers early**, such as the history ring, because of fragmentation [A].
10. **In hot loops, use locals.** Globals are dict lookups. Bind `ap = out.append` once.
11. **Store rationals as `(p, q)` tuples.** Keep the values small and normalised.

### 10.4 Loading and unloading modules

* `import X` compiles the source, which needs a transient RAM peak higher than the final size,
  and keeps the bytecode, the globals and the interned names.
* To unload, remove every reference, then call `gc.collect()`:
  * `del sys.modules["X"]` (assumes `sys.modules` exists [A]);
  * the name bound by `import X`;
  * any copies made by `from X import f`;
  * rule tables that hold X's functions.

  Interned names and short strings stay [A]. Expect about 1 KB of "kept" memory per module; PRBMEM
  measures it.
* **Lazy-load only from depth 2 or less**, because the module body runs one frame deeper [A]
  (PROBE5 `imptop`/`impfn`). Module bodies must only define functions and build tables, and must
  not run deep calls.
* Avoid star imports in our own modules. MicroPython's handling of `__all__` is unverified [A].
* Measure the start-up time (the compile time of eagerly imported modules) with `time.monotonic`.

### 10.5 Measuring on the device

Use **PRBMEM** (section 14.3). It reports:

* **bytes per object shape**, which validates the table in 10.2;
* for each module in `MODS`: `cost`, the steady-state footprint (bytecode, globals and interned names);
* `kept`, the memory not reclaimed after unloading;
* `peak`, an estimate of the transient RAM needed to compile the module. PRBMEM finds the
  largest "ballast" `bytearray` that still lets the import succeed, by binary search.

Run it in a fresh shell (every program run starts one). List the modules leaf-first, so that each
cost is incremental. Note that `free()` calls `gc.collect()` twice, so a fragmented heap
still gives stable numbers.

---

## 11. Module naming and bundling

* **Device names:** 1-8 characters, upper case, starting with A-Z. Digits are allowed after the first
  character [V: PROBE2, PROBE3, PROBE4, PRBMOD all ran and imported]. The CE also allows `_` [D],
  but that is unverified on the EVO, so use `[A-Z][A-Z0-9]{0,7}`.
* **Flat namespace:** no packages, no `__init__.py`, no relative imports. Imports use exact
  device names (`import PRBMOD` [V]).
* **Prefix:** use a project prefix, so that we never collide with other programs on the
  calculator. Example: entry program `CAS`, modules `CASxxxxx` (up to 5 more characters).
  A manifest in `build/` maps each `src/` module to its device name. The bundler checks that
  names are unique, at most 8 characters and valid. Don't derive names by automatic truncation.
* **Import rewriting:** the bundler rewrites `import cas.parse as P`, `from cas import parse` and
  `from .parse import f` to the device names. String references to module names (the lazy
  loader's `sys.modules[...]`) must come from one generated table, not literals scattered
  through the code.
* **The entry program** is run as `from CAS import *` [V]. Its body is depth 0, and
  `__name__ == "CAS"`. Keep it tiny: import the UI module and run the event loop at module level.
  No other module may import the entry module. It is still half-initialised while the app runs.
* **Minify** (output only):
  * strip comments, docstrings and blank lines;
  * use 1-space indentation [V];
  * optionally shorten module-level names, attributes and function names, which are interned
    permanently. Local names matter less [A].
  * Emit a line map (device line number to source line), because device errors report only
    line numbers [D].
* **ASCII and LF only.** Keep each module's source at roughly 20-30 KB or less, to limit the
  compile peak until PRBMEM gives real numbers. CE AppVars max out around 64 KB [A]; the EVO
  limit is unknown.
* **After bundling,** run the section 13 lint and `compile()` on every output file. Then run the
  whole test suite against the *bundled* modules, with a shim `sys.path`, to catch rewrite bugs.

---

## 12. Desktop call-depth checker

### 12.1 Design

* **Mechanism.** It uses `sys.monitoring` (PEP 669, CPython 3.12+) with events `PY_START`,
  `PY_RESUME` (generator resume), `PY_RETURN`, `PY_YIELD`, `PY_UNWIND`, `CALL`, `C_RETURN` and
  `C_RAISE`. Callbacks return `DISABLE` for non-device code, so its call sites stop costing
  anything after their first hit.
* **What counts.** Only frames whose code lives under `src/` (the "device dirs") count. pytest,
  test modules, `shim/` (which stands in for native `ti_*`) and the stdlib are invisible: on the
  device they are native code or don't exist. **No test-harness frames need excluding by name.**
* **Depth.** On each `PY_START`/`PY_RESUME` of a device frame, the checker looks back along
  `f_back` for the nearest *live* device ancestor and takes its depth, or `base` if there is
  none, then adds 1.
  * `base` is the device depth of whatever calls the code under test. The default is 2, the
    command runner's caller. Set it per test with `@pytest.mark.device_base(n)`.
  * Because the walk stops at the first live device ancestor, it is short. It reaches the
    stack root only when tests call into `src/`.
* **Builtins that call back into Python.** A `CALL` event in device code whose callable has no
  `__code__` (a builtin function or a class) marks the calling frame as "inside a builtin". The
  mark is cleared by `C_RETURN`/`C_RAISE` or by the next Python call. A device frame started
  while its caller holds the mark costs `1 + native_penalty`. This covers `sorted`/`min`/`max`
  key functions, `map`/`filter` (when consumed by a builtin), `list(gen)`, `sum(genexpr)` and
  class instantiation (`__init__`).
* **Implicit dunders.** A frame named `__x__` that was not entered through a builtin costs
  `1 + dunder_penalty`. Examples: `a == b`, `hash(x)` on a user class, `x in s`, `str(obj)`.
* **Comprehensions.** CPython 3.12+ inlines list, set and dict comprehensions (PEP 709), but the
  device gives each one a frame.
  * The checker parses each device file once and collects the comprehension source spans.
  * A callee started at an instruction inside k comprehension spans gets +k.
  * Each frame is also checked at its "reach": its depth plus the deepest comprehension nesting
    inside its own code. That catches a leaf at depth 8 whose comprehension would be frame 9.
  * Generator expressions are real frames on both platforms, so they need no special handling.
* **Penalties.** The defaults are `native_penalty=1` and `dunder_penalty=1`, the strict setting,
  until PROBE5 measures the real cost. The one data point we have (`list(gen)` cost 0 [V]) means
  strict mode can over-count by 1 for that pattern. That is the safe direction.
* **Two limits.**
  * `budget` (8) is the test limit. Every frame deeper than it is recorded as a violation, with
    a squashed stack.
  * `hard_limit` (10) is the device's limit. With `emulate=True`, the checker raises
    `RuntimeError('maximum recursion depth exceeded')` *inside the code under test* when depth 11
    is entered, as the device does. Error-handling paths can then be tested, and recursion
    stops at the device depth instead of CPython's 1000.
  * Violations are recorded even when the code under test catches that RuntimeError.
* **Calibration.** A replica of the PROBE4 shapes must reproduce the device's numbers
  (plain 9, mutl 9, meth 9, gen 8, nest3 6) with zero penalties. Section 12.4 has the test,
  which passes on 3.14 [C]. When PROBE5 reports the `lcomp`, `sortk`, `eq`, ... numbers, add
  them to the calibration table and set the default penalties to match.
* **Cost.** It is about 33x slower on a call-heavy microbenchmark [C]. Real CAS code does more
  work per call. If the suite gets slow, run the full suite under the checker in CI and a fast
  subset locally.
* **Limitations.**
  * The checker only sees exercised paths, so pair it with the static lint (section 13) and
    its recursion check.
  * It does not see native C recursion (nested-tuple `==`/`hash`, quicksort). Section 2.3,
    rule 5, covers that by design.
  * `for x in map(f, xs)` (iteration by the `FOR_ITER` bytecode, not a builtin call) gets no
    native penalty.
  * `restart_events()` on exit re-enables locations DISABLEd by *other* tools (coverage), which
    only costs speed.
  * Monitoring is global across threads. Our tests are single-threaded.

**Why not `sys.setprofile`?** It works for counting (a `'call'` event, `f_back` walk, `'c_call'`
to detect builtins). However, when a profile function raises, CPython **removes the profiler**
(`sys.getprofile()` returns `None` afterwards [C]), so device emulation stops after the first
violation, and the bookkeeping leaks because the `'return'` events are lost. It was also slower
in our test (38x [C]). Use it only as a fallback on CPython < 3.12, with `emulate=False`.

### 12.2 `tests/support/evodepth.py` (tested on CPython 3.14.7)

```python
"""Emulate the TI-84 EVO call-depth cap on desktop CPython (3.12+).

Counts the device-code Python frames on the stack (code under DEVICE_DIRS),
skipping test/pytest/shim/stdlib frames, which are free on the device
(pytest does not exist there; ti_* and stdlib modules are native C).
"""
import ast
import linecache
import os
import sys

_M = sys.monitoring
_E = _M.events
HARD_LIMIT = 10     # deepest frame that ran on device (PROBE4); 11th raised


class DepthChecker(object):
    TOOL_IDS = (4, 3)   # free sys.monitoring ids (0,1,2,5 are taken by convention)

    def __init__(self, device_dirs, base=0, budget=8, hard_limit=HARD_LIMIT,
                 native_penalty=1, dunder_penalty=1, emulate=True):
        self.dirs = tuple(os.path.normcase(os.path.abspath(d)) + os.sep
                          for d in device_dirs)
        self.base = base                  # device depth of the caller of the entry point
        self.budget = budget              # depth allowed by tests (margin below hard_limit)
        self.hard_limit = hard_limit
        self.native_penalty = native_penalty   # frame entered from a builtin (sorted key=, map, C(), ...)
        self.dunder_penalty = dunder_penalty   # implicit dunder (a == b, hash(x), x in s, ...)
        self.emulate = emulate            # raise RuntimeError past hard_limit, like the device
        self._dev = {}                    # code object -> is device code
        self._live = {}                   # running device frame -> its device depth
        self._native = {}                 # frame -> builtin it is currently calling
        self._spans = {}                  # filename -> comprehension source spans
        self._pos = {}                    # code -> list of instruction positions
        self._here = {}                   # (code, offset) -> comprehension nesting
        self._maxcomp = {}                # code -> max comprehension nesting inside it
        self.max_depth = base
        self.max_stack = ()
        self.violations = []              # (depth, stack) for every depth > budget

    def _is_dev(self, code):
        r = self._dev.get(code)
        if r is None:
            fn = os.path.normcase(os.path.abspath(code.co_filename))
            r = self._dev[code] = fn.startswith(self.dirs)
        return r

    # CPython 3.12+ inlines list/set/dict comprehensions (PEP 709); MicroPython
    # runs each one as a separate function, i.e. one more frame on the device.
    def _comp_spans(self, filename):
        spans = self._spans.get(filename)
        if spans is None:
            spans = []
            try:
                tree = ast.parse(''.join(linecache.getlines(filename)))
            except (SyntaxError, ValueError):
                tree = None
            for n in (ast.walk(tree) if tree else ()):
                if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp)):
                    spans.append(((n.lineno, n.col_offset),
                                  (n.end_lineno, n.end_col_offset)))
            self._spans[filename] = spans
        return spans

    def _nest_at(self, code, index, spans):
        pos = self._pos.get(code)
        if pos is None:
            pos = self._pos[code] = list(code.co_positions())
        if index >= len(pos) or pos[index][0] is None:
            return 0
        l, el, c, ec = pos[index]
        return sum(1 for (a, b) in spans if a <= (l, c) and (el, ec) <= b)

    def _comp_here(self, frame):          # comprehensions around the current call
        key = (frame.f_code, frame.f_lasti)
        n = self._here.get(key)
        if n is None:
            spans = self._comp_spans(frame.f_code.co_filename)
            n = self._nest_at(frame.f_code, frame.f_lasti // 2, spans) if spans else 0
            self._here[key] = n
        return n

    def _comp_max(self, code):            # deepest comprehension inside this code
        m = self._maxcomp.get(code)
        if m is None:
            spans = self._comp_spans(code.co_filename)
            m = 0
            if spans:
                n = len(list(code.co_positions()))
                m = max([self._nest_at(code, i, spans) for i in range(n)] + [0])
            self._maxcomp[code] = m
        return m

    def _start(self, code, offset):                  # PY_START, PY_RESUME
        if not self._is_dev(code):
            return _M.DISABLE
        frame = sys._getframe(1)
        depth = self.base
        f = frame.f_back
        while f is not None:                         # nearest device ancestor
            d = self._live.get(f)
            if d is not None:
                depth = d
                break
            f = f.f_back
        depth += 1
        caller = frame.f_back
        if caller is not None and self._is_dev(caller.f_code):
            depth += self._comp_here(caller)
        if caller is not None and caller in self._native:
            depth += self.native_penalty
        elif code.co_name[:2] == '__' and code.co_name[-2:] == '__':
            depth += self.dunder_penalty
        self._live[frame] = depth
        reach = depth + self._comp_max(code)   # its own comprehensions run deeper
        if reach > self.max_depth:
            self.max_depth = reach
            self.max_stack = self.stack(frame)
        if reach > self.budget:
            self.violations.append((reach, self.stack(frame)))
        if self.emulate and depth > self.hard_limit:
            del self._live[frame]
            raise RuntimeError('maximum recursion depth exceeded')

    def _leave(self, code, offset, value):           # PY_RETURN, PY_YIELD
        if not self._is_dev(code):
            return _M.DISABLE
        f = sys._getframe(1)
        self._live.pop(f, None)
        self._native.pop(f, None)

    def _unwind(self, code, offset, exc):            # PY_UNWIND (cannot be disabled)
        f = sys._getframe(1)
        self._live.pop(f, None)
        self._native.pop(f, None)

    def _call(self, code, offset, func, arg0):       # CALL, in device code only
        if not self._is_dev(code):
            return _M.DISABLE
        f = sys._getframe(1)
        if hasattr(func, '__code__'):                # plain Python call
            self._native.pop(f, None)
        else:                                        # builtin function or a class
            self._native[f] = func

    def _c_done(self, code, offset, func, arg0):     # C_RETURN, C_RAISE
        self._native.pop(sys._getframe(1), None)

    def stack(self, frame):
        out = []
        f = frame
        while f is not None:
            if f is frame or f in self._live:
                out.append('%s:%s' % (os.path.basename(f.f_code.co_filename),
                                      f.f_code.co_name))
            f = f.f_back
        out.reverse()
        return tuple(out)

    _EVENTS = ((_E.PY_START, '_start'), (_E.PY_RESUME, '_start'),
               (_E.PY_RETURN, '_leave'), (_E.PY_YIELD, '_leave'),
               (_E.PY_UNWIND, '_unwind'), (_E.CALL, '_call'),
               (_E.C_RETURN, '_c_done'), (_E.C_RAISE, '_c_done'))

    def __enter__(self):
        free = [i for i in self.TOOL_IDS if _M.get_tool(i) is None]
        if not free:
            raise RuntimeError('no free sys.monitoring tool id')
        self.tool = free[0]          # a second, nested checker gets the next id
        _M.use_tool_id(self.tool, 'evo-depth')
        mask = 0
        for ev, name in self._EVENTS:
            _M.register_callback(self.tool, ev, getattr(self, name))
            mask |= ev
        _M.set_events(self.tool, mask)
        return self

    def __exit__(self, *exc):
        _M.set_events(self.tool, 0)
        for ev, name in self._EVENTS:
            _M.register_callback(self.tool, ev, None)
        _M.free_tool_id(self.tool)
        _M.restart_events()          # re-enable locations DISABLEd for this tool
        return False
```

### 12.3 `tests/conftest.py` integration

Every test's *call phase* runs under a checker. Fixture setup is not measured.

```python
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, 'src'), os.path.join(ROOT, 'shim'),
                os.path.join(HERE, 'support'), HERE]
sys.set_int_max_str_digits(0)       # the device has no int<->str digit limit

from evodepth import DepthChecker  # noqa: E402

BUDGET = 8           # device hard limit is 10; keep 2 frames of margin
DEFAULT_BASE = 2     # device depth of the caller of the code under test
DEVICE_DIRS = [os.path.join(ROOT, 'src')]


def _squash(stack):
    out = []
    for s in stack:
        if out and out[-1][0] == s:
            out[-1][1] += 1
        else:
            out.append([s, 1])
    return ' > '.join(s if n == 1 else '%s x%d' % (s, n) for s, n in out)


def pytest_configure(config):
    config.addinivalue_line(
        'markers', 'device_base(n): device depth of the caller of the code under test')


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    m = item.get_closest_marker('device_base')
    base = m.args[0] if m else DEFAULT_BASE
    with DepthChecker(DEVICE_DIRS, base=base, budget=BUDGET) as dc:
        res = yield
    if dc.violations:
        d, stack = max(dc.violations)
        pytest.fail('device call depth %d > budget %d (base %d): %s'
                    % (d, BUDGET, base, _squash(stack)), pytrace=False)
    return res
```

It also turns off CPython's int/str digit limit, as section 5.1 requires. The `shim/` directory on
`sys.path` provides the desktop `ti_*` stand-ins. Those frames are not counted.

### 12.4 Calibration test

`tests/depth_shapes/probe4_shapes.py` (this directory is passed to the checker as a device dir):

```python
# Desktop replica of probe/PROBE4.py call shapes (device results in comments).
cnt = [0]


def measure(start):
    cnt[0] = 0
    try:
        start()
        return -1
    except RuntimeError:
        return cnt[0]


def plain():                   # device: 9
    cnt[0] += 1
    plain()


def ping():                    # device: 9
    cnt[0] += 1
    pong()


def pong():
    cnt[0] += 1
    ping()


class C:
    def m(self):               # device: 9
        cnt[0] += 1
        self.m()


def gen(n):                    # device: 8 (started via lambda + list())
    cnt[0] += 1
    yield from gen(n + 1)


def w1():                      # device: 6
    w2()


def w2():
    w3()


def w3():
    plain()


def lc():                      # device: not measured yet (PROBE5 'lcomp')
    cnt[0] += 1
    [lc() for _ in (1,)]


def run_gen():                 # PROBE4 used lambda: list(gen(0))
    return list(gen(0))
```

`tests/test_depth_calibration.py`:

```python
import os
from evodepth import DepthChecker
from depth_shapes import probe4_shapes as s

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'depth_shapes')


def run_shapes(**kw):
    with DepthChecker([HERE], base=0, budget=99, **kw):
        return {
            'plain': s.measure(s.plain),
            'mutl': s.measure(s.ping),
            'meth': s.measure(s.C().m),
            'gen': s.measure(s.run_gen),
            'nest3': s.measure(s.w1),
            'lcomp': s.measure(s.lc),
        }


def test_matches_probe4_on_device():
    got = run_shapes(native_penalty=0, dunder_penalty=0)
    assert got == {'plain': 9, 'mutl': 9, 'meth': 9, 'gen': 8, 'nest3': 6,
                   'lcomp': 5}


def test_strict_mode_is_never_more_lenient_than_device():
    got = run_shapes()          # default penalties = 1
    assert got['gen'] == 7      # list() charged one frame; the device charged 0
```

The `lcomp: 5` expectation is the checker's prediction (a frame per comprehension). Confirm it with
PROBE5 `lcomp` before relying on it.

---

## 13. Static subset lint (sketch)

`ast.parse(src, feature_version=(3, 4))` rejects only part of the newer syntax. On 3.14 it
**accepts** f-strings, annotations, keyword-only parameters, `[*a]`, `{**d}` and `raise from` [C].
So the lint walks the AST explicitly. It also flags banned modules, attributes and builtins,
`__slots__`, the `__main__` guard, non-ASCII source and direct self-recursion. Extensions worth
adding:

* a module-wide call graph with cycle detection (mutual recursion) and longest-path depth per
  layer;
* a ban on `ast.Div` in exact-core modules;
* a ban on `sum(` over float expressions in numeric modules;
* a check that only `ui*` modules import `ti_*`.

Run it in a test over `src/` and over the bundler output.

```python
"""Static checks that device code stays inside the TI-84 EVO Python subset."""
import ast
import sys

BANNED_MODULES = {'re', 'fractions', 'decimal', 'functools', 'itertools',
                  'cmath', 'os', 'typing', 'dataclasses', 'enum', 'abc',
                  'copy', 'operator', 'string', 'struct', 'io', 'micropython'}
BANNED_ATTRS = {'bit_length', 'isqrt', 'gcd', 'lcm', 'comb', 'perm', 'prod',
                'fsum', 'log2', 'log10', 'hypot', 'removeprefix',
                'removesuffix', 'casefold', 'ljust', 'rjust', 'zfill',
                'isalnum', 'isnumeric', 'isdecimal', 'isidentifier'}
BANNED_NAMES = {'reversed', 'frozenset', 'format', 'vars', 'ascii', 'open',
                'compile', 'breakpoint', 'NotImplemented', 'RecursionError'}


def lint(src, filename='<src>'):
    errs = []

    def err(node, msg):
        errs.append('%s:%d: %s' % (filename, getattr(node, 'lineno', 0), msg))

    try:
        tree = ast.parse(src, filename, feature_version=(3, 4))
    except SyntaxError as e:
        return ['%s:%s: not Python 3.4 syntax: %s' % (filename, e.lineno, e.msg)]
    if any(ord(c) > 126 for c in src):
        errs.append('%s: non-ASCII character in source' % filename)
    funcs = {}
    for node in ast.walk(tree):
        t = type(node)
        if t is ast.JoinedStr:
            err(node, 'f-string')
        elif t in (ast.FunctionDef, ast.Lambda):
            a = node.args
            if a.kwonlyargs:
                err(node, 'keyword-only parameters')
            if t is ast.FunctionDef:
                funcs[node.name] = node
                if node.returns is not None:
                    err(node, 'return annotation')
            for p in a.args + a.kwonlyargs + [a.vararg, a.kwarg]:
                if p is not None and p.annotation is not None:
                    err(node, 'parameter annotation')
        elif t in (ast.List, ast.Tuple, ast.Set) and not isinstance(
                getattr(node, 'ctx', None), ast.Store):
            if any(isinstance(e, ast.Starred) for e in node.elts):
                err(node, '*unpacking inside a display (3.5+)')
        elif t is ast.Call:
            if sum(isinstance(a, ast.Starred) for a in node.args) > 1:
                err(node, 'more than one *args in a call (3.5+)')
            if sum(k.arg is None for k in node.keywords) > 1:
                err(node, 'more than one **kwargs in a call (3.5+)')
        elif t is ast.Dict and None in node.keys:
            err(node, '{**d} (3.5+)')
        elif t is ast.Raise and node.cause is not None:
            err(node, 'raise ... from ... (chaining is not kept on device)')
        elif t in (ast.Import, ast.ImportFrom):
            mods = [a.name for a in node.names] if t is ast.Import else [node.module or '']
            for m in mods:
                if m.split('.')[0] in BANNED_MODULES:
                    err(node, 'module %r is not on the device' % m)
        elif t is ast.Attribute and node.attr in BANNED_ATTRS:
            err(node, '.%s is missing on the device' % node.attr)
        elif t is ast.Name and node.id in BANNED_NAMES:
            err(node, 'builtin %r is missing/unverified on the device' % node.id)
        elif t is ast.Name and node.id == '__slots__':
            err(node, '__slots__ has no effect on the device')
        elif t is ast.Compare and isinstance(node.left, ast.Name) \
                and node.left.id == '__name__':
            err(node, "__name__ == '__main__' is never true on device "
                      "(programs run as 'from NAME import *')")
    # direct recursion: a function that calls itself by name
    for name, fn in funcs.items():
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                    and sub.func.id == name:
                err(sub, 'direct recursion in %s()' % name)
    return errs


if __name__ == '__main__':
    bad = 0
    for path in sys.argv[1:]:
        with open(path, encoding='ascii', errors='replace') as fh:
            for e in lint(fh.read(), path):
                print(e)
                bad += 1
    sys.exit(1 if bad else 0)
```

---

## 14. Open questions and probes to run

### 14.1 PROBE5: settles most [A] tags

Copy it to `probe/PROBE5.py` and `probe/PRBIMP.py`, send both to the EVO and run PROBE5. It
pauses after each screenful; take a screenshot, then press any key. The last section
(nested tuples) is **risky**: if native recursion is unchecked, the calculator could freeze or
reset. It prints each step before running it, so the last line shown is the answer. Archive or
back up anything important first, or delete that section.

Expected CPython output, for comparison (desktop run [C]): `nosyn:slots` (CPython enforces
`__slots__`), `bigeqf False`, `rnd2.5 (2, 4, 0)`, `r.1+.2 0.30000000000000004`,
`sum.1 1.0`, `swtup True`, `stopit E:RuntimeError`, `dictord xambzcqe`,
`stable bdfhjlacegik kc12`, `lcomp 998`. Device answers that differ confirm the corresponding
[A] claims above.

How to read the frame lines: they use the same harness as PROBE4, where `plain` gave 9. A shape
that prints 9 costs one frame per level. A shape that prints 4 costs two frames per level (for
example, a comprehension or a trampoline plus the function).

```python
# PROBE5: fills the [A] gaps in docs/reference/device-python.md.
# Prints short lines and pauses every screenful: press any key to go on.
# The risky nested-data test runs LAST and prints before each step.
import gc
import sys
try:
    from ti_system import wait_key as _wk
except ImportError:
    _wk = input
_n = [0]


def out(s):
    print(s)
    _n[0] += 1 + len(s) // 30
    if _n[0] >= 9:
        _wk()
        _n[0] = 0


def miss(label, names, ns):
    m = []
    for n in names:
        try:
            if ns is None:
                eval(n)
            elif not hasattr(ns, n):
                m.append(n)
        except Exception:
            m.append(n)
    out(label + ":" + (" ".join(m) if m else "-"))


def syn(label, snippets):
    bad = []
    for name, src in snippets:
        try:
            exec(src, {})
        except BaseException:
            bad.append(name)
    out(label + ":" + (" ".join(bad) if bad else "-"))


def tryit(label, f):
    try:
        out(label + " " + str(f()))
    except BaseException as e:
        out(label + " E:" + type(e).__name__)


def _gstop():
    yield 1
    raise StopIteration


NL = chr(10)
out("name " + __name__)
out("impl " + str(getattr(sys, "implementation", "?"))[:56])
miss("nobi", ("reversed", "frozenset", "compile", "open", "format",
              "vars", "ascii", "delattr", "NotImplemented", "bytearray",
              "memoryview", "RecursionError", "callable", "next", "iter",
              "min", "max", "sum", "any", "all", "zip", "map", "filter",
              "enumerate", "slice", "hex", "bin", "oct", "chr", "ord",
              "id", "hash", "pow", "super", "property", "classmethod",
              "staticmethod", "globals", "locals", "setattr", "getattr",
              "hasattr", "isinstance", "issubclass", "__import__"), None)
import math
miss("nomath", ("gcd", "isqrt", "factorial", "log10", "log2", "sinh",
                "cosh", "tanh", "asinh", "acosh", "atanh", "expm1",
                "log1p", "gamma", "lgamma", "erf", "hypot", "inf", "nan",
                "tau", "isclose", "frexp", "ldexp", "fsum", "comb",
                "prod", "trunc", "modf", "fmod", "copysign"), math)
miss("nostr", ("center", "ljust", "rjust", "zfill", "title", "isalnum",
               "isnumeric", "isdecimal", "isidentifier", "partition",
               "rpartition", "rsplit", "splitlines", "casefold",
               "swapcase", "capitalize", "expandtabs", "translate",
               "format", "encode", "count", "rindex", "rfind",
               "removeprefix"), "")
miss("noint", ("bit_length", "to_bytes", "from_bytes"), 0)
miss("nolist", ("copy", "clear", "sort", "reverse", "insert"), [])
miss("nodict", ("copy", "clear", "setdefault", "popitem", "fromkeys",
                "update"), {})
miss("nosys", ("modules", "implementation", "maxsize", "path", "exit",
               "getrecursionlimit", "setrecursionlimit", "intern",
               "print_exception", "settrace", "getsizeof"), sys)
import collections
miss("nocoll", ("OrderedDict", "namedtuple", "deque", "defaultdict"),
     collections)
import time
miss("notime", ("monotonic", "time", "ticks_ms", "perf_counter"), time)
miss("nogc", ("mem_free", "mem_alloc", "threshold", "enable"), gc)
syn("nosyn", (
    ("fstr", "x=1" + NL + "y=f'{x}'"),
    ("walrus", "y=(x:=1)"),
    ("star=", "a,*b=(1,2,3)"),
    ("kwonly", "def f(a,*,b=0):pass"),
    ("[*a]", "a=[1];b=[*a,2]"),
    ("{**d}", "d={1:2};e={**d}"),
    ("f(*a,*b)", "print(*[],*[],end='')"),
    ("1_0", "x=1_000"),
    ("raisefrom", "try:" + NL + " raise ValueError from None" + NL +
     "except ValueError:pass"),
    ("nonlocal", "def f():" + NL + " x=1" + NL + " def g():" + NL +
     "  nonlocal x" + NL + "  x=2" + NL + " g()" + NL + " return x" + NL +
     "assert f()==2"),
    ("annot", "def f(a:int)->int:return a"),
    ("varannot", "x:int=1"),
    ("async", "async def f():pass"),
    ("with", "class C:" + NL + " def __enter__(s):return s" + NL +
     " def __exit__(s,*a):return False" + NL + "with C() as c:pass"),
    ("deco", "def d(f):return f" + NL + "@d" + NL + "def g():pass"),
    ("setcomp", "s={x for x in range(3)}"),
    ("dictcomp", "d={x:1 for x in range(3)}"),
    ("slots", "class C:" + NL + " __slots__=('a',)" + NL + "C().b=1"),
    ("super0", "class A:" + NL + " def f(s):return 1" + NL +
     "class B(A):" + NL + " def f(s):return super().f()" + NL +
     "assert B().f()==1"),
    ("multinh", "class A:pass" + NL + "class B:pass" + NL +
     "class C(A,B):pass"),
    ("radd", "class A:" + NL + " def __radd__(s,o):return 7" + NL +
     "assert 1+A()==7"),
    ("getattr_", "class A:" + NL + " def __getattr__(s,n):return 7" + NL +
     "assert A().zz==7"),
    ("property", "class A:" + NL + " @property" + NL +
     " def p(s):return 7" + NL + "assert A().p==7"),
    ("ne_auto", "class A:" + NL + " def __eq__(s,o):return True" + NL +
     "assert not (A()!=A())")))
tryit("pow3", lambda: pow(3, 200, 1000003))
tryit("f10^400", lambda: float(10 ** 400))
tryit("bigeqf", lambda: (10 ** 20 + 1) == 1e20)
tryit("rnd2.5", lambda: (round(2.5), round(3.5), round(-0.5)))
tryit("rnd.125", lambda: round(0.125, 2))
tryit("r.1+.2", lambda: repr(0.1 + 0.2))
tryit("s1e16", lambda: (str(1e16), str(1.0), str(1e-5)))
tryit("g10", lambda: "%.10g|%.10g" % (2.0 / 3, 1e22))
tryit("e17", lambda: "%.17g" % 0.1)
tryit("sum.1", lambda: repr(sum([0.1] * 10)))
tryit("star%", lambda: "%*d|%-4s|" % (5, 42, "ab"))
tryit("fmt", lambda: "{0}-{1:>4}".format(1, 2))
tryit("swtup", lambda: "abc".startswith(("x", "a")))
tryit("rsplitN", lambda: "a b c".rsplit(None, 1))
tryit("negmod", lambda: (-7 // 2, -7 % 2, divmod(-7, 2)))
tryit("cplx", lambda: (complex(1, 2) * 2j, abs(3 + 4j)))
tryit("1/0.", lambda: 1.0 / 0.0)
tryit("bigstr", lambda: len(str(7 ** 6000)))
tryit("stopit", lambda: list(_gstop()))
tryit("frzset", lambda: hash(frozenset((1, 2))) is not None)
tryit("revrs", lambda: list(reversed([1, 2, 3])))
tryit("slice", lambda: [0, 1, 2, 3, 4][::-2])
d = {}
for k in ("x", "a", "m", "b", "z", "c", "q", "e"):
    d[k] = 1
out("dictord " + "".join(d))
ks = [(1, "a"), (0, "b"), (1, "c"), (0, "d"), (1, "e"), (0, "f"),
      (1, "g"), (0, "h"), (1, "i"), (0, "j"), (1, "k"), (0, "l")]
calls = [0]


def kf(p):
    calls[0] += 1
    return p[0]


r = sorted(ks, key=kf)
out("stable " + "".join(p[1] for p in r) + " kc" + str(calls[0]))
# Frame cost of constructs; same harness as PROBE4 (plain gave 9 there).
cnt = [0]
res = []


def measure(name, start):
    cnt[0] = 0
    try:
        start()
        res.append(name + " ok")
    except BaseException as e:
        res.append("%s %d %s" % (name, cnt[0], type(e).__name__[:4]))


def plain():
    cnt[0] += 1
    plain()


def ks_(x):
    cnt[0] += 1
    sorted((1, 2), key=ks_)
    return 0


def mp_(x):
    cnt[0] += 1
    list(map(mp_, (1,)))


def mk_(x):
    cnt[0] += 1
    min((1, 2), key=mk_)


def ev_():
    cnt[0] += 1
    eval("ev_()")


def lc_():
    cnt[0] += 1
    [lc_() for _ in (1,)]


def ge_():
    cnt[0] += 1
    sum(ge_() for _ in (1,))


class Q:
    def __eq__(s, o):
        cnt[0] += 1
        return Q() == Q()


class R:
    def __init__(s):
        cnt[0] += 1
        R()


class H:
    def __hash__(s):
        cnt[0] += 1
        return hash(H())


class S:
    def __str__(s):
        cnt[0] += 1
        return str(S())


class A:
    def __add__(s, o):
        cnt[0] += 1
        return A() + 1


lam = lambda: (cnt.append(0), lam())
measure("plain", plain)
measure("sortk", lambda: ks_(0))
measure("map", lambda: mp_(0))
measure("minkey", lambda: mk_(0))
measure("eval", ev_)
measure("lcomp", lc_)
measure("genexp", ge_)
measure("eq", lambda: Q() == Q())
measure("init", R)
measure("hash", lambda: hash(H()))
measure("str", lambda: str(S()))
measure("add", lambda: A() + 1)
for line in res:
    out(line)
del cnt[1:]
try:
    lam()
except BaseException as e:
    out("lamb %d %s" % (len(cnt) - 1, type(e).__name__[:4]))
try:
    import PRBIMP
    out("imptop %d" % PRBIMP.N)
except ImportError:
    out("imptop: PRBIMP missing")


def _imp_in_fn():
    if "PRBIMP" in sys.modules:
        del sys.modules["PRBIMP"]
    import PRBIMP
    return PRBIMP.N


tryit("impfn", _imp_in_fn)
gc.collect()
out("free " + str(getattr(gc, "mem_free", lambda: -1)()))
# RISKY: native recursion over nested tuples. If the calculator freezes
# or resets, the last "nest" line printed is the answer.
for dep in (8, 16, 32, 64, 128):
    t = u = 0
    for i in range(dep):
        t = (i, t)
        u = (i, u)
    for op in ("eq", "hash", "repr", "lt"):
        print("nest", dep, op)
        try:
            if op == "eq":
                t == u
            elif op == "hash":
                hash(t)
            elif op == "repr":
                repr(t)
            else:
                t < u
        except BaseException as e:
            out("nest %d %s E:%s" % (dep, op, type(e).__name__))
out("nest done")
```

`PRBIMP.py`, the companion module. `N` is how many frames its body could still open:

```python
c = [0]


def r():
    c[0] += 1
    r()


try:
    r()
except RuntimeError:
    pass
N = c[0]
```

### 14.2 Other open questions

* What `get_key()` returns when no key is pressed, and whether `escape()` behaves as on the CE
  (True once after `[clear]`) [R/A]. Both matter for the cancel poll.
* Whether `[on]` raises KeyboardInterrupt on the EVO [D (CE)].
* What `ti_graphics.setFont` sizes exist, `string_size` metrics, and which glyphs `drawString`
  can render (pi, the square root sign, the integral sign, superscripts) [unknown]. These matter
  for the 2D renderer.
* The size limit for one PY file on the EVO, and its total storage [unknown].
* Whether `sys.modules` deletion really frees the bytecode (PRBMEM `kept`) [A].

### 14.3 PRBMEM: memory per object and per module

Set `MODS` to device module names, leaf modules first. `PRBMOD` is the tiny module from
`probe/`.

```python
# PRBMEM: measure RAM per object shape and per module on the device.
# Edit MODS (device names, leaf modules first). Run from a fresh shell.
import gc
import sys
MODS = ("PRBMOD",)
N = 200


def free():
    gc.collect()
    gc.collect()
    return gc.mem_free()


def per(make):
    keep = [None] * N
    a = free()
    for i in range(N):
        keep[i] = make(i)
    b = free()
    return (a - b) // N


class P:
    def __init__(s, a, b):
        s.a = a
        s.b = b


def mkclo(i):
    def f():
        return i
    return f


print("start", free())
print("tup3", per(lambda i: (i, i, i)))
print("tup6", per(lambda i: (i, i, i, i, i, i)))
print("list3", per(lambda i: [i, i, i]))
print("dict2", per(lambda i: {1: i, 2: i}))
print("inst2", per(lambda i: P(i, i)))
print("float", per(lambda i: i * 1.5))
print("int64", per(lambda i: (1 << 64) + i))
print("str20", per(lambda i: "abcdefghijklmnopqr" + str(i % 10) + "x"))
print("clos", per(mkclo))


def unload(name):
    if name in sys.modules:
        del sys.modules[name]
    gc.collect()


def peak(name):
    # largest ballast that still lets the import succeed -> peak need
    lo, hi = 0, free()
    while hi - lo > 1024:
        mid = (lo + hi) // 2
        try:
            ballast = bytearray(mid)
        except MemoryError:
            hi = mid
            continue
        ok = True
        try:
            __import__(name)
        except MemoryError:
            ok = False
        ballast = None
        unload(name)
        if ok:
            lo = mid
        else:
            hi = mid
    return free() - lo


for name in MODS:
    a = free()
    try:
        __import__(name)
    except MemoryError:
        print(name, "MemErr at", a)
        continue
    b = free()
    unload(name)
    c = free()
    print(name, "cost", a - b, "kept", a - c, "peak", peak(name))
print("end", free())
```

---

## Appendix A: probe transcripts (from the on-device screenshots)

**PROBE3** (`from PROBE3 import *`):
```
v 3.4.0
free 185296
mods: ti_draw ti_plotlib time array collections        (cmath, micropython, re, fractions, os absent)
rec 8 RuntimeError maximum recursion depth             (rec(8) ok, rec(12) failed)
meth err RuntimeError                                  (41-deep method recursion)
cxY setY dmY rndY inpY bigY sortY isubY slotsY fmtY    ("slots" actually tested hash((1,"a")))
```

**PROBE4** (`from PROBE4 import *`):
```
plain 9 Runtim
biglc 9 Runtim
mutl 9 Runtim
meth 9 Runtim
lamb 0 Attrib        (cnt.__setitem__ does not exist)
gen 8 Runtim
chain 8 Runtim
nest3 6 Runtim
paren 80
```

**PROBE2** (the top lines scrolled away):
```
no bi: exec? eval? compile? open? input? complex? set? frozenset? property? divmod? round?
eval Y exec Y fstr N imp Y
rec 0 list Y
loop 0.06600000000003092
ts: disp_at disp_clr disp_cursor disp_wait escape getKey recall_RegEQ recall_list sleep store_list wait wait_key get_key
```
(`no bi` printed `name?` for every builtin, which means `dir(__builtins__)` itself raised.)

**PROBE** (tail): `... 'drawLine', 'drawPolyLine', 'drawRect', 'drawString', 'fillArc', 'fillCircle',
'fillPolygon', 'fillRect', 'getPixel', 'hsv_to_rgb', 'popImage', 'pushImage', 'setColor', 'setFont',
'setPen', 'setPixel', 'string_size']` then `free end 173360`.

**PROBEK** (key codes, in the order pressed):
`11 12 13 14 15 25 34 24 26 105 23 22 41 44 91 104 45 21 11 31 41`
These are y= window zoom trace graph, up down left right, enter del mode math vars sto (-) clear, then
`2nd` (21) followed by y= (11), and `alpha` (31) followed by math (41). Modifiers arrive as separate key codes.

## Appendix B: sources

* `probe/PROBE.py`, `PROBE2.py`, `PROBE3.py`, `PROBE4.py`, `PROBEK.py`, `PRBMOD.py`, and their
  output screenshots.
* *Python Programming for the TI-84 Plus CE Python Graphing Calculator*, CE bundle 5.7.0
  (TI, 2021): pp. 1-3 (limits), 21-36 (modules, ti_draw, messages), 40-41 (CircuitPython basis,
  number model, module list), 55-147 (reference), 149-163 (built-in, keyword and module lists).
* Desktop experiments on CPython 3.14.7 (the project venv): the checker, the calibration, the
  PROBE5 dry run, the lint and the behaviour differences in section 9.
