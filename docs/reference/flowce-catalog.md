# FlowCE command catalog, menus, keys and input rules: reference

What FlowCE shows the user and how it reads what the user types: the command catalog and menus,
the key bindings, the input preprocessing (implicit multiplication, Ans, the leading-operator rule,
key-to-text translation, `sto→`), and the settings and themes. Where cas-evo should copy FlowCE and
where it should not.

- Source: the FlowCE clone at `C:\Users\conner\.cache\cas-evo-ref\FlowCE`, commit `c32720d`
  (FlowCE 1.9, `src/focus.h:11`). Line numbers refer to that tree. All paths are relative to it.
- Build analyzed: the released English build. The makefile sets `APPLANG=en` and
  `FEATURE_DEFS = -DWITH_LAPLACE -DWITH_DESOLVE -DWITH_EQW -DWITH_PLOT` (`makefile:13,23-38`,
  `mkappen:7`). Units, `WITH_QUAD`, `WITH_SHEET` and `WITH_TABVAR` are off. English sets
  `lang 0` (`src/console.h:28-30`, `src/main.h:12-14`).
- FlowCE has two UIs: the original KhiCAS console and FlowCE's own **Focus** interface
  (`focus_on` is the constant 1, `src/focus.h:10`). This document describes **Focus**. It
  mentions a KhiCAS path only where Focus still uses it, or as a fallback.
- Related doc: `docs/reference/flowce-answer-format.md` covers the output side (term order,
  `+ C`, the decimal line, the F4 forms, message strings, 2D layout). This document only
  summarizes those topics where the input side needs them.

Scope tags in the tables:

| tag | meaning |
|---|---|
| **T1** | in the cas-evo T1 milestone (exact arithmetic, simplify/expand/factor, solve, Ans, sto→, history) |
| **T2** | in T2 (derivatives, limits, integrals, partial fractions, Taylor) |
| **T3** | in T3 (improper integrals, series sums, Riemann sums, ODEs, gradients, multiple integrals, polar/parametric areas) |
| **opt** | not in the settled scope, but cheap once the core exists (it reuses internal algorithms, or is a thin alias). Add it to the catalog if there is space. |
| **out** | out of scope for v1 (graphing, programming, lists, matrices, number theory, drawing, display options, transforms) |

---

## 1. How a command reaches the user

FlowCE has six ways to insert a command. All of them insert **plain giac text** into the one edit
line. The 2D display is computed from that text (`src/mathinput.cc:1-6`).

| surface | open with | what it inserts | source |
|---|---|---|---|
| F1-F5 popovers | F1 to F5 | a template with the caret placed in it, or an action | `src/focus_menu.cc:25-70,600-621` |
| math-key popover | `math` | a 2D template (fraction, root, integral, ...) | `src/focus_menu.cc:61-65` |
| 2nd/alpha F-key menus | `2nd`/`alpha` + F1-F5 | `name(`, which becomes a call template | `src/console.cc:3408`, `src/focus_menu.cc:514-598` |
| command search | `▼` on the edit line, `2nd 0` (catalog), *more → All commands* | the catalog entry's `insert` text as a call template | `src/focus_catalog.cc:492-560`, `src/console.cc:1941-1993,2427-2432,2910-2918` |
| F1/F2 "action" rule | an F1/F2 popover item when the caret is at the end of the line, or the line is empty | `factor(<line>)` or `factor(ans())` | `src/console.cc:2300-2333` |
| typing | letters, digits, function keys | plain text | `src/console.cc:1804-1919,2489-2498` |

### 1.1 Catalog entry format

`struct catalogFunc { name; insert; desc; example; example2; category; }` (`src/menuGUI.h:67-74`).

- `name` is the signature shown to the user, e.g. `diff(f,var,[n])`. A name that starts with a
  space is a programming construct, and the Focus search hides it (`src/focus_catalog.cc:216`).
- `insert` is the text inserted. When it is null, FlowCE inserts `name` up to and including the
  first `(` (`src/focus_catalog.cc:61-67`, `src/menufr.cc:1018-1030`).
- `desc` is the help text. The Focus UI shows only its **first sentence**: the text up to the
  first `.` that is followed by a space or by the end of the text
  (`src/focus_catalog.cc:271-282`). The tables below reproduce this behavior exactly. It has
  quirks: `solve` shows "Exact solving of equation w.r.t." and `approx` shows "Approx.".
- `example` and `example2`: an example that starts with `#` is a complete expression. Otherwise
  the shown example is `insert + example + ")"`. FlowCE also uses the example as given when it
  already starts with the command name, or when `insert` does not end with `(`
  (`src/focus_catalog.cc:253-269`). The Focus UI shows **only `example`**. `example2` appeared
  only in the old KhiCAS catalog help (F2/F3 there, `src/menufr.cc:1180-1275`).
- `category` holds up to three category codes, one per byte (`src/menuGUI.h:76-94`).

### 1.2 Command search (`src/focus_catalog.cc`)

- The search is a full-screen list with a search field ("Search commands" placeholder, `:326`)
  and a match count ("N matches", `:328-333`). It shows 7 rows of 19 px: the name in bold, then
  `desc` cut with an ellipsis (`:25-26,336-346`). The footer shows the selected entry's full
  signature, the hint "enter  insert", and the example drawn in 2D (`:348-361`). When nothing
  matches it shows `No command matches "<q>"` (`:381-387`).
- Opening the search (`src/console.cc:1964-1983`): the query is the name being typed before the
  caret. A trailing `(` is dropped (`sin(` gives the query `sin`). Leading digits are skipped
  (`2sin` gives `sin`). When the word is shorter than 2 characters, the search opens empty. The
  chosen text replaces that word.
- Matching (`:210-251`) puts each entry in one class:
  - class 0: the name (up to its `(`) starts with the query;
  - class 1: the name contains the query;
  - class 2: `desc` contains the query (case-insensitive);
  - class 3: no match, so the entry is hidden.

  The results show class 0, then class 1, then class 2. Inside a class, entries keep catalog
  order. With an empty query, names that start with a letter come first, then symbols.
- Tabs are on F1-F5 (`:45-48`):

  | key | tab | categories |
  |---|---|---|
  | F1 | all | every category |
  | F2 | algebra | ALGEBRA, POLYNOMIAL, SOLVE |
  | F3 | calculus | CALCULUS |
  | F4 | trig | TRIG |
  | F5 | numbers | ARIT, REAL, COMPLEXNUM |

- Keys (`:508-551`):
  - Alpha is locked, so plain keys type letters. `2nd` makes the next key a digit.
  - `(-)` types `_`. The query holds at most 15 characters. `del` removes one character.
  - `▲`/`▼` move the selection. `◀`/`▶` page by 7 rows.
  - `enter` inserts the selected entry.
  - `clear` or `del` on an empty query closes the search. `▲` at the top also closes it, but
    only when nothing was typed.
- After the search closes, a `name(` insert goes into the 2D line as a **call template**
  (`src/console.cc:1956-1958`, §1.3).

### 1.3 Call templates, argument labels, and the help line

- **Template** (`src/focus_catalog.cc:78-138`). A signature is split at its top-level commas.
  An argument is **required** unless it is `..` (more of the same), or it is a trailing optional
  argument in brackets (`[n]`, `[a,b]`). When every argument is bracketed, all are required
  (`ichinrem([a,m],[b,n])`). The template has one empty slot per required argument, and a list
  argument keeps its brackets. Examples: `irem(` gives `irem(,)`, `diff(` gives `diff(,)` (the
  `[n]` is dropped), `linsolve(` gives `linsolve([],[])`. The caret goes into the first slot.
  A command with no catalog signature is inserted as `name()` with the caret inside
  (`src/console.cc:1921-1939`).
- **Argument labels** (`src/focus_catalog.cc:140-154`). Empty slots of commands with 2 or more
  required arguments show the argument name in gray: `powmod(a, n, p)`. Optional arguments lose
  their brackets. Single-argument commands show a plain box.
- **Help line under the edit line** (`src/focus_catalog.cc:167-188,271-282`,
  `src/focus.cc:294-295,385-391`). When the caret is inside a call whose signature has at
  least 2 required arguments, two centered lines appear under the edit line:
  - line 1: the first sentence of `desc`, in gray;
  - line 2: `e.g.  ` followed by the example, in ink.

  The help line does not appear for calls that are drawn as 2D templates (integral, `d/dx`,
  `lim`, Σ, `sqrt`, `surd`, `abs`, `exp`, `series` with 4 arguments), because "what it does is
  plain to see" (`src/mathinput.cc:274-288`).
- **ENTER with an empty slot** (`src/console.cc:2210-2245,2995-3006`): FlowCE does not evaluate.
  It moves the caret to the empty box and shows "fill in the empty box". These count as empty:
  - `(,` `,,` `,)`;
  - `()` after one of `sqrt abs surd integrate int diff sum limit exp ln log log10 sin cos tan`;
  - a bare `()`;
  - a line that ends with `+ - * / ^ (`.

### 1.4 F1/F2 action rule (`src/console.cc:2300-2333`)

This rule applies to these popover items: `solve(` `factor(` `expand(` `simplify(`
`partfrac(` `integrate(` `diff(` `limit(` `series(` (not `sum(`: its index is `k`).

- When the caret is at the **end of a non-empty line**, the whole line becomes the first
  argument. `x^2-1` then *Factor* gives `factor(x^2-1)`. `x^2` then *Antiderivative* gives
  `integrate(x^2,x)`.
- When the **line is empty** and a result is selected or shown large, the item applies to Ans:
  `factor(ans())`.
- In all other cases the template is inserted.
- After the insert, the caret goes to the first empty slot (`,,` or `,)`):
  `integrate(x^2,x,|,)`, `limit(1/x,x,|)`.
- ENTER then evaluates as usual.

---

## 2. Menus

### 2.1 Popovers (Focus), plain F-keys and `math` (`src/focus_menu.cc:25-70`)

A popover is a card over the dimmed stage. Each item is a template plus a `back` count: after
the insert, the caret moves `back` characters to the left, which places it in the first slot.
Previews are drawn in 2D with an empty box for each slot.

**F1 algebra** (list): numbered rows with a 2D preview and a label.

| # | template (caret = `\|`) | label | scope |
|---|---|---|---|
| 1 | `solve(\|,x)` | Solve for x | T1 |
| 2 | `factor(\|)` | Factor | T1 |
| 3 | `expand(\|)` | Expand | T1 |
| 4 | `simplify(\|)` | Simplify | T1 |
| 5 | `partfrac(\|)` | Partial fractions | T2 |
| 6 | `(\|)/()` | Fraction | T1 |

**F2 calculus** (cards, 2 columns, each a 2D preview over a label):

