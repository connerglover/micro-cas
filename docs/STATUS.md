# Delivery status and evidence

Last reviewed: 2026-10-22. Repository: connerglover/cas-evo (private).
Use [AGENTS.md](../AGENTS.md) for operating instructions. This file records a
dated snapshot; verify remote heads, build results and hosting before reporting
them as current.

## Current delivery

- **v1.0.0 accepted on the user's EVO (user report, 2026-10-22).** The user merged
  `mathprint` into `main`, tagged `v1.0.0` and reported that it works on their TI-84 EVO,
  F-key row included. The remote tag `v1.0.0` is annotated and names 22b0464 (the F-key row
  and its review fixes; `origin/main` and `origin/mathprint` are the same commit); this
  clone's local `v1.0.0` tag still names 8bb69b5 and was left alone. No device timings or
  transcripts were recorded.
- **v1.0.1 in progress on `mathprint` (local, not pushed or tagged; 2026-10-22).** User
  requests: CLEAR on a highlighted history cell deletes that entry, input and answer,
  selects the older one (the newer one when the oldest went) and returns to the edit line
  when the history is empty; Ans and variables stay (MATHPRINT.md §0.14). Every text the
  calculator shows was re-read for the current UI (§0.15): `Press math` on the empty page,
  capitalized status texts and engine messages, help tips that match the F-key row (quit is
  2nd MODE), `Order (empty: 1)`-style argument help, shorter catalog explanations. Version
  1.0.1 (`build/manifest.py`, About, INSTALL.md, `release.json`/`archive.json`). The code
  was minimized with the same methods and results (UI: shared state read once, menu keys
  through `ui.kmap`; core: one-character token table, merged comma and sign rules; families:
  repeated pure calls and dead branches removed, the test-only `polyb.bezout` and
  `polyc.mrel` dropped), and the line/KB budgets of the touched modules lowered.
  **Host and native evidence** (not hardware): lint, framelint, the not-slow suite with
  `--strict-depth -n 6` in source and bundled tiers (4,313 passed; four bezout/mrel unit
  tests went with them), the slow suite of the touched engine modules (65 passed),
  `build/release.py`, `build/archive.py` with the pinned v1.12 `mpy-cross`,
  `tests/test_archive_release.py`, and every native heap of `build.yml` on cas32/cas64
  (startup 95,000; ui and ui_edit 173,360; ui_calculus 189,776 and 185,680; probe 212,000
  at 55/55; cas64 500,000 at 55/55). Compiled v1.0.0 → v1.0.1: CASUX 31,218 → 30,884 B,
  CASUI 3,490 → 3,486 B, CASMNU 8,732 → 8,511 B, CASALG 19,817 → 19,076 B, CASPR 12,173 →
  11,925 B, archive 206,030 → 203,960 B; native cas32 result heap after shedding `ui`
  58,976 B, `ui_edit` 56,016 B, `ui_calculus` (185,680) 69,232 B; T1-T3 corpus CPU time
  unchanged (19.65 s v1.0.0, 19.39 s v1.0.1, three interleaved rounds).
  `package_archive.mjs`, `archive_zip.py`, the Node installer tests and the website build
  were not rerun. **Pending:** an EVO run of
  v1.0.1, and the user's merge and `v1.0.1` tag to deliver it (INSTALL.md ships in the ZIP).
- **Hardware acceptance (user report, 2026-10-22).** The user ran the MathPrint
  test builds on their TI-84 EVO and reported that they work (the latest build
  delivered before this report was `cas-evo-678d16d.zip`: launcher CAS, no
  CVTEST, Nspire names, argument boxes and the argument help row). This is the
  first actual EVO acceptance of the MathPrint editor; no device timings or
  transcripts were recorded.
