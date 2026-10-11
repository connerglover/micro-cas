# cas-evo handover

Updated: 2026-10-11. Branch: v1.
Remote: https://github.com/connerglover/cas-evo.git (private).

## Current outcome

T1, T2, T3 and the calculator UI are implemented. The user authorized multiple
files after the oversized single-file build was rejected, and explicitly
requested a final commit and push. The v1 download is dist/cas-evo-v1.zip:
238 minified Python files, 317,277 source bytes total, largest file 6,238 bytes.
Extract the ZIP, send every .py file together, and run CASEVO. CVTEST is the
optional 55-command diagnostic. Do not send files from src/ or dist/device/.

Release commit 88a443b is pushed to origin/v1. GitHub Actions
[run 38164295044](https://github.com/connerglover/cas-evo/actions/runs/38164295044)
passed every step. The downloaded
[cas-evo-v1 artifact](https://github.com/connerglover/cas-evo/actions/runs/38164295044/artifacts/11711359556)
contains the verified ZIP. This artifact expires 2026-10-25; a new push or
manual workflow dispatch produces a fresh download. The private repository
requires GitHub sign-in. Extract the artifact ZIP, then cas-evo-v1.zip inside it.

All 238 final files passed TI Connect Evo 7.1.0.792's actual converter, with
matching source hashes recorded in docs/reference/multifile-converter-checks.json.
The old CASEVO.py was 262,679 bytes, beyond the 65,511-byte per-program limit.
The build enforces source bytes + 18 + module-name bytes <= 65,535 for every
file, checks combined storage and compilation, and produces a deterministic ZIP.

The actual final calculator bytes pass native MicroPython UI arithmetic/quit,
seven UI calculus/recovery commands, and CVTEST 55/55 on both a 173,360-byte
32-bit total heap and a 500,000-byte 64-bit total heap. The physical EVO probe
measured 173,360 free Python bytes; total user RAM is not Python heap. The host
harness uses short import paths so checkout path length does not change the
memory test. Graphics shims allocate no framebuffer. Physical EVO transfer,
graphics, speed and depth calibration remain device checks, not completed work.

## Next step

No implementation or publication work remains in the agreed v1 scope.
The next step is Conner's physical calculator acceptance using docs/INSTALL.md:
send all 238 Python files from the verified ZIP, run CASEVO, and run CVTEST.
Investigate any reported device failure against that exact package and traceback.
Do not describe native or desktop checks as a physical calculator run.

## Validation

- Final actual-package/paging/transfer acceptance: 100 tests pass, strict depth.
- Corrected node/debug-arena, normalizer, solver, mapping and build regressions:
  418 tests pass. Build/paging/transfer/memory tests: 84 pass.
- Full final bundled regression: 2,906 pass; 55 slow/oracle tests deselected.
  The debug-arena reset bug found in the earlier run is fixed and its affected
  algebra/node tests pass. Final actual-package strict depth remains eight.
- GitHub run 38164295044: source 2,829 pass, 77 artifact tests skipped;
  bundled 2,906 pass. Each run deselects 55 slow/oracle tests. Both native word
  sizes pass UI arithmetic/quit, seven UI calculus commands and CVTEST 55/55.
- Native 32-bit/173,360 bytes and 64-bit/500,000 bytes: all three smoke suites
  pass against final immutable calculator bytes. Logs are ignored under dist/.
- Source subset lint, FRAMELINT, actionlint 1.7.12 and git diff checks pass.
- ZIP members, SHA256SUMS, release metadata, smoke copies and converter captures
  match exactly. Independent local builds produce the identical 245,512-byte ZIP:
  SHA256 983a0be93eb525a1239d9ab93c8b4b2d700bb1242754a135a960f554319a0a79.
- Downloaded GitHub ZIP: 246,901 bytes, SHA256
  864e7abdeecd1106a65f3f43e5fa4e196b0e935ab7488ff540f6f81630fb3d20.
  Every uncompressed member is byte-for-byte identical to the local package;
  compression differs between host environments. All downloaded member checksums
  and ZIP CRCs pass. CI log: dist/github-build.log (ignored).

## Packaging architecture

See docs/notes/PACKAGING.md. Source stays in ordinary modules. The release uses
live namespace dictionaries, bounded source carriers, phased input/output/UI
code and 128 native function pages for 180 functions. Each generator owns its
page; cold imports never add a Python forwarding frame. Deep level-seven leaves
and escaped complex callbacks remain resident. Page caches clear on imports,
phase transitions, trampoline steps and command exits, including failures.

Node tables start at 64 slots and grow to the unchanged 768-node cap. Reset
shrinks normal backing tables but preserves the host debug arena's explicit
preallocation. Partial allocation cannot modify the intern/hash state. The
RPN template cache retains only its most recent program. Bounds and formal
fallbacks from T2/T3 are unchanged; this is not an unrestricted symbolic engine.

Source spans survive AST rewriting in release.json, including native-page
output positions and pre-transform origin_linemap. Use:

    python build/linemap.py --map dist/release.json CVF00001:8

The desktop artifact harness uses synthetic free memory and native no-op
collection to avoid repeatedly scanning the unrelated SymPy heap. Runtime heap
acceptance is performed by the native MicroPython tests, not that harness or
the provisional memory model (117,619 bytes before documented exclusions).

## Build and project rules

Use .venv/Scripts/python locally; requirements-dev.txt pins build dependencies.

    python tests/support/lint.py src
    python tests/support/framelint.py
    python -m pytest -q -m "not slow" --strict-depth
    python build/release.py
    python -m pytest -q -m "not slow" --strict-depth --bundled
    python build/check_release.py
    python build/micro_smoke.py --run /path/to/32-bit/micropython --heap 173360

GitHub Actions builds/tests on push, pull requests and manual dispatch, including
both native word sizes. The artifact cas-evo-v1 contains cas-evo-v1.zip.
Generated files and experiments under dist/ are ignored; only ZIP members in
release.json belong on the calculator. Never rebuild a directory while a test
process is reading its artifacts; use a separate --dist for comparison builds.

- Work autonomously; no questions. Preserve the v1 feature set; multiple files
  explicitly allowed. Commit milestones, update HANDOVER and push v1 when done.
- Commit footer: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>.
- Read docs/DESIGN.md and task notes for APIs/bounds/deviations. No graphing.
- Target Python 3.4 subset; no recursion, use explicit stacks/trampoline.
  Desktop strict depth budget eight; device/native costs need calibration.
- Reference repos under C:/Users/conner/.cache/cas-evo-ref are read-only.
- No PR requested; do not change repository visibility.

## Milestones and native environment

T1 841cbfe; T2 2273a6d; T3 c08edd0; UI d767ade; compatibility 699cc12;
original CI/single-file build f19de2b; transferable companions cffa02e;
identifier/input overlap 08ad2dd; dynamic storage/template cache 54ac8d5;
native function paging and final release checks 88a443b (pushed to origin/v1).

Pinned MicroPython v1.29.0: 0fd6c573ea815774668bbb16b8e197c8822368b2.
WSL cachyos: /tmp/cas-evo-micropython/ports/unix/build-cas32/micropython
and build-cas64/micropython. Native32 uses the private extracted sysroot
/tmp/cas-evo-i686, launched through usr/lib32/ld-linux.so.2 with
--library-path /tmp/cas-evo-i686/usr/lib32. No local system packages were installed.
