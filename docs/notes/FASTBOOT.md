# Fast boot and packed engine (2026-10-11)

## Device report that started this

The v1 package (236 archived `.8mp2` libraries plus two RAM launchers) took
**5 min 30 s** on the user's EVO before failing with:

```
File "CVP00051.py", line 123, in aQ
File "CVP00051.py", line 64, in aZ
TypeError: function takes 1 positional arguments but 3 were given
```

Line 64 of the CVP00051 initializer is `G.setColor(*COLORS['BG'])`, the first
drawing call of `ui.redraw` reached from `ui.boot`. **`ti_graphics.setColor`
takes one positional argument on the EVO.** The desktop shim accepted
`setColor(r, g, b)`, and PROBE7 (which would have settled the signature) was
never run, so every ti_graphics call in the UI was an unverified assumption.

## Where the time went (measured, native MicroPython v1.12)

| run | archive imports | notes |
| --- | --- | --- |
| boot to first key | 51 | 62,087 bytecode bytes; host compute about 10 ms |
| `2+3` | 25 | function pages |
| one definite integral | 332 to 882 | CVF pages evict each other on every import |
| seven UI calculus cases | 2,806 | 169 distinct files |

Host compute for boot is about 10 ms; the EVO runs the same 20,000-iteration
loop about 75 times slower than an Apple M3 host (66 ms versus 0.89 ms), so
extrapolating that loop suggests about one second of boot computation. Amortizing
the reported 330 s across 51 imports gives about **6.5 s per archive import**;
this is an inference, not a measurement of each import. One device run cannot
separate fixed import overhead, per-byte loading and lookup costs that grow
with the number of files. The replacement reduces files, imports and total
bytes; its actual boot time still needs an EVO measurement.

Function paging (`build/function_pages.py`) made every call to a paged function
an `__import__`, and importing a page deleted every other page from
`sys.modules`, so alternating calls re-imported pages continuously. Each
trampoline step also purged all pages and ran `gc.collect()`.

## Initial 32-bit heap measurements (2026-10-11)

A local 32-bit MicroPython v1.12 (unix port compiled to wasm32 with emscripten,
Asyncify register scanning for the GC) reproduces the CI numbers: CVTEST on the
v1 package ends with 66,768 bytes free at a 173,360-byte heap (CI recorded
66,704). Whole, unpaged modules cost (bytes of heap, 32-bit):

| module | heap | module | heap |
| --- | --- | --- | --- |
| node | 29,696 | rules + rulesb | 4,240 |
| alg | 16,224 | poly + polyb + polyc | 6,128 |
| parse | 23,136 | ident | 3,664 |
| printer | 13,760 | norm + normb + normc | 7,488 |
| run | 16,912 | diff | 2,960 |
| draw | 10,576 | itab + integ | 4,208 |
| ui | 7,488 | | |

Identifier shrinking saves only about 3 % (for the packs before CASBIG, 191,506 to 185,367
archive bytes); bytecode, not names, dominates.
The namespace-dictionary initializers used by v1 add 10 to 20 % to heap and
bytecode. Whole modules with the old eager UI leave 41,648 bytes free after boot
and fail heavy commands, so the memory manager has to evict at pack granularity.

## Architecture

1. **UI first.** `CASEVO` imports only the UI pack and draws immediately. The
   engine loads when it is first needed (first ENTER, or a menu that needs it),
   with a status line showing what is loading and how long it took.
2. **Graphics through `ti_draw`** with the semantics CalcPlex documents from the
   device: 320 x 210 pixels, `get_screen_dim()` returns `[319, 209]`;
   `draw_text(x, y, s)` puts ink in rows `y-17` to `y-3`; a fixed-width font of
   10 pixels per character (31 characters per line); `fill_rect(x, y, w, h)`
   fills the interior only, so an exact area is `fill_rect(x-1, y-1, w+1, h+1)`
   and width/height below 2 raise; `set_color(r, g, b)` and `clear()` are slow
   (cache the current color, paint with `fill_rect`).
