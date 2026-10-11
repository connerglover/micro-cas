# cas-evo handover

Updated: 2026-10-11 00:52 CDT. Whoever is working on this rewrites this file at every milestone.

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
| Design | done (commit 4ee35da) |
| M0 foundations (M0.1-M0.5) | done |
| T1.1 node, T1.2 poly, T1.3 tokens, T1.4 dec10, T1.5 builders, T1.8 alg | done (commits cdcfeab, 1e6d423) |
| T1.6 runner, T1.7 printer, T1.9 rules, T1.10 norm | done; included in this continuation checkpoint |
| T1.11 factor | done; four parts fit LAZYMAX, strict acceptance tests pass |
| T1.12 solve | inherited implementation checkpointed; 116 strict tests pass; completion review and part split pending (see notes) |
| T1.13 integration, T1 review and fixes, T1.14 bundle-lite | todo |
| UI (U.1-U.4), full bundler (B.1), CVTEST (D.1) | todo (planned right after T1, so Conner can test on the device) |
| T2 (T2.1-T2.8) | todo |
| T3 (T3.1-T3.8) | todo |

**Next step:** run `git status`, then read `docs/notes/T1.11.md` and the new
`docs/notes/T1.12.md` checkpoint note. Finish **T1.12 Solve**, following DESIGN section 21.4:
review the existing implementation against section 11.2, split its oversized compile units,
finish its API/deviation notes, and run the full strict suite. Then proceed to T1.13's corpus,
nesting, determinism and memory integration tests. Do not mark the full T1 milestone complete
before T1.13 passes.

## This continuation (2026-10-11)

- Preserved and checkpointed the inherited uncommitted runner, printer, rule engine, normalizer,
  factor and solver work. The solver was further along than the original status table said.
- Fixed the stale PRBMEM dry-run test. It now checks both the real generated probe modules and
  an intentionally missing-module case, retaining the fallback coverage.
- Finished the factoring task's compile-unit split: `factor/factorb/factorc/factord` have
  **131/121/129/134 minified lines** (515 total), all below provisional `LAZYMAX = 150`.
  Updated loader, manifest, lint and FRAMELINT maps together. The family still loads/evicts as
  a unit, with no added wrapper frames. `factc.g_mfac` and `factd.nroots` are the new helper
  locations; `factb` still owns the search budgets and `FACTBUG`.
- Factored fractions print with a denominator: `factor(360/7)` -> `2^3*3^2*5/7`,
  `factor(1/36)` -> `1/(2^2*3^2)`. Tests verify exact values, output and re-parsing.
- Updated DESIGN section 4.3, the implementation log, T1.7/T1.11 notes and this handover.
  Created a T1.12 checkpoint note so the next continuation does not repeat the inventory.

## Verification

- `.venv\Scripts\python -m pytest -q -m "not slow" --strict-depth`:
  **1,942 passed, 2 skipped, 55 deselected, 3 xfailed**, no failures (313.92 s).
- All factor tests including slow oracle cases: **113 passed**, with `--strict-depth`.
- Factor/solve/build/runner/lint cross-family checks before the fraction display change:
  **484 passed, 1 skipped, 1 xfailed** under strict depth.
- Device-subset lint and FRAMELINT: clean.
- Device probes and heap calibration remain deferred; no on-device verification claimed.

## Known issues

- **Compile-unit sizes:** `norm/normb` are 210/164 minified lines; `solve/solveb/solvec` are
  225/232/196. Three existing strict xfails record these overruns. Split them before bundling;
  do not raise LAZYMAX without device evidence. The factoring size xfail is resolved.
- **Overall heap:** resident modules (especially node, parse, alg, printer and run) remain well
  above the original section 4.1 estimates. Splitting factoring caps compile peak only; it does
  not prove the whole application fits the approximately 175 KB heap. Recalibrate at T1.15.
- `mpy-cross` is not installed in the venv, so the two existing compiler-dependent tests skip.
- `invariants.py` flags some correct non-simplifications of complex constants (see T1.1 notes).
- Solver review is still pending; its generic numerical search samples a finite interval
  (-10 to 10 outside trig), so it is not a general root-completeness guarantee.
