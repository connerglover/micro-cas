# cas-evo handover

Updated: 2026-10-11, single-file build and native compatibility milestone.
Rewrite this file at each milestone. Branch: v1.

## Current outcome

T1, T2, T3 and the calculator UI are implemented, with bounded algorithms and
documented unsupported cases. The build produces one minified, compressed
runtime file, dist/CASEVO.py, plus an optional standalone CVTEST.py.
GitHub Actions builds, tests and packages these automatically on push, pull
request and manual dispatch. The local repository currently has no Git remote;
the workflow has been checked locally, not executed on GitHub.

**The user's requested finished calculator v1 is NOT yet established. Heap fit
is the remaining release blocker.** Do not equate passing desktop/native tests
with completion on the EVO. The current artifact is a device test build and may
fail during startup on the real calculator.

## Next step

Resolve the memory architecture before declaring v1 complete. Preserve the full
T1-T3/UI behavior and single-file requirement. Do not repeat completed feature
work or merely raise the heap limit. The existing device probes measured
**173,360 bytes of free Python heap** after native imports; the user's roughly
500 KB of total accessible RAM is not all available to Python.

The current provisional stage subtotal is **236,690 bytes**, before namespace
overhead, working data, lazy families and some compilation temporaries. The
single-file archive retains **87,456 bytes** even when compiled definitions are
evicted. No verified EVO API permits reading/paging source from the same file;
open is absent. More aggressive phasing alone has not established a viable
full-calculus footprint. Further work needs a materially smaller representation
or new device evidence, not another optimistic budget adjustment.

After resolving this, repeat the source/bundled/native checks, regenerate the
package, commit and update this handover. Physical transfer, depth calibration,
graphics and heap checks remain deferred to Conner under the existing project
instructions. Never claim those gates passed without results.

## User instructions and project rules

- Work autonomously; do not ask Conner questions. Complete all milestones and
  the downloadable app, rather than stopping after T1/T2/T3.
- Commit at milestones; end messages with
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>.
- Produce one .py runtime file and an automatic GitHub Action. Minify for
  limited storage and especially heap. No graphing in v1.
- Read docs/DESIGN.md and docs/notes/<TASK>.md for APIs, bounds and deviations.
  docs/reference/device-python.md records measured versus assumed device facts.
- Target the EVO's Python 3.4 subset. No recursion; use explicit stacks and the
  generator trampoline. Strict desktop depth budget: eight; measured ceiling:
  about ten total Python calls. Native/dunder costs require device calibration.
- Reference repositories are read-only: C:/Users/conner/.cache/cas-evo-ref/FlowCE
  and C:/Users/conner/.cache/cas-evo-ref/ti-ce-giac.
- The project is personal and has no licence yet. No push or publication occurred.

## Implemented milestones

| Milestone | Evidence / commit |
|---|---|
| T1 exact core | 841cbfe; rational/radical/complex arithmetic, normalization, factor/solve, sessions; split lazy units |
| T2 calculus | 2273a6d; derivatives, Laurent/Taylor series, limits and verified integration strategies |
| T3 | c08edd0; definite/improper/nested integrals, sums/Riemann, ODEs, gradients/geometric macros |
| UI and diagnostic | d767ade; editor/history, 2D answers, F1-F5 menus/forms/help, cancellation/panic; 55-command CVTEST |
| MicroPython compatibility | 699cc12; unsupported stepped slices replaced with loops and subset-lint gates |
| Single-file/CI packaging | This milestone; see docs/notes/B.1.md |

T2/T3 notes list deliberate bounds and remaining DESIGN differences, including
generic infinite-series tests, general numerical singularity isolation and the
independent quadrature cross-check. Unsupported cases stay formal; do not
describe this as an unrestricted symbolic mathematics engine.

## Build and artifacts

Use .venv/Scripts/python on this Windows checkout. Dependencies are pinned in
requirements-dev.txt. mpy-cross checks the final Python and supplies provisional
compiled-size estimates; the factor 1.8 is uncalibrated, not a measured heap bound.

    python -m pip install -r requirements-dev.txt
    python tests/support/lint.py src
    python tests/support/framelint.py
    python -m pytest -q -m "not slow" --strict-depth
    python build/release.py
    python -m pytest -q -m "not slow" --strict-depth --bundled
    python build/check_release.py
    python build/micro_smoke.py --run /path/to/micropython --heap 500000

- dist/CASEVO.py: **262,679 bytes**; the only runtime file to transfer.
- dist/CVTEST.py: independent optional diagnostic, **267,644 bytes**.
- dist/cas-evo-v1.zip: app, diagnostic, installation guide, release.json
  metadata and SHA256SUMS. Generated files are Git-ignored.
- docs/INSTALL.md: transfer steps, controls, acceptance commands and candid
  heap/physical-validation status. README describes local and Actions downloads.
- dist/device and dist/blocks: inspectable desktop build intermediates;
  neither is needed on the calculator.

The release pipeline shrinks identifiers, uses native dictionary namespaces,
packs bounded source blocks, and evicts input/print/UI phases. Compressed binary
literals save resident memory compared with base85 at the cost of ASCII file
size; the result is well below the 3.5 MB storage budget. A deterministic LZ/Huffman
decoder needs no third-party calculator modules or file access. Checksums,
fixed ZIP metadata and LF output support reproducible builds. The action reports
heap fit as unresolved rather than silently substituting 500 KB.

## Verification for this milestone

- Full source strict non-slow suite: **2,780 passed**, 55 slow tests deselected,
  in 460.81 seconds. Command also used --ignore=tests/test_release.py because
  the bundled run includes the actual-artifact suite. A clean checkout skips
  those artifact tests until the single-file program has been built.
- Full bundled strict non-slow suite: **2,856 passed**, 55 slow tests deselected,
  in 746.31 seconds. This includes 76 tests of the actual compressed artifact,
  its dynamic frames, real event loop, phase transitions and failure recovery.
- Device-subset lint, FRAMELINT and actionlint 1.7.12 pass.
- Current actual CASEVO.py: native MicroPython 1.29, 64-bit, 500,000-byte heap:
  boot, real key replay 2+3, answer 5, and normal quit pass.
- Current actual standalone CVTEST.py: **55/55 pass**, plus native depth
  3/6/8 and math checks. The native graphics shim allocates no framebuffer.
- Native testing exposed stepped-slice incompatibility, lazy-source garbage
  retention and quadrature float-key dictionary fragmentation. The release
  loader now collects after decoded-source execution; admission collects before
  rejecting a load; quadrature uses a fixed 449-slot dyadic sample grid.
- Independent builds produce identical CASEVO, CVTEST and release metadata.
  The final package is checked against a second build and all member checksums.
- Native 64-bit object sizes differ from the calculator. These results do not
  establish fit in its 173,360-byte heap. A 173,360-byte native-host startup
  experiment failed; that is not an EVO measurement either.
- Physical transfer, font metrics, execution timing, PRBMEM/PROBE6 and device
  acceptance remain unrun. See probe/README.md and probe/README-MEM.md.

Native interpreter built from MicroPython commit
0fd6c573ea815774668bbb16b8e197c8822368b2 (v1.29.0). Local WSL executable:
/tmp/cas-evo-micropython/ports/unix/build-cas64/micropython in cachyos.
Use wsl -d cachyos --exec and an absolute /mnt/c/... script path; the user's
login shell resets the working directory. build/micro_smoke.py recopies the
unchanged release into dist/micro-smoke and verifies copied hashes.
