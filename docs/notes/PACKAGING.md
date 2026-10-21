# Calculator release packaging

The user authorized multiple files after TI Connect Evo rejected the oversized
single-file build. The measured converter limit for a source program is source
bytes plus 18 plus the module-name length, at most 65,535; it now applies only to
the two RAM launchers. See the converter evidence under `docs/reference/`.
Calculator storage and Python heap are separate budgets.

The current format is **packs-v1**. [FASTBOOT.md](FASTBOOT.md) records why it
replaced v1 (236 archived libraries: a 5.5-minute boot on the EVO and a
`ti_graphics.setColor` crash), the measurements behind it and its known limits.
That note is the source for the measured numbers quoted here; the loader
constants come from `build/manifest.py`.

## Packs

A pack is an ordinary MicroPython module that holds several device modules, or
single functions placed away from their module. Its functions read their
globals directly; no initializer, namespace dictionary or forwarding call runs
on the calculator. Each pack is one compiled `.8mp2` library in Archive. An
archive import cost seconds on the EVO, so the release keeps the number of
packs, and of imports, small.

`build/manifest.py` `PACKS` lists every pack as (device name, members, kind).
A member is a `src/` module (whose *home* pack this is) or `module.function`
(a placed function). Device names match `[A-Z][A-Z0-9]{0,7}`, and `PACKMAX`
caps a pack's bytecode at 60,000 bytes (one TI variable).

| kind | packs | loaded | unloaded |
| --- | --- | --- | --- |
| ui | CASUI (draw, ui state, busy/status/panic) | at boot | never |
| view | CASUX (keys, screens, 2D layout) | at boot | only while a computation runs (`run.INGO`) |
| core | CASK1 (node, alg), CASK2 (parse, run) | with the engine (first ENTER or a menu) | never |
| soft | CASIN (input parsing, `run.start`), CASPR (printer) | on first use | first, when memory runs short |
| aux | CASAX (alg helpers that never reach the loader), CASBIG (`nodeb`: powers too large to fold) | on first use | last |
| family | CASALG, CASFAC, CASSOL, CASINT, CASIN2, CASIN2B, CASIN3, CASIN3B, CASLIM, CASDEF, CASSUM, CASODE, CASMNU | by `run.need` | LRU, only when a load needs memory |

Each loader family (`PARTS`) is exactly one pack, so a family costs one archive
import. Soft, view and aux packs hold no state that a reload would lose, and
nothing holds them: every reference is `__import__('PACK').name`, which reloads
the pack on demand.

### Merging (`build/packs.py`)

`packs.merge` takes the bundled device modules and rewrites them:

- A project import becomes an import of the target's home pack, bound under the
  pack's own name (one import per pack), or disappears inside that pack.
  `A.name` becomes a plain global in the same pack, `PACK.name` for a resident
  pack, and `__import__('PACK').name` for a soft, view or aux pack. Same-pack
  stores get the `global` declarations they need.
- **Placement.** A placed function lives in the named pack and reaches its
  module's state through the home pack.
- **Renames.** A top-level name bound by two modules of one pack is renamed in
  the later module (`name_<module>`), unless both bind the same literal or import
  the same native module. MicroPython's compiler keyword `const` is always
  renamed.
- **Lazy aliases.** A module-level `R = None` that a function binds with
  `global R` and `import run as R` (as in `ui.engine`) binds the pack at run time,
  through the UI's home pack, so the engine never loads at boot.
- run.py's `DEV` table maps every runtime key to its pack.
- Entry programs (CASEVO, CVTEST) are rewritten with the same mapping, not packed.

The packer raises `PackError` instead of emitting a pack it cannot prove
correct: dynamic dispatch to a renamed or placed name, module code that would
hold a soft pack, aux code that could reach the loader or is a generator, a
soft-pack module that assigns its own globals, nested functions, classes or
lambdas, `from` imports and comprehension targets that rebind a rewritten name.

### Loader tables

The release writes these tables into the run pack (`src/run.py` holds desktop
defaults). `packs.merge` writes `DEV`, `SOFT`, `VIEW`, `AUX`, `EVDICT` and
`FRAG`; `build/release.py` writes `COST`, `ROOM` and `SHEDAT` from compiled sizes.

| table | value on the calculator |
| --- | --- |
| `DEV` | runtime key -> pack |
| `COST` | family key -> heap estimate: compiled bytes x 1.25 + 512 (`PACKCOST`) |
| `ROOM` | phase (`input`, `print`, `layout`) -> (soft pack, compiled bytes x 1.4 + 512) (`ROOMS`, `ROOMCOST`) |
| `SOFT`, `VIEW`, `AUX` | the packs of each kind |
| `SHEDAT` | 65,536: below this many free bytes after parsing, a command that preloads families first unloads idle soft and view packs (arithmetic keeps the layout pack) |
| `FRAG` | 2,048 (`PACKFRAG`): the slack each load asks for |
| `EVDICT` | 1: `run.unload` sets every global of a module to None before dropping it |
| `PEAKB`, `LINES` | 0 and empty: nothing compiles on the calculator |

The 32-bit measurements put a pack's heap at 1.1 to 1.6 times its bytecode. A
short estimate only means the import raises MemoryError, which the loader
handles.

## Loading and memory

- `CASEVO` imports `ti_system` and the UI. `ui.boot` draws the first screen with
  no engine loaded: two archive imports (CASUI, CASUX).
- `ui.engine()` imports the core packs on the first ENTER, or from a menu that
  needs them, records the load time and returns the run module to the entry loop
  at depth 1. If the import fails, it removes every module the attempt added.
