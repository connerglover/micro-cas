# cas-evo handover

Updated: 2026-10-11, UI milestone. Whoever is working on this rewrites this file at every milestone.

## What this is

cas-evo is a computer algebra system for the **TI-84 EVO**, written in the calculator's Python. It is a
spiritual port of [FlowCE](https://github.com/tommyb3ll/FlowCE), a giac-based CAS for the TI-84 Plus CE.
The EVO runs only Python, so the math is a new, small CAS. giac is only a reference for algorithms.

The owner is Conner. It's a personal project for GitHub with no licence yet. Don't ask him questions
while he's away; make the reasonable choice and record it.

## Read these first

1. `docs/DESIGN.md`: the authoritative spec. §0 is the one-screen summary, §21 the milestone and task
   tables, and the "Design review log" at the end records later changes.
2. `docs/notes/<TASK>.md`: one file per finished task. Each covers what was built, the API as
   implemented, deviations from the design, gaps, and requests to other tasks.
3. `docs/reference/`: research on device facts (`device-python.md`), algorithms (`algorithms.md`), and
   FlowCE's input and answer formats.

## Hard device constraints (measured on the real EVO)

- **About 10 nested Python calls in total.** Every call counts, not just recursion. So there is no
  recursion anywhere in `src/`: code uses explicit stacks, a generator trampoline and `#@L n` level
  annotations. The desktop depth checker in `tests/support/evodepth.py` enforces this in every test.
- Python reports 3.4.0 (MicroPython-like). No f-strings, `cmath`, `re`, `fractions` or `functools`.
  `eval`/`exec` work. One user module can import another. Module names are at most 8 uppercase
  letters (the bundler renames them).
- About 175 KB of heap. Code is lazy-loaded per command family; see DESIGN §18.
- Key codes are TI-BASIC `getKey` codes. 2nd and alpha arrive as separate keys.
- Drawing is done with `ti_graphics`.

## Settled scope

v1 is three milestones, each with a commit:
- **T1, exact core:** rationals, radicals, complex numbers, simplify, expand, factor, solve, Ans,
  variables, history.
- **T2, calculus:** derivatives, limits, integrals, Taylor series.
- **T3:** improper integrals, sums, Riemann sums, ODEs, gradients, multiple integrals,
  polar/parametric areas.

After those come the UI (1D editor, 2D answers, F1–F5 menus) and a bundle for the device. There is no
graphing in v1. DESIGN §2 and Appendix C list every default.

## How to work

- Branch `v1`. One commit per milestone (`T1: exact core`, ...); WIP commits are fine. End commit
  messages with the co-author line used in `git log`.
- Tests: `.venv\Scripts\python -m pytest -q -m "not slow"` from the repo root. The venv has pytest and
  sympy; recreate it with `python -m venv .venv` and `pip install pytest sympy`. Use
  `--strict-depth` for the strict frame budget.
- Each task in DESIGN §21 lists the files it owns. Write tests first. A task is done when its
  acceptance tests pass, the full suite is green, and lint and FRAMELINT are clean.
- Reference sources, read-only and never executed: FlowCE at `C:\Users\conner\.cache\cas-evo-ref\FlowCE`,
  giac at `C:\Users\conner\.cache\cas-evo-ref\ti-ce-giac`.
- The device gates (PROBE6, PRBMEM calibration, T1.15) are deferred until Conner runs the probes;
  until then use the provisional numbers. `probe/README.md` and `probe/README-MEM.md` tell him what to
  run.

## Status

| milestone | state |
|---|---|
| Design and M0 foundations | done; real-device calibration deferred |
| T1 exact core and integration (T1.1-T1.13) | complete, desktop verified |
| T1.14 bundle / full B.1 | underway with final v1 packaging |
| T2 calculus | complete, desktop verified; release integration underway |
| T3 | complete, bounded fallbacks documented and desktop verified |
| UI U.1-U.4 and CVTEST D.1 | implemented, desktop tested; packaging underway |

**Next step:** continue through ALL T2, T3, UI, and packaging without stopping at a milestone.
The user's explicit continuation instruction requires a downloadable complete v1 application.
Finish integration strategies, definite/improper integrals and ODEs; split every lazy compile
unit; implement the interface, phase-2 bundler and CVTEST; run source and bundled strict tests;
produce a single minified `CASEVO.py`, an automatic GitHub Actions build, and installation instructions. Commit at milestones and update this handover.
Do not claim actual EVO validation: the device probes remain deferred to Conner.

## This continuation (2026-10-11)

- Finished solver review and split into solve/solveb/solvec/solved/solvee:
  136/129/150/139/109 minified lines. Inverse templates moved to solvee; verification and
  numerical roots moved to solved. No forwarding frames were added.
- Split the normalizer into norm/normb/normc: 144/112/122 lines. Replaced size xfails with gates.
- Added T1 acceptance corpus, session integration, nested-command, hash-seed determinism,
  arena recovery and repeated-command tests. All 39 new/focused strict checks pass.
- Installed mpy-cross and ran the first real compiled-size estimate. The original resident
  budgets were too optimistic: five core modules estimate 111.8 KB at provisional factor1.8,
  before UI and working data. Final bundling must address this and publish measured estimates.
- Derivatives, Laurent/Taylor series, and limits now have dedicated strict acceptance tests.
  These and the other calculus files remain work in progress until the T2 commit.

## Verification

- Full tracked T1 non-slow strict suite: 2,078 passed, one failure in a previously dormant
  derivative-template test activated by T2's new diff module. Its allowed-name list omitted
  sign; fixed the test contract and reran both template oracle cases successfully.
- Normalizer, solver, factor, runner and build cross-family checks: 504 passed; one stale
  solver INV location assertion was updated and independently passed.
- The T1 compile-unit size assertions are now ordinary passing tests (no size xfails).
- Device-subset lint and FRAMELINT clean for the completed T1 changes.
- Real-device depth, heap calibration, graphics and transfer smoke remain unrun.

## Known limitations and release work

- Solver numerical search is bounded (-10 to 10 outside trig), not a completeness guarantee.
- Overall heap fit remains a release engineering concern. Splitting caps compile transients
  but does not lower total steady resident memory. Phase eviction and identifier shrinking
  are still required; do not silently increase the provisional 175 KB device heap.
- Pending agent-owned files are not part of the T1 milestone commit.

### T2 checkpoint

- Derivatives, Laurent/Taylor series, limits, table/substitution/tabular/rational/trig/radical/by-parts integration and primitive verification implemented. See `docs/notes/T2.md`.
- Focused T2/T3 calculus run: 467 strict-depth tests passed. Additional limit growth and quadrature review regressions passed independently.
- User now requires one minified `.py` file and automatic GitHub Actions artifacts. `build/release.py` is implementing compressed lazy exec namespaces, retaining the stricter measured Python heap budget.
- Continue through final v1 release; do not stop at this checkpoint.

### T3 checkpoint

- Added definite/improper integrals, bounded quadrature, mapped double-integral fallback, exact/symbolic/infinite sums, Riemann sums, gradients, nested/polar/parametric integrals and ODEs.
- Bernoulli ODEs support rational exponents, preserve implicit branches and verify zero equilibria.
- Review regressions prevent false limit growth, false sum divergence, missed narrow peaks and silently truncated primitive jumps.
- Focused definite/double-integral suite: 67 strict-depth tests passed; ODE suite: 59 passed. Full suite exposed stale factor test imports after deliberate calculus eviction; fixture now follows live loader instances.
- Single-file artifact is building; compressed release and final source/bundled tests remain in progress.

### UI checkpoint

- Calculator editor, history, 2D mathematical layout, F1 catalog, F2 recall, F3 settings, F4 forms and F5 contextual help implemented.
- Strict UI/menu/forms/layout suite: 65 passed. Boundary wrapping preserves input; empty calls retain editor; decimal views omit duplicate footer.
- Panic draws directly without the layout engine, preserving input, history and Ans. Single-file entry recovery is being validated separately with phases unloaded.
- CVTEST contains 55 device-engine acceptance commands plus bounded depth and math checks. Its source tests pass; physical execution remains deferred.

### Native Python compatibility checkpoint

- The actual single-file artifact runs on native 64-bit MicroPython 1.29 with a
  500,000-byte heap. Boot and `2+3=5` pass; this is not an EVO emulator.
- Native CVTEST exposed three unsupported stepped slices in node/factor/poly
  routines. Replaced them with explicit loops and added subset-lint regression
  checks. Node/lint: 213 strict tests passed; factor/poly: 159 passed.
- The full bundled desktop suite before these equivalent loop replacements
  passed 2,838 tests, 55 slow tests deselected. Final native/source checks continue.
- The release now reports a provisional 236,684-byte stage subtotal before
  runtime-data exclusions against the measured 173,360-byte Python heap. Do not
  describe this as hardware-ready or silently substitute the 500 KB total RAM.
