# cas-evo

A Python computer algebra system for the TI-84 EVO: exact arithmetic, radicals,
complex numbers, simplify/expand/factor/solve, derivatives, limits, integration,
series, sums, differential equations, gradients and geometric integrals. Includes
a calculator editor, history, stored variables/functions and 2D answers.

**Device acceptance remains open.** The full v1 feature set is implemented and
tested on desktop. The generated single-file build currently exceeds the
provisional model for the EVO's measured 173 KB Python heap; it is not yet a
proven working calculator release. About 500 KB of total user RAM does not imply
500 KB available to Python. See [installation and device testing](docs/INSTALL.md).

## Download a test build

Pushes and pull requests run the **Build calculator app** GitHub Action. Download
the `cas-evo-v1` artifact from a successful run, then extract `CASEVO.py`.
Only that file is needed for the app. `CVTEST.py` is an optional standalone
diagnostic. The package includes instructions, size/memory metadata and SHA-256
checksums. Local builds write the same files to `dist/`.

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