- `run.need` loads a family by importing its pack; a family whose pack is
  already imported binds without another import. Eviction is LRU at pack
  granularity, only when a load needs memory, and never touches pinned or live
  families. Failed integration strategies use `drop(keys, True)` to release their own
  pins while remaining cached; phase boundaries still use immediate eviction.
- `run.room(phase)` makes room for a phase's soft pack (unpinned families and
  other soft packs give way first) and retries once after freeing everything
  idle. The entry loop calls `room('layout')` before the UI code reloads.
- A load that raises MemoryError unloads the half-run module, frees one more
  thing (soft pack, LRU family, aux pack) and retries. An Out of memory with
  stale families or idle soft packs loaded reruns the command once on a cleaner
  heap.
- MicroPython 1.12 keeps a module whose body raised in `sys.modules`, and
  deleting a module from `sys.modules` frees nothing while a stale C-stack word
  still points at it. `run.unload` therefore clears the module's globals
  (`EVDICT`) before dropping it.
- Node tables start at 64 slots and grow in 64-slot steps to the 768-node cap.
  `node.keep` marks one rule pattern at a time, and the quadrature cache is
  split into 64-slot rows, so a fragmented heap need not supply one large block.

GitHub Actions runs the pack sources on MicroPython 1.29 and the compiled bytes
on 1.12 at the heaps in `build.yml`: startup at 95,000 bytes, UI arithmetic at
173,360, the UI calculus session at 189,776 and the 55 diagnostics at 212,000
(32-bit), and the UI, calculus and diagnostic suites at 500,000 bytes (64-bit).
`build/micro_smoke.py` uses short import paths, so a host checkout's path length
cannot change the heap result, and a `ti_draw` stub that raises like the device
but allocates no framebuffer. Physical EVO graphics, transfer, performance and
heap remain device checks.

## Build stages

1. `build/release.py`: `build/bundle.py` writes minified device modules to
   `dist/device`; `packs.merge` builds the packs; `build/shrink.py` shortens
   identifiers. The release sizes every pack with mpy-cross, writes the loader
   tables, checks `PACKMAX`, and writes the pack sources (`CAS*.py`),
   `CASEVO.py`, `CVTEST.py`, `release.json`, `SHA256SUMS`, `INSTALL.md` and the
   build input `dist/cas-evo-packs.zip`.
2. `build/check_release.py` (with `tests/test_release.py`) runs the packed
   release in CPython with strict EVO depth checks and MicroPython's import
   rules, so eviction, soft packs and failed imports run their calculator paths.
3. `build/archive.py` compiles the packs; the launchers stay source.
4. `build/package_archive.mjs` converts every object with pinned TIVarsLib into
   the EVO container and reads it back to verify name, type and payload bytes.
5. `build/archive_zip.py` writes `cas-evo-calculator.zip`: the 23 EVO objects,
   `archive.json`, `INSTALL.md` and `SHA256SUMS`.

### Compiler and ABI

MicroPython v1.12 at `1f371947309c5ea6023b6d9065415697cbc75578` compiles the
packs with `-mcache-lookup-bc -msmall-int-bits=31`, and the `TIGHT` packs of
`build/manifest.py` (the UI packs CASUI and CASUX) also with `-O3`, which drops
their line-number tables; the required header is
`4d05031f` (MPY v5.3, 31-bit small ints). The builder rejects another ABI. A
newer `mpy-cross` is not interchangeable with the EVO compiler. Renaming `.py`
or `.mpy` files cannot perform the TIVarsLib conversion.

## Reproducibility and debugging

The builder enforces ASCII, Python 3.4 syntax, the launchers' converter limit,
`PACKMAX`, combined object storage and compilation of every file with
`mpy-cross`. It invalidates only recognized previous outputs before building and
writes deterministic ZIPs (fixed timestamps and attributes) only after the
checks succeed. Never transfer development modules or mix files from different
builds.

`release.json` (`format: packs-v1`) records:

- `files`: bytes and SHA-256 of every pack source and launcher;
- `names`: the identifier shrink mapping;
- `packs` and `kinds`: each pack's kind, home modules and placed functions;
- `owner` (device module -> home pack), `place` (`MODULE.function` -> pack) and
  `renames` (`MODULE.name` -> new name); `dev`, `cost`, `room` and
  `mpy_estimate` (compiled bytes per pack);
- `levels`: `{pack: {function: frame level}}` for the desktop depth checker;
- `linemap`: for each pack, one entry per line, `[first, last, src]`, the
  source span of the statement that produced the line, or null for generated
  lines such as added pack imports;
- `launchers`, `transfer_check` and `device_validation`.

AST rewriting changes line layout, so a mapping identifies the containing source
statement, not an exact line. A `TIGHT` pack has no line numbers (`-O3`): its
traceback frames report line 1, and only their function names locate them. To
map a device traceback line of another pack:

    python build/linemap.py --map dist/release.json CASK1:120

or annotate a whole traceback with `--map dist/release.json --tb FILE`. Use a
build of the same commit as the calculator files.

`archive.json` records each object's module, kind (bytecode or source),
destination (archive or RAM), bytes and SHA-256 with the hashes of its compiler
input, plus the compiler revision and ABI; `dist/archive/source/` holds the exact
compiler inputs and `release.json`. The website manifest adds converted-object
hashes and bytes, and the `website/legacy-*.json` records (generated by
`build/legacy_manifest.mjs` from the published v1 and packs-v1 packages and the
delivered MathPrint test ZIPs) list the earlier objects the installer may
remove or replace. The installer validates both before device
access and verifies locations after sending. Native tests and the website do not
claim physical EVO execution acceptance.
