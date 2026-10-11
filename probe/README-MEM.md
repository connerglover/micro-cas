# Memory probe (M0.5 gate): what to run and what to send back

This run measures how much RAM our kind of code takes on the TI-84 EVO. The numbers fix the
memory budget in `docs/DESIGN.md` (section 18.7) before the core modules are written. Until you
run it, the design uses estimates, marked "provisional" in `build/manifest.py`.

It takes about 5 minutes. Most of it is waiting and taking screenshots.

## Files to send to the calculator

Send these with TI Connect CE, the same way as the earlier probes:

| file | what it is |
|---|---|
| `PRBMEM.py` | the memory probe (you run this one) |
| `PRBMOD.py` | a tiny module that PRBMEM imports and unloads |
| `PRBL100.py`, `PRBL200.py`, `PRBL300.py` | test modules of 100, 200 and 300 lines; PRBMEM imports them. **Do not run them**: they print nothing and do nothing. |
| `PROBE6.py` | only if it is not on the calculator already (step 3) |

If an older copy of a file is on the calculator, replace it. All six files together need about
31 KB of storage.

## Steps

1. **Start fresh.** Open the Python app. Do not run anything else first: PRBMEM must start with
   as much free memory as possible.
2. **Run `PRBMEM`.** It needs no input. It prints short lines and stops at lines like
   `-- p3: screenshot, key --`. **Take a screenshot, then press any key.** There are 5 pages; the
   last line is `== PRBMEM end, p5 ==` (take a screenshot of that screen too).
   - The module part is slow: it imports each test module about 10 times. A page can stay on
     the screen for up to a minute. That is normal; wait for the `-- pN` line.
   - If it stops with an error message, take a screenshot of it. That is also a result.
3. **Run `PROBE6` again** (as in `probe/README.md`, step 4). This time the line `imp6` should say
   `ok` and a number, because `PRBL300.py` is now on the calculator. Send all its screenshots
   again, or at least the page with the `imp6` line.

## What to send back

- The PRBMEM screenshots, in order (5 pages).
- The PROBE6 screenshots (or the page with `imp6`).

Typing the PRBMEM lines into a text file instead of screenshots is fine. Copy every line as it
appears on the screen; the `-- pN` lines may be left out. Lines that start with a space belong
to the line above them. Example of the module part:

```
PRBL100 cost 3104 ms 212
 kept 904 k2 120 kD 100
 peak 11000
```

## What the lines mean (for the curious)

| line | meaning |
|---|---|
| `start`, `end` | free memory at the start and at the end, in bytes |
| `tup2` ... `dent` | bytes per object of each kind (tuples, lists, dicts, ...) |
| `sys.modules yes` | the calculator can unload modules |
| `delmod ok reimport new` | unloading works, and importing again builds a fresh module |
| `dictclr ok` | clearing a module's contents works |
| `PRBL100 cost C ms T` | the module takes C bytes once imported; the import took T ms |
| ` kept K1 k2 K2 kD KD` | bytes still taken after unloading it (first time, second time, and after clearing it first) |
| ` peak P` | free memory the import needs while it compiles |

---

## For developers: applying the results

1. Type the PRBMEM screens into a text file, for example `docs/notes/prbmem-m05.txt` (keep it:
   it is the record of the measurement).
2. Run `python build/genprobe.py --derive docs/notes/prbmem-m05.txt`. It prints:
   - `unparsed:` lines (typos in the transcript: fix them and run again);
   - per module `cost`, `kept`, `peak`, the compile transient, B/line and the import time;
   - straight-line fits through the three sizes (fixed bytes + bytes per line);
   - `FACTOR`, `PEAKB`, `LAZYMAX`, `NMAX`, the eviction mechanism (`EVICT`) and whether CVDRAW
     must become evictable (`DRAW_EVICTABLE`, ladder step 4), with the rules of DESIGN 18.7;
   - the DESIGN 18.1 ledger and the 18.2 load sets with the measured numbers, and the KB column
     of DESIGN 4.1;
   - warnings (for example `LAZYMAX < 150`: the DESIGN 4.3 seams move).
3. If the report is plausible, run it again with `--apply`. That rewrites only the constants
   `CALIBRATION FACTOR PEAKB LAZYMAX NMAX EVICT DRAW_EVICTABLE` in `build/manifest.py`
   (`CALIBRATION` becomes `'M0.5'`).
4. Update by hand, from the report:
   - DESIGN 4.1 (the KB column and the B/line figure), 4.3 (seams, if `LAZYMAX` changed),
     18.1-18.2 (ledger and load-set tables), 18.7 (the status paragraph), 5.1/5.11 (`NMAX`),
     and change the [A]/[E] tags of the measured items to [V];
   - device-python 10.2 (object sizes) and 10.4 (`kept` per module);
   - tell the owners: `src/node.py` `NMAX` (T1.1), the loader's eviction mechanism in
     `src/run.py` (T1.6, DESIGN 18.5), CVDRAW residency (the UI tasks; `lint.RESIDENT` and the
     manifest row class if it changes).
5. Run `python -m pytest -q tests/test_genprobe.py tests/test_build.py`. The check that the
   manifest still holds the provisional numbers switches itself off once `CALIBRATION` is no
   longer `'provisional'`.

**Special outcomes:**

- `PRBLnnn MemoryError`: the module could not even be imported once. The reserve is far too
  small: `LAZYMAX` must drop below that size (the report uses the modules that did import).
- ` peak E:...`: the ballast search failed; `PEAKB` then comes from the other modules, or stays
  at 80 with a warning.
- `delmod stays`, `reimport same` or large `k2`: unloading does not free the code. The report
  picks `EVICT = 'dict'` or `'none'` (DESIGN 18.5 fallbacks; `'none'` moves the T3 cut decision
  to T1.15).
- `imp6 E:RuntimeError` in PROBE6: compiling a 300-line module from depth 6 spends the depth
  budget. Move `need` into the driver (DESIGN 17.2).

The generated modules are rebuilt with `python build/genprobe.py` (never edit them by hand), and
`python build/genprobe.py --check` tells whether the files in `probe/` are current. If they are
rebuilt, the `.mpy` sizes in `MPY_BYTES` must be re-measured (`--stats` with mpy-cross), and the
calculator needs the new files before PRBMEM runs.