| # | template | label | scope |
|---|---|---|---|
| 1 | `integrate(\|,x)` | Antiderivative | T2 |
| 2 | `integrate(\|,x,,)` | Definite integral | T2 (improper bounds: T3) |
| 3 | `diff(\|,x)` | Derivative | T2 |
| 4 | `limit(\|,x,)` | Limit (giac's `limit(f,x,a)`, not the catalog's `x=a`) | T2 |
| 5 | `sum(\|,k,,)` | Sum | T3 |
| 6 | `series(\|,x,0,5)` | Taylor series (order 5 by default) | T2 |

**F3 trig** (grid, 3 columns): `sin() cos() tan() / asin() acos() atan() / sec() csc() cot() /
sinh() cosh() tanh()`, each with the caret inside. sin-cot and their inverses are **T1**. The
hyperbolic functions are **opt**.

**F4 symbols** (grid, 4 columns; `src/focus_menu.cc:47-52`). F4 acts as **forms** instead when
a result is selected or shown large (`src/console.cc:2356-2366`; see
`flowce-answer-format.md` §6).

| row | items |
|---|---|
| 1 | `pi` `e` `oo` `theta` |
| 2 | `sqrt(\|)` `surd(\|,)` (n-th root) `abs(\|)` `!` (preview `n!`) |
| 3 | `^(\|)` `exp(\|)` `ln(\|)` `(\|)/()` |
| 4 | `=` `<=` `>=` `!=` |

All of these are T1, except `theta`, which is only a symbol (T3 polar).

**F5 more** (list of actions; `src/focus_menu.cc:53-60`, dispatch at `src/console.cc:2377-2426`):

| label | hint | action | scope |
|---|---|---|---|
| Graph | line or answer | plots the line or the selected/large answer as `plot(...)`. It refuses an empty line ("Type a function of x first") and an equation ("Not a function of x"). | out |
| All commands | search | opens the command search with an empty query | T1 |
| Paper or Night | theme | switches the theme at once | T1 (cas-evo: F3 settings) |
| Other plots | kinds | KhiCAS's plot menu (classic F3, below) | out |
| File | sessions | KhiCAS's File menu (save/load sessions, scripts, ...) | out |
| Clear history | | asks "Clear the history?", then clears | T1 |

**`math` key** (grid, 3 columns; `src/focus_menu.cc:61-65`): `()/()` `sqrt()` `abs()` /
`integrate(,x)` `integrate(,x,,)` `diff(,x)` / `limit(,x,)` `sum(,k,,)` `^()`.

Non-Focus fallback for `math` (`src/console.cc:2254-2279,2588-2606`): a text list with these
items:
- `fraction  a/b`
- `n-th root`
- `|x| absolute value`
- `integral`
- `integral from a to b`
- `derivative d/dx`
- `sum`
- `limit`
- `trigonometry ...`, a submenu: `sec`, `csc`, `cot`, `asin (sin^-1)`, `acos`, `atan`, `sinh`,
  `cosh`, `tanh`, `expand: sin(2x)->2sin.cos` (`texpand(`), `linearize: sin^2->cos(2x)`
  (`tlin(`), `collect: sin+cos->1 term` (`tcollect(`), `rewrite with sin`/`cos`/`tan`
  (`trigsin(` `trigcos(` `trigtan(`)
- `all commands ...`

Popover keys (`src/focus_menu.cc:248-295`):
- The arrows move the selection and wrap around, as in TI menus.
- `1`-`9` pick the item with that number. `enter` picks the selected item.
- `clear` cancels.
- The popover's own F-key closes it. Another F-key or `math` switches to that popover.

### 2.2 2nd and alpha F-key menus (KhiCAS menus drawn as Focus cards)

The menu configuration string is at `src/console.cc:3408` (English, `WITH_PLOT`). Menu index:
`F6`-`F10` are 2nd+F1-F5, `F11`-`F15` (`;` `<` `=` `>` `?`) are alpha+F1-F5, `F16` (`@`)
is `stat` (`src/k_csdk.c:213-222`, `src/console.cc:3172-3206,3434-3444`).

Focus draws at most 9 entries per menu, as a 3-column grid of cards. Each card shows the command
drawn as its template over a short label from `fm_lab` (`src/focus_menu.cc:516-532,561-598`).
The F-key bar shows the menu names as text: 2nd names in accent color, alpha names in green
(`src/focus.cc:633-660`).

| key | bar label | entries (card label) | scope |
|---|---|---|---|
| 2nd F1 | arithm. | ` mod ` (Modulo), `irem(` (Remainder), `ifactor(` (Prime factors), `gcd(` (GCD), `isprime(` (Is prime?), `nextprime(` (Next prime), `powmod(` (Power mod), `iegcd(` (Bezout) | opt/out |
| 2nd F2 | reals | `exact(` (Exact), `approx(` (Decimal), `floor(`, `ceil(` (Ceiling), `round(`, `sign(`, `max(` (Maximum), `min(` (Minimum) | approx T1; rest opt |
| 2nd F3 | complexes | `abs(` (Modulus), `arg(` (Argument), `re(` (Real part), `im(` (Imag. part), `conj(` (Conjugate), `csolve(` (Solve in C), `cfactor(` (Factor in C), `cpartfrac(` (Partial fr. C) | abs T1; rest opt |
| 2nd F4 | polynomials | `proot(` (Roots), `pcoeff(` (From roots), `quo(` (Quotient), `rem(` (Remainder), `gcd(`, `egcd(` (Bezout), `resultant(` | opt/out |
| 2nd F5 | lin. alg. | `matrix(` (New matrix), `det(`, `matpow(` (Power), `ranm(` (Random), `rref(` (Row reduce), `tran(` (Transpose), `egvl(` (Eigenvalues), `egv(` (Eigenvectors) | out |
| alpha F1 | misc | `()/()` (Fraction: like n/d on a TI, `src/console.cc:3159-3164`), `_`, `!`, `rand()`, `randint(`, `binomial(`, ` and `, ` or ` | `()/()` T1; rest out |
| alpha F2 | lists | `makelist(`, `range(`, `seq(`, `len(`, `append(`, `ranv(`, `sort(`, `apply(` | out |
| alpha F3 | program | `:`, `&`, `#`, `hex(`, `bin(`, `f(x):=`, `debug(`, `python(` | `f(x):=` opt; rest out |
| alpha F4 | draw | `draw_pixel(` ... `clearscreen();` | out |
| alpha F5 | colors | `red green blue magenta cyan yellow white filled` | out |
| stat | mat | `[A]`..`[H]` (TI matrices) | out |
| plain F3 (classic; Focus opens it via *more → Other plots*) | plot | `plot( plotseq( plotlist( plotparam( plotpolar( plotfield( histogram( barplot(` | out |

The classic plain F1 (`algebra`) and F2 (`calculus`) menus still exist in the configuration
string but Focus never shows them. Their contents: `simplify( factor( partfrac( tcollect(
texpand( sum( oo product(` and `' diff( integrate( limit( series( solve( desolve( =`
(`src/console.cc:3408`).

### 2.3 The full catalog (English build, 166 entries, `src/menufr.cc:725-1008`)

Columns:
- **line**: the line in `src/menufr.cc`.
- **help line**: what Focus shows (§1.1).
- **example shown**: the example after the §1.1 transformation.
- **search tabs**: the Focus tabs (§1.2) that list the entry besides "all".

Entries are grouped by their first category byte. The French catalog
(`src/menufr.cc:431-711`) is not built in English. It has a few extra entries: `series`,
`comb`, `binomial`, `denom`, `cross`, `dot`, `factorial`, `jordan`, `rref`, `randint`,
`range`, `rand`, `elif`.

#### Algebra

| line | signature (catalog `name`) | inserts | help line (1st sentence of `desc`) | example shown | example 2 | search tabs | scope |
|---|---|---|---|---|---|---|---|
| 840 | `cfactor(p)` | `cfactor(` | Factorization over C. | `cfactor(x^4-1)` |  | algebra, numbers | opt |
| 851 | `cpartfrac(p,x)` | `cpartfrac(` | Partial fraction decomposition over C. | `cpartfrac(1/(x^4-1))` |  | algebra, numbers | out |
| 878 | `factor(p,[x])` | `factor(` | Factors polynomial p (run ifactor for an integer). | `factor(x^4-1)` | `factor(x^6+1,sqrt(3))` | algebra | T1 |
| 929 | `mult_conjugate` | `mult_conjugate` | Multiplier par le conjugue (sqrt). | `sqrt(2)-sqrt(3)` |  | algebra | opt |
| 935 | `partfrac(p,x)` | `partfrac(` | Partial fraction expansion. | `partfrac(1/(x^4-1))` |  | algebra | T2 |
| 958 | `quote(x)` | `quote(` | Returns expression x unevaluated. |  |  | algebra | out |
| 963 | `ratnormal(x)` | `ratnormal(` | Puts everything over a common denominator. |  |  | algebra | T1 |
| 973 | `simplify(expr)` | `simplify(` | Returns x in a simpler form. | `simplify(sin(3x)/sin(x))` |  | algebra | T1 |
| 979 | `subst(a,b=c)` | `subst(` | Substitutes b for c in a. | `subst(x^2,x=3)` |  | algebra | opt |

#### Polynomials

| line | signature (catalog `name`) | inserts | help line (1st sentence of `desc`) | example shown | example 2 | search tabs | scope |
|---|---|---|---|---|---|---|---|
| 824 | `abcuv(a,b,c)` | `abcuv(` | Find 2 polynomial u,v such that a*u+b*v=c | `abcuv(x+1,x^2-2,x)` |  | algebra | out |
| 845 | `coeff(p,x,n)` | `coeff(` | Coefficient of x^n in polynomial p. |  |  | algebra | opt |
| 856 | `degree(p,x)` | `degree(` | Degre of polynomial p in x. | `degree(x^4-1)` |  | algebra | opt |
| 867 | `egcd(A,B)` | `egcd(` | Find polynomials U,V,D such that A*U+B*V=D=gcd(A,B) | `egcd(x^2+3x+1,x^2-5x-1)` |  | algebra | out |
| 906 | `interp(X,Y)` | `interp(` | Lagrange interpolation at points (xi,yi) where X is the list of xi and Y of yi. | `interp([1,2,3,4,5],[0,1,3,4,4])` | `interp([1,2,3,4,5],[0,1,3,4,4],interp)` | algebra | out |
| 915 | `lcoeff(p,x)` | `lcoeff(` | Leading coefficient of polynomial p in x. | `lcoeff(x^4-1)` |  | algebra | opt |
| 931 | `numer(x)` | `numer(` | Numerator of x. | `numer(3/4)` |  | algebra | opt |
| 950 | `proot(p)` | `proot(` | Returns real and complex roots, of polynomial p. | `proot(x^3+2.1*x^2+3x+4.2)` |  | algebra | opt |
| 957 | `quo(p,q,x)` | `quo(` | Quotient of synthetic division of polynomials p and q (variable x). |  |  | algebra | opt |
| 966 | `rem(p,q,x)` | `rem(` | Remainder of synthetic division of polynomials p and q (variable x) |  |  | algebra | opt |
| 967 | `resultant(p,q,x)` | `resultant(` | Resultant in x of polynomials p and q. | `P:=x^3+p*x+q;resultant(P,P',x);` |  | algebra | out |
| 990 | `tchebyshev1(n)` | `tchebyshev1(` | Tchebyshev polynomial 1st kind: cos(n*x)=T_n(cos(x)) | `tchebyshev1(10)` |  | algebra | out |
| 991 | `tchebyshev2(n)` | `tchebyshev2(` | Tchebyshev polynomial 2nd kind: sin((n+1)*x)=sin(x)*U_n(cos(x)) | `tchebyshev2(10)` |  | algebra | out |

