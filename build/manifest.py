"""Build manifest: the src -> device name map, residency, families and budgets (DESIGN 19.1).

Desktop-only data, read by build/bundle.py, tests/conftest.py (--bundled) and the M0.5 probe
generator. Changing a name here renames the device module; nothing else needs editing:

- ``bundle.py`` rewrites ``import node as K`` to ``import CVNODE as K`` and writes the device
  tables of run.py (``DEV``, ``PARTS``, ``FAMILY``, ``CLOSURE``, ``COST``, ``LINES``,
  ``PEAKB``, ``FRAG``) from this file.
- ``bundle.check_manifest`` checks the names and keeps this file in step with the lint's
  module map (tests/support/lint.py ``ALIASES``/``RESIDENT``) and FRAMELINT's runtime keys.

The numbers are provisional. The M0.5 memory gate sets FACTOR, PEAKB, LAZYMAX and the budgets
(DESIGN 18.7); T1.15 re-measures them on the real T1 bundle.
"""

# The entry program (DESIGN 0.6): a program runs as ``from CASEVO import *``.
ENTRY = ('casevo', 'CASEVO')
ENTRY_BUDGET = (30, 1)          # max lines, KB (DESIGN 4.1)

# One row per device module. A lazy logical module longer than LAZYMAX lines is written as
# parts (DESIGN 4.3, D17); each part is a row of its own. Device names are CV plus up to 6
# letters or digits (DESIGN 0.6). "max lines" counts minified lines (one logical line each);
# "KB budget" bounds .mpy bytes x FACTOR (the size gate, DESIGN 19.2).
# Per-source ceilings below reflect measured mpy-cross output, not simultaneous RAM.
# build/release.py phases the resident sources and reports the separate heap model.
MODULES = (
    # src         device       class  max lines  KB budget
    ('node',      'CVNODE',    'R',   1200,       29),   # 28 + the giant-power hooks (6.1)
    ('nodeb',     'CVNODEB',   'R',   320,        8),
    ('alg',       'CVALG',     'R',   850,       19),
    ('parse',     'CVPARSE',   'R',   1250,       33),
    ('printer',   'CVPRINT',   'R',   900,       21),
    ('run',       'CVRUN',     'R',   640,       22),   # + memory-failure recovery (sweep)
    ('draw',      'CVDRAW',    'R',   1075,      28),   # + the MathPrint layout (MATHPRINT.md 5)
    ('ui',        'CVUI',      'R',   1400,      37),   # + the MathPrint editor and screen (MATHPRINT.md 2-7)
    # lazy (L) and lazy UI (U) modules and parts, DESIGN 4.1 and 4.3
    ('rules',     'CVRULE',    'L',   150,       4),
    ('rulesb',    'CVRULEB',   'L',   150,       4),
    ('poly',      'CVPOLY',    'L',   150,       3),
    ('polyb',     'CVPOLYB',   'L',   150,       3),
    ('polyc',     'CVPOLYC',   'L',   150,       3),
    ('norm',      'CVNORM',    'L',   150,       4),
    ('normc',     'CVNORMC',   'L',   150,       4),
    ('normb',     'CVNORMB',   'L',   150,       4),
    ('ident',     'CVIDENT',   'L',   150,       5),
    ('factor',    'CVFACT',    'L',   150,       4),
    ('factorb',   'CVFACTB',   'L',   150,       3),
    ('factorc',   'CVFACTC',   'L',   150,       3),
    ('factord',   'CVFACTD',   'L',   150,       4),
    ('solve',     'CVSOLVE',   'L',   150,       5),
    ('solveb',    'CVSOLVEB',  'L',   150,       5),
    ('solved',    'CVSOLVED',  'L',   150,       4),
    ('solvee',    'CVSOLVEE',  'L',   150,       5),
    ('solvec',    'CVSOLVEC',  'L',   150,       4),
    ('forms',     'CVFORM',    'L',   150,       3),
    ('diff',      'CVDIFF',    'L',   150,       5),
    ('series',    'CVSER',     'L',   150,       4),
    ('seriesb',   'CVSERB',    'L',   150,       5),
    ('limit',     'CVLIM',     'L',   150,       4),
    ('limitb',    'CVLIMB',    'L',   150,       4),
    ('limitc',    'CVLIMC',    'L',   150,       5),
    ('integ',     'CVINT',     'L',   150,       4),
    ('itab',      'CVITAB',    'L',   150,       3),
    ('integ2',    'CVINT2',    'L',   150,       5),
    ('integ2b',   'CVINT2B',   'L',   150,       5),
    ('integ3',    'CVINT3',    'L',   150,       5),
    ('integ3b',   'CVINT3B',   'L',   150,       3),
    ('defint',    'CVDEF',     'L',   150,       5),
    ('defintb',   'CVDEFB',    'L',   150,       6),
    ('defintc',   'CVDEFC',    'L',   150,       4),
    ('sums',      'CVSUM',     'L',   150,       5),
    ('sumsb',     'CVSUMB',    'L',   150,       4),
    ('sumsc',     'CVSUMC',    'L',   150,       4),
    ('ode',       'CVODE',     'L',   150,       5),
    ('odeb',      'CVODEB',    'L',   150,       4),
    ('odec',      'CVODEC',    'L',   150,       6),
    ('oded',      'CVODED',    'L',   150,       4),
    ('menu',      'CVMENU',    'U',   200,       7),
    ('menub',     'CVMENUB',   'U',   150,       3),
    ('catalog',   'CVCAT',     'U',   150,       8),
    ('catalogb',  'CVCATB',    'U',   150,       4),
)

