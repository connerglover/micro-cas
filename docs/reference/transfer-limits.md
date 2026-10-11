# TI Connect Evo rejects the oversized single-file build

Verified 2026-10-11 using the actual TI Connect Evo converter, version
**7.1.0.792**, loaded from [TI's application](https://connectevo.ti.com/ticevo/en/).
The user reported the same generic invalid-file dialog when sending CASEVO.py.

## Reproduction and cause

The application accepts the .py extension. Its send-file preparation calls
TIConnect.convertPyToPyVar, and a non-success return opens the user's generic
invalid-file dialog. The converter returned **4 (XFR_ERROR_NOMEM)** for the
actual 262,679-byte CASEVO.py, leaving its token name empty. A tiny program with
the same name returned **0 (XFR_SUCCESS)**. No USB connection was needed to
exercise this conversion path.

Binary search with controlled ASCII sources found these exact boundaries:

| File name | Largest accepted source | First rejected source |
|---|---:|---:|
| A.py | 65,516 bytes | 65,517 bytes |
| CASEVO.py | 65,511 bytes | 65,512 bytes |
| CVTEST.py | 65,511 bytes | 65,512 bytes |
| ABCDEFGH.py | 65,509 bytes | 65,510 bytes |

Both a single long comment and many short lines give the same boundaries.
The original file's 253,723-character archive line is therefore not the cause
of this rejection. Changing CASEVO to a shorter valid name gains only a few
bytes. Total calculator storage and Python runtime heap are separate limits.

The observed boundary is source bytes + 18 + module-name bytes <= 65,535.
The [Evo USB project's Python object encoder](https://github.com/Evo-Programming/evo_usb_py/blob/main/evo_usb.py)
independently shows the 18-byte overhead plus name and source, with a 16-bit
source-length field. The enclosing transfer file can exceed 65,535 bytes;
this is a limit on its Python object, not the entire CBOR file or calculator.

## Repeat the checks

On the loaded TI Connect Evo page, evaluate build/transfer_probe.js. It calls
the public converter API with the sixteen boundary/line-shape cases above and
throws if an expected result changes. If a global casSource contains the
program's source, it also reports that program's conversion result. The captured
run is in transfer-checks.json alongside this note; no TI library is vendored.

The release's fast offline gate uses the observed ASCII-source boundary:

    python build/transfer.py dist/CASEVO.py dist/CVTEST.py

For the rejected build it exits 1 and reports:

    CASEVO.py: 262679 / 65511 source bytes: REJECTED
    CVTEST.py: 267644 / 65511 source bytes: REJECTED

## Multi-file correction

After this diagnosis the user authorized companion files to preserve functionality.
The new build contains 238 Python files, 317,277 source bytes combined, with a
largest file of 6,238 bytes. All 238 were passed through the same actual converter
and returned XFR_SUCCESS (0). Captured results are in
`multifile-converter-checks.json`, including each source SHA-256;
SHA256SUMS/release.json identify the complete package bytes.
No USB connection was requested during these checks.

`build/transfer_probe.js` accepts a global `casFiles` array of [filename, source]
pairs to repeat the full-package check. The normal release build uses the exact
observed size bound for every entry and carrier before packaging. It removes
stale generated deliverables first, including prior single-file ZIPs. There is
no oversized-development override. CI independently gates all generated files.

The runtime imports small source carriers and native function pages, releasing
unused modules and source strings. Generators retain their own individual pages;
deep leaves and callback functions remain resident to preserve the frame budget.
This removes the retained 87,456-byte archive and decoder while keeping all v1
features. The actual release boots and passes 55/55 diagnostic calculations in
32-bit MicroPython with a 173,360-byte total heap, using graphics shims. Physical
EVO heap/graphics/depth acceptance remains a device test. See INSTALL.md.