#### Solve

| line | signature (catalog `name`) | inserts | help line (1st sentence of `desc`) | example shown | example 2 | search tabs | scope |
|---|---|---|---|---|---|---|---|
| 853 | `csolve(equation,x)` | `csolve(` | Solve equation (or polynomial system) in exact mode over the complex numbers. | `csolve(x^2+x+1=0)` |  | algebra, numbers | opt |
| 857 | `desolve(equation,t,y)` | `desolve(` | Exact differential equation solving. | `desolve([y'+y=exp(x),y(0)=1])` | `desolve([y'=[[1,2],[2,1]]*y+[x,x+1],y(0)=[1,2]])` | algebra, calculus | T3 |
| 886 | `fsolve(equation,x=a..b)` | `fsolve(` | Approx equation solving in interval a..b. | `fsolve(cos(x)=x,x=0..1)` | `fsolve(cos(x)-x,x=0.0)` | algebra | opt |
| 920 | `linsolve([eq1,eq2,..],[x,y,..])` | `linsolve(` | Linear system solving. | `linsolve([x+y=1,x-y=2],[x,y])` | `p,l,u:=lu([[1,2],[3,4]]); linsolve(p,l,u,[5,6])` | algebra | opt |
| 933 | `odesolve(f(t,y),[t,y],[t0,y0],t1)` | `odesolve(` | Approx. | `odesolve(sin(t*y),[t,y],[0,1],2)` | `odesolve(0..pi,(t,v)->{[-v[1],v[0]]},[0,1])` | algebra | out |
| 976 | `solve(equation,x)` | `solve(` | Exact solving of equation w.r.t. | `solve(x^2-x-1=0,x)` | `solve([x^2-y^2=0,x^2-z^2=0],[x,y,z])` | algebra | T1 |

#### Calculus

| line | signature (catalog `name`) | inserts | help line (1st sentence of `desc`) | example shown | example 2 | search tabs | scope |
|---|---|---|---|---|---|---|---|
| 859 | `diff(f,var,[n])` | `diff(` | Derivative of expression f with respect to var (order n, n=1 by default), for example diff(sin(x),x) or diff(x^3,x,2). | `diff(sin(x),x)` | `diff(sin(x^2),x,3)` | calculus | T2 (gradient form `diff(f,[x,y])`: T3) |
| 882 | `fourier_an(f,x,T,n,a)` | `fourier_an(` | Cosine Fourier coefficients of f | `fourier_an(x^2,x,2*pi,n,-pi)` |  | calculus | out |
| 883 | `fourier_bn(f,x,T,n,a)` | `fourier_bn(` | Sine Fourier coefficients of f | `fourier_bn(x^2,x,2*pi,n,-pi)` |  | calculus | out |
| 884 | `fourier_cn(f,x,T,n,a)` | `fourier_cn(` | Exponential Fourier coefficients of f | `fourier_cn(x^2,x,2*pi,n,-pi)` |  | calculus | out |
| 901 | `ilaplace(f,s,x)` | `ilaplace(` | Inverse Laplace transform of f | `ilaplace(s/(s^2+1),s,x)` |  | calculus | out |
| 903 | `inf` | `inf` | Plus infinity. | `oo` |  | calculus | T2 |
| 905 | `integrate(f,x,[a,b])` | `integrate(` | Antiderivative of f with respect to x, like integrate(x*sin(x),x). | `integrate(x*sin(x),x)` | `integrate(cos(x)/(1+x^4),x,0,inf)` | calculus | T2 (inf bounds: T3) |
| 913 | `laplace(f,x,s)` | `laplace(` | Laplace transform of f | `laplace(sin(x),x,s)` |  | calculus | out |
| 918 | `limit(f,x=a)` | `limit(` | Limit of f at x = a. | `limit(sin(x)/x,x=0)` | `limit(exp(-1/x),x=0,1)` | calculus | T2 |
| 980 | `sum(f,k,m,M)` | `sum(` | Summation of expression f for k from m to M. | `sum(k,k,1,n)` |  | calculus | T3 |
| 985 | `tabvar(f,[x=a..b])` | `tabvar(` | Table of variations of expression f, optional arguments variable x in interval a..b | `tabvar(sqrt(x^2+x+1))` | `tabvar([cos(t),sin(3t)],t)` | (hidden: `WITH_TABVAR` not built, `src/focus_catalog.cc:217-219`) | out |
| 989 | `taylor(f,x=a,n,[polynom])` | `taylor(` | Taylor expansion of f of x at a order n, add parameter polynom to remove remainder term. | `taylor(sin(x),x=0,5)` | `taylor(sin(x),x=0,5,polynom)` | calculus | T2 |

#### Trigonometry

| line | signature (catalog `name`) | inserts | help line (1st sentence of `desc`) | example shown | example 2 | search tabs | scope |
|---|---|---|---|---|---|---|---|
| 826 | `acos(x)` | `acos(` | Inverse cosine arccos(x), between 0 and pi. | `acos(1/2)` |  | trig | T1 |
| 831 | `asin(x)` | `asin(` | Inverse sine arcsin(x), between -pi/2 and pi/2. | `asin(1/2)` |  | trig | T1 |
| 833 | `atan(x)` | `atan(` | Inverse tangent arctan(x), between -pi/2 and pi/2. | `atan(1)` |  | trig | T1 |
| 848 | `cos(x)` | `cos(` | Cosine. | `cos(pi/3)` |  | trig | T1 |
| 849 | `cosh(x)` | `cosh(` | Hyperbolic cosine (e^x+e^-x)/2. | `cosh(0)` |  | trig | opt |
| 850 | `cot(x)` | `cot(` | Cotangent 1/tan(x). | `cot(pi/4)` |  | trig | T1 |
| 852 | `csc(x)` | `csc(` | Cosecant 1/sin(x). | `csc(pi/6)` |  | trig | T1 |
| 876 | `exp2trig(expr)` | `exp2trig(` | Convert complex exponentials to sin/cos | `exp2trig(exp(i*x))` |  | trig | out |
| 893 | `halftan(expr)` | `halftan(` | Convert cos, sin, tan with tan(angle/2). | `halftan(cos(x))` |  | trig | out |
| 969 | `sec(x)` | `sec(` | Secant 1/cos(x). | `sec(pi/3)` |  | trig | T1 |
| 974 | `sin(x)` | `sin(` | Sine. | `sin(pi/6)` |  | trig | T1 |
| 975 | `sinh(x)` | `sinh(` | Hyperbolic sine (e^x-e^-x)/2. | `sinh(0)` |  | trig | opt |
| 987 | `tan(x)` | `tan(` | Tangent. | `tan(pi/4)` |  | trig | T1 |
| 988 | `tanh(x)` | `tanh(` | Hyperbolic tangent. | `tanh(0)` |  | trig | opt |
| 992 | `tcollect(expr)` | `tcollect(` | Linearize and collect trig functions. | `tcollect(sin(x)+cos(x))` |  | trig | opt |
| 993 | `texpand(expr)` | `texpand(` | Expand trigonometric, exp and ln functions. | `texpand(sin(3x))` |  | trig | opt |
| 995 | `tlin(expr)` | `tlin(` | Trigonometric linearization of expr. | `tlin(sin(x)^3)` |  | trig | opt |
| 998 | `trig2exp(expr)` | `trig2exp(` | Convert complex exponentials to trigonometric functions | `trig2exp(cos(x)^3)` |  | trig | out |
| 999 | `trigcos(expr)` | `trigcos(` | Convert sin^2 and tan^2 to cos^2. | `trigcos(sin(x)^4)` |  | trig | opt |
| 1000 | `trigsin(expr)` | `trigsin(` | Convert cos^2 and tan^2 to sin^2. | `trigsin(cos(x)^4)` |  | trig | opt |
| 1001 | `trigtan(expr)` | `trigtan(` | Convert cos^2 and sin^2 to tan^2. | `trigtan(cos(x)^4)` |  | trig | opt |

#### Reals

| line | signature (catalog `name`) | inserts | help line (1st sentence of `desc`) | example shown | example 2 | search tabs | scope |
|---|---|---|---|---|---|---|---|
| 828 | `approx(x)` | `approx(` | Approx. | `approx(pi)` |  | numbers | T1 |
| 839 | `ceil(x)` | `ceil(` | Smallest integer not less than x | `ceil(1.2)` |  | numbers | opt |
| 874 | `exact(x)` | `exact(` | Converts x to a rational. | `exact(1.2)` |  | numbers | opt |
| 875 | `exp(x)` | `exp(` | Exponential e^x. | `exp(1)` |  | numbers | T1 |
| 880 | `float(x)` | `float(` | Converts x to a floating point value. | `float(pi)` |  | numbers | opt |
| 881 | `floor(x)` | `floor(` | Largest integer not greater than x | `floor(pi)` |  | numbers | opt |
| 921 | `ln(x)` | `ln(` | Natural logarithm (base e). | `ln(e^2)` |  | numbers | T1 |
| 922 | `log(x)` | `log(` | Logarithm in base 10. | `log(100)` |  | numbers | T1 |
| 972 | `sign(x)` | `sign(` | Returns -1 if x is negative, 0 if x is zero and 1 if x is positive. |  |  | numbers | opt |
| 978 | `sqrt(x)` | `sqrt(` | Square root. | `sqrt(8)` |  | numbers | T1 |

#### Complex numbers