# Runtime keys (R.need, R.MODS, DEPS, STRATS, CMDS) -> src module, where they differ from the
# src name (DESIGN 4.3, 15.1). Must equal tests/support/framelint.py KEYS.
KEYS = {
    'fact': 'factor', 'factb': 'factorb', 'factc': 'factorc', 'factd': 'factord',
    'ser': 'series', 'serb': 'seriesb',
    'lim': 'limit', 'limb': 'limitb', 'limc': 'limitc', 'int': 'integ',
    'int2': 'integ2', 'int2b': 'integ2b', 'int3': 'integ3', 'int3b': 'integ3b',
    'def': 'defint', 'defb': 'defintb', 'defc': 'defintc', 'sum': 'sums', 'sumb': 'sumsb', 'sumc': 'sumsc',
    'form': 'forms', 'cat': 'catalog', 'catb': 'catalogb',
}

# Families of parts (runtime keys; DESIGN 4.3, 15.1, docs/notes/FASTBOOT.md). need() loads and
# evicts a family as a unit; the first part is the family key. On the calculator every family is
# exactly one pack (PACKS below), so a family costs one archive import. A lazy module in no tuple
# here is a one-part family.
PARTS = {
    'norm': ('norm', 'normb', 'normc', 'poly', 'polyb', 'polyc', 'rules', 'rulesb', 'ident',
             'diff'),
    'fact': ('fact', 'factb', 'factc', 'factd', 'form'),
    'solve': ('solve', 'solveb', 'solvec', 'solved', 'solvee'),
    'int': ('int', 'itab'),   # strategies load one at a time (integ.EXTRA: need, then drop)
    'lim': ('lim', 'limb', 'limc', 'ser', 'serb'),
    'def': ('def', 'defb', 'defc'),
    'sum': ('sum', 'sumb', 'sumc'),
    'ode': ('ode', 'odeb', 'odec', 'oded'),
    'menu': ('menu', 'menub', 'cat'),
}

# part key -> family key, for every part that is not its family's first (need's FAMILY.get).
# Must agree with PARTS (checked).
FAMILY = {}
for _f in PARTS:
    for _p in PARTS[_f][1:]:
        FAMILY[_p] = _f
