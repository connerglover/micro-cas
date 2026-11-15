# Step-by-step working (2026-11-14)

User request: other third-party CAS programs show "steps" (FlowCE, CalcPlex); add them in the
manner of FlowCE, without spending the EVO's heap. Branch `steps`.

## What FlowCE does (read from its source, commit 68cddf6)

- Steps are **regenerated on demand**, never logged: its steps screen parses the typed input
  again and a separate walk decides which rule explains each part. The CAS still computes every
  result; a chain is shown only once checked.
- A step is a rule number and its parts, with the math line built only when it is drawn.
- `enter` on the empty input line opens a scrolling steps page: numbered rule titles with 2D
  working, the answer last; an input it cannot explain reads "No steps for this one".

MicroCAS follows that shape. CalcPlex publishes no source; its page describes the same entry
(`ENTER: steps` under an answer, `clear` to return).

## Design

1. **Nothing is recorded while a command runs.** An ordinary command differs from before in
   three small ways: `run.start` sets the record flag `F_STEPS` (32) when the line's last
   command is one a walk explains, a successful substitution writes its `u` into one list cell
   (`integ.USUB`), and `go` empties `run.STEPS`. A session that never asks for steps never
   imports a steps pack.
2. **A steps job.** `run.go(('steps', i))` parses history entry `i` again through the usual
   input pipeline, in the entry's own angle mode. `run.start` replaces the entry's last command
   (`diff`, `integrate`, `solve`, `limit`, and the macros that expand to them) with the
   registry entry `'?'`, which it writes for the job and `go` removes again: `'?'` cannot be
   typed. `g_eval` therefore evaluates the arguments exactly as before and hands them to that
   command's walk, `g_walk`. An entry that used `ans()`, a definition or a `purge` is refused:
   running it again would not repeat it.
3. **A walk only builds nodes**: a title in `run.STEPS` and a pair `lhs, rhs` per step,
   returned as one list node. The texts are made afterwards by `printer.steps`, at the point
   where `go` has already let the command's families give way to the printer, exactly as for an
   answer. (The first version printed each line during the walk; the printer pack then sat
   beside the integration families and three of nine steps jobs ran out of memory at the
   189,776-byte heap.) A step is two strings, `(title, 'lhs=rhs')`, in the history's own text.
   Caps: 24 steps, 560 nodes in the table when a walk stops, 150 characters per line and 2,400
   in all (a line past a cap keeps its title).