- **Release v1.0.0 on `mathprint` (tag `v1.0.0`; 2026-10-22).** User requests: the theme function is gone (one light palette,
  no F3 row, `R.SET = {'deg': 0}`); MathPrint is the only entry (the Classic
  setting and its code paths are removed; the internal 1D fallback for
  over-cap/out-of-memory lines and after a panic stays); the answer's form label
  (`exact`, `decimal`, ...) moved from the footer (`exact  F4`) to the top right
  of the status row, left of the modifier chip, hidden while a status message
  needs the room; the empty page reads `Press math or menu`; F2 (tab `hist`)
  and up scroll the history instead of opening the recall menu (VARS keeps Ans,
  variables and functions), with TI-Nspire cell selection: up/down between
  entries, left the input, right the answer (a wide answer scrolls first), the
  band behind that cell only, ENTER copies the cell into the edit line
  (MATHPRINT.md §0.12). The workflow now runs only for `v*` tags, published
  Releases and manual dispatch, attaches `cas-evo-<tag>.zip` to the tag's
  Release (creating it if needed) and publishes the website from tags only
  (HOSTING.md); `release.json` and `archive.json` record `release: 1.0.0`.
  **Host and native evidence** (not hardware): lint, framelint, the not-slow
  suite in source and bundled tiers (4,268 passed each), `build/release.py`,
  `build/transfer.py`, `build/archive.py` with the pinned v1.12 `mpy-cross`,
  `tests/test_archive_release.py`, `build/package_archive.mjs`,
  `build/archive_zip.py`, checksums, `node --test website/tests/*.test.js`
  (31 passed), the workflow YAML loads, and every native heap of `build.yml`
  passes on cas32/cas64. Compiled sizes: CASUX 31,480 → 30,998 B, CASUI
  3,794 → 3,515 B, CASMNU 9,068 → 8,696 B, archive 206,945 → 205,799 B; native
  cas32 `ui` boot heap 120,416 → 121,104 B free and result 31,920 → 32,528 B,
  `ui_calculus` (189,776) result 45,872 → 46,816 B. `build/website.py` could not
  download the WebTILP source archive in this sandbox (HTTP 403), so the website
  assembly and `check_pages.py` ran only in earlier CI. **Pending:** the first tag
  run (Release upload and pages publication have not been observed; the account
  was out of Actions minutes) and an EVO run of the changes made after the
  accepted 678d16d build (status-row form label, history selection and copy,
  theme and Classic removal).
