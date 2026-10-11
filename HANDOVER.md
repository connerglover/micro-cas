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

The user now requests Cloudflare Pages hosting on their existing domain. Use
**cas.connerglover.com**, Pages project **cas-evo**, production branch **v1**.
Deployment preparation is implemented. The user then requested instructions
instead of further account automation. Cloudflare authentication was not
completed (Wrangler OAuth timed out); no Pages project, deployment, DNS record,
custom-domain binding or deployment secret was created. The site is not live.
The user will perform the one-time setup in docs/HOSTING.md.

Once hosting is configured, the next acceptance step is the user's physical
EVO: use the installer, run CASEVO, then run CVTEST in a fresh Python session.
Record the OS version, complete traceback/free-heap values if a failure occurs,
and CVTEST's final result. Native checks do not complete hardware acceptance.
Do not restore the old source-only package or recommend putting all companions
in RAM. Preserve all T1/T2/T3/UI features when addressing any device feedback.

The user requests no questions, wants commits pushed, and has not requested a
PR or repository visibility change. Publishing the built installer and attaching
the subdomain are authorized. Credentials must stay out of chat and source files.

## Cloudflare hosting preparation

- `.github/workflows/build.yml` now has a Pages deployment job after the existing
  complete build. Only `v1` push/manual builds deploy; PRs never publish. It uses
  that run's `cas-evo-web-installer` artifact, pinned Wrangler 4.149.0 and Node 22.
- Configure repository secret `CLOUDFLARE_API_TOKEN` (account-scoped Pages Edit),
  then repository variable `CLOUDFLARE_ACCOUNT_ID` to enable it. Neither was set
  when this task began. Without the account variable the deploy job is skipped.
- `build/check_pages.py` checks the exact upload folder for Pages limits,
  required files/licenses, isolation headers, manifest/vendor hashes and stray
  root files. The existing downloaded CI artifact passes: 28 files, largest
  25,642,244 bytes, below the 26,214,400-byte limit. GPL source ZIPs remain served.
- Workflow validation: actionlint 1.7.12 passes (official release SHA-256 checked).
- `docs/HOSTING.md` documents Direct Upload, custom-domain binding, token setup
  and production verification. PRODUCT.md records the new hosting authorization.
- Local `.wrangler/` state is ignored. Deploy only the built `website/` folder;
  preserve private repository/design briefs and unrelated DNS records.

## Final delivery verification

- Runtime milestone 3eee7ba: successful run 38169620143.
- Installer milestone 9f83514: successful run
  https://github.com/connerglover/cas-evo/actions/runs/38170910971.
- Both final artifacts were downloaded to dist/ci-38170910971 and checked.
  All 238 transfer objects match the locally native-tested bytes. ZIP checksums,
  site manifest integrity, vendor hashes and committed browser sources match.
- `cas-evo-v1` artifact ID: 11713354445; `cas-evo-web-installer`: 11713429278.
  Artifact retention is 14 days; rerun the workflow to regenerate a download.
- The website's calculator ZIP equals the calculator artifact's ZIP. The
  installer artifact contains website/, serve_installer.py, START-INSTALLER.txt,
  matching upstream source archives/licenses, and no private design briefs.
- Downloaded server command options were checked; its script matches the
  browser-tested local server. The running server returns HTTP200 and both
  required isolation headers. A second temporary-server launch was blocked by
  automatic approval review; verification used file equivalence and the already
  running server instead, without retrying the blocked launch.
- Final documentation-only commit records these results and the Impeccable
  design files with [skip ci]; calculator, website and build code remain 9f83514.

## Web installer

`website/` is a static, self-contained desktop Chrome/Edge Web Serial installer
using pinned, unmodified WebTILP. `build/website.py` consumes the compiled EVO
manifest, validates vendor hashes, mirrors corresponding upstream source, and
bundles a calculator ZIP, local server, credits, licenses and integration source.
GitHub's `cas-evo-web-installer` artifact contains `website/`,
`serve_installer.py` and `START-INSTALLER.txt`. Extract it, run
`python serve_installer.py --directory website`, visit http://127.0.0.1:4173.
The repository's local server is `python build/serve_website.py` after building.
No public hosting or repository visibility change has been made.

Installer behavior: verify every object hash before device access, check space,
move only exact hash-matched old cas-evo source companions out of RAM, install
compiled libraries to archive before the RAM launchers, then verify directory
types and destinations. Modified old files are preserved with a manual recovery
message. Native calls are serialized; stop waits for the current file; a timeout
retires the WASM instance because JavaScript cannot cancel Asyncify safely.

12 Node checks pass, including the real TIVarsLib source round-trip/migration,
native init reference-count handling, storage errors, ordering, stop, timeout,
location verification and all 238 package hashes. Real browser WASM loads and
initializes (its `init()` returns 1, not a zero success code). T3 browser checks
cover settled package state, SHA-256, all 238 rows, matching/empty search, and no
horizontal overflow at 1440, 1280 and 390px, including the expanded mobile table.

Impeccable finish reviewer: **ship**, no material fixes. All three full-page
captures were reviewed; no approved comp exists (autonomous code-led choice).
UI design lives in root DESIGN.md and .impeccable/design.json; engine architecture
remains docs/DESIGN.md. Review images/results under .impeccable/review are ignored.
Product/direction/review material is not served or included in website downloads.

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
- Website transport/installer tests: 12 pass; physical USB not tested.
- GitHub runtime milestone: 2,837 source tests, 2,915 bundled tests and 85
  archive tests pass. Skips are artifact-dependent tests before their build
  stage. The standard acceptance command excludes 55 slow cases; CVTEST is a
  separate 55-command native diagnostic, not a substitute for those tests.

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
artifact now contains cas-evo-calculator.zip. The runtime workflow is pushed in
3eee7ba; the website milestone adds its own installer artifact to the same action.

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
  Its storage wording now matches compiled libraries + RAM launchers. Finish
  review completed with ship. Root DESIGN.md and .impeccable/design.json passed
  schema/token/source checks; docs/DESIGN.md remains unchanged.

Previous milestones: T1 841cbfe; T2 2273a6d; T3 c08edd0; UI d767ade;
compatibility 699cc12; CI/single-file f19de2b; companions cffa02e;
identifier/input 08ad2dd; storage/cache 54ac8d5; paging 88a443b;
prior handover 7ddc258. The current memory fix supersedes their install advice.
Current milestones: memory/compiled packaging 3eee7ba; web installer 9f83514.
