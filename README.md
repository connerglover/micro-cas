# cas-evo

A Python computer algebra system for the TI-84 EVO: exact arithmetic, radicals,
complex numbers, simplify/expand/factor/solve, derivatives, limits, integration,
series, sums, differential equations, gradients and geometric integrals. Includes
a calculator editor, history, stored variables/functions and 2D answers.

The calculator build is now a **multi-file package**. Small companion modules
load only when needed, preserving the full feature set. The package has 238
minified Python files totaling about 317 KB, well below the 3.5 MB storage
allowance. All 238 files passed TI Connect Evo's actual converter. This replaces
the rejected single-file build.

## Download and run

Download **cas-evo-v1** from a successful **Build calculator app** GitHub Actions
run. Extract the artifact, then extract its `cas-evo-v1.zip`. Locally, the same
ZIP is written to `dist/cas-evo-v1.zip`.

Send **all `.py` files from the extracted ZIP** to the calculator together.
Open the Python app and run **CASEVO**. `CVTEST` runs the optional 55-command
diagnostic against the same companions. Keep filenames unchanged.
See [INSTALL.md](docs/INSTALL.md) for controls and acceptance examples.

Physical calculator execution is still pending. The actual release boots and
passes all 55 diagnostic calculations on 32-bit MicroPython with a 173,360-byte
total heap. The EVO probe measured that amount as free Python heap; about
500 KB of total user RAM is not the Python heap. Native tests use minimal
graphics shims and do not replace an EVO run.

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
55 diagnostic commands with both a 173,360-byte 32-bit heap and a 500,000-byte
64-bit heap. Locally, prepare those checks with `python build/micro_smoke.py`,
or pass `--run /path/to/micropython --heap 173360` for a 32-bit executable.
The tiny shims allocate no framebuffer; calculator graphics remain a device test.

The calculator uses only its native Python modules. `sympy`, `pytest`, and
`mpy-cross` are development dependencies. Source and transformed code target the
calculator's Python 3.4 subset. The strict desktop call-depth budget is eight.

[HANDOVER.md](HANDOVER.md) records current work and the next step.
[DESIGN.md](docs/DESIGN.md) defines the architecture and bounded algorithms;
[task notes](docs/notes/) record implementation details and limitations.
