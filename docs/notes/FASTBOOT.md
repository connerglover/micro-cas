# Fast boot and packed engine (2026-10-11)

## Device report that started this

The v1 package (236 archived `.8mp2` libraries plus two RAM launchers) took
**5 min 30 s** on the user's EVO before failing with:

```
File "CVP00051.py", line 123, in aQ
File "CVP00051.py", line 64, in aZ
TypeError: function takes 1 positional arguments but 3 were given
```

Line 64 of the CVP00051 initializer is `G.setColor(*COLORS['BG'])`, the first
drawing call of `ui.redraw` reached from `ui.boot`. **`ti_graphics.setColor`
takes one positional argument on the EVO.** The desktop shim accepted
`setColor(r, g, b)`, and PROBE7 (which would have settled the signature) was
never run, so every ti_graphics call in the UI was an unverified assumption.

## Where the time went (measured, native MicroPython v1.12)

| run | archive imports | notes |
| --- | --- | --- |
| boot to first key | 51 | 62,087 bytecode bytes; host compute about 10 ms |
| `2+3` | 25 | function pages |
| one definite integral | 332 to 882 | CVF pages evict each other on every import |
| seven UI calculus cases | 2,806 | 169 distinct files |

Host compute for boot is about 10 ms; the EVO runs the same 20,000-iteration
loop about 75 times slower than an Apple M3 host (66 ms versus 0.89 ms), so
compute explains about one second of the 330 s boot. The remainder is import
overhead: about **6.5 s per archive import** on the device. 62 KB in 330 s rules
out a per-byte transfer cost; a fixed per-import cost, or a lookup cost that
grows with the number of files on the calculator, both fit. Either way the fix is
the same: **few files and few imports**.

Function paging (`build/function_pages.py`) made every call to a paged function
an `__import__`, and importing a page deleted every other page from
`sys.modules`, so alternating calls re-imported pages continuously. Each
trampoline step also purged all pages and ran `gc.collect()`.

## 32-bit heap measurements

A local 32-bit MicroPython v1.12 (unix port compiled to wasm32 with emscripten,
Asyncify register scanning for the GC) reproduces the CI numbers: CVTEST on the
current package ends with 66,768 bytes free at a 173,360-byte heap (CI recorded
66,704). Whole, unpaged modules cost (bytes of heap, 32-bit):

| module | heap | module | heap |
| --- | --- | --- | --- |
| node | 29,696 | rules + rulesb | 4,240 |
| alg | 16,224 | poly + polyb + polyc | 6,128 |
| parse | 23,136 | ident | 3,664 |
| printer | 13,760 | norm + normb + normc | 7,488 |
| run | 16,912 | diff | 2,960 |
| draw | 10,576 | itab + integ | 4,208 |
| ui | 7,488 | | |

Identifier shrinking saves only about 3 %; bytecode, not names, dominates.
The namespace-dictionary initializers used by v1 add 10 to 20 % to heap and
bytecode. Whole modules with the old eager UI leave 41,648 bytes free after boot
and fail heavy commands, so the memory manager has to evict at pack granularity.

## Architecture

1. **UI first.** `CASEVO` imports only the UI pack and draws immediately. The
   engine loads when it is first needed (first ENTER, or a menu that needs it),
   with a status line showing what is loading and how long it took.
2. **Graphics through `ti_draw`** with the semantics CalcPlex documents from the
   device: 320 x 210 pixels, `get_screen_dim()` returns `[319, 209]`;
   `draw_text(x, y, s)` puts ink in rows `y-17` to `y-3`; a fixed-width font of
   10 pixels per character (31 characters per line); `fill_rect(x, y, w, h)`
   fills the interior only, so an exact area is `fill_rect(x-1, y-1, w+1, h+1)`
   and width/height below 2 raise; `set_color(r, g, b)` and `clear()` are slow
   (cache the current color, paint with `fill_rect`).
3. **Packs.** Device modules are merged into a small number of real
   MicroPython modules ("packs") with plain globals. Cross-module attribute
   access inside a pack becomes a plain global; access to another pack goes
   through that pack module. Each pack is imported once and stays in
   `sys.modules` until memory is needed. There are no function pages and no
   phase payloads.
4. **Families are packs.** The run-time loader (`run.need`) loads a family by
   importing its pack. Eviction is LRU at pack granularity and happens only when
   a load needs memory. A command that fails with MemoryError evicts every
   unpinned family and is retried once.
5. **Observability.** The UI records boot and pack load times
   (`time.monotonic` / `ticks_ms`, whichever exists) and shows them, so the next
   device report contains the real import cost.

## Contracts between the parts

- `src/casevo.py` imports `ti_system` and `ui` only. It obtains the engine from
  `U.engine()` (at depth 1, before calling `R.go(job)`), so `R.go` stays at
  depth 1 and the frame budget is unchanged.
- `ui.py`, `draw.py`, `menu.py` and `menub.py` never import engine modules
  (`node`, `alg`, `parse`, `printer`, `run`, families) at module level. The UI
  works with no engine loaded (empty history, default settings).
- Pack membership lives in `build/manifest.py`. A pack is at most about 60 KB
  of compiled bytecode (TI variable limit) and has a device name
  `[A-Z][A-Z0-9]{0,7}`.