3. **Packs.** Device modules are merged into a small number of real
   MicroPython modules ("packs") with plain globals. Cross-module attribute
   access inside a pack becomes a plain global; access to another pack goes
   through that pack module. Each pack is imported once and stays in
   `sys.modules` until memory is needed. There are no function pages and no
   phase payloads.
4. **Families are packs.** The run-time loader (`run.need`) loads a family by
   importing its pack. Eviction is LRU at pack granularity and happens only when
   a load needs memory. A command that fails with MemoryError evicts every
   unpinned family and is retried once.
5. **Observability.** The UI records boot and pack load times
   (`time.monotonic` / `ticks_ms`, whichever exists) and shows them, so the next
   device report contains the real import cost.

## Contracts between the parts

- `src/casevo.py` imports `ti_system` and `ui` only. It obtains the engine from
  `U.engine()` (at depth 1, before calling `R.go(job)`), so `R.go` stays at
  depth 1 and the frame budget is unchanged.
- `ui.py`, `draw.py`, `menu.py` and `menub.py` never import engine modules
  (`node`, `alg`, `parse`, `printer`, `run`, families) at module level. The UI
  works with no engine loaded (empty history, default settings).
- Pack membership lives in `build/manifest.py`. A pack is at most about 60 KB
  of compiled bytecode (TI variable limit) and has a device name
  `[A-Z][A-Z0-9]{0,7}`.

## Local package (packs-v1)

Twenty-one packs and two launchers replace 236 libraries and two launchers. The archive holds
191,697 bytes (compiled packs plus the 6,045 bytes of launcher source); the largest pack,
CASK1, compiles to 22,121 bytes with the pinned v1.12 compiler. These are the
2026-10-12 reviewed bytes; publication remains pending (see STATUS.md).

| kind | packs | role |
| --- | --- | --- |
| ui | CASUI | editor state, busy/status/panic, drawing primitives; imported at boot |
| view | CASUX | keys, screens and the 2D layout; only a computation unloads it |
| core | CASK1 (node, alg), CASK2 (parse, run) | loaded with the engine, never unloaded |
| soft | CASIN (input parsing, `run.start`), CASPR (printer) | unloaded first when memory runs short |
| aux | CASAX (alg helpers), CASBIG (giant powers) | computation code that never reaches the loader; unloaded last |
| family | CASALG, CASFAC, CASSOL, CASINT, CASIN2, CASIN2B, CASIN3, CASIN3B, CASLIM, CASDEF, CASSUM, CASODE, CASMNU | one loader family each |

`build/packs.py` merges modules, places functions away from their home pack, renames the
few colliding names, and rejects anything it cannot prove: dynamic dispatch to a renamed or
placed name, module code that would hold a soft pack, aux code that could reach the loader,
nested closures. MicroPython's `const` keyword is renamed. Module-level aliases of another
pack bind it under the pack's own name (`import CASK2`, then `CASK2.x`): merged code may use
an old alias spelling as a local, and the identifier shrinker's alias analysis has no
scopes, so a shared spelling had made three registry lookups look dynamic and switched
shrinking off. Lazy UI aliases (`R = None`,
then `global R; import run as R` in `ui.engine`) bind the pack at run time, through the UI's
home pack, so the engine never loads at boot.

Later addition: a second aux pack, CASBIG, holds `nodeb` (powers too large to fold, DESIGN
6.1). `node` keeps only cheap tests and reaches it through `__import__`, so a command without a
giant power never loads it; `nodeb`'s back-reference to `node` (`K = None`, bound by node's
module body) compiles to plain references to CASK1. Keeping that code out of CASK1 holds the
initial 95,000-byte startup at 16,912 bytes free (17,360 without the feature,
13,328 with it in CASK1). The reviewed build leaves 16,192 bytes free.

