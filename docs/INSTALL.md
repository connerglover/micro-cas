# Install cas-evo on the TI-84 EVO

The package preserves the full v1 feature set across **238 small Python files**.
The largest is 6,238 bytes; total Python source is 317,277 bytes. Every file
passed TI Connect Evo's actual converter. Physical transfer and execution on an
EVO still need testing.

The earlier single-file CASEVO.py was too large and produced the generic
"One or more files was invalid" error. This package replaces that build.
Companions also let the engine release source after compilation instead of
keeping the full 87 KB compressed archive in its Python heap.

## Get the program

From a successful **Build calculator app** GitHub Actions run, download the
**cas-evo-v1** artifact. Extract the download, then extract `cas-evo-v1.zip`
inside it into a new folder. For local builds, extract `dist/cas-evo-v1.zip`.
Use the ZIP's files, not development files under `src/` or `dist/device/`.

## Transfer and launch

1. Turn on the EVO and connect it to the computer with a USB data cable.
2. Open [TI Connect Evo](https://connectevo.ti.com) in a browser supported by TI.
   Select **Connect to Calculator**, choose the EVO, and connect.
3. Open **Send Files**, then **Send to Calculator**. Select **all 238 `.py`
   files from the extracted folder** together. Do not select the ZIP, JSON,
   Markdown or checksum files. Keep every Python filename unchanged. Allow
   CASEVO/CVTEST to replace earlier versions and wait for transfer to finish.
4. Open the calculator's **Python** app, select **CASEVO**, and run it.
5. The cas-evo screen should show `RAD`, an edit line, and the five bottom labels
   `menu`, `recall`, `setup`, `forms`, and `help`.

Keep the companions on the calculator: CASEVO imports them on demand. Only
CASEVO and CVTEST are entry programs. Running a support module individually
will not start the app. If a module is missing, re-send all `.py` files from the
same ZIP. Avoid mixing builds. Python objects use about 0.33 MB before device
storage bookkeeping, below the 3.5 MB total allowance.

TI documents the connection and file-transfer controls in its
[TI Connect Evo guide](https://education.ti.com/en/product-resources/eguides/eguide-84-evo/evo-connect-user-guide).
Its [product page](https://education.ti.com/en/products/calculators/graphing-calculators/ti-84-evo/ti-connect-evo)
lists Python-program transfer and current browser requirements. Those pages do
not specify the raw `.py` conversion limit; that limit was tested directly in
the converter. Renaming the extension does not convert or shrink Python data.

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
imports. The release passes all 55 diagnostics and an arithmetic/quit UI check
on native 32-bit MicroPython with a 173,360-byte total heap. Graphics are shimmed,
so this is not a calculator measurement. Code loads in small pages, node storage
grows only as needed, and temporary code/cache data is released. If either program
fails before drawing its first screen, keep the complete traceback and any
free-heap value. Restarting Python creates a fresh session. Small programs in
`probe/` can measure device capabilities without loading the CAS.

For a failed check, keep the expression, displayed result/error, calculator OS
version, and a screen capture. TI Connect Evo's **Capture Screen** page can save
the display. The repository's `docs/notes/UI.md` describes the implementation
and desktop coverage.
