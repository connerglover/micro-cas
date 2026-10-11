# B.1: single-file build and release checks

`python build/release.py` produces `dist/CASEVO.py`, an optional independent
`CVTEST.py`, `INSTALL.md`, `release.json`, `SHA256SUMS`, and `cas-evo-v1.zip`.
Only CASEVO is needed for the app. Files under `dist/device` and `dist/blocks`
are desktop diagnostics, not transfer dependencies. Generated artifacts are
ignored by Git; the action publishes them after tests pass.

## Pipeline

1. `bundle.py` checks the source subset and frame annotations, rewrites short
   imports and loader tables, minifies, enforces per-unit budgets, and compiles
   every module with pinned mpy-cross. Lazy units remain at most 150 lines.
2. `shrink.py` consistently renames proven project identifiers and reflective
   registry names. Native attributes, builtins and ambiguous strings are reserved.
3. `phases.py` splits whole function definitions into bounded source blocks.
   Resident blocks compile at their original definition positions. Input,
   mathematical printing and UI definitions load at runner/entry boundaries.
   Oversize indivisible functions and their larger admission requirements are
   explicitly recorded, not claimed to meet the 120-line packing target.
4. Project module accesses become native dictionary lookups into shared exec
   namespaces. This preserves mutable globals and avoids proxy-call frames.
   The event loop remains at module scope. Lazy families use the normal pin and
   eviction protocol. Phase loading rolls back partial definitions on failure.
5. `codec.py` creates independent bounded LZ/Huffman blocks, each checksummed.
   The decoder uses bytes/bytearrays and small bit accumulators. No zlib, base64,
   filesystem, module constructor or downloaded runtime library is required.
6. The entry, archive, decoder and loader become one ASCII Python 3.4 file.
   mpy-cross checks the final program and standalone diagnostic. LF text,
   deterministic ordering, fixed ZIP metadata and SHA-256 hashes make rebuilds
   reproducible across Windows/Linux checkouts.

Byte literals require more ASCII escape characters than base85 encoding, but
save approximately 20% of resident compressed payload memory. With storage well
below 3.5 MB, the build prioritizes the more constrained Python heap. The file
is about 262 KB and the resident compressed archive about 88 KB. Exact current
sizes and line/name maps are recorded in `release.json`.

## Memory acceptance is unresolved

The calculator probes recorded 173,360 bytes free after native imports, not
500 KB. `memory_report.py` compiles the transformed blocks and reports archive,
decoded dictionary, resident/phase bytecode, node backing arrays, and reserve.
The provisional .mpy multiplier remains 1.8. Current stages model roughly
235-237 KB **before** excluded object/namespace overhead, working nodes,
history/caches, lazy families and some compilation temporaries. The report's
`fits_known_heap_model` is false. The action emits a warning and includes this
status in its summary instead of calling the artifact hardware-ready.

Compressed sources remain rooted in the running single-file program. Removing
function definitions frees those functions but does not turn archive literals
into flash-backed storage. No verified EVO API currently permits paging source
from the same file. Additional phasing alone has not demonstrated a viable
full-calculus footprint within the measured heap. Meeting that limit requires
further architectural reduction or new device evidence; increasing the model's
heap constant would not solve it.

## Validation

- Final 2026-10-11 strict non-slow runs: 2,780 source tests passed in 460.81 s
  (actual-artifact tests omitted from that run), then 2,856 bundled tests passed
  in 746.31 s, including all 76 actual-artifact checks. Both deselected 55 slow
  tests. Native MicroPython passed the UI key flow and all 55 CVTEST commands.
- Source and intermediate bundled suites run with the strict eight-frame budget.
- `check_release.py` and `test_release.py` execute the actual compressed file,
  including dynamically compiled frames and the native exec penalty. Coverage
  includes T1/T2/T3 corpora, menus/forms, cancellation/interruption, partial phase
  rollback, repeated low-memory recovery and shared session state. Heap injection
  tests exercise recovery only; their free-memory stub is not a heap simulator.
- `micro_smoke.py` supplies tiny keyboard/graphics stubs and imports the unchanged
  files in native MicroPython. UI arithmetic/quit and CVTEST's 55 commands run in
  separate processes with a 500,000-byte heap. This caught stepped-slice and
  quadrature-cache problems missed by CPython. It is not an EVO emulator.
- `.github/workflows/build.yml` runs on pushes, pull requests and manual dispatch,
  installs pinned dependencies, builds/tests, checks checksums, and uploads the
  app plus the archive. Actions are pinned to commits with read-only permissions.

Physical transfer, graphics, execution time, call-depth calibration and heap
acceptance remain unrun. Follow [INSTALL.md](../INSTALL.md); do not report those
gates as passed from desktop evidence.
