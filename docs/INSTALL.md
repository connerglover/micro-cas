# Install cas-evo on the TI-84 EVO

Use **cas-evo-calculator.zip**, the compiled EVO package: **cas-evo 1.0.0**
(format `packs-v1`). On a GitHub Release the same file is named
`cas-evo-v1.0.0.zip`.
It preserves all v1 features with **21 compiled library packs in archive**
(`CAS*.8mp2`) and **one launcher in RAM** (`CAS.8xpy2`): 22 files, well below the 3.5 MB storage allowance. `archive.json` in the ZIP
lists each file's size. Runtime Python heap is a separate, smaller budget.

This replaces the v1 package of 236 compiled libraries. On the EVO, v1 took
about 5.5 minutes to start, because it needed 51 archive imports before its
first screen and each one took seconds, and then stopped with `TypeError:
function takes 1 positional arguments but 3 were given` from a
`ti_graphics.setColor` call. The new package draws through `ti_draw`, imports
two packs before its first screen, and loads the engine on the first ENTER. It
never compiles the engine on the calculator. The launcher CAS remains a small
Python source program so it appears in the Python app.

## Get the program

From a successful **Build calculator app** GitHub Actions run, download the
**cas-evo-v1** artifact. Extract the download, then extract
`cas-evo-calculator.zip` inside it into a new folder. For local builds, use
`dist/cas-evo-calculator.zip`. `dist/cas-evo-packs.zip` is an internal build
input, not the calculator download. Do not mix files from different packages.

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
   launcher CAS to RAM, and verifies their locations. Wait for completion.
4. Start a fresh **Python** session, select **CAS**, and run it.
5. The screen should show `RAD` and `Ready` with the start time in seconds in
   the top row, `Press math` in the middle, an empty edit line, and the
   five bottom labels `Alg`, `Calc`, `Trig`, `More`, and `Forms`. Press **2nd**:
   the labels change to `All`, `Tmpl`, `Test`, `Setup`, and `Help`, and press it
   again to change them back. Without a
   calculator clock the top row shows only `Ready`.
6. Type `2+3` and press **ENTER**. The first ENTER loads the engine: the top row
   shows `Loading engine...`, then `Calculating...`, and the answer `5` appears
   with `Engine` and the engine load time in seconds; the top right shows the
   answer's form, `exact`. Opening a menu first also loads the engine. Later
   commands reuse it.