### Loader changes (`src/run.py`)

- A family whose pack is already imported binds without another import.
- MicroPython 1.12 keeps a module whose body raised; `need` and `ui.engine` remove it.
- **Deleting a module from `sys.modules` frees nothing** while a stale word on the C stack
  still points at it (conservative collector; reproduced on 64-bit native and 32-bit). With
  `EVDICT` (set for the calculator), `unload` sets every global of the module to None first,
  so its code is released even when the module object survives.
- `room(phase)` loads a phase's soft pack (input, print, layout) after unpinned families and
  other soft packs give way, and retries once after freeing everything idle.
- After parsing, a command that preloads families first unloads idle soft and view packs
  when less than `SHEDAT` (64 KB) is free. Arithmetic, which loads no family, keeps the
  layout pack instead of reloading it to show the answer.
- A load that raises MemoryError frees one more thing (soft pack, LRU family, aux pack) and
  retries. An Out of memory with stale families or idle soft packs loaded reruns the
  command once on a cleaner heap.
- `node.keep` marks one rule pattern at a time, and the quadrature cache is split into
  64-slot rows: both had been single allocations that a fragmented heap could not satisfy.

### Initial measurements (2026-10-11, wasm32 MicroPython v1.12)

This table records the earlier build, not the final review below. The reviewed
UI smoke script also corrects the plus key from 95 (`< >`) to 85; its earlier
basic arithmetic result is superseded by the verified `2+3=5` run below.

Pack imports were counted inside the 32-bit runs by wrapping `builtins.__import__`; "host"
counts come from the CPython harness, whose heap never runs short.

| check | v1 | packs-v1 |
| --- | --- | --- |
| archive imports to the first key | 51 | 2 (CASUI, CASUX) |
| imports, first `2+3` after boot | 25 | 4 (two core, input, printer) |
| imports, 7 UI calculus cases (5 definite integrals) | 2,806 (host) | 29 (host); 43 at 212,000 B, 51 at 196,000 |
| imports, 10 light commands (arithmetic, expand, factor, diff, solve, simplify) | - | 24 at 185,296 B, 34 at 173,360 |
| files on the calculator | 238 | 23 |
| startup on a 95,000-byte heap | 13,520 B free | 16,912 B free |
| `2+3` UI session, 173,360-byte heap | pass | pass |
| 7 UI calculus cases, 173,360 | pass | fail (definite integrals: Out of memory) |
| 7 UI calculus cases, 189,776 | pass | pass, under 2 KB to spare |
| CVTEST 55 cases, 173,360 | 55/55 | 40/55 |
| CVTEST 55 cases, 189,776 | 55/55 | 53/55 (52 to 53 across builds) |
| CVTEST 55 cases, 196,000 / 204,000 / 212,000 | 55/55 | 54/55 / 55/55 / 55/55 |

Builds that move code around shift these counts by a case or two at the tighter heaps: the
failures are fragmentation, so the exact cases depend on where packs land.

The code a long session touches (about 160 KB of bytecode) does not fit the heap
with the core resident, so input, printer and layout packs
reload after heavy commands. The final review also found avoidable strategy eviction
inside an integration search, corrected below. Explicit phase boundaries still evict
families (`integ`, `defint`). Lowering `SHEDAT` saved few light imports and broke the heaviest
integrals, so it stays at 64 KB.

v1 fitted the heaviest cases by keeping only the executing functions resident, at the cost
of the import storm. Packs keep whole families and the full core resident, so the heaviest
definite integrals need roughly 15-40 KB more, and long sessions end in a fragmented heap
(at the failures, 25 KB was free but the largest free run was under 1.2 KB). PROBE3 measured
185,296 bytes free at program start; the 173,360 figure was taken after the probe imported
ti_plotlib, ti_graphics, ti_image and more, which this program does not import. 189,776 is
185,296 plus the 4,480 bytes the harness itself uses. Physical EVO runs decide which model
holds: CASEVO shows its boot and engine load times, and CVTEST prints its startup heap.