4. **The answer is not computed again.** The last step is the entry's own answer text. A
   definite integral is explained by its antiderivative's steps and then `Evaluate at the
   bounds` with the stored answer, so the definite-integral path (CASDEF, limits at the
   endpoints, quadrature) never runs for steps.
5. **The session is untouched**: no history entry, no Ans, no store. `finish` returns at once
   for a steps job and empties `STEPS` on any failure.
6. **Four small packs**, each a loader family of its own: CASSTD (`sdiff`), CASSTI (`sint`),
   CASSTA (`salg`: equations and limits) and the screen CASSTV (`stepview`). A walk holds no
   steps code but its own, about 2 KB, beside the command's families; with one 8 KB pack for
   everything the two heaviest integrals' steps needed about 190 KB.
7. **The screen** (`stepview.view`, a modal page like the menus) lays out only the steps on
   the screen with the engine-free `draw.mlayout` (the history-input layout and its cache) and
   keeps no layout of its own. A line too wide for one row is cut at its `=`, and a side still
   too wide at the `+` or `-` nearest its middle; anything past the layout caps is wrapped
   text. Before its first page, and before it returns to the home page, it makes room as the
   loader does: the least recently used family gives way until 12 KB are free. `ui.show`
   empties `run.STEPS` when the screen closes.

## The name pool (`stepview.warm`)

MicroPython 1.12 keeps interned names (qstrs) in pools that double: 20, 40, ... 640, 1,280
entries. The pool for names 1,261 to 2,540 is **one block of 5,136 bytes**, allocated for good
at the moment name 1,261 is interned, wherever a run that long is free. Its failure reads
`memory allocation failed, allocating 1280 bytes`: the number is the pool's entries.

Measured on the pinned runtime (`micropython.qstr_info()` at every key): 457 names at boot,
1,017 after the engine and a first derivative, about 129 more for the menu pack, 1,281 at the
end of a ten-command session on `main`. Every such session crosses the line. On `main` the
test session stood at 1,250 names after its first menu and crossed inside the next command;
with this branch's 17 more resident names it crossed inside the menu import, outside a
command, beside the view pack, where the heap held 47 KB free and no run of 5 KB: the menu
could not open, and could not on any later try either.

The steps screen and the menus are imported outside a command. A walk's packs are imported
inside one, but the line met there fails that command at an arbitrary point, and when the
heap is full of the command's own pinned families the retry meets it again (measured at
192,000: two steps jobs in a row reported Out of memory). So before the first steps job of a
session `go` empties the heap of every lazy pack and `stepview.warm` crosses the line there,
where the block lands low: the screen pack is imported (that is the call), the menu pack is,
and then spare names are looked up (`getattr((), '_0', None)`: a name looked up is a name
interned) until the free heap drops by the block, at most 80 of them. 73 were needed after the
lightest session (one derivative); all 80 are spent, about 0.8 KB, when the session crossed
the line earlier. The code lives in the screen's pack, so none of it is resident.
`build/shrink.py` accepts a computed lookup on a tuple or list literal, which reaches no
module attribute.

Cost: the first `ENTER: steps` of a session imports two more packs (CASSTV 1.3 KB, CASMNU
8.4 KB) and reloads the command's families. The pool itself is no extra memory: the session
would have allocated it anyway, at a moment nobody chose.

**The same line exists without steps.** A session on `main` that meets it while a menu is
imported on a split heap fails in the same way; that it did not in the tested session is a
margin of ten names. Crossing the line for every session at engine load would cost about 7 KB
there (the pool, and some 220 spare names) and would break the tuned 177,456-byte gate, so it
is not done here; it is a decision for a later change.

## Walkers

| command | module | rules shown |
| --- | --- | --- |
| `diff` | `sdiff` | Sum rule, Constant multiple, Product rule, Quotient rule, Power rule, Chain rule, Known derivative, Logarithmic differentiation; an order above 1 is one line per derivative (up to 6); an equation (implicit differentiation): Differentiate both sides, Chain rule: y depends on x, Solve for the derivative, then Differentiate again per further order |
| `integrate` | `sint` | Integral of a constant, Constant multiple, Sum rule, Power rule, Known integral, Substitution / Rewrite the integral / Substitute back, Integration by parts, Trig identities, Partial fractions (then its terms one by one), Radical formula; then Answer (+C) or Evaluate at the bounds |
| `solve` | `salg` | Move all terms to one side, Multiply by the denominator, Isolate the variable term / Divide both sides, Factor / A factor is zero, Standard form / Read off a, b, c / Quadratic formula / Discriminant / With these numbers / And with the other sign |
| `limit` | `salg` | Direct substitution, L'Hopital's rule (0/0 and oo/oo, at most three times) |

The integral walk mirrors `integ.g_int` and calls the same strategies in the same order, so a
line appears only for a primitive the engine found and checked (`integ.g_check`). A limit chain
carries a check pair that `printer.steps` compares with the entry's answer: a chain that ends
anywhere else shows nothing. Derivative lines are identities by construction.
`tests/test_steps.py` checks every derivative line by evaluating both sides and every integral
line by differentiating them.

No steps (the status row reads `No steps for this one`): integrals with no elementary
primitive, floor/ceil integrands, systems, inequalities, non-polynomial equations, polynomial
equations of degree 3 or more that do not factor, limits that need series or one-sided
analysis, approximate answers, and every other command.

## Keys

- After an exact answer whose last command has a walk, the hint row reads `ENTER: steps`
  (beside the decimal line when there is one). ENTER on the empty line opens the steps. For any
  other entry, and after CLEAR dismissed the answer, ENTER on the empty line repeats the last
  input as before.
- On the steps screen: up/down move one step, right a page, left three steps back; CLEAR,
  ENTER or F1 return. A key that moves nothing repaints nothing.

## Memory

Measurements: [FASTBOOT.md](FASTBOOT.md#steps-2026-11-14) and [STATUS.md](../STATUS.md).

What did not work, for whoever changes this next:

- Evicting families around the steps screen (before it, after it, or all of them at the end of
  the job) made later imports fail more often, not less: a large free region is where small
  long-lived objects (layout caches, the entry's model) end up spread, while a pack evicted
  only when its space is needed leaves a clean hole.
- Dropping the UI's layout caches when an import fails did not help; the failure was the name
  pool above.
- Importing the walker packs once at engine load made every heap pass, but only by moving the
  name-pool line to a lucky moment, at the price of four imports in every session.
