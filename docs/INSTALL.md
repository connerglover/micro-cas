# Install cas-evo on the TI-84 EVO

Use **cas-evo-calculator.zip**, the compiled EVO package. It preserves all v1
features with **236 compiled libraries in archive and two launchers in RAM**.
The transfer objects total about 261 KiB; the two launcher sources total 6,760
bytes. This is well below the 3.5 MB storage allowance. Runtime Python heap is
a separate, smaller budget.

This replaces the source package that reported `MemoryError: phase compile
memory` in both CASEVO and CVTEST. Compiling source carriers alone did not fix
that error: their loader still invoked `exec`. The new package imports compiled
initializers and never compiles the engine on the calculator. The launchers
remain small Python source programs so they appear in the Python app.

## Get the program

From a successful **Build calculator app** GitHub Actions run, download the
**cas-evo-v1** artifact. Extract the download, then extract
`cas-evo-calculator.zip` inside it into a new folder. For local builds, use
`dist/cas-evo-calculator.zip`. The older `dist/cas-evo-v1.zip` is now an internal
source-build input, not the calculator download. Do not mix these packages.

## Transfer and launch

1. Exit Python, turn on the EVO, and connect a USB data cable. Close TI Connect
   and any other calculator connection tabs.
2. Download and extract **cas-evo-web-installer** from the same successful Actions
   run. In that folder, run `python serve_installer.py --directory website`, then
   open `http://127.0.0.1:4173` in desktop Chrome or Edge. For a repository build,
   build the website first and run `python build/serve_website.py`.
3. Choose **Connect your EVO**, select the calculator's serial port, then
   **Install cas-evo**. The installer checks space and reads back every
   calculator file that has the name of an earlier cas-evo file. It deletes or
   replaces only exact content matches of a recorded release and lists any
   others it keeps. It then sends the compiled libraries to archive, sends the
   launchers to RAM, and verifies their locations. Wait for completion.
4. Start a fresh **Python** session, select **CASEVO**, and run it.
5. The screen should show `RAD`, an edit line, and the five bottom labels
   `menu`, `recall`, `setup`, `forms`, and `help`.

