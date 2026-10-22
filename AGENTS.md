# Agent guide for cas-evo

This is the shared operating guide for coding agents in this repository.
`CLAUDE.md` points here; maintain instructions in this file only. Current user
instructions take precedence over repository defaults.

## Purpose and priorities

cas-evo is a Python computer algebra system for the **TI-84 EVO**. It provides
exact algebra, calculus, series, sums, differential equations, geometric
integrals, and a calculator editor with textbook-style answers. Preserve the
complete T1/T2/T3/UI feature set when fixing compatibility or memory problems.
Multiple calculator files are intentional and authorized. Graphing is outside
the current scope.

Prioritize mathematical correctness, device compatibility, bounded memory and
call depth, then usability. Desktop success alone is insufficient evidence of
calculator compatibility. Keep measured results, host tests, and hardware
acceptance clearly distinguished.

## Start a task

1. Read [docs/STATUS.md](docs/STATUS.md) for the last verified delivery, unresolved
   external checks, and superseded installation approaches. Refresh mutable
   facts such as branch heads, workflow status and deployment before relying on
   the recorded snapshot.
2. Inspect `git status --short --branch` and the relevant diff. Preserve user
   edits. Source work belongs on `main` or a feature branch based on it;
   `pages` is generated deployment output. Keep `v1` as historical work unless
   the user explicitly requests a different branch operation.
3. Follow the task-specific references below before changing the associated
   behavior. Read the implementation and its existing tests, identify a concrete
   acceptance condition, and make the smallest complete change that satisfies it.
4. Work autonomously on routine choices. Commit useful milestones and push
   completed work when requested; the established project preference is to
   finish and push rather than stop at a proposal. If account access or physical
   hardware is missing, complete independent work and state the exact remaining
   external step without claiming it succeeded.

## Read by task

| Task | Required context |
| --- | --- |
| Engine algorithms, representation, parser, UI architecture | Relevant sections of [docs/DESIGN.md](docs/DESIGN.md), then the affected module and its tests |
| Device syntax, builtins, stack limits, TI-specific assumptions | [docs/reference/device-python.md](docs/reference/device-python.md); retain its evidence tags |
| Loader, packs, minification, heap, bytecode, transfer formats | [docs/notes/FASTBOOT.md](docs/notes/FASTBOOT.md), [docs/notes/PACKAGING.md](docs/notes/PACKAGING.md), relevant `build/` code and the build workflow |
| Calculator installation or user-reported device failure | [docs/INSTALL.md](docs/INSTALL.md) and [docs/STATUS.md](docs/STATUS.md) |
| Website layout, copy, interaction or visual review | [PRODUCT.md](PRODUCT.md), root [DESIGN.md](DESIGN.md), and [.impeccable/surfaces/website-index-html.md](.impeccable/surfaces/website-index-html.md) |
| Browser transfer or package migration | `website/installer.js`, `website/transport.js`, `website/tests/installer.test.js`, vendor provenance and packaging notes |
| GitHub, branch publication, Cloudflare or domains | [docs/HOSTING.md](docs/HOSTING.md), `.github/workflows/build.yml`, `build/publish_site.py` and `build/cloudflare/` |

Root `DESIGN.md` describes the website design system; `docs/DESIGN.md` describes
the calculator engine. Earlier architecture estimates and milestone plans do not
override the implemented compiled loader, current packaging notes, or measured
device evidence. Historical `docs/notes/` files explain decisions, not unfinished
work to restart automatically.

## Repository map

| Location | Responsibility |
| --- | --- |
| `src/` | Device-compatible engine, parser, command registry, session and calculator UI |
| `shim/` | Desktop replacements for TI modules; not calculator deliverables |
| `probe/` | Small on-device experiments; their transcripts support device claims |
| `tests/` | Engine, UI, packaging and publication tests; `tests/support/` owns lint, depth and invariant checks |
| `build/` | Source transformation, compiled archive packaging, native smoke tests, website assembly and branch publication |
| `website/` | Browser installer source, tests, pinned WebTILP/TIVarsLib assets and fonts |
| `docs/` | Architecture, installation, deployment, status and implementation evidence |
| `dist/` | Ignored generated outputs and local validation artifacts; regenerate rather than hand-edit |

## Device and mathematics constraints

These constraints apply to calculator code and generated calculator modules.
Desktop build scripts can use the modern Python version pinned in CI.