- **v1.0.0 F-key row (on `mathprint` after the `v1.0.0` tag; 2026-10-22).** The
  user's approved design (MATHPRINT.md §0.13): the plain row reads `Alg Calc Trig
  More Forms` (F1-F4 open the menu on the Algebra, Calculus, Trig and More tabs;
  F5 cycles the focused or selected answer's forms, as < >, and does nothing
  without an answer); while the 2nd chip is lit it reads `All Tmpl Test Setup
  Help` (All tab, template picker, TEST picker, Setup, help for the command at
  the caret), repainted only when the layer changes. MATH opens the tab used
  last (Algebra at first, tabs switched inside the menu count); 2nd MATH, VARS,
  MODE and 2nd 0 are unchanged. The `hist` tab is gone: up scrolls the history,
  CLEAR or down past the newest entry leaves it. INSTALL.md (which ships in the
  ZIP), DESIGN.md §16, notes/UI.md and MATHPRINT.md are updated. **Host and
  native evidence** (not hardware): lint, framelint, the new
  `tests/test_fkeys.py`, the not-slow suite in source and bundled tiers (4,299
  passed bundled; source 4,298 plus the host-timing guard
  `test_dense_line_host_time_guard`, which failed once under `-n 6` load and
  passes alone), `build/release.py`, `build/transfer.py`, `build/archive.py`
  with the v1.12 `mpy-cross`, and every cas32/cas64 native heap of `build.yml`.
  Estimates CASUX ~29,031 → ~29,218 B, CASUI ~3,417 → ~3,388 B; compiled
  CASUX 30,998 → 31,218 B, CASUI 3,515 → 3,490 B, CASMNU 8,696 → 8,732 B,
  archive 205,799 → 206,030 B; native cas32 `ui` boot heap 121,104 → 120,848 B
  free, result after shedding 59,136 → 58,208 B, `ui_calculus` (185,680) 69,184
  → 68,464 B, `ui_edit` 55,968 → 55,376 B. **Pending:** an EVO run of the
  F-key row, and a new release tag to deliver it (and the updated INSTALL.md)
  to users; nothing is pushed or tagged.
- **packs-v1 is merged into local `main`**: `perf/fast-boot` was fast-forwarded
  from 177779f through the verified fixes at **1e06608**, as requested on
  2026-10-12. It is not pushed and CI has not run on it. Remote main remains
  177779f; pages still publishes source commit 25b83b0 until main is pushed
  and CI passes. The merge changed no tested source bytes;
  see [v1 delivery](#v1-delivery-published-superseded) below.
- **MathPrint branch `mathprint` (local, not pushed; 2026-10-20).** The 2D
  editor ([notes/MATHPRINT.md](notes/MATHPRINT.md)) grew CASUX from 11.6 KB to
  34.8 KB of bytecode. The shrink review (MATHPRINT.md §0.9) brings it to
  29.3 KB (native import heap 41.8 KB to 34.6 KB) without dropping a feature:
  native cas32 `ui` result-screen heap 26,960 to 34,320 B free (54,016 before
  MathPrint), boot 115.5 KB to 123.0 KB (142.4 KB before), `ui_calculus` passing
  from 179,632 B, `ui_edit` from 166,384 B; every CI heap passes. Harness
  evidence only; no EVO run of the MathPrint build yet. The empty page no
  longer shows the "cas-evo" title and tagline.
- **QPL changes on `mathprint` (local, not pushed; 2026-10-21).** Q1: the
  diagnostic CVTEST no longer ships (it took 5.5 KB of calculator RAM); the
  package is 21 packs plus one launcher, 22 files, and CVTEST is built to
  `dist/dev/` for the native CI suites only. Q2: the launcher is `CAS` (was
  CASEVO). The installer now records packs-v1 and the two delivered MathPrint
  test ZIPs (`website/legacy-*.json`), so it upgrades their packs and removes
  their CASEVO/CVTEST on an exact match instead of stopping. Q3: menus,
  catalog, find, help and the template picker use the Nspire's command names.
  Q4: every empty argument of a plain call is a box. Q5: the hint row explains
  the argument at the caret and whether it is required (MATHPRINT.md §0.11).
  CASUX 29,736 → 31,480 B, CASUI 3,777 → 3,794 B, CASMNU 9,039 → 9,068 B;
  native cas32 `ui` boot heap 122,576 → 120,560 B and result 34,000 → 32,064 B
  free; every CI heap passes (startup, ui, ui_edit, ui_calculus at 189,776 and
  185,680, the 55-case probe at 212,000, cas64). Harness evidence only.
- **Device report on v1, 2026-10-11.** The v1 package (236 archived libraries
  plus two RAM launchers) took **5 min 30 s** on the user's EVO and then failed
  with `TypeError: function takes 1 positional arguments but 3 were given` at
  line 64 of `CVP00051.py`, `G.setColor(*COLORS['BG'])`, the first drawing call
  of `ui.boot`. `ti_graphics.setColor` takes one positional argument on the EVO.
  Boot needed 51 archive imports (about 6.5 s each if the reported boot time is
  amortized across them; individual device imports were not timed), and
  function pages evicted each other, so alternating calls re-imported them
  continuously. The analysis is in [notes/FASTBOOT.md](notes/FASTBOOT.md).
- **What changed.** The UI draws only through `ti_draw` with the semantics
  CalcPlex documents from the device, and the lint rejects `ti_graphics` in
  `src/`. CASEVO imports only the UI and draws its first screen after two archive
  imports (CASUI, CASUX); the engine loads on the first ENTER, or a menu that
  needs it, with boot and engine load times in the status line. Device modules
  are merged into **21 packs** (ui, core, family, soft, view and aux kinds;
  `build/manifest.py` `PACKS`) plus the two launchers: 23 files, largest pack
  22,121 bytes compiled; the archive holds 191,697 bytes in all. Identifier
  shrinking works across packs. Phase payloads, function pages and namespace
  initializers are gone (`build/phases.py`, `build/function_pages.py`,
  `build/archive_modules.py`, `build/memory_report.py`, `build/check_archive.py`
  and their tests were removed). The loader evicts whole packs, clears evicted packs (`EVDICT`),
  removes half-run modules after a failed import and retries after MemoryError.
  The browser installer removes v1 files whose contents exactly match the
  recorded release (`website/legacy-v1.json`). The T1/T2/T3 and UI feature set
  is unchanged.
- **Giant exact powers** (from CalcPlex's design: keep giant powers as powers
  instead of freezing). `3^(2^20)` gives `3^1048576` and `2^100000*2` gives
  `2^100001` at once, where v1 said "number too large". The code is the aux pack
  CASBIG, loaded only when a command meets a giant power. The final review
  preserves ordinary folded integers and rejects unsupported giant algebra
  before it can produce false nonzero tests or roots. Denominators are no longer
  factored in a number kernel or past
  degree 64, which had made `1/(2^100000+1)` (and, before this work,
  `1/(x^2000+1)`) run for minutes without a cancel check.
- **CI gates** (`.github/workflows/build.yml`), all on the compiled packs with
  native MicroPython v1.12: startup at 95,000 bytes (32-bit, `startup`), UI
  arithmetic at 173,360 (`ui`), the UI calculus session at 189,776
  (`ui_calculus`), the 55 diagnostics at 212,000 (`probe`), and the UI,
  calculus and diagnostic suites at 500,000 bytes on 64-bit. v1 ran all three
  32-bit suites at 173,360. That figure was the free heap after a probe imported
  `ti_plotlib`, `ti_graphics`, `ti_image` and more, which CASEVO does not
  import; PROBE3 measured **185,296 bytes free at program start**, and 189,776
  is that plus the 4,480 bytes the harness uses. The 55 diagnostics run at
  212,000 because one long session fragments the heap (below).

The historical table below records the initial 2026-10-11 build. Final reviewed
results follow it; do not use the older free-heap figures as current evidence.
The measured results come from a 32-bit **MicroPython v1.12 harness (unix
port compiled to wasm32)**, which reproduces CI's recorded v1 CVTEST free heap
(66,768 versus 66,704 bytes). They are harness measurements, not device
acceptance. The original UI arithmetic script had a stale plus-key code; its
result is superseded by the corrected `2+3=5` check in the final review.

| check | v1 | packs-v1 |
| --- | --- | --- |
| archive imports to the first key | 51 | 2 (CASUI, CASUX) |
| imports, first `2+3` after boot | 25 | 4 |
| imports, 7 UI calculus cases (5 definite integrals) | 2,806 (host count) | 29 (host count); 43 at 212,000 B, 51 at 196,000 |
| imports, 10 light commands | - | 24 at 185,296 B, 34 at 173,360 |
| files on the calculator | 238 | 23 |
| startup on a 95,000-byte heap | 13,520 B free | 16,912 B free |
| `2+3` UI session, 173,360-byte heap | pass | pass |
| 7 UI calculus cases, 173,360 | pass | fail (definite integrals: Out of memory) |
| 7 UI calculus cases, 189,776 | pass | pass, under 2 KB to spare |
| CVTEST 55 cases, 173,360 | 55/55 | 40/55 |
| CVTEST 55 cases, 189,776 | 55/55 | 53/55 |
| CVTEST 55 cases, 196,000 / 204,000 / 212,000 | 55/55 | 54/55 / 55/55 / 55/55 |

**Known limitation.** Packs keep whole families and the full core resident, so
the heaviest definite integrals need roughly 15-40 KB more heap than v1 and sit
near the measured device limit. Long CVTEST sessions end in a fragmented heap:
at the failures 25 KB was free but the largest free run was under 1.2 KB. Only
EVO runs can show whether these cases fit on the calculator.

- Cloudflare and hosting are unchanged from the v1 delivery. Cloudflare
  dashboard connection, a live Worker, DNS and HTTPS at
  **cas.connerglover.com** have not been verified; use [HOSTING.md](HOSTING.md).

### Final review, 2026-10-12

- **Acceptance:** 3,138 source tests and 3,138 bundled tests pass with
  `-m 'not slow' --strict-depth`, including the archive compiler-input tests;
  each run deselects 65 slow cases and has no artifact-dependent skips. The
  154 focused checks also pass, including ten slow giant-power oracle seeds.
  Device lint, frame lint, packaged self-test (8/8 depth), Markdown link targets
  and `git diff --check` pass. Local CPython is 3.15.0; CI's pinned 3.14 run
  remains pending publication.
- Failed integration strategies now remain cached until memory is needed, while
  releasing their generator pins. Host packed-engine imports for
  `integrate(sin(x)^21,x)` fell from 703 to 10, and for the power-25 case from
  1,664 to 9, with the same results. Explicit phase eviction is retained.
- Exact finite sums poll CLEAR each term and keep a formal `sum(...)` or
  `riemann(...)` when the accumulator exceeds about 13,200 bits. No implicit
  floating-point replacement is made. Giant-power regressions cover cancellation,
  false roots, infinity, ordinary large integer preservation and complex bases.
  A 2,422-case comparison against main found no result text/kind differences
  except cases where main already returned `number too large` (67 cases).
- The corrected native smoke script types the EVO plus key (85), verifies the
  expected answer, requires the correct suite completion marker and rejects
  tracebacks even if the runtime returns exit status zero.
- Final pinned MPY v5.3 bytes pass startup at **95,000 B** (16,192 B free),
  UI arithmetic at **173,360 B**, seven UI calculus commands at **189,776 B**,
  and **55/55 diagnostics at 212,000 B** on the 32-bit wasm unix harness.
  The native 64-bit **500,000 B** run passes all three suites, including 55/55.
  Workflow budgets are unchanged. At the extra 189,776 B diagnostic stress
  budget, **54/55** pass: case 35's heavy definite integral runs out of memory
  in the long session. This limitation remains; these runs are not EVO acceptance.
- A 750-key recovery session passes at the measured 185,296 B start heap and
  the tested heaps from 155,500 to 196,000 B. Lower-heap instrumentation failures
  are recorded in [FASTBOOT.md](notes/FASTBOOT.md#final-review-2026-10-12).
- **Local deliverable:** `dist/cas-evo-calculator.zip`, **133,020 bytes**;
  SHA-256 `9726c531537f724064a50209750e8e56984d6d931c1a3f115d869dd60c684e1d`.
  It contains 23 transfer files totalling **194,120 container bytes**; raw
  bytecode/source is **191,697 bytes**, including **6,045 launcher source bytes**.
  TIVarsLib round-trips and all transfer hashes pass, and the compiled bytes
  match the native-tested snapshot. The bundled installation guide reflects
  the reviewed memory result.
- **Installer:** 25 Node tests pass; the rebuilt 29-file site passes static
  integrity checks. Real browser checks verified 23 files, hash validation,
  `crossOriginIsolated`, WebTILP WASM initialization (`init() == 1`), matching
  and empty file filters, and no overflow at 1280/390 px. USB was not attempted.
- **Publication:** the GitHub connector confirms remote main at **177779f** and
  pages still records source **25b83b0**, run **38174533070**. Normal Git fetch
  cannot authenticate (`could not read Username for 'https://github.com'`).
  Connector read access works; this is a local Git credential limitation, not
  a claim that all account access is absent. No source or deployment branch has
  been replaced through the API. Local main now includes the verified feature
  branch; only this delivery record changes after 1e06608.

## Remaining acceptance

1. Restore local Git authentication, push `main`, and confirm the full build
   and publication runs pass. Record the run, the calculator ZIP SHA-256 and
   the pages commit here. The requested local merge is complete.
2. On the physical EVO:
   - Install through the web installer, which removes exact-match files of a
     recorded earlier release (v1, packs-v1, the MathPrint test builds) and
     lists any it keeps. Record the installer's summary.
   - Run CAS. Note the boot time in the status line (`ready` and seconds).
     Type `2+3` and press ENTER: the status line shows `Loading engine...`, then
     the answer `5` with `engine` and the engine load time. Then try a definite
     integral such as `integrate(1/(2+cos(x)),x,0,2*pi)` (expected
     `2*sqrt(3)*pi/3`) and note whether it answers or reports Out of memory.
   - Open F3 > About and report the free heap (the diagnostic CVTEST no longer
     ships; its 55 cases run in CI on native MicroPython).
   - Record the OS version and, for any failure, the complete traceback.
     `python build/linemap.py --map dist/release.json --tb FILE`, run on a build
     of the same commit, maps pack lines to source. A native host check is not
     an emulator.
3. Connect Cloudflare Worker cas-evo to the generated pages branch, deploy, attach
   the custom domain, and verify HTTPS, isolation headers, package downloads and
   WASM initialization. Repository visibility remains private.

The device numbers decide the next memory work: the cost of one archive import
(fixed, or growing with the number of files) and the free heap at CAS start.
Do not reopen finished feature milestones without a new defect or request.
Address device feedback while preserving the complete v1 feature set.

## v1 delivery (published, superseded)

These facts describe the v1 package that main and pages still publish. They
remain evidence for the installer, publication and v1 bytes, not for packs-v1.

- T1/T2/T3 and calculator UI features are implemented. The v1 compiled loader
  addressed the reported startup `MemoryError: phase compile memory` in CASEVO
  and CVTEST.
- The v1 calculator download `cas-evo-calculator.zip` held 236 compiled `.8mp2`
  libraries for Archive (phase payloads `CVP*`, function pages `CVF*` and engine
  modules `CV*`) and two `.8xpy2` launchers for RAM. Its transfer objects
  totalled 266,520 bytes; launcher sources totalled 6,760 bytes.
- The web installer is implemented and tested locally. Its download includes
  the full calculator package, WASM, fonts, licenses, corresponding-source ZIPs,
  and a local Python server.
- `v1` was fast-forward merged into `main` at **25b83b0**. Both were pushed; main
  remains the default source branch and v1 is retained. The generated **pages**
  branch is intended for a Cloudflare Worker connected through GitHub.
- Main verification/publication run:
  https://github.com/connerglover/cas-evo/actions/runs/38174533070.
  **Both build and publication passed.** It created pages commit
  **2849055909cabe6137bcdda0ada89b579628da11**, with source commit
  25b83b0eb8cf4a90b9ba0ee0c734cae55b47247b recorded in deployment.json.

### Verified evidence (v1)

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
  failed on the user's EVO. `cas-evo-v1.zip` became v1's intermediate build
  input; packs-v1 uses `cas-evo-packs.zip` instead.
- Sending ordinary source companions to Archive is not the compiled-library
  installation. Sending all companions to RAM exhausted memory. Ship compiled
  archived libraries plus only the small RAM launchers.
- The v1 archive design (236 compiled libraries: phase payloads `CVP*`, function
  pages `CVF*`, engine modules `CV*` with namespace-dictionary initializers, and
  admission by phase) fitted the 173,360-byte native gates but booted in 5 min
  30 s on the EVO and crashed in `ti_graphics.setColor`. packs-v1 replaces it;
  see [notes/FASTBOOT.md](notes/FASTBOOT.md).
- The original Cloudflare Pages Direct Upload job was replaced by generated
  branch publication. The current target is a Cloudflare Worker watching pages.
  No Cloudflare token needs to be copied into GitHub for this integration.

## Local reproduction notes

Canonical CI output directories are `dist/archive`, `dist/archive-smoke` and
`dist/archive-transfer`.
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

The packs-v1 32-bit measurements used a local MicroPython v1.12 unix port
compiled to wasm32 with emscripten (Asyncify register scanning for the GC) under
`/tmp/cas-evo-mp/evo32` on the macOS host, and a native 64-bit build under
`/tmp/cas-evo-mp/evo`. Both are local and temporary; CI's gcc builds are the
reference.

Optional read-only reference checkouts have lived at
`C:/Users/conner/.cache/cas-evo-ref`. They are algorithm/protocol references, not
deployment input. giac is an algorithm reference; its code is not shipped.

An earlier attempt to start an extra temporary local server was blocked by
automatic approval review. Existing-server and file-equivalence checks were
used instead. Do not claim that the blocked launch ran or retry it as a workaround.