| line | signature (catalog `name`) | inserts | help line (1st sentence of `desc`) | example shown | example 2 | search tabs | scope |
|---|---|---|---|---|---|---|---|
| 825 | `abs(x)` | `abs(` | Absolute value or norm of x x | `abs(-3)` | `abs([1,2,3])` | numbers | T1 |
| 829 | `arg(z)` | `arg(` | Angle of complex z. | `arg(1+i)` |  | numbers | opt |
| 847 | `conj(z)` | `conj(` | Complex conjugate of z. | `conj(1+i)` |  | numbers | opt |
| 873 | `evalc(z)` | `evalc(` | Write z=x+i*y. | `evalc(1/(1+i*sqrt(3)))` |  | numbers | opt |
| 902 | `im(z)` | `im(` | Imaginary part. | `im(1+i)` |  | numbers | opt |
| 928 | `mult_c_conjugate` | `mult_c_conjugate` | Multiplier par le conjugue complexe. | `1+2*i` |  | numbers | opt |
| 964 | `re(z)` | `re(` | Real part. | `re(1+i)` |  | numbers | opt |

#### Arithmetic

| line | signature (catalog `name`) | inserts | help line (1st sentence of `desc`) | example shown | example 2 | search tabs | scope |
|---|---|---|---|---|---|---|---|
| 736 | `%` | `%` | a % b means a modulo b |  |  | numbers | out |
| 830 | `asc(string)` | `asc(` | List of ASCII codes os a string | `asc("Hello")` |  | numbers | out |
| 841 | `char(liste)` | `char(` | Converts a list of ASCII codes to a string. | `char([97,98,99])` |  | numbers | out |
| 871 | `euler(n)` | `euler(` | Euler indicatrix: number of integers < n coprime with n | `euler(25)` |  | numbers | out |
| 891 | `gcd(a,b,...)` | `gcd(` | Greatest common divisor. | `gcd(23,13)` | `gcd(x^2-1,x^3-1)` | algebra, numbers | opt |
| 895 | `iabcuv(a,b,c)` | `iabcuv(` | Find 2 integers u,v such that a*u+b*v=c | `iabcuv(23,13,15)` |  | numbers | out |
| 896 | `ichinrem([a,m],[b,n])` | `ichinrem(` | Integer chinese remainder of a mod m and b mod n. | `ichinrem([3,13],[2,7])` |  | numbers | out |
| 897 | `idivis(n)` | `idivis(` | Returns the list of divisors of an integer n. | `idivis(10)` |  | numbers | opt |
| 899 | `iegcd(a,b)` | `iegcd(` | Find integers u,v,d such that a*u+b*v=d=gcd(a,b) | `iegcd(23,13)` |  | numbers | out |
| 900 | `ifactor(n)` | `ifactor(` | Factorization of an integer (not too large!). |  |  | numbers | opt |
| 908 | `iquo(a,b)` | `iquo(` | Integer quotient of a and b. | `iquo(23,13)` |  | numbers | opt |
| 909 | `irem(a,b)` | `irem(` | Integer remainder of a and b. | `irem(23,13)` |  | numbers | opt |
| 910 | `isprime(n)` | `isprime(` | Returns 1 if n is prime, 0 otherwise. | `isprime(11)` | `isprime(10)` | numbers | opt |
| 914 | `lcm(a,b,...)` | `lcm(` | Least common multiple. | `lcm(23,13)` | `lcm(x^2-1,x^3-1)` | algebra, numbers | opt |
| 948 | `powmod(a,n,p)` | `powmod(` | Returns a^n mod p. | `powmod(123,456,789)` |  | numbers | out |

#### Linear algebra, matrices, lists (all **out**; tab "all" only)

| line | signature | inserts | help line | example shown | example 2 |
|---|---|---|---|---|---|
| 962 | `ranv(n,[loi,parametres])` | `ranv(` | Random vector. | `ranv(10)` | `ranv(4,normald,0,1)` |
| 842 | `charpoly(M,x)` | `charpoly(` | Characteristic polynomial of matrix M in variable x. | `charpoly([[1,2],[3,4]],x)` |  |
| 858 | `det(A)` | `det(` | Determinant of matrix A. | `det([[1,2],[3,4]])` |  |
| 869 | `egv(A)` | `egv(` | Eigenvectors of matrix A. | `egv([[1,2],[3,4]])` |  |
| 870 | `egvl(A)` | `egvl(` | Eigenvalues of matrix  A. | `egvl([[1,2],[3,4]])` |  |
| 898 | `idn(n)` | `idn(` | Identity matrix of order n | `idn(4)` |  |
| 907 | `inv(A)` | `inv(` | Inverse of A. | `inv([[1,2],[3,4]])` |  |
| 923 | `lu(A)` | `lu(` | LU decomposition LU of matrix A, P*A=L*U | `lu([[1,2],[3,4]])` |  |
| 926 | `matpow(A,n)` | `matpow(` | Returns matrix A^n | `matpow([[1,2],[3,4]],n)` | `assume(n>=1);matpow([[0,2],[0,4]],n)` |
| 927 | `matrix(r,c,func)` | `matrix(` | Matrix from a defining function. | `matrix(2,3,(j,k)->j^k)` |  |
| 961 | `ranm(n,m,[loi,parametres])` | `ranm(` | Random matrix with integer coefficients or according to a probability law (ranv for a vector). | `ranm(3,3)` | `ranm(4,2,normald,0,1)` |
| 996 | `trace(A)` | `trace(` | Trace of the matrix A. | `trace([[1,2],[3,4]])` |  |
| 997 | `transpose(A)` | `transpose(` | Transposes matrix A. | `transpose([[1,2],[3,4]])` |  |
| 827 | `append` | `append` | Adds an element at the end of a list | `l.append(x)` |  |
| 877 | `extend` | `extend` | Merge 2 lists. | `l1.extend(l2)` |  |
| 917 | `len(l)` | `len(` | Size of a list. | `len([3/2,2,1,1/2,3,2,3/2])` |  |
| 925 | `map(f,l)` | `map(` | Maps f on element of list l. | `map(lambda x:x*x,[1,2,3])` |  |
| 977 | `sorted(l)` | `sorted(` | Sorts a list. | `sorted([3/2,2,1,1/2,3,2,3/2])` | `sorted([[1,2],[2,3],[4,3]],(x,y)->when(x[1]==y[1],x[0]>y[0],x[1]>y[1])` |

#### Plots (all **out**: no graphing in v1; tab "all" only)

| line | signature | inserts | help line | example shown | example 2 |
|---|---|---|---|---|---|
| 836 | `barplot(list)` | `barplot(` | Bar plot of 1-d statistic series data in list. | `barplot([3/2,2,1,1/2,3,2,3/2])` |  |
| 843 | `circle(center,radius)` | `circle(` | Circle | `circle(2+i,3)` | `circle(1-i,1+i)` |
| 894 | `histogram(list,min,size)` | `histogram(` | Histogram of data in list, classes begin at min of size size. | `histogram(ranv(100)/100.,0,0.1)` |  |
| 919 | `line(equation)` | `line(` | Line of equation or from 2 points | `line(y=2x+1)` | `line([1,2],[3,1])` |
| 937 | `plot(expr,x)` | `plot(` | Plot an expression. | `plot(ln(x),x,0,5)` | `plot(1/x,x=1..5,xstep=1)` |
| 940 | `plotfield(f(t,y),[t=tmin..tmax,y=ymin..ymax])` | `plotfield(` | Plot field of differential equation y'=f(t,y), an optionnally one solution by adding plotode=[t0,y0] | `plotfield(sin(t*y),[t=-3..3,y=-3..3],plotode=[0,1])` |  |
| 942 | `plotode(f(t,y),[t=tmin..tmax,y],[t0,y0])` | `plotode(` | Plot solution of differential equation y'=f(t,y), y(t0)=y0. | `plotode(sin(t*y),[t=-3..3,y],[0,1])` |  |
| 943 | `plotparam([x,y],t)` | `plotparam(` | Parametric plot. | `plotparam([cos(3t),sin(2t)],t,0,2*pi)` | `plotparam([t^2,t^3],t=-1..1,tstep=0.1)` |
| 944 | `plotpolar(r,theta)` | `plotpolar(` | Polar plot. | `plotpolar(cos(3*x),x,0,pi)` | `plotpolar(1/(1+cos(x)),x=0..pi,xstep=0.05)` |
| 945 | `plotseq(f(x),x=[u0,m,M],n)` | `plotseq(` | Plot f(x) on [m,M] and n terms of the sequence defined by u_{n+1}=f(u_n) and u0. | `plotseq(sqrt(2+x),x=[6,0,7],5)` |  |
| 947 | `point(x,y)` | `point(` | Point | `point(1,2)` | `point(1+2i)` |

#### Programs, operators, display options (tab "all" only)

| line | signature | inserts | help line | example shown | example 2 | scope |
|---|---|---|---|---|---|---|
| 735 | `#` | `#` | Python comment, for Xcas comment type //. |  |  | out |
| 855 | `debug(f(args))` | `debug(` | Runs user function f in step by step mode. |  |  | out |
| 904 | `input()` | `input()` | Read a string from keyboard |  |  | out |
| 949 | `print(expr)` | `print(` | Print expr in console |  |  | out |
| 994 | `time(cmd)` | `time(` | Time to run a command or set the clock | `time(int(1/(x^4+1),x))` | `time(8,0)` | out |
| 734 | `!` | `!` | Logical not (prefix) or factorial of n (suffix). | `7!` | `~!b` | opt (factorial) |
| 737 | `&` | `&` | Logical and or + | `1&2` |  | out |
| 817 | `=>` | `=>` | Store value in variable or conversion (touche ->). | `5=>a` | `x^4-1=>*` | **T1** (sto→; §5.6) |
| 819 | `a and b` | ` and ` | Logical and |  |  | out |
| 820 | `a or b` | ` or ` | Logical or |  |  | out |
| 832 | `assume(hyp)` | `assume(` | Assumption on variable. | `assume(x>1)` | `assume(x>-1 and x<1)` | out |
| 834 | `axes` | `axes` | Axes visible or not axes=1 or 0 | `axes=0` |  | out |
| 844 | `clearscreen()` | `clearscreen()` | Clear screen. |  |  | out |
| 860-866 | `draw_arc(...)`, `draw_circle(x1,y1,r,c)`, `draw_line(x1,y1,x2,y2,c)`, `draw_pixel(x,y,color)`, `draw_polygon([[x1,y1],...],c)`, `draw_rectangle(x,y,w,h,c)`, `draw_string(s,x,y,c)` | `draw_*(` | Pixelised arc/circle/line/polygon, Rectangle, ... | e.g. `draw_line(100,50,300,200,blue)` |  | out |
| 872 | `eval(f)` | `eval(` | Evals f. |  |  | out |
| 879 | `filled` | `filled` | Display option |  |  | out |
| 930 | `not(x)` | `not(` | Logical not. |  |  | out |
| 951 | `purge(x)` | `purge(` | Clear assigned variable x. |  |  | opt (variable store) |
| 970 | `seq(expr,var,a,b)` | `seq(` | Generates a list from an expression. | `seq(j^2,j,1,10)` |  | out |
| 1006 | `\|` | `\|` | Logical or | `1\|2` |  | out |
| 1007 | `~` | `~` | Complement | `~7` |  | out |
| 837-1005 | `black` `blue` `cyan` `green` `magenta` `red` `yellow` (`display=<color>`), `tstep`, `xstep` | itself | Display option / graph step | `display=red`, `tstep=0.2` |  | out |
| 726-733 | ` loop for`, ` loop in list`, ` loop while`, ` test if`, ` test else`, ` function def` (`f(x):=`), ` range(a,b)`, ` return res` | `for ` ... | (hidden from the Focus search: the name starts with a space) |  |  | out |

