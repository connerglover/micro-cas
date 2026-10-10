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
MODULES = (
    # src         device       class  max lines  KB budget
    ('node',      'CVNODE',    'R',   520,       12),
    ('alg',       'CVALG',     'R',   300,       7),
    ('parse',     'CVPARSE',   'R',   440,       10),
    ('printer',   'CVPRINT',   'R',   330,       7),
    ('run',       'CVRUN',     'R',   300,       7),
    ('draw',      'CVDRAW',    'R',   350,       8),
    ('ui',        'CVUI',      'R',   400,       9),
    # lazy (L) and lazy UI (U) modules and parts, DESIGN 4.1 and 4.3
    ('rules',     'CVRULE',    'L',   150,       3),
    ('rulesb',    'CVRULEB',   'L',   150,       3),
    ('poly',      'CVPOLY',    'L',   150,       3),
    ('polyb',     'CVPOLYB',   'L',   150,       3),
    ('polyc',     'CVPOLYC',   'L',   150,       3),
    ('norm',      'CVNORM',    'L',   150,       4),
    ('normb',     'CVNORMB',   'L',   150,       4),
    ('ident',     'CVIDENT',   'L',   150,       3),
    ('factor',    'CVFACT',    'L',   150,       3),
    ('factorb',   'CVFACTB',   'L',   150,       3),
    ('solve',     'CVSOLVE',   'L',   150,       3),
    ('solveb',    'CVSOLVEB',  'L',   150,       3),
    ('solvec',    'CVSOLVEC',  'L',   150,       3),
    ('forms',     'CVFORM',    'L',   150,       3),
    ('diff',      'CVDIFF',    'L',   150,       3),
    ('series',    'CVSER',     'L',   150,       4),
    ('seriesb',   'CVSERB',    'L',   150,       4),
    ('limit',     'CVLIM',     'L',   150,       4),
    ('limitb',    'CVLIMB',    'L',   150,       4),
    ('integ',     'CVINT',     'L',   150,       4),
    ('integb',    'CVINTB',    'L',   150,       4),
    ('itab',      'CVITAB',    'L',   150,       3),
    ('integ2',    'CVINT2',    'L',   150,       4),
    ('integ2b',   'CVINT2B',   'L',   150,       4),
    ('integ3',    'CVINT3',    'L',   150,       3),
    ('integ3b',   'CVINT3B',   'L',   150,       3),
    ('defint',    'CVDEF',     'L',   150,       4),
    ('defintb',   'CVDEFB',    'L',   150,       4),
    ('sums',      'CVSUM',     'L',   150,       4),
    ('sumsb',     'CVSUMB',    'L',   150,       4),
    ('ode',       'CVODE',     'L',   150,       3),
    ('odeb',      'CVODEB',    'L',   150,       3),
    ('odec',      'CVODEC',    'L',   150,       3),
    ('menu',      'CVMENU',    'U',   150,       3),
    ('menub',     'CVMENUB',   'U',   150,       3),
    ('catalog',   'CVCAT',     'U',   150,       4),
    ('catalogb',  'CVCATB',    'U',   150,       4),
)

# Runtime keys (R.need, R.MODS, DEPS, STRATS, CMDS) -> src module, where they differ from the
# src name (DESIGN 4.3, 15.1). Must equal tests/support/framelint.py KEYS.
KEYS = {
    'fact': 'factor', 'factb': 'factorb', 'ser': 'series', 'serb': 'seriesb',
    'lim': 'limit', 'limb': 'limitb', 'int': 'integ', 'intb': 'integb',
    'int2': 'integ2', 'int2b': 'integ2b', 'int3': 'integ3', 'int3b': 'integ3b',
    'def': 'defint', 'defb': 'defintb', 'sum': 'sums', 'sumb': 'sumsb',
    'form': 'forms', 'cat': 'catalog', 'catb': 'catalogb',
}

# Families of parts (runtime keys; DESIGN 4.3, 15.1). need() loads and evicts a family as a
# unit; the first part is the family key. A lazy module in no tuple here is a one-part family
# (ident, itab, forms, diff, int2, int2b, int3, int3b, menu, menub, cat, catb).
PARTS = {
    'rules': ('rules', 'rulesb'),
    'poly': ('poly', 'polyb', 'polyc'),
    'norm': ('norm', 'normb'),
    'fact': ('fact', 'factb'),
    'solve': ('solve', 'solveb', 'solvec'),
    'ser': ('ser', 'serb'),
    'lim': ('lim', 'limb'),
    'int': ('int', 'intb'),
    'def': ('def', 'defb'),
    'sum': ('sum', 'sumb'),
    'ode': ('ode', 'odeb', 'odec'),
}

# part key -> family key, for every part that is not its family's first (need's FAMILY.get).
# Must agree with PARTS (checked).
FAMILY = {
    'rulesb': 'rules', 'polyb': 'poly', 'polyc': 'poly', 'normb': 'norm', 'factb': 'fact',
    'solveb': 'solve', 'solvec': 'solve', 'serb': 'ser', 'limb': 'lim', 'intb': 'int',
    'defb': 'def', 'sumb': 'sum', 'odeb': 'ode', 'odec': 'ode',
}

# Memory model (DESIGN 4.1, 18.1, 18.7). Provisional until the M0.5 gate.
FACTOR = 1.8      # RAM bytes per .mpy byte; set by the M0.5 gate (section 18.7)
PEAKB = 80        # compile peak in bytes per source line; set by the M0.5 gate
LAZYMAX = 150     # lines per lazy part; set by the M0.5 gate
FRAG = 3072       # fragmentation allowance per import, bytes
MPYB = 12.5       # .mpy bytes per minified line [M]: COST estimate when mpy-cross is missing