del _f, _p

# Compiled archive libraries (docs/notes/FASTBOOT.md, build/packs.py). Each row: device name,
# members, kind. A member is a src module (its home pack, load order) or 'module.function' (a
# function placed away from its home). 'ui' loads at boot; 'core' loads with the engine and
# stays resident; 'family' packs hold exactly the parts of one family (PARTS) and are loaded and
# evicted by run.need; 'soft' packs hold no state and are evicted only when memory runs short;
# 'view' packs are soft packs that only a running computation may unload; 'aux' packs hold
# computation code that never reaches the loader and gives way last.
# A pack must compile to at most PACKMAX bytes of bytecode (one TI variable).
PACKS = (
    ('CASUI', ('draw', 'ui'), 'ui'),
    ('CASK1', ('node', 'alg'), 'core'),
    ('CASK2', ('parse', 'run'), 'core'),
    # Soft packs stay cached but give way when a computation needs memory (one reload later).
    ('CASIN', ('parse.fnpre', 'parse.fnin', 'parse.mclose', 'parse.cutname', 'parse.scan',
               'parse.ti_rewrite', 'parse.ti_implicit', 'parse.untok', 'parse.tokens',
               'parse.expand_names', 'parse.approx', 'run.start'), 'soft'),
    ('CASPR', ('printer',), 'soft'),
    # Computation helpers that never reach the loader (alg imports only node): loaded on first
    # use, and the last code to give way when a family needs memory.
    ('CASAX', ('alg.cpow', 'alg.cval', 'alg.degree', 'alg.linear', 'alg.nev', 'alg.nprobe',
               'alg.nprog', 'alg.nrun', 'alg.ntol', 'alg.pco', 'alg.quadratic', 'alg.rebuild',
               'alg.size', 'alg.split_const', 'alg.subst'), 'aux'),
    # Powers too large to fold (DESIGN 5.3, 6.1): node calls it only for a giant power, or once
    # a command has built one (K.HUGE), so a session without one never loads it.
    ('CASBIG', ('nodeb',), 'aux'),
    # The interactive UI: keys, screens and 2D layout. A 'view' pack is unloaded only while a
    # computation runs (run.go), since menus load families from inside key(). busy, status,
    # panic and the drawing primitives stay in CASUI for use during and after a computation.
    ('CASUX', ('ui.key', 'ui.show', 'ui.redraw', 'ui.boot', 'ui.engine', 'ui.insert',
               'ui.enclosing', 'ui.empty_slot', 'ui.wrapped', 'draw.leaf', 'draw.row',
               'draw.frame', 'draw.large', 'draw.tree', 'draw.measure', 'draw.place',
               'draw.layout', 'draw.render', 'draw.glyph', 'ui.PLAIN', 'ui.SECOND', 'ui.ALPHA', 'ui.kmap',
               'ui.HINT', 'ui.ALIAS', 'ui.hint', 'ui.tmpl', 'ui.TN',
               # MathPrint (docs/notes/MATHPRINT.md 9.2): the engine-free editor layout
               'ui.tidy', 'draw.TPL', 'draw.TGAP', 'draw.MPREC',
               # the MathPrint editor keys (milestone B)
               'ui.emodel', 'ui.edkey', 'ui.picker', 'ui.edins', 'ui.eddel', 'ui.edmove',
               'ui.edvert', 'ui.epaint', 'ui.paste', 'ui.empty_map', 'ui.edslot', 'ui.edterm', 'ui.leave',
               'ui.wrapend',
               'ui.put', 'ui.tput', 'ui.bmatch', 'ui.spans', 'ui.keep', 'ui.TMPL',
               'draw.MFNT', 'draw.mlayout', 'draw.mflat', 'draw.mcall', 'draw.mname', 'draw.mstop', 'draw.mlex',
               'draw.mparse', 'draw.mpush', 'draw.mshut', 'draw.mreduce', 'draw.mbox', 'draw.tleaf',
               'draw.mplace', 'draw.mmark', 'draw.mrender'), 'view'),
    ('CASALG', ('poly', 'polyb', 'polyc', 'rules', 'rulesb', 'ident', 'norm', 'normb', 'normc',
                'diff'), 'family'),
    ('CASFAC', ('factor', 'factorb', 'factorc', 'factord', 'forms'), 'family'),
    ('CASSOL', ('solve', 'solveb', 'solvec', 'solved', 'solvee'), 'family'),
    ('CASINT', ('itab', 'integ'), 'family'),
    ('CASIN2', ('integ2',), 'family'),
    ('CASIN2B', ('integ2b',), 'family'),
    ('CASIN3', ('integ3',), 'family'),
    ('CASIN3B', ('integ3b',), 'family'),
    ('CASLIM', ('series', 'seriesb', 'limit', 'limitb', 'limitc'), 'family'),
    ('CASDEF', ('defint', 'defintb', 'defintc'), 'family'),
    ('CASSUM', ('sums', 'sumsb', 'sumsc'), 'family'),
    ('CASODE', ('ode', 'odeb', 'odec', 'oded'), 'family'),
    ('CASMNU', ('catalog', 'menu', 'menub'), 'family'),
)
PACKMAX = 60000
# Packs built tight (build/packs.py, build/archive.py): a function that names a never-unloaded
# pack 3+ times reads it through a local alias, ints bound once at module level are read as
# literals, HOTBUILTINS are bound as pack globals (a builtin lookup otherwise misses the module
# dict first, and a nearly full MicroPython dict probes up to its first empty slot), and
# mpy-cross -O3 drops the line-number tables. The UI packs only: tracebacks from them then
# report line 1 (function names remain), so release.json's line map no longer locates them.
TIGHT = ('CASUI', 'CASUX')
HOTBUILTINS = ('len', 'range', 'min', 'max')
# run.room(phase): the soft pack each phase loads, so memory is made for it first.
ROOMS = {'input': 'CASIN', 'print': 'CASPR', 'layout': 'CASUX'}
# Loader tables written into the calculator's run module (build/release.py). Heap estimates are
# bytecode bytes x factor + fixed: 32-bit measurements put packs at 1.1 to 1.6 times their
# bytecode (docs/notes/FASTBOOT.md). Below SHEDAT free bytes after parsing, idle soft packs
# unload before the computation starts. FRAG is the slack each load asks for.
PACKCOST = (1.25, 512)
ROOMCOST = (1.4, 512)
SHEDAT = 65536
PACKFRAG = 2048