- Target the verified **Python 3.4 subset**. Keep the device lint enabled and use
  only supported builtins/modules. The calculator imports a program to run it;
  an ordinary desktop `__main__` guard is not a device entry point.
- Device algorithms use explicit stacks and the generator trampoline, without
  recursive or mutually recursive calls. The strict desktop budget is **eight
  Python frames** against the measured device limit of ten. Preserve `#@L`
  annotations and account for hidden frames and native-import entry paths.
- Expressions are canonical interned tuple DAGs with integer child IDs.
  Preserve node ownership, canonical ordering, symbol masks and reset/recovery
  invariants. Session/history/variable values survive commands as text, not live
  node IDs. Node capacity grows on demand to the existing 768-node cap.
- Exact arithmetic stays exact; keep approximate evaluation and decimal
  presentation separate. Preserve branch assumptions, domain restrictions,
  deterministic output and formal unevaluated fallbacks. An exhausted search
  budget must not produce an unjustified answer.
- Bound searches, caches and temporary allocations. Keep cancellation responsive
  and leave the next command usable after failure. Test cleanup and recovery as
  well as successful answers when changing allocation or loading behavior.
- Storage and Python heap are different budgets. The reported 3.5 MB user
  storage and roughly 500 KB user RAM do not imply a 500 KB Python heap. PROBE3
  measured **185,296 bytes free at program start**; **173,360 bytes** were free
  after a probe imported `ti_plotlib`, `ti_graphics`, `ti_image` and more, which
  cas-evo does not import. Native tests use these values as total heaps, with a
  `ti_draw` stub rather than an EVO emulator; `build.yml` names the heap of each
  suite.
- Draw only through `ti_draw`, with the device semantics recorded in
  [docs/notes/FASTBOOT.md](docs/notes/FASTBOOT.md). `ti_graphics.setColor` takes
  one positional argument on the EVO, and the lint rejects `ti_graphics` in `src/`.
- UI modules (`ui`, `draw`, `menu`, `menub`) never import the engine (`node`,
  `alg`, `parse`, `printer`, `run`, families) at module level. `ui.engine()`
  binds it on first use; the UI must work with no engine loaded.
- Soft, view and aux packs are reached only through `__import__('PACK').name`
  and are never held in a global, alias or table; `build/packs.py` rejects code
  that would hold one. Evicted packs are cleared by `run.unload` with `EVDICT`
  (every global set to None). Deleting a module from `sys.modules` does not free
  memory by itself while a stale C-stack word still points at it.
- On MicroPython 1.12 a failed import leaves the half-run module in
  `sys.modules`. Remove it before retrying (`run.need`, `ui.engine`).

## Calculator build and installation contract

The user download is **`dist/cas-evo-calculator.zip`** (CI artifact
`cas-evo-v1`; on a GitHub Release `cas-evo-<tag>.zip`; the release version is
`build/manifest.py` `VERSION`, recorded in `release.json` and `archive.json`). Its format is **packs-v1**
([docs/notes/FASTBOOT.md](docs/notes/FASTBOOT.md)): **21 compiled `.8mp2`
packs for Archive** and the **`CAS.8xpy2` launcher for RAM**, 22 files. The
user runs CAS from the Python app (source `src/casevo.py`; `manifest.ENTRY`
names it, and no pack may share its name). `build/manifest.py` `PACKS` defines each pack and its kind (ui, core,
family, soft, view, aux); `PACKMAX` caps a pack's bytecode at 60,000 bytes. Read
`archive.json` for current sizes and update public instructions when the package
changes. CAS must reach its first
screen importing only the ui and view packs (CASUI, CASUX); each archive import
cost seconds on the EVO.

The build has distinct stages:

1. `build/release.py` runs `build/bundle.py` (minified device modules in
   `dist/device`), `packs.merge` (`build/packs.py`: modules into packs, function
   placement, renames, lazy aliases) and `build/shrink.py` (identifier
   shortening). It writes the loader tables into the run pack, checks pack sizes
   with mpy-cross, and outputs the pack sources, the launcher, `release.json`,
   `SHA256SUMS`, `INSTALL.md` and the intermediate `dist/cas-evo-packs.zip`.
   It also writes the developer diagnostic probe `dist/dev/CVTEST.py` (shrunk
   with the same mapping, recorded under `release.json` `devtools`) for the
   native CI checks; it never ships to the calculator.
   That ZIP is build input, not the calculator download. The packer raises
   instead of emitting a pack it cannot prove correct; do not bypass it.
