# Delivery status and evidence

Last reviewed: 2026-10-11. Repository: connerglover/cas-evo (private).
Use [AGENTS.md](../AGENTS.md) for operating instructions. This file records a
dated snapshot; verify remote heads, build results and hosting before reporting
them as current.

## Current delivery

- T1/T2/T3 and calculator UI features are implemented. The compiled loader
  preserves the full feature set while addressing the reported startup
  `MemoryError: phase compile memory` in CASEVO and CVTEST.
- The calculator download is `cas-evo-calculator.zip`: 236 compiled `.8mp2`
  libraries for Archive and two `.8xpy2` launchers for RAM. The baseline transfer
  objects total 266,520 bytes; launcher sources total 6,760 bytes.
- The web installer is implemented and tested locally. Its download includes
  the full calculator package, WASM, fonts, licenses, corresponding-source ZIPs,
  and a local Python server. Physical EVO USB transfer/execution remains pending.
- `v1` was fast-forward merged into `main` at **25b83b0**. Both were pushed; main
  remains the default source branch and v1 is retained. The generated **pages**
  branch is intended for a Cloudflare Worker connected through GitHub.
- Main verification/publication run:
  https://github.com/connerglover/cas-evo/actions/runs/38174533070.
  **Both build and publication passed.** It created pages commit
  **2849055909cabe6137bcdda0ada89b579628da11**, with source commit
  25b83b0eb8cf4a90b9ba0ee0c734cae55b47247b recorded in deployment.json.
- Cloudflare dashboard connection, a live Worker, DNS and HTTPS at
  **cas.connerglover.com** have not been verified. The user wants to perform
  setup through the dashboard; use [HOSTING.md](HOSTING.md).

## Remaining acceptance

1. Connect Cloudflare Worker cas-evo to the generated pages branch, deploy, attach
   the custom domain, and verify HTTPS, isolation headers, package downloads and
   WASM initialization. Repository visibility remains private.
2. On the physical EVO, install through the browser, run CASEVO, and run CVTEST
   in a fresh Python session. Record OS version, complete error/traceback and
   free-heap readings if anything fails. A native host check is not an emulator.

Do not reopen finished feature milestones without a new defect or request.
Address device feedback while preserving the complete v1 feature set.

## Verified evidence

| Milestone | Evidence |
| --- | --- |
| Compiled loader, 3eee7ba | Successful Actions run 38169620143; actual MPY v5 bytecode passed both native heap budgets |
| Browser installer, 9f83514 | [Run 38170910971](https://github.com/connerglover/cas-evo/actions/runs/38170910971); both artifacts downloaded and compared with locally tested files |
| Initial hosting checks, 01f2317 | [Run 38173653858](https://github.com/connerglover/cas-evo/actions/runs/38173653858) passed; the former Pages deployment job was skipped because account settings were absent |
| Branch separation, 25b83b0 | Five local publication tests, actionlint 1.7.12, full-site asset checks and Wrangler 4.149.0 dry run pass; full main CI and automatic pages publication pass |

The main run passed **2,842 source tests**, **2,920 bundled tests**, **85 archive
tests**, and **12 installer Node tests**, plus native MPY v5 diagnostics at both
heap budgets and the 95,000-byte startup regression. Source/bundled runs excluded
55 slow tests and skipped 154/76 artifact-dependent cases respectively. The
extra source/bundled passes versus the earlier baseline are the five publisher
tests, not new calculator features.

All **28 published public/ files** were compared byte-for-byte with the downloaded
installer artifact from this run. The pages commit has no source-history parent;
its root contains only deployment metadata/configuration, README/ignore rules and
public/. The calculator ZIP SHA-256 is
`00bb90a3faa14b1eb900ebb23c4a36d41bc79a166486f2cc364bfe52c27a1a0c`.
The later agent-guide replacement changes documentation only; deployed artifact
provenance remains the tested source commit 25b83b0.

The earlier installer artifact's 238 objects matched the native-tested bytes;
its calculator ZIP matched the calculator artifact ZIP. Vendor hashes, website
manifest and committed browser sources were checked. Actions artifacts expire
after 14 days, so use a current successful build instead of relying on an old ID.

Native memory evidence for the loader fix:

- Reproduced the old startup exception on 32-bit MicroPython v1.12 with a
  95,000-byte total heap. Compiling source carriers without removing embedded
  `exec` still failed.
- The replacement reached CVTEST's first page at the same heap with 13,520 bytes
  free. This is a startup regression budget, not full-engine acceptance.
- Final MPY v5 bytes passed UI arithmetic/quit, seven UI calculus/recovery cases,
  and CVTEST 55/55 on 32-bit/173,360-byte and 64-bit/500,000-byte total heaps.
  The final baseline probes reported 66,704 and 341,120 bytes free respectively.
- 85 archive semantic/corpus/recovery/depth tests passed. The baseline full
  source and bundled suites passed 2,837 and 2,915 tests before publication tests
  were added. The normal command excludes 55 slow cases; those differ from the
  55 native CVTEST calculations.

Browser evidence: 12 Node tests covered real TIVarsLib round-trips/migration,
storage/order/stop/timeouts, location verification and every transfer-object
hash. Real browser WASM initialized. The 238-file listing, matching/empty search
and overflow were checked at 1440, 1280 and 390 px. The Impeccable finish review
returned ship. Existing design direction is recorded in root DESIGN.md and
.impeccable; a new task should use that context rather than repeat discovery.

## Superseded approaches

- The oversized single-file transfer was rejected by TI Connect Evo; multiple
  files are authorized. Renaming files is not format conversion.
- The source-only build at 88a443b/run 38164295044 passed modern host tests but
  failed on the user's EVO. `cas-evo-v1.zip` is now only intermediate build input.
- Sending ordinary source companions to Archive is not the compiled-library
  installation. Sending all companions to RAM exhausted memory. Ship compiled
  archived libraries plus only the small RAM launchers.
- The original Cloudflare Pages Direct Upload job was replaced by generated
  branch publication. The current target is a Cloudflare Worker watching pages.
  No Cloudflare token needs to be copied into GitHub for this integration.

## Local reproduction notes

Canonical CI output directories are `dist/archive` and `dist/archive-transfer`.
Earlier native validation used `dist/archive-final` and
`dist/archive-final-transfer`; ignored logs included `dist/archive-final-32.log`
and `dist/archive-final-64.log`. Treat their availability as local, not guaranteed
in a fresh checkout. Never rebuild an output tree while another check uses it.

The previous native environment used WSL cachyos and `/tmp/cas-evo-mpy5-ti`.
MicroPython v1.12 needed `-DMICROPY_NLR_SETJMP=1` with modern GCC for correct
exception handling, and 32-bit Linux needed `-D_FILE_OFFSET_BITS=64` for stat on
the NTFS mount. The local 32-bit executable used a private
`/tmp/cas-evo-i686` loader/library path. These are host harness details, not changes
to the calculator bytecode ABI. Prefer the current workflow's reproducible build
commands; verify any historical local path before using it.

Optional read-only reference checkouts have lived at
`C:/Users/conner/.cache/cas-evo-ref`. They are algorithm/protocol references, not
deployment input. giac is an algorithm reference; its code is not shipped.

An earlier attempt to start an extra temporary local server was blocked by
automatic approval review. Existing-server and file-equivalence checks were
used instead. Do not claim that the blocked launch ran or retry it as a workaround.