### 2.4 Commands outside the English catalog

These commands work and are offered elsewhere in the UI, but are not in the English catalog,
so the search cannot find them.

| command | where it comes from | scope |
|---|---|---|
| `expand(` | F1 popover (`src/focus_menu.cc:28`), drawn as a known function (`src/mathinput.cc:243-246`) | T1 |
| `series(f,x,a,n)` | F2 popover *Taylor series* (`src/focus_menu.cc:39`). With 4 arguments it is a 2D template (`src/mathinput.cc:274-277`). | T2 |
| `surd(a,n)` | F4 symbols, n-th root (`src/focus_menu.cc:49`) | T1 (real n-th roots) |
| `int(` | alias of `integrate(`. It is a 2D template and gets `+ C` (`src/focus.cc:110-121`, `src/mathinput.cc:274-276`) | T2 |
| `f'(x)`, `'` | the derivative prime. The `diff` catalog text says "run f' (shortcut F3)" (`src/menufr.cc:859`); it is the first item of the classic F2 menu (`src/console.cc:3408`). | T2 |
| `product(` | classic F1 algebra menu | opt |
| `nextprime( round( max( min( pcoeff( rref( tran( makelist( range( sort( apply( rand() randint( binomial( hex( bin( python( get_pixel(` | 2nd/alpha menus (§2.2) | round/max/min opt; rest out |
| `perm(n,k)`, `nPr(n,k)` | rewritten to `comb(n,k)*k!` before evaluation (`src/answer.cc:2986-2996,3055-3056`) | out |
| `grad(f,[x,y])`, `dot(`, `cross(`, `norm(`, `l2norm(` | giac builtins used by the Calc 3 test corpus (`tools/hostgiac/corpus_calc23.txt:216-236`; directional derivatives in `tools/hostgiac/corpus_calc23_web.txt:285-290`) | grad T3; vectors opt |

FlowCE has **no dedicated commands** for several T3 topics. Users type the set-up integral or
sum instead (README "Calculus 1, 2 and 3", `README.md:37-42`, and the test cases
`tools/emu/cases/calc3.tsv`):

| topic | how the user types it |
|---|---|
| polar area | `1/2*integrate((1+cos(t))^2,t,0,2π)` |
| parametric arc length | `integrate(sqrt((2t)^2+(3t^2)^2),t,0,1)` |
| parametric slope | `diff(t^3,t)/diff(t^2,t)` |
| Riemann sum | `sum((i/n)^2*(1/n),i,1,n)`, then `limit(sum(...),n,inf)`. The index `i` is renamed (§5.7). |
| multiple integral | nested: `integrate(integrate(x*y,y,0,2),x,0,3)` (`tools/hostgiac/corpus_calc23.txt:223-229`) |
| gradient | `grad(x^2*y+y^3,[x,y])` |
| directional derivative | `subst(dot(grad(f,[x,y]),u),[x,y],[a,b])` (`tools/hostgiac/corpus_calc23_web.txt:285-290`) |
| ODE / IVP | `desolve([y''+4y=0,y(0)=1,y'(0)=0],y)`. Constants print as `C1`, `C2`. |

cas-evo can follow FlowCE here, or add thin convenience commands such as `polarArea(r,t,a,b)`.
That choice belongs in the design doc.

---

## 3. Key bindings (Focus console)

FlowCE turns TI scan codes into KhiCAS key codes in `src/k_csdk.c:207-344`. The console handles
them in `Console_GetKey`, `src/console.cc:2336-3141`.

- 2nd and alpha arrive as their own key presses. They set a state for the next key
  (`src/k_csdk.c:245-266`).
- `alpha` types **lowercase** letters by default: the case offset is `(alpha>>1)<<5`, and
  `alpha=2` (`src/k_csdk.c:207`).
- `alpha alpha` and `2nd alpha` lock alpha. During alpha-lock, `2nd` toggles the case.
- The status chip shows `2nd`, `a`, `A`, `a-lock` or `A-LOCK` (`src/focus.cc:528-533`).

| TI key | plain | 2nd | alpha | notes / source |
|---|---|---|---|---|
| `y=` `window` `zoom` `trace` `graph` (F1-F5) | popovers: algebra, calculus, trig, symbols (F4 = **forms** when a result is selected or shown large), more | menus F6-F10: arithm., reals, complexes, polynomials, lin. alg. | menus F11-F15: misc, lists, program, draw, colors | `src/k_csdk.c:213-222`, `src/console.cc:2356-2426,2839-2843` |
| `math` | math-template popover | `=` (TEST) | `a` | `src/k_csdk.c:267-268` |
| `apps` (`sk_Matrice`; the 83 Premium CE labels it "matrice") | lin. alg. menu (code becomes F10) | | `b` | `src/k_csdk.c:269-270`, `src/console.cc:2434` |
| `prgm` | program editor (`focus_edit.cc`; out of scope) | alpha-F5 (colors) menu | `c` | `src/console.cc:2946-2952`, `src/k_csdk.c:271-272` |
| `vars` | variable list: the variables (name and type), then `purge(`, `assume(`, `restart`, `VARS()`. `del` on a variable inserts `purge(var)`. | | | `src/main.cc:259-321` |
| `stat` | stat code → F16 "mat" menu ([A]-[H] TI matrices) | lists menu | | `src/console.cc:2435-2444` |
| `mode` | **Config** menu (§6.1) | **quit** | | `src/k_csdk.c:223-224`, `src/console.cc:2989-2993` |
| `del` | delete (2D-aware, §5.2) | paste (ins) | | `src/console.cc:3032-3091` |
| `clear` (`sk_Annul`) | non-empty line: erase it. Empty line: "Clear the history?" card. In history: back to the edit line. | AC: empty line hides the large result (it goes up into the history) | | `src/console.cc:2953-2988`. Discrepancy: `README.md:134` says "on an empty line, the answer", but the code only does that for AC. |
| `X,T,θ,n` | `x` (`t` when the editor uses `xthetat`) | ignored in Focus | undo | `src/console.cc:1827-1828,2532-2533` |
| `x⁻¹` (`sk_TglExact`, arrives as tab) | `^-1` (2D: `^(-1)`) | | `d` | `src/console.cc:2458-2459,2474-2475` |
| `sin` `cos` `tan` | `sin(` `cos(` `tan(` | `asin(` `acos(` `atan(` | `e` `f` `g` | `src/k_csdk.c:290-295` |
| `^` | `^` (2D: `^()` with the caret inside) | `pi` | `h` | `src/console.cc:3124-3130` |
| `x²` | `^2` (2D: `^(2)`) | `sqrt(` | `i` | |
| `,` | `,` | `E` (EE) | `j` | |
| `(` `)` | `(` `)` (2D: structure-aware, §5.2) | `{` `}` | `k` `l` | |
| `÷` | `/` (2D: the term before the caret becomes a numerator) | `e` | `m` | |
| `log` | `log10(` | `10^(` | `n` | `src/console.cc:1832-1836` |
| `ln` | `ln(` | `exp(` (eˣ) | `s` | `src/console.cc:1830-1831,1836-1837` |
| `×` `−` | `*` `-` | `[` `]` | `r` `w` | |
| `+` | `+` | `+` | `"` | |
| `sto→` | `=>` | RCL: run a script | `x` | `src/console.cc:1856-1858` |
| `(-)` | `-` (a minus sign; KhiCAS used `_`) | **Ans**: inserts `ans()` | `?` | `src/console.cc:1813-1814,1866-1867` |
| `0`-`9` | digits | `2nd 0`: catalog, opens the **command search**. `2nd 1-9`: inserts `Y1`..`Y9` (KhiCAS legacy: TI function variables). | `0`: space; `1 2 3`: `y z θ`; others: letters | `src/console.cc:2427-2432,2445-2452` |
| `.` | `.` | `i` | `:` | |
| `▲` | from the edit line: into the history, selecting the last calculation. In history: the previous entry (keeps input/result side); "Oldest calculation" at the top. | page up (8 lines) | | `src/console.cc:2507-2516,2887-2893`, `src/focus.cc:903-922` |
| `▼` | edit line: opens the **command search** with the word before the caret. This happens only when the caret cannot move down inside a 2D construct (`src/console.cc:2877-2886`). In history: the next entry, or back to the edit line. | page down | | `src/console.cc:2910-2918` |
| `◀` `▶` | caret moves in 2D. In history: select that entry's input (◀) or result (▶). | shift-left/right | | `src/console.cc:2877-2886,2507-2516` |
| `enter` | evaluate. Jumps to an empty box first (§1.3). In history: **paste** the selected input or result at the caret of the edit line. | **ENTRY**: puts the last input on the line; each press goes one input further back | | `src/console.cc:2995-3030,3092-3110` |
| `ON` (or `clear`) while computing | **stop**. The status bar shows "ON or clear: stop". giac's `control_c()` reads the CLEAR key row and the ON latch directly, and sets `ctrl_c`/`interrupted`. The answer becomes "Interrupted", or "Out of memory" when the heap ran out. | | | `ti-ce-giac/kglobal.cc:152-163`, `src/main.cc:461-500,1212-1215` |

While a calculation runs, after 0.4 s the empty-line prompt is replaced by "Calculating" over
three dots that light in turn, 4 times a second. The animation runs from `control_c_hook`, which
giac's `control_c()` polls (`src/focus.cc:751-784`, `src/main.cc:1200-1201`). cas-evo needs the
same arrangement: one cancel-check function, called from every long loop, that polls
`ti_system.escape()`/`get_key` and also animates the busy indicator.

---

## 4. Screen structure (Focus)

The screen has three bands: a 16 px status bar, the stage at y 16-218, and a 22 px F-key bar at
the bottom (`src/focus.cc:40`).

- **Status bar** (`src/focus.cc:469-548`), three zones:
  - left: `RAD    EXACT` or `DEG    EXACT`. In history it shows `HISTORY  n / N` instead, and in
    a view, the view's label (e.g. `COMMANDS`).
  - middle: a status message in accent color, or `SIMPLIFY OFF` when that setting is off.
  - right: the 2nd/alpha chip, or `FlowCE v1.9`, then the battery.