2. `build/archive.py` compiles the packs with the pinned MicroPython v1.12
   `mpy-cross` and validates the **MPY v5.3 / 31-bit-small-int ABI**, header
   `4d05031f`, and `PACKMAX`. The launcher stays source. The exact revision and
   native build flags live in the workflow and compiler script. A newer
   `mpy-cross` is not interchangeable with the EVO compiler. The calculator
   never compiles engine source.
3. `build/package_archive.mjs` creates real EVO containers with pinned TIVarsLib
   and round-trips every name, type and payload. `build/archive_zip.py` verifies
   and packages the final transfer objects.

Ordinary archived `.py` files are not substitutes for compiled libraries.
Renaming `.py`/`.mpy` files does not convert their format. Preserve the recorded
hashes the installer uses to recognize earlier files (`archive.json` source
hashes, `website/legacy-*.json`) and never mix files from different releases.
Avoid rebuilding an output directory while another test or server depends on its
current bytes.

## Development and validation

Use the repository virtual environment and `requirements-dev.txt`. Locally on
Windows its interpreter is `.venv/Scripts/python`; on Linux it is
`.venv/bin/python`. The following commands assume the intended environment is
active. Python/compiler/runtime versions and Linux build commands in
`.github/workflows/build.yml` are the reproducible reference.

```text
python -m pip install -r requirements-dev.txt
python tests/support/lint.py src
python tests/support/framelint.py
python -m pytest -q -m "not slow" --strict-depth
python build/release.py
python build/transfer.py dist/CAS.py dist/dev/CVTEST.py
python -m pytest -q -m "not slow" --strict-depth --bundled
```

After building the pinned EVO compiler/runtime, continue with:

```text
python build/archive.py --mpy-cross <pinned-v1.12-mpy-cross>
python -m pytest -q tests/test_archive_release.py --strict-depth
python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run <v1.12-cas32> --heap 95000 --suite startup
python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run <v1.12-cas32> --heap 173360 --suite ui
python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run <v1.12-cas32> --heap 173360 --suite ui_edit
python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run <v1.12-cas32> --heap 189776 --suite ui_calculus
python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run <v1.12-cas32> --heap 185680 --suite ui_calculus
python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run <v1.12-cas32> --heap 212000 --suite probe
python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run <v1.12-cas64> --heap 500000
node build/package_archive.mjs
python build/archive_zip.py
node --test website/tests/*.test.js
python build/website.py
python build/check_pages.py dist/website
```

The 32-bit heaps follow the device measurements: 173,360 bytes were free after
a probe imported several `ti_*` modules, and 189,776 is PROBE3's 185,296 bytes
free at program start plus the 4,480 bytes the harness uses; `ui_calculus` also
runs 4,096 bytes below it, because native heap layout varies with the run's path
and a pass at exactly the nominal heap can be luck. `ui_edit` types long 2D lines
after a result. The 64-bit run uses the default `all` suite (UI, UI calculus, UI
edit and the 55 diagnostics of the developer probe `dist/dev/CVTEST.py`, which
the `startup` and `probe` suites also run). FASTBOOT.md
records why packs need more heap than v1 for the heaviest definite integrals.

Use targeted tests during iteration, then the checks appropriate to the final
change. Do not weaken depth, mathematical invariants or memory gates to make a
failure disappear.

| Changed behavior | Acceptance evidence |
| --- | --- |
| Mathematics/parser/printing | Affected regression/corpus tests, round-trips where applicable, device lint, strict depth and source acceptance |
| Calculator UI/session | Scripted-key and recovery tests, preserved session semantics, source and bundled acceptance |
| Loader/compiler/packs/memory | Source and bundled acceptance, `build/check_release.py` and `tests/test_archive_release.py` (UI-only boot, eviction, failed-import recovery, depth), and actual MPY v5 native checks at every `build.yml` heap |
| Transfer/installer | Rebuilt package, real TIVarsLib round-trips, Node installer tests, browser behavior and package integrity |
| Website presentation | Relevant browser states and responsive/accessibility checks using the existing design direction |
| Branch publisher/workflow | `tests/test_publish_site.py`, `tests/test_workflow.py`, workflow lint (YAML load or actionlint), Worker dry run, and observed Release upload and publication from a successful `v*` tag run |
| Instructions/documentation only | Paths, links, command accuracy, stale-reference scan and `git diff --check`; no unrelated engine retest |