# Memory model (DESIGN 4.1, 18.1, 18.7). CALIBRATION says where the numbers come from:
# 'provisional' = the DESIGN 18 estimates, because the M0.5 device run (PRBMEM on the
# PRBL100/200/300 modules) is still pending. `python build/genprobe.py --derive FILE --apply`
# writes the measured values here (probe/README-MEM.md); T1.15 re-measures the real T1 bundle.
CALIBRATION = 'provisional'
FACTOR = 1.8      # RAM bytes per .mpy byte; set by the M0.5 gate (section 18.7)
PEAKB = 80        # compile peak in bytes per source line; set by the M0.5 gate
LAZYMAX = 200     # lines per lazy part. Was 150 while parts compiled on the calculator; packs
                  # are precompiled (FASTBOOT.md), so PACKMAX and measured heap now bind
NMAX = 768        # node slots preallocated at boot (DESIGN 5.1); set by the M0.5 gate
EVICT = 'modules'           # eviction: 'modules', 'dict' (__dict__.clear() first) or 'none'
DRAW_EVICTABLE = False      # ladder step 4 (DESIGN 18.8): CVDRAW evictable during a command
FRAG = 3072       # fragmentation allowance per import, bytes
MPYB = 12.5       # .mpy bytes per minified line [M]: COST estimate when mpy-cross is missing
