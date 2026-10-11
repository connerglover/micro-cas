# cas-evo

A Python computer algebra system for the TI-84 EVO: exact arithmetic, radicals,
complex numbers, simplify/expand/factor/solve, derivatives, limits, integration,
series, sums, differential equations, gradients and geometric integrals. Includes
a calculator editor, history, stored variables/functions and 2D answers.

The calculator build is now a **multi-file package**. Small companion modules
load only when needed, preserving the full feature set. All 110 files passed
TI's actual converter; the largest is 6,314 bytes. Combined Python source is
about 272 KB. This replaces the rejected single-file build.

## Download and run

Download **cas-evo-v1** from a successful **Build calculator app** GitHub Actions
run. Extract the artifact, then extract its `cas-evo-v1.zip`. Locally, the same
ZIP is written to `dist/cas-evo-v1.zip`.

Send **all `.py` files from the extracted ZIP** to the calculator together.
Open the Python app and run **CASEVO**. `CVTEST` runs the optional 55-command
diagnostic against the same companions. Keep filenames unchanged.
See [INSTALL.md](docs/INSTALL.md) for controls and acceptance examples.

Physical calculator execution is still pending. Paging removes the old 87 KB
resident archive. The provisional core/phase subtotal is now about 139 KB
against a measured 173,360-byte Python heap, before documented exclusions.
Native MicroPython and desktop tests do not replace an EVO run. About 500 KB
of total user RAM is not the Python heap.

## Build locally

Use Python 3.14 in a virtual environment:

```text
python -m pip install -r requirements-dev.txt
python tests/support/lint.py src
python tests/support/framelint.py
python -m pytest -q -m "not slow" --strict-depth
python build/release.py
python -m pytest -q -m "not slow" --strict-depth --bundled
python build/check_release.py
```

The build minifies identifiers and source, checks every file's converter limit,
compiles every carrier with `mpy-cross`, and creates a deterministic ZIP with
checksums. GitHub Actions builds and tests on pushes, pull requests and manual
dispatch. An invalid build cannot leave an old release ZIP in the output folder.

The action also builds pinned MicroPython 1.29 and runs the actual app and all
55 diagnostic commands with a 500,000-byte native heap. Locally, prepare those
checks with `python build/micro_smoke.py`, or pass `--run /path/to/micropython
--heap 500000`. The tiny shims allocate no framebuffer; this checks interpreter
compatibility, not calculator graphics or the smaller EVO Python heap.

The calculator uses only its native Python modules. `sympy`, `pytest`, and
`mpy-cross` are development dependencies. Source and transformed code target the
calculator's Python 3.4 subset. The strict desktop call-depth budget is eight.

[HANDOVER.md](HANDOVER.md) records current work and the next step.
[DESIGN.md](docs/DESIGN.md) defines the architecture and bounded algorithms;
[task notes](docs/notes/) record implementation details and limitations.
