# Install and try cas-evo v1

cas-evo runs in the TI-84 EVO Python app. The release contains **one runtime file,
`CASEVO.py`**. Its parser, algebra, calculus, menus, and graphics code are embedded;
there are no companion modules to transfer.

**This is a device test build, not a hardware-validated release.** The existing
EVO probes measured about **173 KB of free Python heap**, although the calculator
has about 500 KB of total user RAM. The current build's provisional heap model
exceeds that smaller budget. It may stop with `MemoryError` during startup.
Passing desktop tests does not establish calculator memory fit. The exact model,
its exclusions, and the file checksum are in `release.json`.

The file is about 263 KB, comfortably below 3.5 MB of storage. It uses minified
identifiers, compressed embedded code, bounded compilation, and phase eviction.
Byte storage was chosen over base85 text because it uses less runtime memory,
despite producing a larger ASCII transfer file. Graphics metrics, transfer
conversion and execution speed also still need physical validation.

## Get the program

Download `CASEVO.py`, or extract it from `cas-evo-v1.zip`. Repository builds place
the release archive under `dist/`. GitHub Actions provides downloadable artifacts
on a successful build: open the repository's **Actions** tab, select the completed
build, and download its release artifact. Extract downloaded archives on the
computer before selecting the Python file for transfer.

Keep the name `CASEVO.py`. Transfer the generated release file; the files in
`src/` are development sources.

## Transfer and launch

1. Turn on the EVO and connect it to the computer with a USB data cable.
2. Open [TI Connect Evo](https://connectevo.ti.com) in a browser supported by TI.
   Select **Connect to Calculator**, choose the EVO, and connect.
3. Open **Send Files**, then **Send to Calculator**. Select `CASEVO.py` and wait
   for transfer to finish.
4. Open the calculator's **Python** app, select **CASEVO**, and run it.
5. The cas-evo screen should show `RAD`, an edit line, and the five bottom labels
   `menu`, `recall`, `setup`, `forms`, and `help`.

TI documents the connection and file-transfer controls in its
[TI Connect Evo guide](https://education.ti.com/en/product-resources/eguides/eguide-84-evo/evo-connect-user-guide).
Its [product page](https://education.ti.com/en/products/calculators/graphing-calculators/ti-84-evo/ti-connect-evo)
lists Python-program transfer and current browser requirements. Those pages do
not specify raw `.py` conversion details; acceptance of this exact release file
still needs to be checked on the calculator. If the transfer dialog rejects it,
record the exact error and Connect/browser version. Renaming the extension does
not convert the file.

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

The archive also contains **CVTEST.py**, an optional, independent test program.
Transfer and run it separately from CASEVO. It includes its own engine, so you
do not need any other CV modules. It checks 55 algebra/calculus commands and
prints the available heap, bounded call-depth checks, and native-math results.
Photograph each page and press ENTER to continue; CLEAR at a page prompt stops.
The expected final line is `CVTEST: 55/55 PASS`.

Because CVTEST includes the same engine archive, it can encounter the same
startup heap limit. If either program fails before drawing its first screen,
keep the complete traceback and the free-heap value if printed. Restarting the
Python shell creates a fresh session; deleting your calculator data is not a
remedy for a fixed Python heap limit. The small programs in `probe/` can measure
device capabilities without loading the CAS.

For a failed check, keep the expression, displayed result/error, calculator OS
version, and a screen capture. TI Connect Evo's **Capture Screen** page can save
the display. The repository's `docs/notes/UI.md` describes the implementation
and desktop coverage.
