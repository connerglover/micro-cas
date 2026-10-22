# cas-evo

A Python computer algebra system for the TI-84 EVO: exact arithmetic, radicals,
complex numbers, simplify/expand/factor/solve, derivatives, limits, integration,
series, sums, differential equations, gradients and geometric integrals. Powers
too large to compute stay exact powers (`3^(2^20)` gives `3^1048576`). Includes
a MathPrint (2D) editor, a scrollable history whose inputs and answers can be
copied back, stored variables/functions and 2D answers.

The calculator build (format `packs-v1`) contains **21 compiled library packs
for Archive and one small launcher, `CAS`, for RAM**, preserving the full
feature set: 22 EVO transfer objects, whose sizes `archive.json` in the ZIP
records. CAS imports two packs before its first screen and loads the engine on the first
ENTER. This replaces the v1 package of 236 libraries, which took 5.5 minutes to
start on the EVO and then stopped at a `ti_graphics.setColor` call; see
[FASTBOOT.md](docs/notes/FASTBOOT.md).

## Download and run

The current release is **cas-evo 1.0.0** (tag `v1.0.0`); the source is at
1.0.1, not yet tagged (history CLEAR, polished texts). Download
**cas-evo-v1.0.0.zip** from its GitHub Release; it is the calculator ZIP
(`cas-evo-calculator.zip`) of the tag's **Build calculator app** run, whose
artifact **cas-evo-v1** (the artifact name is unchanged) holds the same file.
Locally, the same ZIP is written to `dist/cas-evo-calculator.zip`.

For automatic placement, download **cas-evo-web-installer** from that run,
extract it, and run `python serve_installer.py --directory website`. Open
`http://127.0.0.1:4173` in desktop Chrome or Edge, connect the EVO, and choose
**Install cas-evo**. It checks the package, removes earlier cas-evo files only
when their contents exactly match a recorded earlier release (v1, the first
pack release with its `CASEVO` and `CVTEST` launchers, and the MathPrint test
builds), sends the complete
package, and verifies every destination. It uses pinned
[WebTILP](https://github.com/adriweb/tilibs) locally; no account or upload is needed.

For manual transfer, send every `.8mp2` file to **Archive** and the `.8xpy2`
launcher `CAS` to **RAM** using WebTILP. Remove the files of an earlier install
first (an earlier pack release left `CASEVO` and `CVTEST` in RAM);
[INSTALL.md](docs/INSTALL.md#remove-an-earlier-version) lists them. Open Python
and run **CAS**. Keep filenames unchanged. See
[INSTALL.md](docs/INSTALL.md) for controls and acceptance examples.

Physical calculator execution of `packs-v1` is still pending. On 32-bit
MicroPython v1.12, which is not an EVO emulator, the compiled packs start on a
95,000-byte heap and pass a typical session at 173,360 bytes. The heaviest
definite integrals need more: they pass at 189,776 bytes, the free heap the EVO
probe measured at program start plus the test harness's own use. The 55
diagnostics of the developer probe `CVTEST` (built to `dist/dev/` for CI, not
shipped) pass in one long session at 204,000 bytes and up; at 189,776 the heap
fragments and 53 pass. About 500 KB of total user RAM is not the Python heap.

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
python build/transfer.py dist/CAS.py dist/dev/CVTEST.py
python -m pytest -q -m "not slow" --strict-depth --bundled
python build/check_release.py
python build/archive.py --mpy-cross /path/to/pinned-v1.12/mpy-cross
python -m pytest -q tests/test_archive_release.py --strict-depth
node build/package_archive.mjs
python build/archive_zip.py
node --test website/tests/*.test.js
python build/website.py
python build/serve_website.py
```

The build bundles and minifies `src/`, merges the device modules into packs
(`build/packs.py`, membership in `build/manifest.py`), shortens identifiers,
compiles the packs to MPY v5.3 with pinned MicroPython v1.12, then converts and
round-trips every EVO object with TIVarsLib. The downloadable ZIP is
deterministic and checksummed. `dist/cas-evo-packs.zip` is internal build input
only. GitHub Actions builds both downloadable artifacts for pushed `v*` tags,
published GitHub Releases and manual dispatch (not on ordinary pushes or pull
requests); the workflow contains the exact compiler revision and flags. A tag run
attaches the calculator ZIP to the tag's Release as `cas-evo-<tag>.zip` and
updates the deployment branch ([docs/HOSTING.md](docs/HOSTING.md)).

The action checks the pack sources on MicroPython 1.29 and the actual MPY v5
bytecode on 1.12: startup on a 95,000-byte 32-bit heap, UI arithmetic at
173,360 bytes, the UI calculus session at 189,776 bytes, all 55 diagnostics at
212,000 bytes, and the UI, calculus and diagnostic suites on a 500,000-byte
64-bit heap. Run a bytecode check locally with
`python build/micro_smoke.py --archive dist/archive --output dist/archive-smoke --run /path/to/micropython-cas32 --heap 173360 --suite ui`.
The native `ti_draw` stub allocates no framebuffer; calculator graphics remain a
device test.

The calculator uses only its native Python modules. `sympy`, `pytest`, and
`mpy-cross` are development dependencies. Source and transformed code target the
calculator's Python 3.4 subset. The strict desktop call-depth budget is eight.

[AGENTS.md](AGENTS.md) is the shared development guide;
[delivery status](docs/STATUS.md) records verified results and remaining checks.
[DESIGN.md](docs/DESIGN.md) defines the architecture and bounded algorithms;
[task notes](docs/notes/) record implementation details and limitations.