### Final review (2026-10-12)

Failed integration strategies now release the current generator's pin and stay
cached until memory admission needs an LRU victim. Explicit phase drops still
evict immediately. This removes repeated archive loading during nested searches
without pinning idle strategies or changing mathematical results.

| Command | Before review imports | Reviewed imports |
| --- | ---: | ---: |
| `integrate(sin(x)^21,x)` | 703 | 10 |
| `integrate(sin(x)^25,x)` | 1,664 | 9 |
| `integrate(cos(x)^30,x,0,pi/2)` | 585 | 12 |
| `desolve(y'=sin(x)^30)` | 585 | 12 |
| `integrate(e^(x^2),x)` | 12 | 10 |
| `integrate(atan(x)^5,x)` | 36 | 10 |

These counts use the same host packed-engine harness on both revisions; they
are not EVO timings. Results are unchanged, including the bounded `too long`
fallback for the power-25 case. The seven-calculus-command engine-only harness
drops from 25 to 21 imports; it omits UI loading and is not comparable to the
earlier whole-UI counts.

Exact finite sums poll CLEAR each term and stop when an accumulator coefficient
exceeds 3,300 hex digits (about 13,200 bits across numeric fields). Temporary
nodes are released and the caller retains `sum(...)` or `riemann(...)`. The
reviewed 1,000-panel rational Riemann case and large factorial/reciprocal sums
finished in 0.79–1.53 seconds on the desktop, with maximum polling gaps below
0.009 seconds. These are host measurements, not a device latency guarantee.

Giant real powers still remain exact powers when they exceed the old whole-base
integer limit. Ordinary folded integers retain their old representation.
Unsupported multi-term giant algebra and oversized non-real powers now report
`number too large` instead of giving false nonzero tests or roots. Real-only
absolute-value/power identities require proof that the base is real. A
2,422-case comparison with main found no result text/kind changes except cases
where main already returned `number too large` (67 such cases). See DESIGN.md
sections 6.1 and 11.4 for the supported bounds.

Final pinned MPY v5.3 bytecode passed these unchanged workflow budgets:

| Suite | Total harness heap | Result |
| --- | ---: | --- |
| 32-bit startup | 95,000 B | pass; 16,192 B free |
| 32-bit UI | 173,360 B | pass; `2+3=5`, normal quit |
| 32-bit UI calculus | 189,776 B | pass; seven commands, normal quit |
| 32-bit diagnostics | 212,000 B | 55/55 |
| 64-bit UI, calculus and diagnostics | 500,000 B | pass; 55/55 diagnostics |
| Extra 32-bit diagnostic stress | 189,776 B | 54/55; case 35 runs out of memory |

Case 35 is `integrate(1/(2+cos(x)),x,0,2*pi)` during the long diagnostic
session; it passes in the shorter calculus session at the same heap. The smoke
runner now requires the suite completion marker and rejects tracebacks even
when a runtime incorrectly exits with status zero. The 32-bit checks use the
local wasm32 unix harness and the 64-bit checks the native unix build; neither
emulates EVO graphics, USB, archive-import latency or its allocator exactly.

A 750-key recovery session with heavy calculations, menus, forms and later
arithmetic quits normally at the measured 185,296-byte start heap and all
tested heaps from 155,500 through 196,000 bytes. At 150,000/154,000 bytes the
instrumented driver's traceback reporting itself can exhaust the wasm runtime;
a brief error reporter recovered at 150,000. This does not establish universal
recovery below the measured device heap.

### Next steps that need device data

- The cost of one archive import (fixed, or growing with the number of files). If imports
  are cheap, families can be split further for memory; if not, the current split is right.
- Free heap at CASEVO start, and whether the heaviest definite integrals pass in practice.