For manual transfer, use [WebTILP](https://adriweb.github.io/tilibs/). Send every
`.8mp2` library from the ZIP to **Archive**, then send `CASEVO.8xpy2` and
`CVTEST.8xpy2` to **RAM**. Keep their names unchanged. Do not send JSON, Markdown,
checksum files, raw `.mpy`, or source files from `src/` or `dist/device/`.
WebTILP handles the older EVO 7.0 compiled-module container when needed.
For a manual transfer, remove an earlier cas-evo first; see
[Remove an earlier version](#remove-an-earlier-version).

The browser installer removes an earlier version for you. It reads each file
with an earlier cas-evo name back from the calculator and compares the decoded
module or source text with the recorded v1 release (`legacy-v1.json` on the
installer site), including the source companions that the v1 installer moved to
archive. Only exact matches are deleted, or replaced by a new file with the same
name. A file that differs or cannot be read is kept and listed. If such a file
would be overwritten, or would hide a new library in Python, the installer
changes nothing and asks you to remove it yourself. It does not erase RAM,
unrelated programs, or firmware.

Only CASEVO and CVTEST should appear as launchable programs. The compiled
companions stay in archive and load on demand. Ordinary archived `.py` files
cannot replace compiled `.8mp2` libraries. Merely renaming a file does not convert
it. Imported code still occupies working heap; archive does not add RAM.
Reinstall the complete package if a companion is missing.

The EVO format and archive behavior come from
[WebTILP's EVO implementation](https://github.com/adriweb/tilibs) and the
[EVO Python transfer implementation](https://github.com/Evo-Programming/evo_usb_py).
Physical USB transfer and execution of this cas-evo package still need hardware
acceptance; native tests are not an EVO emulator.

## Remove an earlier version

The v1 release put **236 compiled libraries** in archive and the two launchers
`CASEVO` and `CVTEST` in RAM. The new release uses far fewer, differently named
libraries. Leftover v1 libraries are not used by the new release. Whether
removing them changes loading time on the EVO has not been measured yet.

To remove them without the browser installer, use **TI Connect Evo**: connect
the calculator, open its list of calculator files, select the files below and
delete them. Menu names can differ between TI Connect Evo versions. Deleting
cannot be undone; copy anything you are unsure about to your computer first.

| v1 files | Names |
|---|---|
| Launchers (RAM) | `CASEVO`, `CVTEST` |
| Phase libraries (archive) | `CVP00000` to `CVP00055` (56 files) |
| Function pages (archive) | `CVF00001` to `CVF00128` (128 files) |
| Engine and UI libraries (archive) | `CVALG` `CVCAT` `CVDEF` `CVDEFB` `CVDEFC` `CVDIFF` `CVDRAW` `CVFACT` `CVFACTB` `CVFACTC` `CVFACTD` `CVFORM` `CVIDENT` `CVINT` `CVINT2` `CVINT2B` `CVINT3` `CVINT3B` `CVITAB` `CVLIM` `CVLIMB` `CVLIMC` `CVMENU` `CVMENUB` `CVNODE` `CVNORM` `CVNORMB` `CVNORMC` `CVODE` `CVODEB` `CVODEC` `CVODED` `CVPARSE` `CVPH` `CVPOLY` `CVPOLYB` `CVPOLYC` `CVPRINT` `CVRULE` `CVRULEB` `CVRUN` `CVSER` `CVSERB` `CVSOLVE` `CVSOLVEB` `CVSOLVEC` `CVSOLVED` `CVSOLVEE` `CVSUM` `CVSUMB` `CVSUMC` `CVUI` (52 files) |

Earlier source-package copies of these modules can also exist as Python source
files with the same names, in RAM or archive. Remove them the same way.

- **Before installing the new release:** delete every file in the table,
  including `CASEVO` and `CVTEST`, then send the new package.
- **After installing the new release:** first compare the table with the file
  names in the new `cas-evo-calculator.zip`. Keep `CASEVO`, `CVTEST` and every
  file that is part of the new package, even when a new library reuses a v1
  name. Delete only the remaining names from the table.

Only delete names that appear in the table. Other programs that start with `CV`
are not cas-evo files. If you edited a cas-evo file yourself, keep a copy before
deleting it.

## First checks

Use RAD mode for these examples. Type each expression and press **ENTER**. F1
opens command templates; **MATH** opens the Calculus tab. Type letters with
**ALPHA**. Equivalent reordered expressions are acceptable.

| Input | Expected result |
|---|---|
| `1/3+1/6` | `1/2`, drawn as a fraction |
| `expand((x+1)^3)` | `x^3+3*x^2+3*x+1` |
| `solve(x^2-5*x+6,x)` | `x=2,x=3` |
| `diff(x^3,x)` | `3*x^2` |
| `integrate(x^2,x)` | `x^3/3`, with `+ C` in the footer |
| `limit(sin(x)/x,x,0)` | `1` |
| `sum(k^2,k,1,10)` | `385` |
| `grad(x*y,[x,y])` | `[y,x]` |

Then try `sqrt(2)` and press **F4** to request its decimal form. Open **F3**,
switch to Night, and check that the editor and menus remain readable. While a
longer calculation is running, press **CLEAR** to cancel, then check that `2+3`
still returns `5`.

## Everyday controls

| Key | Action |
|---|---|
| F1 / Y= | Command menu; left/right changes tabs |
| F2 / WINDOW / VARS | Recall Ans, recent results, variables, and functions |
| F3 / ZOOM / MODE | Angle mode, theme, session clearing, About |
| F4 / TRACE | Next available form of the displayed answer |
| F5 / GRAPH | Help for the command around the caret; ENTER inserts its example |
| Up/down | Browse history; ENTER inserts the selected result |
| 2nd ENTER | Recall earlier input; in history, insert the selected input |
| Left/right | Move the caret; with an empty editor, scroll the answer |
| DEL | Backspace; `ans()` is removed as one unit |
| CLEAR | Clear input, leave history/menu, or cancel a calculation |
| 2nd MATH | Relation picker: `= != < <= > >= !` |
| 2nd 0 | All commands |
| 2nd MODE | Quit to Python |

Starting with `+`, `-`, `*`, `/`, a power key, or STO uses the previous answer.
Use the separate **(-)** key to begin a negative number. **2nd (-)** inserts
`ans()`. **2nd ^** inserts `pi`; **2nd .** inserts `i`; **ALPHA .** inserts the
prime in `y'`. **2nd multiply/minus** insert `[` and `]`.

History, stored variables/functions, and settings belong to the current run.
Quit and restart starts a fresh session. Large or unsupported expressions may
remain symbolic or return a size/time/memory message.

## Automated calculator diagnostic

Run **CVTEST** in a fresh Python session after sending the complete package.
It uses the same companion modules as CASEVO. It checks 55 algebra/calculus
commands and prints available heap, bounded call-depth checks and native-math results.
Photograph each page and press ENTER to continue; CLEAR at a page prompt stops.
The expected final line is `CVTEST: 55/55 PASS`.

The EVO probes measured **173,360 bytes of free Python heap** after native
imports. The build checks the actual MPY v5 bytecode on native 32-bit MicroPython
with a 173,360-byte total heap, including all 55 diagnostics and UI sessions.
An additional 95,000-byte startup regression reproduces the old exact error
and checks that the compiled loader reaches CVTEST's first page. Graphics are
shimmed, so these are not calculator measurements. Code loads in small pages,
node storage grows only as needed, and temporary code/cache data is released. If either program
fails before drawing its first screen, keep the complete traceback and any
free-heap value. The new loader reports the module or phase and available/required
bytes if its memory reserve cannot be met. Seeing `phase compile memory` still
means source-loader files from an earlier build are running. Restarting Python
creates a fresh session. Small programs in
`probe/` can measure device capabilities without loading the CAS.

For a failed check, keep the expression, displayed result/error, calculator OS
version, and a screen capture. TI Connect Evo's **Capture Screen** page can save
the display. The repository's `docs/notes/UI.md` describes the implementation
and desktop coverage.