For manual transfer, use [WebTILP](https://adriweb.github.io/tilibs/). Send every
`.8mp2` library from the ZIP to **Archive**, then send `CAS.8xpy2` to **RAM**.
Keep the names unchanged. Do not send JSON, Markdown,
checksum files, raw `.mpy`, or source files from `src/` or `dist/device/`.
WebTILP handles the older EVO 7.0 compiled-module container when needed.
For a manual transfer, remove an earlier cas-evo first; see
[Remove an earlier version](#remove-an-earlier-version).

The browser installer removes an earlier version for you. It reads each file
with an earlier cas-evo name back from the calculator and compares the decoded
module or source text with the recorded earlier releases (the `legacy-*.json`
files on the installer site: v1, the first pack release and the MathPrint test
builds), including the source companions that the v1 installer moved to
archive. Only exact matches are deleted, or replaced by a new file with the same
name. A file that differs or cannot be read is kept and listed. If such a file
would be overwritten, or would hide a new library in Python, the installer
changes nothing and asks you to remove it yourself; this includes a program of
your own that is already called `CAS`. It does not erase RAM, unrelated
programs, or firmware.

Only CAS should appear as a launchable program. The compiled
libraries stay in archive and load on demand. Ordinary archived `.py` files
cannot replace compiled `.8mp2` libraries. Merely renaming a file does not convert
it. Imported code still occupies working heap; archive does not add RAM.
Reinstall the complete package if a library is missing.

The EVO format and archive behavior come from
[WebTILP's EVO implementation](https://github.com/adriweb/tilibs) and the
[EVO Python transfer implementation](https://github.com/Evo-Programming/evo_usb_py).
Physical USB transfer and execution of this cas-evo package still need hardware
acceptance; native tests are not an EVO emulator.

## Remove an earlier version

### An earlier pack release

The first pack release and the MathPrint test builds had 23 files: the same
`CAS*` library names and two RAM launchers, `CASEVO` and the diagnostic
`CVTEST`. The launcher is now called `CAS`, and the diagnostic no longer ships
(it only took calculator memory). The browser installer replaces each library
and removes `CASEVO` and `CVTEST` when their contents match a recorded release.
After a manual transfer, delete `CASEVO` and `CVTEST` from RAM yourself with
TI Connect Evo; the new libraries replace the old ones of the same name.

### v1

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
  names in the new `cas-evo-calculator.zip`. Keep `CAS` and every file that is
  part of the new package, even when a new library reuses a v1 name. Delete
  the remaining names from the table, `CASEVO` and `CVTEST` included.

Only delete names that appear in the table. Other programs that start with `CV`
are not cas-evo files. If you edited a cas-evo file yourself, keep a copy before
deleting it.

## First checks

Use RAD mode for these examples. Type each expression and press **ENTER**. F1 to
F4 open the command menu on its Algebra, Calculus, Trig and More tabs; **MATH**
opens the tab you used last (Algebra at first). Type letters with **ALPHA**.
Equivalent reordered expressions are acceptable.

| Input | Expected result |
|---|---|
| `7-2*3+8/4^1` | `3`; the edit line must show exactly these characters (it checks the Evo's ÷ × − + and x^n keys) |
| `1/3+1/6` | `1/2`, drawn as a fraction |
| `expand((x+1)^3)` | `x^3+3*x^2+3*x+1` |
| `solve(x^2-5*x+6,x)` | `x=2,x=3` |
| `diff(x^3,x)` | `3*x^2` |
| `integrate(x^2,x)` | `x^3/3`, with `+ C` drawn right after it on the same row |
| `limit(sin(x)/x,x,0)` | `1` |
| `sum(k^2,k,1,10)` | `385` |
| `grad(x*y,[x,y])` | `[y,x]` |
| `integrate(1/(2+cos(x)),x,0,2*pi)` | `2*sqrt(3)*pi/3`; one of the heaviest commands for memory |

Then try `sqrt(2)` and press **F5** (or < >) to request its decimal form: the
label at the top right changes from `exact` to `decimal`. Press up: the last
answer is highlighted; press left to highlight its input, then **ENTER** to copy
it into the edit line. Press up again and **CLEAR** to delete that entry from the
history. While a longer calculation is running, press **CLEAR** to
cancel, then check that `2+3` still returns `5`.

## Everyday controls

| Key | Action |
|---|---|
| F1 / Y= (`Alg`) | Command menu on the Algebra tab; left/right changes tabs |
| F2 / WINDOW (`Calc`) | Command menu on the Calculus tab |
| F3 / ZOOM (`Trig`) | Command menu on the Trig tab |
| F4 / TRACE (`More`) | Command menu on the More tab |
| F5 / GRAPH (`Forms`), < > | Next available form of the highlighted or last answer (exact, decimal, ...); its name is shown at the top right. Nothing without an answer |
| MATH | Command menu on the tab used last (Algebra at first) |
| 2nd F1 (`All`) | All commands, A to Z; ALPHA letters find a command |
| 2nd F2 (`Tmpl`) | Template picker (as 2nd fraction key) |
| 2nd F3 (`Test`) | Relation picker (as 2nd MATH) |
| 2nd F4 (`Setup`), MODE | Angle mode, session clearing, About |
| 2nd F5 (`Help`) | Help for the command around the caret; ENTER inserts its example |
| VARS | Ans, stored variables, and functions |
| Up/down | Up from the edit line scrolls the history; in the history, up/down move between entries (2nd: 5 at a time) |
| Left/right in the history | Left highlights the input, right the answer; a wide answer scrolls first |
| ENTER in the history | Copy the highlighted input or answer into the edit line at the caret |
| CLEAR in the history | Delete the highlighted entry (input and answer); Ans and variables stay |
| 2nd ENTER | Recall earlier inputs into the edit line |
| Left/right | Move the caret; with an empty editor, scroll the answer |
| DEL | Backspace; `ans()` is removed as one unit |
| CLEAR | Clear the edit line, close a menu, or cancel a calculation. Down past the newest entry leaves the history |
| 2nd MATH | Relation picker: `= != < <= > >= !` |
| 2nd 0 | All commands |
| Fraction key | Stacked fraction: numerator box over denominator box |
| 2nd fraction key | Template picker: square and nth root, e^x, 10^x, log base b, absolute value, integral, d/dx, nth derivative, sum, limit. Every box starts empty; optional boxes (log base, derivative order, limit direction, both integral bounds) may stay empty |
| 2nd x^n | nth root template, index box first (`surd(8,3)` is `2`) |
| 2nd MODE | Quit to Python |

Menus and the catalog list commands by the names the TI-Nspire CX II CAS uses
(Simplify, Solve, Derivative, Integral, Taylor Polynomial, Convert to Decimal,
...); ALPHA find matches the name or the command itself (`diff` finds
Derivative). A command arrives with an empty box for each argument, and the row above the edit line explains
the box the caret is in and whether it is required, for example `Expr. to
simplify (required)` or `Order (empty: 1)`, which says what an empty box means.
Optional boxes may stay empty; ENTER moves to an empty required box and shows
`Fill in the empty box`.

Starting with `+`, `-`, `*`, `/`, a power key, or STO uses the previous answer.
Use the separate **(-)** key to begin a negative number. **2nd (-)** inserts
`ans()`; **2nd .** inserts `i`; **ALPHA .** inserts the prime in `y'`. **2nd ÷**
inserts `pi`, **2nd ×** inserts `e`, and **2nd −** / **2nd +** insert `[` and `]`.
These 2nd keys follow the TI-84 Plus CE labels by key position; if a label
printed on your Evo keypad says otherwise, report the key and what it typed.

History, stored variables/functions, and settings belong to the current run.
Quit and restart starts a fresh session. Large or unsupported expressions may
remain symbolic or return a size/time/memory message. Exact finite sums that exceed the
bounded accumulator stay written as `sum(...)` or `riemann(...)`. Some combinations of
giant powers return `Number too large`; ordinary exact and complex arithmetic are retained.

## Memory

The EVO probes measured **185,296 bytes of free Python heap** at the start of a
small program and 173,360 bytes after importing `ti_plotlib`, `ti_graphics`,
`ti_image` and more, which cas-evo does not import. The build runs the compiled
packs on native 32-bit MicroPython v1.12: startup on a 95,000-byte total heap,
`2+3` and long 2D lines at 173,360 bytes, seven calculus commands at 189,776
bytes, and 55 diagnostic calculations at 212,000 bytes. Graphics are stubbed, so
these are not calculator measurements. **MODE > About cas-evo** shows the free
heap, and a calculation that runs out of memory shows `Out of memory`; the next
command should still work. The 55-case diagnostic program (`CVTEST`) is a
developer tool built and run in CI; it is not part of the package.

If CAS fails before drawing its first screen, keep the complete traceback and
any free-heap value. A traceback that names a `CVP` or `CVF` file
means v1 files are still running; see
[Remove an earlier version](#remove-an-earlier-version). Restarting Python
creates a fresh session. Small programs in `probe/` can measure device
capabilities without loading the CAS.

For a failed check, keep the expression, displayed result/error, calculator OS
version, and a screen capture. TI Connect Evo's **Capture Screen** page can save
the display. The repository's `docs/notes/UI.md` describes the implementation
and desktop coverage.
