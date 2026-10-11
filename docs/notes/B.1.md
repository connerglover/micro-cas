# B.1: automatic calculator builds

## Current multi-file release (2026-10-11)

The user authorized multiple files after TI Connect Evo rejected the single-file
build. `build/release.py` now preserves the full T1/T2/T3/UI implementation in
110 Python files. CASEVO and CVTEST are entry programs; the remaining files
carry minified source strings. The whole package contains 272,097 source bytes;
the largest individual file is 6,314 bytes. All 110 passed TI's actual converter.

`_read` imports one carrier, takes its CODE string and immediately removes the
carrier from `sys.modules`. `_load` executes source into shared native dictionary
namespaces, preserving live globals without proxy call frames. Existing bounded
phases evict UI/input/print definitions and reload them from carriers. Decoded
source and compilation temporaries are collected after execution. No archive,
codec dictionary or decoder remains in the resident application.

The provisional memory subtotal drops from 236,690 to 139,442 bytes, including
code, node backing and reserve. Namespace/working/lazy-family/compiler costs
remain exclusions. The 173,360-byte device heap is unchanged; only a physical
EVO test can establish runtime fit and graphics/depth behavior.

The build rejects every carrier or entry exceeding its per-program converter
limit and checks their combined Python-object storage. It compiles each output,
writes complete hashes/metadata and a deterministic `cas-evo-v1.zip`. It removes
previous known generated outputs before building, so a rejected build cannot
leave a stale apparently valid release ZIP. The removed --allow-oversize option
is no longer useful. GitHub Actions uploads only the complete ZIP, making it
harder to accidentally download the entry without its companions.

Validation: 76 actual-package acceptance tests pass under strict frame checking;
31 initial transfer/memory checks pass, including a reused-directory rejection
regression. Native 64-bit MicroPython passes UI arithmetic/quit and CVTEST 55/55.
The full bundled regression suite and final publication are recorded in HANDOVER.

## Historical single-file implementation (superseded)

The rest of this note records the previous design and its failed constraints.
It does not describe the current downloadable package.

# B.1: single-file build and release checks

The current default `python build/release.py` **fails the transfer-size gate**:
CASEVO.py is 262,679 bytes versus a verified 65,511-byte converter limit.
See [the transfer investigation](../reference/transfer-limits.md). The former
cas-evo-v1.zip was not transferable; the total-storage check was insufficient.

With `--allow-oversize`, desktop developers can still produce CASEVO.py,
CVTEST.py, INSTALL.md, release.json, SHA256SUMS and cas-evo-development.zip.
Metadata explicitly records the failed transfer check. Only a size-compliant
build can generate a new cas-evo-v1.zip. Generated files are Git-ignored.

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
   `transfer.py` checks the per-program source limit before publication;
   mpy-cross checks the final program and standalone diagnostic. LF text,
   deterministic ordering, fixed ZIP metadata and SHA-256 hashes make rebuilds
   reproducible across Windows/Linux checkouts.

Byte literals require more ASCII escape characters than base85 encoding, but
save approximately 20% of resident compressed payload memory. This tradeoff
still exceeds the newly verified per-program transfer limit: the file is about
263 KB and the resident archive about 88 KB. Exact current sizes, transfer
status and line/name maps are recorded in development `release.json`.

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
