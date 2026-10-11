# Calculator release packaging

The user authorized multiple files after TI Connect Evo rejected the oversized
single-file build. The measured converter limit is source bytes plus 18 plus
the module-name length, at most 65,535. See the converter evidence under
`docs/reference/`. Calculator storage and Python heap are separate budgets.

`build/release.py` creates the downloadable ZIP. Normal development modules
remain under `src/`; `dist/device/` is the conventional bundled test target.
The release is transformed further, so it also has its own acceptance harness
in `build/check_release.py` and `tests/test_release.py`.

## Loading and memory

- Short names can be reused in distinct module/local scopes. Unknown native
  attributes, reflection names and probe comparison strings remain intact.
- Project modules become live namespace dictionaries. Source carriers contain
  one bounded CODE string. The loader imports a carrier, removes it from the
  native module cache, executes the string, then drops it and collects.
- UI, input and output definitions load at explicit phase boundaries. The
  input frame returns before its code is unloaded and math families preload.
- `build/function_pages.py` moves audited functions into native CVF pages.
  Functions receive their original namespace as the first argument. Global
  reads/writes use that dictionary, including state changed while a generator
  is suspended. Calls add no Python forwarding frame. Known target calls
  evaluate the namespace expression once; dynamic calls require a bound
  namespace and preserve the command/strategy dispatch name.
- Each generator has its own page. Ordinary functions share small pages.
  A newly imported page removes other CVF cache entries; live frames retain
  whatever code they still require. Cleanup also runs after input, at each
  trampoline step, before printing and on command exit, including failures.
- Level-seven leaves and the twelve escaped complex-number callbacks stay
  resident. Cold native imports of deeper leaves would exceed the eight-frame
  desktop budget. Nonliteral default values must resolve to immutable source
  constants; the builder does not copy a hardcoded numeric substitute.
- Node tables initially allocate 64 slots, grow in 64-slot steps to the same
  768-node cap, and shrink on reset. All backing capacities grow before any
  node/hash-chain update, so partial allocation failure can be retried safely.
  The template cache retains only the most recent RPN program; callers can
  continue using an earlier returned program.

No compressed source archive stays resident. The memory report remains a
provisional subtotal with explicit exclusions; its passing estimate is not
heap acceptance. GitHub Actions runs the actual bytes in pinned MicroPython
1.29, on both 32-bit/173,360-byte and 64-bit/500,000-byte total heaps. Each run
checks UI arithmetic/quit, seven UI calculus/recovery commands, and CVTEST's
55 diagnostics. The harness uses short import paths so a host checkout's path
length cannot change the heap result. Minimal graphics shims allocate no framebuffer. Physical EVO
graphics, transfer, performance and depth calibration remain device checks.

## Reproducibility and debugging

The builder enforces ASCII, Python 3.4 syntax, per-file converter limits,
combined object storage, and compilation of every file with `mpy-cross`.
It invalidates only recognized previous outputs before building and writes the
deterministic ZIP only after the checks succeed. The ZIP includes all Python
files, INSTALL.md, release.json and SHA256SUMS. Never transfer development
modules or mix companions from different ZIPs.

`release.json` records file hashes, module/function ownership, native-page
output spans and source spans. AST rewriting changes individual line layout;
release mappings deliberately identify the containing source statement or
function instead of claiming an exact line. The original pre-rewrite maps are
also retained under `origin_linemap`. For a page traceback:

    python build/linemap.py --map dist/release.json CVF00001:8

Generated loader-only lines have no source location. An exec traceback may
report `<string>`; use the named function and page/phase ownership metadata to
identify its source. The desktop artifact harness assigns filenames to these
exec blocks solely to make profiling and failure injection observable.