- **Stage** (`src/focus.cc:152-250,693-720`):
  - Past calculations are stacked as entries. Each entry shows its input (small, gray, left)
    and its result (right-aligned). At most 2 message lines show in between.
  - The **edit line** is drawn large and centered (the "hero"), with 2D math and the caret
    (`:275-300,377-392`).
  - After ENTER, the last result is shown large instead, under its input
    (`:394-424`). The footer shows `≈ decimal` and a forms chip `<form name> F4`
    (`:425-440`).
  - On an empty line with no result, the prompt "Type a calculation" appears with key hints
    `[math] templates  [▲] history  [▼] search` (`:441-448`).
  - In history mode the edit line peeks small at the bottom with the hints
    `[enter] paste  [<] entry  [>] answer` and `▼ back` (`:451-463`).
- **F-key bar** (`src/focus.cc:609-665`): five 64 px tabs, each an icon and a word: algebra
  (x²), calculus (∫), trig (wave), symbols (π) or forms (two arrows), more (three dots). With
  2nd or alpha held, the tabs show the menu names as text.
- **Messages** (text instead of math) are detected by `is_text`: a space followed by a letter,
  a giac `// Error`, or a capitalized single word (`src/focus.cc:95-108`). They are drawn wrapped
  and centered. The exact strings are in `flowce-answer-format.md` §7.
- `+ C` is **not** part of the result text. FlowCE draws it in the secondary color whenever the
  *input* is `integrate(`/`int(` with at most 2 arguments (`src/focus.cc:109-121,208-214,419-423`).

---

## 5. Input preprocessing (precise enough to reimplement)

### 5.0 Pipeline order

A line goes through these stages, in this order:

1. **At each key press** (`src/console.cc:2336-3141`):
   - key-to-text translation (§5.1);
   - the leading-operator rule (§5.3);
   - F1/F2 action wrapping (§1.4);
   - 2D structure editing (§5.2).

   In math mode FlowCE inserts **no `*`** at key time. Only Python mode adds a `*` when a value
   key follows a value (`src/console.cc:2149-2171,3118-3122`).
2. **On ENTER** (`src/console.cc:2995-3019`):
   - the empty-slot check (§1.3);
   - `console_autoclose`: open `( [ {` are closed at the end of the line, as TI-OS does
     (`sin(x` becomes `sin(x)`). The line is left alone if it has an unterminated string, a `//`
     comment, a mismatched closer, or more than 64 nesting levels (`:2173-2208`).

   The **history keeps this text**. The rewrites below are not stored, so the history shows
   `2pi` as typed (`src/answer.cc:2977-2978`, `src/console.cc:2250`).
3. **At evaluation** (`src/main.cc:1083-1131`, `src/answer.cc:2976-2984`):
   1. `ans()` substitution (§5.4);
   2. control characters: `0x1e` and `0x9c` become `\n`, `\r` becomes a space
      (`src/main.cc:1119-1130`);
   3. `ti_rewrite` (paper notation, §5.5);
   4. `ti_implicit_mult` with name splitting (§5.6). Steps 3 and 4 run together as
      `khicas_implicit_mult`, which Python mode skips (`src/tiinput_glue.cc:71-82`);
   5. `log(` becomes `log10(` (§5.7);
   6. a Riemann-sum index `i` is renamed (§5.7);
   7. giac parses the text, then `answer_before` applies the evaluation-side rules (§5.8).

### 5.1 Key-to-text translation (`keytostring`, `src/console.cc:1804-1919`)

| key | text | key | text |
|---|---|---|---|
| `+` `−` `×` `÷` | `+` `-` `*` `/` | `(-)` | `-` (Focus) |
| `^` | `^` | `x²` / `x⁻¹` | `^2` / `^-1` |
| `2nd x²` (√) | `sqrt(` | `X,T,θ,n` | `x` |
| `ln` | `ln(` (Focus; KhiCAS gave `log(`) | `log` | `log10(` |
| `2nd log` | `10^(` | `2nd ln` | `exp(` |
| `2nd ÷` | `e` | `2nd .` | `i` |
| `2nd ^` | `pi` | `2nd ,` | `E` |
| `sin` ... `atan` | `sin(` ... `atan(` | `sto→` | `=>` |
| `2nd (-)` | `ans()` | `2nd math` | `=` |
| `( ) [ ] { } ,` | themselves | `vars` | the variable picked (§3) |

In 2D mode, a text that ends in `(` (a function) is inserted as `name()` with the caret inside,
and `^` is inserted as `^()` (`src/console.cc:3124-3130`). `x²` and `x⁻¹` insert `^(2)` and
`^(-1)` (`src/console.cc:2472-2475`).

### 5.2 2D editing keys (for the later 2D editor; `src/mathedit.h`, `src/mathedit.cc:1-120`)

- `/` turns the term left of the caret into a numerator: `x|` becomes `(x)/(|)`. The term is
  the run of implicitly multiplied operands with their powers.
- `( [ {` wrap the rest of the slot.
- `)` steps out of a group.
- `, = < > ] }` first leave a denominator or exponent.
- `del` right after `)` steps into the group (`src/console.cc:3043-3050`).
- `del` at the start of a slot unwraps the construct.
- `del` removes `ans()` as one unit (`src/console.cc:3035-3042`). The caret also skips over
  `ans()` as one unit (`src/console.cc:3714-3726`).

The 2D input display is in `src/mathinput.cc` (header `:1-60`). It uses recursive descent with
a nesting cap of 24. cas-evo's explicit-stack parser replaces it.

### 5.3 Leading-operator rule (`src/console.cc:2460-2465`)

FlowCE inserts `ans()` *before* the key's own text when all of these hold:
- the caret is on the edit line;
- the edit line is **empty**;
- a result is available. `focus_result_line() >= 0` means either the last result is still
  shown large, or a result line is selected (`src/focus.cc:896-901`);
- the key is one of `+ − × ÷ ^ x² x⁻¹ sto→`.

Consequences:
- `(-)` is a minus sign, never Ans-minus.
- `sto→ b` on an empty line gives `ans()=>b`.
- After `clear`/AC has hidden the large result, the rule no longer fires.
- Test cases: `tools/emu/cases/ansop.tsv:1-14`. For example, `5` then `{2nd,(-)}{del}7`
  gives `7`, because the whole Ans is deleted at once.

### 5.4 Ans

- The key inserts the text `ans()`. The 2D display shows it as **`Ans`** with hidden parentheses
  and no box (`src/mathinput.cc:236-241,309-310`).
- At evaluation every `ans()` (at most 8) is replaced **textually** by `(` + the text of the
  most recent **output** line + `)` (`src/main.cc:1084-1110`). FlowCE skips the substitution
  when that output is 400 characters or longer, or **contains a space**. A space means a message
  such as "f(x) defined" or "diverges ...", which is not an answer. In that case `ans()` reaches
  giac unchanged and evaluates to undef.
- Implicit multiplication treats `ans()` as a value: `ans()2` becomes `ans()*2` and `2ans()`
  becomes `2*ans()` (`tests/host/test_tiinput.cc:195-196`).
- `ENTRY` (2nd enter) recalls earlier **inputs** one by one. The first press takes the last
  input. Each further press takes the input before the one that was just recalled, provided the
  line still equals it (`src/console.cc:3092-3110`; tests `tools/emu/cases/entry.tsv`).

### 5.5 Paper-notation rewrite: `ti_rewrite` (`src/tiinput.cc:346-583`; spec `src/tiinput.h:27-37`)

