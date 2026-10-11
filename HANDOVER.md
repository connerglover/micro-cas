# cas-evo handover

Updated: 2026-10-11, transfer fix committed; heap optimizations in progress.
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

Finish production integration of native function pages, rerun exact-artifact and
constrained native tests, refresh converter evidence, update these results, then
commit and push v1 and verify GitHub Actions. Do not stop before the download is
ready. User explicitly authorized the push.

The isolated function-page experiment now passes CVTEST **55/55** on native
32-bit MicroPython with a **173,360-byte total heap**. It keeps level-seven leaves
and escaped complex callbacks resident, gives each generator its own code page,
and caches only the currently imported page. Cleanup also runs after input,
at trampoline boundaries, before printing, and on command exit. This result is
from dist/single-gen-cache, not yet proof of the production release.

Source backing tables now start at 64 slots, grow to the unchanged 768-node cap,
and shrink on reset. A failed partial allocation leaves the intern/hash state
intact for retry. Template compilation retains only the most recent RPN program.
229 node/evaluator tests and 13 focused allocation/cache regressions pass with
strict depth. Source subset/frame checks and complete suites are pending.

The production builder integration is in progress in build/function_pages.py.
It must preserve default arguments from source constants, namespace evaluation,
function ownership, live globals, depth limits and failure cleanup. Refresh the
actual TI converter capture after the final build. Existing docs still describe
the earlier 110-file / 264,489-byte package.

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
previous single-file/CI packaging f19de2b; transferable companions cffa02e.
The next milestone reuses names across separate namespaces and frees the input
frame before compiling math families. It preserves the original eight-frame
budget, memory guards, and mathematical behavior.

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
