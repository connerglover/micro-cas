# cas-evo handover

Updated: 2026-10-11. Branch: v1.
Remote: https://github.com/connerglover/cas-evo.git (private).

## Current outcome

The user reported `MemoryError: phase compile memory` in both CVTEST and
CASEVO. The previous source package is superseded. T1/T2/T3/UI features remain
implemented; this is a loader/packaging correction, not a reduced feature build.

The new download is **dist/cas-evo-calculator.zip**: 236 compiled EVO `.8mp2`
libraries for archive, plus CASEVO/CVTEST `.8xpy2` source launchers for RAM.
Transfer objects total 266,520 bytes; launcher sources total 6,760 bytes.
Only the launchers should appear in Python. Ordinary archived `.py` files are
not a substitute for compiled modules. See docs/INSTALL.md.

The old `dist/cas-evo-v1.zip` is retained as an internal source-build input.
Do not recommend it for calculator installation. The old release at 88a443b and
GitHub run 38164295044 passed native 1.29 tests but failed on the user's EVO.
Those checks did not establish physical compatibility.

## Next step

Finish the user's requested WebTILP installer website, preserving this memory
fix as the priority milestone. Website files are in progress under website/;
build/website.py still needs conversion to the compiled manifest format.
Finish browser/protocol checks, Impeccable review/documentation, automatic site
artifact build, final HANDOVER update, commit and push v1. The user authorized
all of that, requests no questions, and has not requested a PR or repo visibility
change. Physical USB transfer/execution remain hardware acceptance, never claim
them completed by native tests.

## Corrected loading architecture

build/release.py still minifies and pages ordinary source modules. Then:

1. build/archive_modules.py converts every source carrier into a native module
   with an initializer. Function signatures and live shared globals survive;
   no engine `exec` remains. Initializers are deleted after use so exported
   functions do not keep initializer bytecode and constants alive.
2. build/archive.py compiles with MicroPython v1.12 commit
   `1f371947309c5ea6023b6d9065415697cbc75578`, MPY v5, flags 3, small-int bits 31.
   It rejects a different ABI. Version 1.18 emits flags 2 and is incompatible.
3. Phase and math-family admission use compiled sizes, with parser line costs
   removed because no runtime parsing occurs. Actual allocation failures still
   roll back partial definitions; memory errors name the module/phase and bytes.
4. build/package_archive.mjs uses pinned TIVarsLib to generate real EVO CBOR
   transfer objects, then reads each one back and compares the exact payload,
   module name and variable type. build/archive_zip.py verifies and zips them.

The source paging rules, node cap, frame budget, caches, mathematical bounds and
formal fallbacks are unchanged. See docs/notes/PACKAGING.md and docs/DESIGN.md.

## Validation of the memory fix

- Reproduced the exact old startup exception on 32-bit MicroPython 1.12 with a
  95,000-byte total heap. Merely compiling the source carriers still failed.
- The replacement reaches CVTEST's first page at the same 95,000-byte heap,
  with 13,520 bytes free. This is a startup regression, not a full-engine budget.
- Actual final MPY v5 bytes pass UI arithmetic/quit, seven UI calculus/recovery
  commands and CVTEST 55/55 on 32-bit/173,360-byte and 64-bit/500,000-byte heaps.
- Native logs: dist/archive-final-32.log and archive-final-64.log (ignored).
  Final probe free heap: 66,704 and 341,120 bytes respectively.
- 85 archive initializer semantics, real artifact/corpus, recovery and strict
  depth tests pass. The existing eight-frame budget still holds.
- All 238 final transfer objects pass actual TIVarsLib round-trip checks.
- Website transport/installer tests currently 9 pass; physical USB not tested.

Final local inputs currently live in dist/archive-final and
dist/archive-final-transfer. CI uses the canonical dist/archive and
dist/archive-transfer. Never rebuild a directory while a test reads its files.

## Reproduce

Use .venv/Scripts/python locally; requirements-dev.txt pins dependencies.

    python build/release.py
    python build/archive.py --mpy-cross /path/to/v1.12/mpy-cross
    python -m pytest -q tests/test_archive_modules.py tests/test_archive_release.py --strict-depth
    python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run /path/to/v1.12/micropython-cas32 --heap 95000 --suite startup
    python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run /path/to/v1.12/micropython-cas32 --heap 173360
    node build/package_archive.mjs
    python build/archive_zip.py

The GitHub action builds both the original 1.29 compatibility checks and the
actual MPY v5 package on 1.12, plus the startup regression. Its cas-evo-v1
artifact now contains cas-evo-calculator.zip. This workflow change is not yet
pushed or verified on GitHub in this milestone.

Native local environment: WSL cachyos, /tmp/cas-evo-mpy5-ti. Old MicroPython
needs `-DMICROPY_NLR_SETJMP=1` with modern GCC (without it, caught exceptions
were corrupted), and 32-bit Linux needs `-D_FILE_OFFSET_BITS=64` on this NTFS
mount (without it, stat returned EOVERFLOW). These affect the host harness,
not MPY format or calculator code. Native executables are
ports/unix/micropython-cas32 and micropython-cas64. The former uses the private
/tmp/cas-evo-i686 sysroot loader and library path; no system packages installed.

## Project rules

- Work autonomously; no questions. Preserve all v1 functionality; multiple files
  explicitly allowed. Commit milestones, update HANDOVER and push v1 when done.
- Commit footer: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>.
- Target Python 3.4 subset; no recursion, explicit stacks/trampoline. No graphing.
- Read-only reference repositories: C:/Users/conner/.cache/cas-evo-ref.
- Source acceptance: python tests/support/lint.py src; framelint.py;
  python -m pytest -q -m "not slow" --strict-depth (and --bundled after release).
- Impeccable context already ran once this session. Do not rerun. Direction is
  in .impeccable/surfaces/website-index-html.md and docs/notes/WEBSITE-DIRECTION.md.
  Its archive-only wording must be corrected for compiled libraries + RAM
  launchers. Finish reviewer and documenter are still owed after website QA.

Previous milestones: T1 841cbfe; T2 2273a6d; T3 c08edd0; UI d767ade;
compatibility 699cc12; CI/single-file f19de2b; companions cffa02e;
identifier/input 08ad2dd; storage/cache 54ac8d5; paging 88a443b;
prior handover 7ddc258. The current memory fix supersedes their install advice.
