# cas-evo handover

Updated: 2026-10-11, multi-file transfer fix and constrained-heap validation in progress.
Branch: v1. Remote: https://github.com/connerglover/cas-evo.git (private).

## Current outcome

T1, T2, T3 and the calculator UI are implemented. The user explicitly authorized
multiple files after the original CASEVO.py transfer failed. They also requested
commit and push when finished. Preserve all features; no single-file constraint
remains. The build now emits CASEVO/CVTEST plus minified source carriers, 110
Python files in one cas-evo-v1.zip. All 110 first-revision files passed TI's actual
converter; the largest is 6,314 bytes. No USB/device transfer was performed.

The old single-file CASEVO (262,679B) exceeded its 65,511B per-program limit.
Boundary experiments prove source bytes + 18 + module-name length must not
exceed 65,535. build/transfer.py gates every new output; stale deliverables are
invalidated before building. No oversized-development override remains.

## Next step

Finish constrained 32-bit native validation, final package/converter checks,
commit and push v1, then verify the GitHub Actions build and downloadable ZIP.
Update this handover with final results before stopping. The first paged native
32-bit test at 173,360B booted the UI, but only 21/55 diagnostic commands passed.
Tracebacks show native allocation failures during carrier import/compilation,
not the admission guard. Collection before and after carrier import has just
been added and is awaiting re-test. Do not claim heap acceptance from a model.

The current provisional stage subtotal is about 139KB, below the unchanged
173,360B measured free Python heap, but excludes namespaces, working data, lazy
families and some compiler temporaries. The old 87,456B resident archive and
decoder have been removed. `_read` imports one CODE-string carrier, removes it
from sys.modules, and collects; `_load` execs source into shared dictionaries
and collects source after use. Existing UI/input/print eviction stays in place.

Physical transfer, depth calibration, graphics and heap validation remain
Conner's device checks. Never report them as passed from host evidence.

## User instructions and project rules

- Work autonomously, no questions. Finish the downloadable v1, commit milestones.
- Multiple files explicitly allowed to preserve functionality; automatic GitHub
  Action and minification still required. User explicitly requests a final push.
- Commit footer: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>.
- Read docs/DESIGN.md and task notes for APIs, bounds and deviations. No graphing.
- Target EVO Python 3.4 subset. No recursion; explicit stacks/generator trampoline.
  Desktop strict depth budget eight. Native/dunder costs need device calibration.
- Reference repositories under C:/Users/conner/.cache/cas-evo-ref are read-only.
- No PR requested. Push the existing v1 branch; do not change repository visibility.

## Implemented milestones

T1 841cbfe; T2 2273a6d; T3 c08edd0; UI d767ade; MicroPython compatibility 699cc12;
previous single-file/CI packaging f19de2b. Current uncommitted milestone replaces
that packaging with demand-loaded companions and transfer-limit validation.

T2/T3 notes document bounds and unsupported cases: this is not an unrestricted
symbolic math engine. Preserve the implemented behavior and formal fallbacks.

## Build and validation

Use .venv/Scripts/python in this Windows checkout. requirements-dev.txt pins
build dependencies. Generated files under dist are ignored; the ZIP contains
all required .py files, INSTALL.md, release.json and SHA256SUMS.

    python -m pip install -r requirements-dev.txt
    python tests/support/lint.py src
    python tests/support/framelint.py
    python -m pytest -q -m "not slow" --strict-depth
    python build/release.py
    python -m pytest -q -m "not slow" --strict-depth --bundled
    python build/check_release.py
    python build/micro_smoke.py

Current validation before the final GC change:
- 76 actual-package strict acceptance tests pass, including corrected native
  __import__ depth accounting as well as exec; max depth stays eight.
- 32 transfer/memory tests pass, including rejected builds in a reused directory.
- Full bundled run: 2,795 pass, 55 slow deselected; two mock-fixture failures were
  corrected and re-run successfully in the focused suite above. The long run
  had loaded the earlier test functions before the correction.
- Device subset/FRAMELINT and actionlint 1.7.12 pass.
- Native64, 500,000B: UI arithmetic/quit and CVTEST 55/55 pass.
- Native32, 173,360B: UI pass (56,784B boot free); calculus failures under diagnosis.
- ZIP audit: all 110 declared Python files and metadata/checksums match.

Native MicroPython pinned commit: 0fd6c573ea815774668bbb16b8e197c8822368b2, v1.29.0.
WSL cachyos checkout: /tmp/cas-evo-micropython. Unix binaries: ports/unix/build-cas64
and build-cas32/micropython. The 32-bit build uses a private extracted sysroot
/tmp/cas-evo-i686; no system packages were installed. Launch via its
usr/lib32/ld-linux.so.2 --library-path /tmp/cas-evo-i686/usr/lib32 BINARY
-X heapsize=173360 /mnt/c/Users/conner/Documents/GitHub/cas-evo/dist/micro-smoke/probe.py.
Use wsl --exec with absolute script paths; login shells change working directory.
`build/micro_smoke.py` restores unchanged release copies before testing; previous
diagnostic copies were temporarily instrumented and must not be published.
