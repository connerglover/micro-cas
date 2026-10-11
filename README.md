# cas-evo

A Python computer algebra system for the TI-84 EVO: exact arithmetic, radicals,
complex numbers, simplify/expand/factor/solve, derivatives, limits, integration,
series, sums, differential equations, gradients and geometric integrals. Includes
a calculator editor, history, stored variables/functions and 2D answers.

The calculator build contains **236 compiled libraries in archive and two small
launchers in RAM**, preserving the full feature set. All 238 EVO transfer objects
total about 261 KiB; launcher source totals 6,760 bytes. This replaces both the
rejected single-file build and the source package that exhausted compile memory.

## Download and run

Download **cas-evo-v1** from a successful **Build calculator app** GitHub Actions
run. Extract the artifact, then extract its `cas-evo-calculator.zip`. Locally,
the same ZIP is written to `dist/cas-evo-calculator.zip`.

For automatic placement, download **cas-evo-web-installer** from that run,
extract it, and run `python serve_installer.py --directory website`. Open
`http://127.0.0.1:4173` in desktop Chrome or Edge, connect the EVO, and choose
**Install cas-evo**. It checks the package, migrates matching old source files,
sends the complete package, and verifies every destination. It uses pinned
[WebTILP](https://github.com/adriweb/tilibs) locally; no account or upload is needed.

For manual transfer, send all `.8mp2` files to **Archive**, and the two `.8xpy2`
launchers to **RAM** using WebTILP. Open Python and run **CASEVO**. `CVTEST` runs
the optional 55-command diagnostic. Keep filenames unchanged.
See [INSTALL.md](docs/INSTALL.md) for controls and acceptance examples.

Physical calculator execution is still pending. The actual release boots and
passes all 55 diagnostic calculations on 32-bit MicroPython with a 173,360-byte
total heap. The EVO probe measured that amount as free Python heap; about
500 KB of total user RAM is not the Python heap. Native tests use minimal
graphics shims and do not replace an EVO run.

## Build locally

`main` contains all calculator and website source. Successful builds publish the
complete website to the generated `pages` branch. Connect a Cloudflare Worker
to **pages**, leave its build command empty, and use
`npx --yes wrangler@4.149.0 deploy` as the deploy command. See
[HOSTING.md](docs/HOSTING.md) for dashboard setup and the custom domain.
The `v1` branch is retained for history; make new changes on main.

Use Python 3.14 in a virtual environment:

```text
python -m pip install -r requirements-dev.txt
python tests/support/lint.py src
python tests/support/framelint.py
python -m pytest -q -m "not slow" --strict-depth
python build/release.py
python -m pytest -q -m "not slow" --strict-depth --bundled
python build/check_release.py
python build/archive.py --mpy-cross /path/to/pinned-v1.12/mpy-cross
python -m pytest -q tests/test_archive_modules.py tests/test_archive_release.py --strict-depth
node build/package_archive.mjs
python build/archive_zip.py
node --test website/tests/*.test.js
python build/website.py
python build/serve_website.py
```

The build minifies source, creates native initializer modules with no engine
`exec`, compiles MPY v5.3 using pinned MicroPython v1.12, then converts and
round-trips every EVO object with TIVarsLib. The downloadable ZIP is deterministic
and checksummed. The old `cas-evo-v1.zip` is an internal source input only.
GitHub Actions builds both downloadable artifacts on main pushes, pull requests
to main and manual dispatch; the workflow contains the exact compiler revision
and flags. Only successful main builds update the deployment branch.

The action checks source compatibility on MicroPython 1.29 and actual MPY v5
bytecode on 1.12: UI arithmetic, calculus/recovery and all 55 diagnostics with
173,360-byte 32-bit and 500,000-byte 64-bit heaps. A 95,000-byte startup regression
targets the reported compile failure. Run bytecode checks locally with
`python build/micro_smoke.py --archive dist/archive --run /path/to/micropython-cas32 --heap 173360`.
The tiny shims allocate no framebuffer; calculator graphics remain a device test.

The calculator uses only its native Python modules. `sympy`, `pytest`, and
`mpy-cross` are development dependencies. Source and transformed code target the
calculator's Python 3.4 subset. The strict desktop call-depth budget is eight.

[HANDOVER.md](HANDOVER.md) records current work and the next step.
[DESIGN.md](docs/DESIGN.md) defines the architecture and bounded algorithms;
[task notes](docs/notes/) record implementation details and limitations.