The normal acceptance command excludes the `slow` marker. Run relevant slow
oracle cases for changed algorithms and report the distinction. CVTEST's 55
diagnostics (a CI-only native suite, no longer shipped) are a separate suite,
not those excluded slow tests.
Artifact-dependent skips before packaging do not establish artifact acceptance.

## Browser installer and asset integrity

- Keep the site static and self-contained. Calculator communication runs in the
  user's browser with explicit device permission; no account, backend upload or
  telemetry is required for installation. Desktop Chrome/Edge are the target.
- Validate all transfer-object hashes before device access. Install compiled
  libraries to Archive before the RAM launcher, then verify their types/locations.
  Delete or replace an earlier cas-evo file only when its decoded contents match
  a recorded release (`website/legacy-*.json`, built by `build/legacy_manifest.mjs`
  from the published v1 and packs-v1 packages and the delivered MathPrint test
  ZIPs) or the current package. Keep and
  list modified or unreadable files, and leave unrelated calculator content alone.
- Serialize native transport calls. Stop waits for an active transfer to finish.
  A timed-out Asyncify/WASM instance is retired rather than reused; JavaScript
  cannot safely cancel its native operation. WebTILP `init()` returning 1 is
  valid reference-count behavior, not an error code.
- `website/vendor/assets.lock.json` and vendor provenance pin runtime bytes.
  Treat upstream assets as vendored code: preserve hashes or intentionally
  update pins, corresponding-source archives, licenses and tests together.
- Serve `_headers` with the built site for cross-origin isolation and Serial/USB
  permissions. Verify WASM initialization and `crossOriginIsolated` when changing
  hosting. Retain source ZIPs and font licenses in the published assets.
- Preview locally with `python build/serve_website.py` after building. Prefer an
  existing server when it serves the correct bytes. Product briefs, design
  reviews, agent instructions and repository credentials are not website assets.

## Branches, commits and Cloudflare

`main` owns source. The build workflow runs only for pushed `v*` tags, GitHub
Releases published for `v*` tags and manual dispatch, not for ordinary pushes or pull requests, so
run the local acceptance commands before committing. A successful tag run
attaches `cas-evo-<tag>.zip` to the tag's GitHub Release (creating it if
missing) and updates `pages` with the exact `cas-evo-web-installer` artifact;
only those two jobs get contents-write permission from the built-in token, and a
Release created by that token starts no run. The publisher requires the tag to
still name the built commit and never replaces a newer release on pages.
Create a release tag only when the user asks for one. `build/cloudflare/`
supplies its Worker configuration; `public/` is the only served directory.
`pages/deployment.json` records the source commit, ref and run. Edit
source/templates on main, not generated files on pages. Keep the independent
deployment history; use normal pushes.

Cloudflare is a **Worker connected to the `pages` Git branch**, not the previous
Pages Direct Upload setup. Use [docs/HOSTING.md](docs/HOSTING.md) for dashboard
settings, custom-domain setup and verification. Keep the repository private.
Routine publication uses GitHub's built-in token; the removed Cloudflare API
secret/account-variable flow is not needed. User-managed dashboard connection,
DNS/TLS and physical USB success must be verified separately.

Write concise intent-based commit messages. Preserve the established footer:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Commit milestones and inspect tag-run outcomes. Avoid creating a PR unless
requested. Keep generated build outputs on pages, in Actions artifacts or on
Releases, out of main. `docs/INSTALL.md` ships in the calculator ZIP, so a
change to it needs a new release tag to reach users.

## Finish a task

1. Verify the requested behavior with the relevant checks and inspect the final
   diff for unintended files, weakened gates or exposed private material.
2. Record changed validation evidence, delivery state and genuine remaining work
   in [docs/STATUS.md](docs/STATUS.md). Update this guide only when enduring
   workflow/constraints change, and keep `CLAUDE.md` a one-line pointer.
3. Commit and push within the user's authorized scope. For publication changes,
   check both source and generated remote branches and compare published files
   with the tested artifact. Keep older valid deployments when checks fail.
4. Report what changed, what passed, the relevant commit/build, and any external
   step still unverified. Hardware acceptance means an actual EVO run; native
   tests, estimates and a successful website build cannot substitute for it.