Tokens are read left to right and copied as they are, except in the cases below. A string
`"..."` (with `\` escapes) and a `//` comment up to the end of the line are copied verbatim.
A number is copied as one token.

**Names.** A name matches `[A-Za-z_\x80-\xff][A-Za-z0-9_\x80-\xff]*`. The UTF-8 π (`CF 80`) is
always a name of its own (`:110-121`).

**Unary function table** `F`. Order matters: the longest names come first, and the first prefix
match wins (`:349-354`):
`asinh acosh atanh log10 sinh cosh tanh asin acos atan sqrt sin cos tan sec csc cot exp abs log ln`.

**Inverse table** for `^-1` (`:363-371`):
sin→asin, cos→acos, tan→atan, sec→asec, csc→acsc, cot→acot, sinh→asinh, cosh→acosh,
tanh→atanh. `ln`, `log`, `exp` and the others have no inverse here.

**Helper scans:**

- `fnin(i, j)`: the first k in (i, j) such that `s[k-1]` is an ASCII letter and `s[k..j)`
  starts with a name from `F`. If there is none, it returns j (`:383-389`).
- `powend(i)`, the end of an exponent that starts at i (`:405-417`):
  - a `(` group: up to its matching `)`;
  - a number;
  - a name not starting with `_`: up to the end of the name, but if the name is UNKNOWN, only up
    to `fnin`;
  - anything else: no exponent (returns i).
- `runend(i)`, the bare argument of `sin x` (`:418-446`). It repeatedly consumes:
  - numbers;
  - names that are not KEYWORD, FUNCTION or USERFN and do not start with an `F` prefix.
    Inside an UNKNOWN name it stops at `fnin`;
  - `^exponent` (via `powend`).

  It stops at the first operator, parenthesis, blank, function name, or nested function.

**Rules, in order, for a name `s[i..j)` with class `c`.** Names starting with `_` (units) are
treated as KEYWORD and never rewritten (`:509`).

0. **Definition `f(x)=...`** (`:447-481,489-498`). The line, after leading blanks, starts with
   NAME `(` params `)` blanks `=`, where the `=` is not `==`. NAME must not be FUNCTION or
   KEYWORD and must not start with `_`. The params are one or more comma-separated names; blanks
   are allowed. The `=` becomes `:=`, and NAME is copied without any rewriting.
   Examples: `f(x)=x^2` → `f(x):=x^2`; `sinx(t)=t` → `sinx(t):=t`.
   Unchanged: `sin(x)=1/2`, `f(2)=5`, `f()=1`, `2f(x)=4`.
1. **Letters times a function in one name** (`:510-517`). Let `f` be the length of the
   longest `F` prefix when `c` is FUNCTION or UNKNOWN (0 otherwise). If `f = 0`, `c` is
   UNKNOWN, and the name is not followed by `:=`, then let `fi = fnin(i, j)`. If `fi < j`, emit
   `s[i..fi)` followed by `*`, and continue scanning at `fi`.
   Examples: `xsinx` → `x*sin(x)`; `2xlnx` → `2x*ln(x)`; `xsec^2x` → `x*sec(x)^2`;
   `e^xsinx` → `e^x*sin(x)`.
2. **Function glued to its argument** (`:518-536`). Requires `f > 0`. Let `k = i + f`, then
   advance `k` while `k < j` and `s[k..j)` does not start (at a letter) with an `F` name. If
   all of these hold: `k > i + f`, `c` is UNKNOWN, and `s[j]` is not `(` (no blank skipping),
   then:
   - let `r = k`;
   - if `k = j` and `s[j] = '^'` and the exponent is non-empty, let `r = powend(j+1)`;
   - emit `fn(` + `s[i+f..r)` + `)` and continue at `r`. The rest of the name is processed as a
     new name.

   Examples: `sinx` → `sin(x)`; `sin2x` → `sin(2x)`; `cost` → `cos(t)`; `ln2` → `ln(2)`;
   `sinx^2` → `sin(x^2)`; `2sinxcosx` → `2sin(x)cos(x)`; `sinpi` → `sin(pi)`.
   Unchanged: `sinx(t)` (a call), `x2sinx` (a digit makes it a plain name).
3. **Exact function name followed by `^`** (`:537-562`). Requires `f = len` and `c` FUNCTION,
   with the next character `^`.
   - If the exponent is `-1` not followed by a digit, `inv` holds, and the power ends 3
     characters later. Otherwise the power ends at `powend`.
   - Skip blanks. The argument is a `(...)` group if one follows; otherwise it is `runend`.
   - If the power is non-empty, the argument is non-empty, and (`inv` implies an inverse
     exists), emit `(inverse or name)(` + **`ti_rewrite(argument content)`** + `)`, then the
     power `^...` unless `inv`.

   Examples: `sin^2(x)` → `sin(x)^2`; `sin^2x` → `sin(x)^2`; `sin^2(sinx)` → `sin(sin(x))^2`;
   `sin^-1(x)` → `asin(x)`; `sec^-1(x)` → `asec(x)`; `sin^(2)(x)` → `sin(x)^(2)`.
   Unchanged: `ln^-1(x)`, `sin^2` (no argument).

   This step **recurses** on the argument; cas-evo must turn it into a loop to fit the device
   frame budget.
4. **Exact function name followed by a space or bare argument** (`:563-576`). Requires `f = len`
   and `c` FUNCTION, with the next character not `(`. Skip blanks; if `runend` returns a
   non-empty argument, emit `name(arg)`.
   Examples: `sin x` → `sin(x)`; `sin 2x` → `sin(2x)`; `sin x^2` → `sin(x^2)`;
   `sin x+1` → `sin(x)+1`; `sin pi/2` → `sin(pi)/2`; `exp x` → `exp(x)`; `sin sin x` →
   `sin sin(x)`.
5. Otherwise the name is copied.

The full expected-output list is in `tests/host/test_tiinput.cc:357-425`. Port it as golden
tests. Every case must also satisfy two properties: running the rewrite again changes nothing,
and the classifier is called only on real names (`:430-441`).

### 5.6 TI-style implicit multiplication: `ti_implicit_mult` (`src/tiinput.cc:1-344`)

The output is the input plus inserted `*` characters and **nothing else**, so the pass is
idempotent (`:1-5`, tested at `tests/host/test_tiinput.cc:314-335`).

**Tokens** (`:6-14,73-135`):

| token | definition |
|---|---|
| blanks | space and tab |
| line break | `\n` or `\r`. It resets the state; so does a `//` comment up to the end of the line. |
| string | `"..."` with `\` escapes. Not a value. |
| number | `[0-9]+(\.[0-9]*)?([eE][+-]?[0-9]+)?` or `\.[0-9]+(exp)?`. Also `0x` hex and `0b` binary. The exponent counts only if a digit follows, so `2e` is 2 then the name `e`. `3.` is one number. |
| name | as in §5.5; π is its own name |
| operator | `:= => -> == != <= >= **`, or any other single character |

**Classifier** `classify(name) → UNKNOWN | VALUE | FUNCTION | KEYWORD | USERFN`
(`src/tiinput.h:18-23`, `src/tiinput_glue.cc:14-68`). It checks, in this order:

1. KEYWORD list: `and break by case catch continue default div do elif else end fi for from
   function global if in local mod not od of or program repeat return step switch then to try
   until while xor`.
2. VALUE constants: `I PI Pi e euler_gamma i inf infinity minus_inf oo pi plus_inf undef
   unsigned_inf π`.
3. giac builtins: a unary-operator token is FUNCTION; a symbol, literal or number token is
   VALUE; any other token is KEYWORD.
4. User variables: an assigned function or program is **USERFN**; any other assigned variable
   is **VALUE**.
5. Everything else is UNKNOWN.

For cas-evo the classifier becomes: our command and function names are FUNCTION, our constants
are VALUE, keywords are KEYWORD, the variable store gives VALUE or USERFN, and everything else
is UNKNOWN.

**State while scanning** (`:263-270`):
- `lk`: the kind of the previous token: NONE, NUM, NAME, STORE (`=>`), or OTHER;
- `lend`: the previous token ends a value;
- `lcall`: the previous token is a name whose following `(` is a call.

**Rules** (`:271-342`). A `*` is always inserted directly **after** the previous token, before
any blanks. So `x y` → `x* y`.

- **Number.** Insert `*` if `lend` and `lk != NUM`. Then `lk = NUM` and `lend = true`.
  Number after number gets no `*`: `2 3` and `1.2.3` are unchanged.
- **Unit** (a name starting with `_`). Copied. `lend = false`, so it never takes part.
- **Name** (class `c`). Insert `*` if `lend` and `c != KEYWORD`. Then let `q` be the index of
  the next non-blank character, and compute:
  - `paren`: `s[q] = '('`;
  - `def`: `paren`, and the matching `)` is followed (blanks allowed) by `:=`. FlowCE
    precomputes this for all parentheses with a right-to-left matching pass, run only when the
    line contains `:=` (`im_defmarks`, `:137-185`);
  - `asg`: `s[q..q+1] = ":="`.

  **Cutting.** The name is cut when `c` is UNKNOWN, and not `def`, not `asg`, not right after
  `=>` (`lk != STORE`), and the name is 2-32 ASCII letters and not a Greek name. The Greek names
  are `alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron rho sigma
  tau upsilon phi chi psi omega` (`:187-205`). The cut is `im_cut(name, fn = paren)`
  (`:207-246`), a dynamic program that splits the name into the **fewest pieces**:
  - a piece is a single letter, or a substring of length 2 or more classified VALUE, or (only as
    the **last** piece, and only when `fn`) a FUNCTION or USERFN name;
  - `oo` and `inf` are never pieces, and the whole name is never one piece;
  - ties go to the **longest first piece** (end positions are tried longest first);
  - the cut is rejected, and the name stays whole, when it needs more than 3 pieces, or when all
    pieces are single letters, `fn` holds, and the name is longer than 2 letters;
  - the pieces are joined with `*`.

  After the name: `lk = NAME`; `lend` = the last piece is VALUE or UNKNOWN. `lcall` holds when
  any of these is true:
  - `def`;
  - the last piece is FUNCTION or USERFN;
  - the last piece is the single letter `f`, `g` or `h` (also `y` and `u` when the line contains
    `desolve`, so that `y(0)=1` is a condition, `:253-255`), and that letter is not VALUE;
  - the last piece has more than one letter and is UNKNOWN: an uncut unknown name before `(`
    is a call.
- **Operator.** For `(`, insert `*` if `lend` and not `lcall`. A single-character `)`, `]`, or
  a `!` after a value sets `lend = true` (postfix factorial). All other operators, including
  `}`, set `lend = false`. `=>` sets `lk = STORE`. Every operator clears `lcall`.

**Selected expected outputs** (`tests/host/test_tiinput.cc:76-290`; port all of them):

| input → output | input → output | input → output |
|---|---|---|
| `2x` → `2*x` | `2pir` → `2*pi*r` | `xy` → `x*y` |
| `abc` → `a*b*c` | `abcd` → `abcd` | `2xyz` → `2*x*y*z` |
| `xsin(x)` → `x*sin(x)` | `xsinx` → `xsinx` (left to `ti_rewrite`) | `xasin(x)` → `x*asin(x)` |
| `pi(x+1)` → `pi*(x+1)` | `(x+1)(y-1)` → `(x+1)*(y-1)` | `sin(x)cos(x)` → `sin(x)*cos(x)` |
| `f(x)` → `f(x)` | `F(x)` → `F*(x)` | `e(x+1)` → `e*(x+1)` |
| `ab(x)` → `a*b*(x)` | `abc(x)` → `abc(x)` | `xy(x+1)` → `x*y*(x+1)` |
| `foo(x)+1` → `foo(x)+1` | `pivot(x)` → `pivot(x)` | `piarea(2)` → `pi*area*(2)` |
| `f(x):=x^2` → unchanged | `g(x):=2x` → `g(x):=2*x` | `ab:=2cd` → `ab:=2*c*d` |
| `5=>abc` → unchanged | `x^4-1=>*` → unchanged | `ab(x):=x;ab(2)` → `ab(x):=x;a*b*(2)` |
| `2e` → `2*e` | `2ex` → `2*e*x` | `2.5e-3x` → `2.5e-3*x` |
| `1e5` → `1e5` | `2i` → `2*i` | `3+4i` → `3+4*i` |
| `3!x` → `3!*x` | `x!=y` → unchanged | `x^2y` → `x^2*y` |
| `x^-1y` → `x^-1*y` | `1/2x` → `1/2*x` | `-xy` → `-x*y` |
| `phi` → `phi` | `xi` → `xi` | `2tau` → `2*tau` |
| `ooo` → `o*o*o` | `book*2` → `book*2` | `2oo` → `2*oo` |
| `x y` → `x* y` | `2 3` → `2 3` | `{1,2}x` → `{1,2}x` |
| `l[2]x` → `l[2]*x` | `ans()2` → `ans()*2` | `max(2x,3)` → `max(2*x,3)` |
| `xy//xy\nxy` → `x*y//xy\nx*y` | `"xy"` → `"xy"` | `5_m*2x` → `5_m*2*x` |

Note that `1/2x` gives `1/2*x`, which is (1/2)·x, as on a TI.

### 5.7 Text passes after implicit multiplication (Focus only; `src/answer.cc:2980-2983`)

- **`log` is base 10** (`src/answer.cc:1807-1824`). Every `log(` is changed to `log10(` when
  it is a whole word (the previous character is not alphanumeric or `_`), it is outside a
  string, and there is room in the buffer. The 2D display draws `log10` as `log` and `asin` as
  `arcsin` (`src/mathinput.cc:236-241`).
- **Riemann-sum index `i`** (`src/answer.cc:1828-1870`). In `sum(`, `seq(` or `product(`, when
  the 2nd argument is the bare letter `i` (or `i=...`), every standalone `i` inside the call
  becomes the first of `k`, `j`, `m` that the call does not use. The length is unchanged, so no
  extra room is needed.

### 5.8 Evaluation-side input rules (`answer_before`, `src/answer.cc:3053-3108`)

- `perm(n,k)` and `nPr(n,k)` become `comb(n,k)*k!` (`:2986-2996`).
- **Real odd roots.** When the input has no `i`, odd roots of negative numbers are real:
  `(-8)^(1/3)` is `-2` (`:3060-3062`).
- **`x=a` stores** `a` in `x` (giac `equaltosto`). The exception is a **self-referential**
  `x=(-x/2)^2`, which is an equation (`:3063-3066`).
- **A lone equation is solved.** An `=` equation with exactly one unassigned unknown (ignoring
  pi, infinities and undef) becomes `solve(eq, unknown)`, and its solutions print as `x=...`
  (`:1734-1749,3067-3079`). `solve(expr)` without a variable solves for `x`.
- **Decimal coefficients.** `solve` with decimal coefficients becomes
  `evalf(solve(exact(eq),x))`, because giac's solve fails on floats (`:3080-3083`).
- **Definitions.** `f(x):=...` on one line (also typed `f(x)=...`, §5.5 rule 0) defines the
  function silently and shows the message `f(x) defined` (`src/main.cc:630-640,1238-1242`).
- **The rest is answer logic** (tables, u-substitution, by parts, the Weierstrass substitution,
  infinite sums, `+ C` constants, DNE limits). See `flowce-answer-format.md`.

### 5.9 `sto→` (`=>`)

- The key inserts `=>`, giac's store-to-the-right operator: `5=>b` stores 5 in `b`
  (`src/console.cc:1856-1858`).
- When `sto→` is pressed first on an empty line, the line becomes `ans()=>` (§5.3).
- The name after `=>` is never cut into letters: `lk == STORE` (`src/tiinput.cc:312`).
- giac's **conversion targets** are documented in the catalog (`src/menufr.cc:715,739,817,878,935,973`):

  | input | effect |
  |---|---|
  | `expr=>*` | factor |
  | `expr=>+` | partfrac |
  | `expr=>/` | simplify |
  | `expr=>sin`, `=>cos`, `=>tan` | rewrite in terms of that function |
  | `eq=>=>` | solve |

  These are **opt** for cas-evo; FlowCE never shows them in a menu.
- KhiCAS extras, all **out**:
  - `...=>Y1`..`=>Y0` also writes the TI equation variable `Yk` (`src/main.cc:1143-1154`);
  - `=>` alone saves the session (`src/main.cc:1477-1480`);
  - `[A]`..`[I]` alone imports a TI matrix (`src/main.cc:1133-1142`).
- Text `:=` (left assignment) also works and is never cut either: `abc:=5`.

---

## 6. Settings and themes

### 6.1 `mode` → Config (`src/console.cc:884-949`)

A list card titled "Config" (KhiCAS `doMenu` drawn by `focus_list`, `src/menufr.cc:29-45`):

| item | effect |
|---|---|
| Simplify answers | checkbox, on by default. Off sets giac `autosimplify(0)`, so results stay as giac computed them (e.g. to store a factored form with `sto→`). The tables and textbook printing still apply. The status bar shows `SIMPLIFY OFF`. The setting is saved with the session (`src/answer.h:24-33`, `src/answer.cc:3044-3052`, `src/focus.cc:506-507`). |
| Set time | prompts for the clock as `HH.mm` |
| Clear variables | confirm, then `restart` (`src/main.cc:1467-1475`) |
| Shortcuts | a scrollable text page (`src/menufr.cc:719`, `src/focus_menu.cc:373-419`) |
| About | credits page (`src/menufr.cc:720`) |
| Quit | quit |

The *Shortcuts* text is FlowCE's own user guide in one string (`src/menufr.cc:719`). It is a
good model for cas-evo's F5 help page.

**Angle unit.** FlowCE has **no in-app radian/degree toggle**. At start it copies the TI-OS
angle mode into giac (`src/main.cc:1435`) and shows `RAD`/`DEG` in the status bar
(`src/focus.cc:503`). cas-evo has no OS mode to read, so its F3 settings must own this setting
(as settled). The `EXACT` label is constant.

**Persistence (not copied by cas-evo).** FlowCE keeps the session across runs:
- the history and variables are saved on quit (`src/main.cc:1423`) and restored at start
  (`:1432`);
- the theme is stored in the appvar `FocusUI` as `N` or `P` (`src/focus.cc:933-944`).

### 6.2 Themes: Paper and Night (`src/ui_gfx.h:34-40`, `src/ui_gfx.c:54-63`)

*more → Paper or Night* toggles the theme **instantly**. Every pixel of the Focus UI is a
palette index, so FlowCE rewrites only the palette (`src/focus.cc:939-944`,
`src/ui_gfx.c:102`). Text is anti-aliased with two intermediate shades per foreground/background
pair, at 1/3 and 2/3 of the way to the ink (`src/ui_gfx.c:82-89`). Fonts: Atkinson Hyperlegible
for the UI and STIX Two for math (`README.md:169`).

| slot | role (where used) | Paper | Night |
|---|---|---|---|
| UC_BG | stage background | `#F7F8FA` | `#0C0F14` |
| UC_INK | primary text, results, the edit line | `#111419` | `#EAEEF3` |
| UC_SUB | secondary text: history inputs, hints, `+ C`, the `≈` line, messages | `#6C7581` | `#86919E` |
| UC_LINE | hairlines, entry separators, scrollbar track | `#DBE0E7` | `#262E3A` |
| UC_ACC | accent: caret, selection frame, form chip text, 2nd chip, tab icons, "CE" of the logo | `#245CCC` | `#64A5FF` |
| UC_ACCSOFT | selected-entry fill, chips, open tab, prompt field | `#E2EAFA` | `#182840` |
| UC_ONACC | text on an accent fill (selected search row) | `#FFFFFF` | `#070B11` |
| UC_CARD | popover and card fill, search field | `#FFFFFF` | `#161C24` |
| UC_BAR | F-key bar fill | `#FFFFFF` | `#10151C` |
| UC_BARINK | F-key bar labels | `#4E5662` | `#96A0AD` |
| UC_GREEN | alpha chip, alpha menu names | `#278C4A` | `#56C882` |
| UC_SHADOW | card drop shadow | `#D0D6DE` | `#040609` |
| UC_WHITE | text on a colored chip | `#FFFFFF` | `#070B11` |
| UC_RED / UC_PURPLE / UC_ORANGE | graph curves 3-5 (after ACC and GREEN) | `#C74440` / `#7048B8` / `#E27618` | `#FF7066` / `#B692FF` / `#FFAA52` |
| UC_DIM | stage behind a popover: BG moved toward `dim_to` | `#A9ACB1` (36% toward `#1E242E`) | `#06080A` (50% toward `#000000`) |

While a popover is open, **every** stage color (palette bank 0) is dimmed the same way: 36%
toward `#1E242E` on Paper, 50% toward black on Night. The card itself is drawn bright in bank 1
(`src/ui_gfx.c:90-91,103`, `src/focus_menu.cc:1-5`).

---

## 7. Implications for cas-evo

1. **One text buffer, rewritten at evaluation time.** Copy FlowCE's split. Keys insert plain
   command text such as `ans()`, `sqrt(`, `=>`. The history stores the text as typed. The
   rewrites (§5.4-5.7) run only when the line is evaluated. This keeps the 1D editor simple and
   lets a later 2D editor share the same buffer and pipeline.
2. **Port `tiinput.cc` as two linear, non-recursive passes.** These are `ti_rewrite` and then
   `ti_implicit_mult`, both using a pluggable `classify`. The only recursion is `ti_rewrite` on
   the argument of `sin^2(...)` (§5.5 rule 3). Use an explicit work stack there. The
   `im_defmarks` parenthesis matching is already a loop with a flag stack. Port
   `tests/host/test_tiinput.cc` (about 200 cases plus property tests: only `*` added,
   idempotent) as the first T1 golden tests.
3. **The classifier is the coupling point.** cas-evo's command registry, constants and variable
   store must answer the five-class query. Name splitting depends on it (`pir` → `pi*r` only
   because `pi` is VALUE).
4. **Catalog data model.** Store the same five fields per entry: signature, insert, desc,
   example, category. They drive the search, the call templates (required-argument rule, §1.3),
   the argument labels, and the help line (first sentence plus `e.g.` example). FlowCE's English
   catalog lacks `expand` and `series`, and keeps some French or truncated help text. Write
   cas-evo's T1-T3 entries fresh. Heap is limited, so store them compactly and load them lazily.
5. **Keep the TI-user habits**, all cheap:
   - the leading-operator rule, including `sto→`;
   - `(-)` as a minus sign;
   - 2nd+enter for ENTRY;
   - autoclose of brackets on ENTER;
   - jump to the empty slot on ENTER;
   - F1/F2 actions that wrap the line or Ans;
   - a lone equation solved for its single unknown;
   - `x=5` stores, unless self-referential;
   - `f(x)=...` defines a function;
   - `log` is base 10;
   - the Riemann `i` index renamed.
6. **Key mapping on the EVO.** FlowCE's F1-F5 popover set (algebra, calculus, trig, symbols,
   more) differs from the settled cas-evo plan (F1 menu, F2 Ans/history, F3 settings, F4 forms,
   F5 help). Keep cas-evo's plan, but fold FlowCE's popover *contents* into the F1 command menu
   tabs, and FlowCE's *more* actions (theme, clear history) into F3. `▼` on the edit line to
   search commands is worth copying if a key is free.
7. **Screen budget.** FlowCE uses 16 px for the status bar, 202 px for the stage and 22 px for
   the F-key bar on a 240 px screen. The EVO Python area is about 210 px, so cas-evo should drop
   or merge the status bar (show RAD/DEG and the 2nd/alpha state in the F-key bar row). The
   Paper and Night palettes above can be used as RGB values. ti_graphics has no custom fonts or
   anti-aliasing, so expect plainer text.
8. **Out of scope.** 96 of the 166 English catalog entries (58%) are out of scope: programming,
   lists, matrices, drawing, colors, plots, transforms and number theory. What remains:
   - 28 T1-T3 entries, plus `expand`, `series`, `int`, `surd` and `'` from §2.4;
   - 42 "opt" candidates.
9. **Test corpora worth mining** (inputs only; compare answers with SymPy):
   - `tools/emu/cases/*.tsv` (75 files: Ans, ENTRY, leading-operator, Calc 1-3 sessions);
   - `tools/hostgiac/corpus_calc1_web.txt`, `corpus_calc23.txt`, `corpus_calc23_web.txt`
     (about 720 problems written as students type them, `kind ; input ; expected`; the `eval`
     lines carry expected values);
   - `tools/hostgiac/numcheck_calc.txt`.
