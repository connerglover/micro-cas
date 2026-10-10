# Algorithm survey for cas-evo (T1 / T2 / T3)

Reference study, 2026-10-10. This file feeds the design doc. It is not a spec.

## Source keys

- `G/` is `C:\Users\conner\.cache\cas-evo-ref\ti-ce-giac\`, the trimmed giac that FlowCE ships.
  Each file has a `k` prefix: `kintg.cc` is giac's `intg.cc`, `kseries.cc` is `series.cc`, and so on.
  The build defines `TICE` and `XLIGHT`.
  **Risch is a stub.** `G/krisch.cc:46` returns the whole integrand as "remains to integrate".
  So FlowCE's integrator is all heuristics, and those heuristics covered its calculus-course scope.
- `F/` is `C:\Users\conner\.cache\cas-evo-ref\FlowCE\src\`. `F/answer.cc` holds the "textbook" fast paths that FlowCE
  added on top of giac. Its comments give the reasons: giac took 18-90 s on the CE for some inputs, or it
  printed forms that are not textbook forms. For our scope these paths are often a better model than giac.
- A `file:line` reference points to the line where the function is defined. For a step inside a long function, the
  reference points to the comment that starts the step.

---

## 0. Summary of conclusions

1. **C-level recursion is a second risk next to Python recursion.** On MicroPython, `==`, `hash()`, `repr()` and
   comparison of nested tuples or lists recurse in C. That recursion may hit the same small C stack that gives the
   10-frame limit, or it may crash the calculator without an exception. Probe this before you choose the node
   representation (section 1.6). Safe design: **intern the nodes** (hash-consing). Each node is a flat tuple of a
   small-int op and child ids. Then equality is an int compare, hashing never goes deep, and memo tables use ids as keys.
2. **Four iteration patterns cover every algorithm** (section 1.2): a post-order "kernel list" over the DAG, a
   fold or memo over that list, a worklist that rewrites until nothing changes, and a task machine for search
   problems. These are integration, solve, limit strategies and ODE classification. giac already uses the first
   pattern for series: `series__SPOL1` (`G/kseries.cc:1408`) walks the kernel list sorted by size and memoizes each
   expansion. Copy that design.
3. **Do not build a general AC pattern matcher.** giac's integrator, solver and limit code are op-indexed tables plus
   a few *shape predicates*: `is_constant_wrt`, `is_linear_wrt`, `is_quadratic_wrt`, `decompose_prod` and
   `extract_cst` (`G/kintg.cc:171-255`), plus kernel lists `lvar` / `rlvarx`. The "rule engine" should be data tables
   keyed by op, with procedural shape checks.
4. **Polynomial core:** dense univariate coefficient lists over Q, best kept as integer lists with one shared
   denominator. Most of T1 and T2 work only in the main variable. For multivariate gcd, use Kronecker substitution
   (y → x^D) so the univariate code does the work. Skip multivariate Hensel.
5. **Integration returns (F, R)**, the part found and the rest left over, like giac's `remains_to_integrate`.
   This makes linearity and partial success simple and needs no exceptions. Check each answer with d/dx, or
   numerically at 2-3 points. giac does this check (`ck_int_numerically`, `G/kintg.cc:3014`), and FlowCE checks
   with Gauss-Legendre (`F/answer.cc:1123`).
6. **Limits:** giac uses substitution, then a series at the point, then Gruntz MRV at +∞ (`G/kseries.cc:2467`,
   `2403`, `2867`). It never uses L'Hôpital. Gruntz is too large for us. Use this chain instead:
   substitution → rational cancel / degree compare → series (Laurent) at the point → bounded L'Hôpital loop →
   exp/power/log growth classes → numeric estimate (labelled ≈, with one-sided values for "does not exist").
7. **Factoring:** take content, then square-free part (Yun), then rational roots, then x^d substitution, cyclotomic
   x^n±1, and the homogeneous case. After that, use Kronecker's method for quadratic factors. This is complete for
   degree ≤ 5. Zassenhaus is a stretch goal.
8. **Probe first:** float precision (single or double), `math.gcd` / `isqrt` / `factorial`, `int.bit_length`,
   dict iteration order, and nested-tuple `==` / `hash` / `repr` depth. Each result changes a design choice.
9. **Speed:** a 20k-iteration loop takes 0.066 s, which is about 300k simple loop iterations per second. A search
   with 30k trial divisions takes seconds. Every search needs a budget, and every loop must poll for [clear].
   For numerics, compile the expression once to a Python `lambda` source string with `eval`, so each sample point
   runs at native speed.

---

## 1. Cross-cutting findings that shape the architecture

### 1.1 Recursion also hides in C

- The probe measured about 10 Python frames. MicroPython raises "maximum recursion depth exceeded" from
  `MP_STACK_CHECK`, which measures the C stack. Every Python call recurses in C, and so do some builtins on nested
  containers: tuple `==` and `hash`, `repr`/`print` of nested lists, and `sorted` on nested keys. Some of those C
  paths may not call the stack check at all, and then deep nesting crashes the device.
- **Recommendation: interned DAG.** Use a node table (`NODES` list: id → `(op, c1, c2, ...)` with int children, and
  `INTERN` dict: tuple → id). Each tuple is flat, so `hash` and `==` stay one level deep in C. Results:
  - Structural equality is `a == b` on ints.
  - Shared subtrees are stored once. This saves heap: `diff` and `series` repeat subtrees a lot.
  - Memo tables (`D[nid]`, `SERIES[nid]`) are plain dicts keyed by int.
  - Garbage: between commands, copy the nodes reachable from Ans, history and variables into a fresh table
    (iterative mark-and-copy), then drop the old one. Without this the table only grows.
- Numbers inside nodes: `(NUM, n, d)` with Python ints, and `(SYM, name_index)`. Do not use operator overloading
  for the core types. Each dunder call costs a frame, and so does each `key=` call made by `sorted`.

### 1.2 The four iteration patterns

1. **Post-order kernel list.** Visit each node of the DAG once, children before parents, using an explicit stack.
   ```python
   def postorder(root):
       out = []; seen = set(); st = [root]
       while st:
           n = st.pop()
           if n >= 0:
               if n in seen: continue
               seen.add(n); st.append(~n)          # ~n = "emit after children"
               for c in kids(n):
                   if c not in seen: st.append(c)
           else:
               out.append(~n)
       return out
   ```
   giac's version is `rlvarx` (`G/kseries.cc:2121`, sorted by size in `tri_rlvarx` at `2145`). It is the core of
   `series__SPOL1` (`G/kseries.cc:1408`) and of integration step 2 (`G/kintg.cc:2453`).
2. **Fold or memo** over that list: `for n in postorder(r): memo[n] = rule[op(n)](n, [memo[c] for c in kids(n)])`.
   This one pattern runs simplify-on-build, diff, subst, float eval, the series engine, `free_of`, node counts,
   and printing (with a second pass for layout). It uses one frame, plus one for the rule function.
3. **Worklist rewriting** until no rule fires, with a pass limit. Use it for simplify identities and for the
   "try candidates, keep the smallest" step (FlowCE `auto_simplify`, `F/answer.cc:781`: it keeps a form only when
   `taille` (node count) goes down).
4. **Task machine** for search problems (integration, solve, ODE classification, multi-strategy limits).
   A task stack plus a value stack. Each handler either pushes a value, or pushes child tasks and a
   "combine" continuation. Handlers never call the driver. One loop holds the step budget and the cancel poll.
   ```python
   def run(task):
       tasks = [task]; vals = []; steps = 0
       while tasks:
           steps += 1
           if not steps & 31: poll_cancel()     # ti_system.escape() through a UI hook
           if steps > BUDGET: raise GiveUp()
           t = tasks.pop()
           HANDLERS[t[0]](t, tasks, vals)      # push tasks and/or values
       return vals.pop()
   ```
   giac's integrator is mutually recursive: `integrate_id_rem` → `linear_integrate_nostep` → `integrate_id_rem`,
   `integrate_rational` → itself, `integrate_sqrt` → `linear_integrate_nostep`. Each of those recursive calls becomes
   a pushed sub-task here.

### 1.3 Shape predicates and op tables, not a pattern matcher

giac's core helpers, worth copying almost one for one:

| helper | giac | job |
|---|---|---|
| `free_of(e,x)` | `is_constant_wrt` `G/kintg.cc:171` | e does not depend on x |
| `linear(e,x)` → (a,b) | `is_linear_wrt` `:188` | e = a·x+b with a, b free of x |
| `quadratic(e,x)` → (a,b,c) | `is_quadratic_wrt` `:200` | |
| `split_sum(e,x)` / `split_prod(e,x)` | `decompose_plus` `:209`, `decompose_prod` `:222`, `extract_cst` `:238` | constant part vs x part |
| `linearity(e,x,f)` | `linear_apply` `:255` | apply f per term, constant factors pulled out |
| `kernels(e)` / `kernels_x(e,x)` | `lvar` `G/ksym2poly.cc:128`, `lvarx` `G/kseries.cc:2087`, `rlvarx` `:2121` | the maximal non-rational subterms. `+`, `*`, `/` and integer `^` are transparent. |
| `as_poly(e,x)` → coeffs or None | `e2r` `G/ksym2poly.cc:1874`, `fxnd` `:853` | polynomial or rational function in x |
| `rewrite_in(f,u,x)` → g with f = g(u) or None | `is_rewritable_as_f_of` `G/kintg.cc:2035` and `1921` | used by u-substitution |

The tables are keyed by op: derivative (`D_at_*` in `G/kusual.cc`), antiderivative of f(ax+b)
(`primitive_tab_primitive`, `G/kintg.cc:1909`), Taylor recurrences (`taylor_exp` `G/kusual.cc:1046`,
`taylor_atan` `:861`, `taylor_asin` `:2501`), solve inverses (`isolate_fcns`, `G/ksolve.cc:217`), and special
values (`table_cos`, `G/kusual.cc:9452`).

### 1.4 Data representations

- **Integers:** Python ints (bignum works on the device). **Rationals:** two ints, normalized (den > 0, gcd 1).
- **Algebraic numbers:** only `sqrt` and `nth-root` of square-free (power-free) positive integers, with i for √−1.
  No RootOf. giac's `algebraic_EXTension` machinery is out of scope.
- **Univariate polynomials** in the main variable: a dense list of ints plus one denominator (Q[x] as Z[x]/d).
  Coefficients that are expressions (parameters a, b, k) go through the generic path: "normal" form on node trees.
- **Multivariate polynomials** (expand, normal): a sparse dict from exponent tuple to rational coefficient, over
  the kernel list. giac's `polynome` is the same idea: a sorted distributed list of monomials.
- **Truncated power series:** a list of coefficients (node ids or rationals), a valuation offset (Laurent), and an
  order. giac's `sparse_poly1` also stores exponents for Puiseux. We can allow a rational step (1/2) later if needed.
- **Never depend on dict or set iteration order.** CPython 3.7+ keeps insertion order. MicroPython may not
  (open-addressing table), and it was not probed. Always sort with explicit keys before output or canonical
  ordering. Otherwise desktop tests pass and the device prints terms in a different order.

### 1.5 Partial results and checks

- **(F, R) contract** for integration, sums, and the series used in limits. A sum of terms joins the Fs and the Rs.
  Show `F + ∫R dx + C` when R ≠ 0 (giac: `G/kintg.cc:3516`).
- **Check after search.** Differentiate F, simplify F′−f, and if that is not clearly 0, compare numerically at 3
  points. For definite integrals, compare with quadrature: giac `ck_int_numerically` `G/kintg.cc:3014`
  (relative error 1e-3, then "returning both"), FlowCE `table_definite` `F/answer.cc:1123` (12-point
  Gauss-Legendre in three uneven panels, so an odd pole cannot cancel). This finds bugs and wrong-branch results
  cheaply.

### 1.6 Probe these on the device before coding

| probe | why |
|---|---|
| `repr(1/3)`, `2.0**53+1 == 2.0**53`, `1e300*10` | single or double floats. FlowCE's CE giac had 7-digit floats (comment at `F/answer.cc:1409`). The 10-significant-digit decimal line needs doubles, or big-int fixed point. |
| `hasattr(math,'gcd')`, `'isqrt'`, `'factorial'`, `'log2'` | MicroPython builds often lack `gcd` and `isqrt`. Write your own (Euclid loop, Newton isqrt). |
| `(5).bit_length()`, `int.from_bytes`, `pow(a,b,m)` | isqrt start value, modular arithmetic |
| nested tuple of depth 20/50/100/300: `==`, `hash`, `repr`, `sorted([t1,t2])` | the C-recursion risk (section 1.1). Save your work first, the device may reset. |
| `{}` iteration order after many inserts and deletes; `set` order | canonical-order bugs |
| `eval("lambda x: " + 200-char expr)` with nested `math.sin(...)` | numeric compile speed, and parser depth |
| `gc.mem_free()` before and after `import` of a 500-line module | real bytecode cost per line, for the budget below |
| `sorted(lst, key=f)` where `f` calls one more function | confirm key calls cost 1 frame and do not stack up |

### 1.7 Memory and speed budget (estimates, check with probe)

- Rough figure: 20-30 bytes of heap per non-comment line of dense code after compile. A 1000-line module is
  about 25 KB. With about 180 KB free, keep about 60-90 KB of code resident. Load the T2 and T3 families on demand
  and unload them after the command (`del sys.modules[n]; gc.collect()`).
- Suggested split: core (nodes, numbers, parser, printer, simplify, poly) resident. `factor`/`solve`, `diff`,
  `series`+`limit`, `integrate`, `sums`, and `ode` as separate lazy modules.
- Speed: Python on the EVO runs about 10^5-10^6 simple ops per second. Every search loop needs a hard cap
  (rational-root candidates, Kronecker combos, integration tasks, series order growth, quadrature intervals).

---

## 2. T1

### 2.1 Exact rationals and big integers

- **giac:** `_FRAC` normalization in `simplify(n,d)` `G/kgen.cc:9836`.
- **Sketch:** `qnorm(n,d)` uses a gcd loop (`while b: a, b = b, a % b`) and makes the sign of d positive.
  For add, Henrici's trick, gcd of denominators first, keeps numbers small. `qpow(q, k)` handles negative k by
  inverting. For rational exponents, `q^(m/n)` becomes `num^(m/n) / den^(m/n)`, then the radical code (2.2) runs.
- **Subset:** all of it. It is small.
- **Pitfalls:** `//` and `%` floor toward −∞, so normalize the sign before dividing. `float(huge_int)` overflows,
  so make the decimal line from ints: `n*10^k // d`, rounded, with 10 significant digits. Printing huge ints is
  quadratic but fine at calculator sizes. Integer `0^0`: decide on 1. `0^(-1)` is undefined, show an error.

### 2.2 Radical simplification

- **giac:** `sqrt` `G/kusual.cc:1312` (perfect square → `isqrt`. 2, 3, 6 are fast paths. Otherwise
  `zint2simpldoublpos` `:1073` splits n = b²·a with a square-free, using `ifactors` or trial division `pfacprem`
  `G/kifactor.cc:562` for big n). `sqrt(p/q) = sqrt(p*q)/q` (`:1416`). Exact complex sqrt
  `sqrt(a+bi) = ½√(2(a+ρ))·(1 + i·b/(a+ρ))` with ρ = |z| (`:1361-1375`). Denesting: `is_sqrtxy`
  `G/ksym2poly.cc:2541` writes `√(d + c√e)` as `√a + sign(c)·√b`, where a and b are the roots of
  `X² − dX + c²e/4`, when those roots are rational. `normalize_sqrt` `:2597` takes repeated factors out from under
  √ in expressions. FlowCE real odd roots: `(-8)^(1/3) = -2`, `real_root_node` `F/answer.cc:1180`.
- **Sketch (n-th root of an integer N):** trial-divide by 2, 3, 5, … up to `min(LIMIT, N^(1/3))` and collect each
  prime power p^e as `p^(e//k)` outside and `p^(e%k)` inside. If the cofactor C left at the end is > 1, test whether
  it is a perfect k-th power (integer Newton root). This is complete when no prime factor is greater than LIMIT
  except possibly one prime, or one square of a prime. Canonical node: `coeff * pow(r, 1/k)` with r k-th-power-free.
  - Product rule: `√a·√b → √(ab)` for positive radicands. Then simplify the radical again.
  - Rationalize monomial denominators: `1/√2 → √2/2`. Rationalize binomial denominators `1/(a+b√r)` with the
    conjugate, only inside `simplify` (not in auto-simplify, which would cause swell).
  - Denest: only `√(p + q√r)` with rational p, q, r. Test whether `p² − q²r` is a rational square s². If yes,
    the answer is `√((p+s)/2) ± √((p−s)/2)`.
- **Subset:** square and n-th roots of rationals, product merge, monomial rationalization, i extraction
  (`√(-4) = 2i`), one-level denesting, odd real roots of negatives (TI convention).
- **Pitfalls:** `√(x²) = |x|`. Keep `abs` like giac (`in_normalize_sqrt` with keep_abs), unless an
  assumption says x ≥ 0. `√a·√b ≠ √(ab)` when both are negative. `(x^2)^(1/2)` must not become x. Trial division
  of a 40-digit prime is slow, so cap LIMIT (for example 10^4) and accept a radicand that is not fully reduced.
  Real versus complex mode: `(-1)^(1/3)` is −1 (TI) or e^(iπ/3) (giac). Pick −1 and document it.

### 2.3 Exact constants and special values

- **giac:** `cos` `G/kusual.cc:1554`, `sin` `:1823`, `tan` `:2102`. A multiple of π/12 is found by
  `is_linear_wrt(e, π)` and `is_multiple_of_12` `:134`. In degree mode the argument/15 must be an integer
  (`is_multiple_of_pi_over_12` `:144`). Value tables: `table_cos[25]` and `table_tan[13]` `:9452`. Special cases:
  π/5 multiples `(√5±1)/4`, π/8 multiples `√(2±√2)/2`, π/10 through sin. Addition reduction
  `cos(kπ/12 + b) = cos(kπ/12)cos b − sin(kπ/12) sin b` (`:1696`), and `cos(nπ + b) = (−1)^n cos b`.
  Inverses: `atan` `:652` (exact for ±1, ±√3, ±√3/3, ±∞), `asin` `:2299`. `ln` `:383`, `exp` `:936`
  (`exp(ln u) = u`, `exp(iπ) = −1`).
- **Sketch:** reduce the argument to `k·π/12` with rational k modulo 2 (24 slots). Then do a table lookup with sign
  symmetry. In degree mode, k = deg/15. Inverse trig: a small dict from canonical value node id to angle. Log rules
  on construction: `ln(1)=0`, `ln(e)=1`, `ln(e^u)=u` (real u), `log(10^k)=k`, `log_b(b^k)=k`, `e^(ln u)=u`.
- **Subset:** multiples of π/12 for sin, cos, tan, sec, csc, cot, plus π/8 and π/5 values (cheap). The
  inverse table over the same values. Degree mode.
- **Pitfalls:** tan at π/2 is undefined. Show an error or "undefined", not ∞. `ln(e^x) = x` holds only for real x.
  `asin(sin(x)) ≠ x` in general, so keep it. Degree mode changes derivatives and integrals by a factor π/180
  (giac `int_sin` `G/kintg.cc:1832` multiplies by 180/π). Show `e` as e, not `exp(1)` (FlowCE output rewrite).

### 2.4 Canonical simplification (sums, products, powers)

- **giac:** two levels.
  1. On construction: flattening, constant folding, and `+`/`*` merging happen inside `operator+` and `operator*`.
  2. `normal` `G/ksym2poly.cc:2771`: `alg_lvar` (`:293`) collects kernels, `e2r` (`:1874`) converts to a rational
     function in the kernels (a sparse multivariate polynomial pair), the gcd cancels, and `r2sym` (`:1975`) converts
     back. `ratnormal` (`:3145`) is the same without algebraic extensions. `simplify` (`G/ksubst.cc:2327`) adds
     identity passes: `lncollect`, `texpand` for exp, `powneg2invpow`, `cossinexp2rootof`, abs factoring, and
     merging powers with the same base (`tsimplify_common`).

  FlowCE replaces giac's slow `simplify` with "candidates, keep the smallest": ratnormal, factored denominator,
  `tan2sincos` then `trigsin`/`trigcos` (sin²+cos²=1 rewrites), `tlin`, `merge_sqrt`
  (`auto_simplify` `F/answer.cc:781`). Its comment says giac's simplify took 5.8 s of 6.4 s for d/dx sin(x)/x.
- **Sketch (ours):**
  - **Auto-simplify in the constructors.** Children are canonical already, so each constructor runs once with no
    recursion.
    - `add(terms)`: flatten nested adds, fold numbers, collect like terms with a dict `term_id → rational coeff`
      (split `c·t` into c and t), drop zeros, sort by a canonical key, unwrap a single term.
    - `mul(factors)`: flatten, fold numbers, collect powers with a dict `base_id → exponent` (exponents add when
      both are rational, or base ∉ negatives, or the exponents are integers), and rules for 0, 1 and −1.
    - `pow(b, e)`: integer e on a number gives an exact value. Rational e on a number goes to 2.2.
      `(b^m)^n → b^(mn)` only for integer n, or m odd/positive-base-safe. `x^1 = x`, `x^0 = 1`.
  - **`normal(e)`:** iterate over the kernel list, build sparse multivariate num/den dicts bottom-up (sums add,
    products multiply, integer powers by square-and-multiply), cancel the gcd (1.4 / 2.6), and rebuild. This is the
    canonical form for "is it zero?" tests across the system.
  - **`simplify(e)`:** candidates = [auto(e), normal(e), trig-identity forms, log-collect forms, radical
    merge]. Keep the smallest by node count, ties going to the auto form.
- **Subset:** constructors + `normal` + `sin²+cos²` via substitution of `sin² → 1−cos²` (keep it if smaller) +
  ln-collect + exp-merge. Leave out general trig simplification.
- **Pitfalls:**
  - `x/x → 1` hides x ≠ 0. That is accepted (giac does it).
  - Do not distribute number factors over sums in auto-simplify, so `2(x+1)` stays for textbook output.
    SymPy distributes, so compare in tests through `simplify(a−b)==0`, not as strings.
  - Keep the internal sort key apart from the print order (descending powers, constants last, `positive_first`
    in `F/answer.cc:418`).
  - Expression swell in `normal` with many kernels: put a cap on term count and raise a "too large" error
    (MemoryError path).
  - Floats in exact expressions: giac's `has_num_coeff` sends them to the approximate path. Do the same: once a
    float appears, evaluate numerically.

### 2.5 Expand

- **giac:** `expand` `G/klin.cc:907` replaces `*`, `^` and `neg` with distributing versions (`prod_expand`,
  `expand_pow_expand`) through `subst` at every level, then `simplifier`. `texpand` `:880` expands trig and exp of sums.
- **Sketch:** a fold over the kernel list where each node maps to a sparse polynomial dict over "atoms". Atoms are
  symbols and kernels whose arguments were expanded first. A sum merges dicts. A product convolves dicts. An integer
  power ≥ 0 uses repeated squaring. A negative power, or a non-integer one, is an atom: `expand(1/(x+1)^2)` stays a
  quotient, but its numerator is expanded. Rebuild in canonical order.
- **Subset:** polynomial expand at all levels, with denominators kept factored. Optional `texpand`
  (sin(a+b), cos(2x)) for the "expanded" view of the F4 forms.
- **Pitfalls:** `(x+y+z)^20` has 231 terms, and `(a+b)^200` explodes. Cap at about 2000 terms. The multinomial
  path beats repeated multiplication only for large powers, so skip it. Expanding inside function arguments
  (`sin(2(x+1))` → `sin(2x+2)`) is what giac does: keep it.

### 2.6 Polynomial arithmetic and GCD

- **giac:** `divrem1` `G/kgausspol.cc:866`, pseudo-division `TPseudoDivRem` (`poly.h`), content `lgcd` `:1748`,
  subresultant PRS `subresultant` `:1474`, `gcdpsr` `:3365`, heuristic GCD `gcdheu` `:2827`, modular GCD
  `gcd_modular_algo` `:2492`, dispatcher `gcd` `:3646`, extended `egcd` `:3724` / `egcdpsr` `:5678`.
- **Sketch:**
  - Univariate Z[x] (dense int lists, high degree first or last, but the same everywhere). `primitive(p)` divides
    by the content and makes the leading coefficient positive.
  - **GCD = primitive PRS:** `while b: r = prem(a,b); a, b = b, primitive(r)`. Then take the primitive part, and
    multiply by gcd(content(a), content(b)). This is iterative and about 30 lines. Fine for degree ≤ 20 with the
    small coefficients of a calculator.
  - Optional speed path **GCDHEU:** ξ = 2·min(‖p‖∞, ‖q‖∞)+2. Integer γ = gcd(p(ξ), q(ξ)). Rebuild g from the
    symmetric ξ-adic digits of γ. If g divides p and q, done. Otherwise ξ = ξ·73794/27011 (giac's constant, `G/kgausspol.cc:3354`) and
    retry up to 6 times, then fall back to PRS. This is fast in Python because big-int gcd runs in C.
  - **Extended Euclid over Q** for Bezout (partial fractions, Hermite): a loop that tracks (s, t).
  - **Multivariate gcd** (`normal` with parameters): Kronecker substitution `y_i → x^(D_i)` with D greater than
    the degree bound, then univariate gcd, then map back, then check by exact division. If the check fails, fall
    back to "gcd = 1" (no cancellation, so the result is still correct, only less simplified).
- **Subset:** univariate PRS + exact division + Bezout. Kronecker-substitution multivariate gcd. GCDHEU only if
  profiling shows a need.
- **Pitfalls:** zero and constant polynomials. Leading-coefficient sign. Pseudo-remainder coefficient growth when
  you skip `primitive` each step. Rational inputs: clear denominators first. Kronecker substitution needs a
  correct degree bound per variable.

### 2.7 Square-free factorization

- **giac:** Yun's algorithm `Tsqff_char0` `G/poly.h:2147` (a plain while loop). Wrapper `sqff`
  `G/kgausspol.cc:4926` puts the constant back.
- **Sketch (Yun):**
  ```python
  def yun(f):                      # primitive f, deg >= 1
      fp = deriv(f); a = gcd(f, fp)
      b = quo(f, a); c = quo(fp, a); d = sub(c, deriv(b)); i = 1; out = []
      while deg(b) > 0:
          a = gcd(b, d)
          if deg(a) > 0: out.append((a, i))
          b = quo(b, a); c = quo(d, a); d = sub(c, deriv(b)); i += 1
      return out
  ```
- **Subset:** all of it. It is needed by factor, partial fractions, Hermite reduction and solve multiplicities.
- **Pitfalls:** characteristic 0 only, which is fine for us. Remove the content and the x^k factor first.

### 2.8 Factoring over Q

- **giac pipeline:** `factor` `G/kgausspol.cc:5525` → `do_factor` `:5380` (content `lgcd`, sign) →
  `do_factor_hensel` `:5110` (univariate goes to `sqff_evident_primitive` `:4944`. Multivariate uses evaluation +
  Hensel, and checks homogeneity) → per square-free part `sqfffactor` `:4776`:
  1. float coefficients → numeric roots `proot`;
  2. `x^n − 1` and `x^n + 1` → products of cyclotomic polynomials (`cyclotomic` `:102`, over the divisors of n or 2n);
  3. gcd of exponents d > 1 → substitute X = x^d and factor that;
  4. `linearfind` → `do_linearfind` `G/kmodfactor.cc:840`. If |lc| and |c0| are < 24, it tries all p/q from a
     divisor table (`idivis23`) by exact division. Otherwise it finds roots mod p and lifts them;
  5. the rest goes to `factorunivsqff` → `do_factorunivsqff` `G/kmodfactor.cc:986`: try primes for few factors
     (distinct-degree factorization, `cantor_zassenhaus` `:286`/`:384`), Hensel `liftl` `:552`, recombination
     `combine` `:619`.

  Integer roots helper: `iroots` `G/krisch.cc:52`.
- **Sketch (ours, all loops):**
  1. Integer content and sign. Factor out x^k (also a monomial content per variable).
  2. Yun (2.7). Then for each square-free part P:
  3. Special shapes: binomial `a·x^n + b` (cyclotomic split for |a| = |b|, and pure powers when a, b are perfect
     n-th powers: difference of squares or cubes), gcd of exponents d → X = x^d (factor in X, then try each factor
     again in x).
  4. **Rational roots.** Candidates p/q with `p | a0`, `q | an`. Prune with `(q−p) | P(1)` and `(q+p) | P(−1)`.
     Test with exact Horner on `q^n·P(p/q)`. If divisor enumeration is too large (big a0 with many divisors, or a0
     that cannot be factored), use numeric real roots (Durand-Kerner, or bisection + Newton) and for each root r
     test `p = round(r·q)` for each `q | an` (rational reconstruction). This stays cheap.
  5. **Kronecker quadratic (and cubic) factors** for the degree-≥4 cofactor:
     - choose d+1 small integers x_i with P(x_i) ≠ 0 and the fewest divisors;
     - for each combination of signed divisors (v_0..v_d), interpolate g of degree ≤ d (Newton divided differences
       over Q);
     - keep g only if its coefficients are integers and lc(g) divides lc(P); test `P mod g == 0`;
     - iterate the combinations with an odometer counter (no recursion), with a step budget.

     This is complete for deg P ≤ 5. Cost grows like (2·τ)^(d+1).
  6. **Multivariate (textbook level):** content in each variable (gcd of coefficients), monomial content,
     homogeneous dehomogenization (set y = 1, factor univariate, rehomogenize; giac checks homogeneity in
     `do_factor_hensel`), then the special binomial shapes (x²−y², x³+y³). Everything else is returned unfactored,
     which is still correct.
- **Subset (T1):** steps 1-5 (d = 2, and d = 3 only when deg ≥ 6 and inside the budget) + step 6.
  **Stretch:** Zassenhaus (Berlekamp or Cantor-Zassenhaus mod p, linear Hensel, subset recombination). That is
  about 250 lines and about 8 KB.
- **Pitfalls:** "Irreducible" can only be claimed when the search was complete. Otherwise just return the
  factorization found, without a claim. Factoring over Q(√): `x²−2` stays as it is under `factor` (giac
  `with_sqrt=false`), while `solve` gives ±√2. Watch the time: Kronecker on `x^4+…` with highly composite values
  needs a budget. Sort factors by degree, then lexicographically, for stable output (giac had sorting turned off,
  `:5527`).

### 2.9 Partial fractions (also the "one fraction" F4 form, in reverse)

- **giac:** `partfrac` `G/kgausspol.cc:5550`. Fast path when all factors are linear or quadratic and of
  multiplicity 1: N mod P / Q mod P with closed forms. General `Tpartfrac` `G/poly.h:2234`. `_partfrac`
  `G/ksym2poly.cc:3795`.
- **Sketch (simplest robust form):** polynomial part by division. Factor the denominator (2.8) into
  ∏ f_j^(m_j). Unknown numerators A_jk with deg < deg f_j for k = 1..m_j. Set N = Σ A_jk·(Den/f_j^k) and match
  coefficients. That gives a square linear system of size deg(Den), solved by Gauss-Jordan over Q. The linear
  solver is reused from `solve`. Iterative, about 40 lines on top of the solver.
  - Alternative with less memory: Bezout per coprime factor, then repeated division by f_j for the f_j-adic
    expansion.
- **Subset:** the linear-system method for deg(Den) ≤ about 12.
- **Pitfalls:** an irreducible cubic or higher factor stays as one term. Denominators with parameters
  (`1/(x²−a²)`) need the generic path: factor over Q(a) with Kronecker substitution, or skip them.

### 2.10 Solve

- **giac:** `solve` `G/ksolve.cc:2124` (relations become an expression = 0, inequalities go to
  `solve_inequation` `:1165`) → `clean` `:1287` → `solve_cleaned` `:1719`:
  - linear test first;
  - product → solve each factor; positive power → its base;
  - `abs` → two cases with sign checks;
  - `rationalize` `:1564`;
  - fractional powers → auxiliary variables (`solve_fracpow` `:1478`);
  - the `α·x^n + β` fast path;
  - `factor`;
  - then `in_solve` `:610` per factor:
    - a single kernel f(x) ≠ x: solve for t = f(x), then invert with `isolate_fcns` `:217` (sin → {asin(t),
      π−asin(t)} + 2kπ, cos → ±acos(t), exp → ln(t) with t > 0 in real mode, ln → e^t, …);
    - composite polynomials through `translate_gcddeg` `:526` (biquadratic);
    - degree 1 and 2 formulas (`:906-945`, half-b form when b/2 is integral);
    - degree > 2 that cannot be factored → numeric roots.

  Then `solve_numeric_check` `:1693` and `solve_ckrange` `:401` (real filter). Rational equations exclude zeros of
  the denominator through `find_singularities` `:319`. `linsolve` `:3474` handles systems. FlowCE solves a bare
  equation for its single unknown (`equation_unknown` `F/answer.cc:1737`).
- **Sketch (worklist):** the items are (expression = 0, variable, pending inverse). Loop:
  1. `normal` → numerator N, denominator D. Solve N = 0 and drop roots where D = 0.
  2. `free_of` → no solution, or "all x".
  3. If N is a product, push each factor.
  4. If N is a polynomial in x: Yun, then rational roots, then degree ≤ 2 by formula (exact radicals), then a
     composite polynomial `P(x^k)` through t = x^k. The rest goes to numeric real roots, labelled ≈.
  5. If exactly one kernel u(x) appears (with N polynomial in u): substitute t, solve for t (push), then for each
     t₀ push `arg(u) = inverse_u(t₀)` from an inverse table (data). Periodic families get an integer parameter n.
  6. If one radical √A appears linearly (`P + Q√A = 0`): square to `P² − Q²A = 0`, solve, and **check every root**
     in the original.
  7. Special trig: `a·sin u + b·cos u = c` → `R·sin(u + φ)`. Mixed sin/cos/tan of the same u → rewrite in tan(u/2)
     only as a last resort.
  8. Otherwise: numeric (bisection or Newton on a sampled interval), labelled ≈.

  For linear systems use Gauss-Jordan with fractions (`linsolve`).
- **Subset:** linear (and linear systems), quadratic exact, rational-root polynomials, biquadratic, single-kernel
  transcendental (exp, ln, log, sin, cos, tan, powers with x in the exponent such as 2^x = 8), one-radical
  equations, the `a·sin+b·cos` form. Numeric fallback.
- **Pitfalls:**
  - Extraneous roots from squaring and from clearing denominators: always check by substitution (exact
    `normal` = 0, or numeric with tolerance when exact is too costly).
  - The domain of ln and √ in real mode.
  - Display choice for trig: general solution with an integer n (giac `isolate_mode & 2`) or principal values in
    [0, 2π). This is a user-facing decision for the design doc.
  - tan has period π. sin = ±1 gives two equal families (asin = π−asin) that must be merged. sin = 0 is one family nπ (giac special-cases `is_zero(e)`, `G/ksolve.cc:157`). |t| > 1 for asin/acos has
    no real solution (`:743`).
  - `2^x = 8` must simplify `ln 8/ln 2` to 3: use an exact integer log when the base is a perfect power.
  - Cubic or quartic closed forms (Cardano, Ferrari) are **not** worth it (casus irreducibilis output). Use
    numeric with ≈.
  - Duplicate roots: merge by node id after `normal`.

---

## 3. T2

### 3.1 Derivatives

- **giac:** `derive_SYMB` `G/kderive.cc:68`:
  - `+` (`:83`); n-ary `*` as Σᵢ (∏ⱼ≠ᵢ fⱼ)·fᵢ′ (`:108`), with a quotient fast path for `u·inv(v)`;
  - `^` (`:148`): constant exponent `e·b′·b^(e−1)`, otherwise `(e′ ln b + e·b′/b)·b^e`;
  - `inv` (`:161`);
  - `ln` of abs, inv and product split (`:223`);
  - one-argument functions through the per-function derivative operator `D` (`:309`) defined in `G/kusual.cc`
    (`d_ln` `:505`, `d_log10` `:574`, `d_atan` `:850`, `exp` `:1045`, `d_sqrt` `:1477`, `d_cos` `:1776`,
    `d_sin` `:2040`, `d_tan` `:2264`, `d_asin` `:2491`, `d_acos` `:2611`, `sinh` `:2717`, `cosh` `:2791`,
    `d_abs` `:3210`, `sign` → 0);
  - integral with variable bounds (FTC, `:332`);
  - `derive(e, vars, n)` `:542` loops n times; `_grad` `:679`.

  FlowCE: `ftc` `F/answer.cc:1678` does d/dx ∫_a(x)^b(x) f(t) dt = f(b)b′ − f(a)a′ without integrating.
- **Sketch:** a fold over the post-order list with memo `D[nid]` (pattern 2). For each node, by op:
  - NUM, other SYM → 0; the variable → 1;
  - ADD → `add(D[c])`;
  - MUL → `add(mul(c₁..D[cᵢ]..cₙ))`;
  - POW → the two cases above;
  - FUNC → `mul(D[arg], TEMPLATE[op](arg))`. The templates are data: sin→cos(u), cos→−sin(u), tan→1+tan²(u) or
    sec²(u), ln→1/u, log→1/(u ln 10), exp→e^u, asin→1/√(1−u²), acos→−1/√(1−u²), atan→1/(1+u²), sinh→cosh u,
    abs→u/|u| (giac: `d_abs` gives `sign`-like), sec→sec u·tan u, csc, cot.

  Then `simplify`. Higher order: loop and simplify between steps. FlowCE `collect_rational` (`F/answer.cc:758`)
  merges rational terms that piled up. Partial derivatives: the same with another variable. Implicit d/dx of y:
  not in scope.
- **Subset:** all elementary functions, n-th order, partials, gradient (4.5), FTC for integral nodes.
- **Pitfalls:**
  - Degree mode: d/dx sin(x) = (π/180) cos(x). giac does it through the `D` operators with `deg2rad`.
  - `log` is base 10 here (FlowCE convention). `d/dx x^x` needs the general-exponent branch.
  - Swell: simplify once at the end, plus light auto-simplify on each build, not a full `simplify` per node.
  - |x| at 0 is undefined. Do not invent sign(0) = 0 semantics in printed answers.

### 3.2 Taylor series (and the series engine shared with limits)

- **giac:**
  - `taylor_` `G/kseries.cc:45` uses repeated differentiation plus substitution. That is the generic fallback for
    any function at a regular point.
  - The real engine is `series__SPOL1` `G/kseries.cc:1408`:
    - rewrite trig constants;
    - take `rlvarx` (kernels sorted by size) and expand each kernel **bottom-up**, memoized in `lvx_s`;
    - rational operations go through `in_series__SPOL1` `:1190` with truncated arithmetic `padd` `:260`,
      `pmul` `:406`, `pdiv` `:610`, `ppow` `:1038` (binomial series composed through `pcompose` `:864`), `pshift`;
    - `ln` is special-cased (`:1486-1531`): pull out the leading term c·x^k, then
      `ln c + k ln x + log-series(rest)`;
    - a generic f(u): expand u, find its value at the limit point (`find_image` `:1288`), then compose with f's
      Taylor table at that point (`series_expansion` per function: `taylor_exp` `G/kusual.cc:1046`, `taylor_atan`
      `:861`, `taylor_asin` `:2501`, otherwise `taylor_` by differentiation).

    The limit code raises the order ×1.5+1 until the leading coefficient is defined (`G/kseries.cc:2625` and
    `:2985`).
- **Sketch:** a power series is `(val, [c0..cN], N)`, meaning `x^val·Σ cᵢ xⁱ + O(x^(val+N+1))`. To expand at a,
  substitute x = a + h. Fold over the kernel list (pattern 2):
  - SYM x → `(0,[a,1])` (or `(1,[1])` when a = 0); constants → `(0,[c])`;
  - ADD → align the valuations and add; MUL → truncated convolution;
  - INV → inversion by recurrence (`b0 = 1/a0`, `bₙ = −(Σ_{k=1..n} aₖ b_{n−k})/a0`), with the valuation negated
    (Laurent);
  - POW with a constant exponent r → pull out the leading term, then a binomial recurrence (J.C.P. Miller:
    `bₙ = (1/(n·a0)) Σ_{k=1..n} (r·k − n + k) aₖ b_{n−k}`), so no composition is needed;
  - exp(u): split u = u0 + ũ, then the recurrence `bₙ = (1/n) Σ k·ũₖ·b_{n−k}` times the constant e^(u0);
  - ln(u): `ln(u0) + ln(1+ũ/u0)`, with the derivative recurrence;
  - sin and cos together through the coupled recurrence;
  - tan = sin/cos; atan, asin through the series of their derivative, then term-by-term integration.

  All of these are O(N²) loops with no recursion and no differentiation. Exact constants such as ln 2, √2 or
  sin(1) appear as nodes.
- **Subset:** order ≤ about 12 by default, at a point a (exact) or at ∞ (h = 1/x), Laurent valuations, the
  functions above. Output: polynomial + `O((x−a)^(n+1))` as FlowCE prints it (FlowCE output rewrites,
  `F/answer.cc:1803` comment).
- **Pitfalls:**
  - Cancellation: `(sin x − x)/x³` needs internal order ≥ 3 more than the requested order. Loop with order + 2,
    + 4, … until the leading coefficient is non-zero or a cap is hit (giac does the same).
  - Non-analytic points: `√x` at 0 is a Puiseux series, so return "not analytic" or support a half-integer step.
  - `ln x` at 0 has no series. Keep a log term as giac does (`exponent*ln(x)` monome), or refuse.
  - Coefficients with parameters need `normal` on each coefficient to detect zeros, which costs time.
  - Factorial denominators grow fast, but they are fine as rationals.

### 3.3 Limits

- **giac:** `limit` `G/kseries.cc:3063` → `in_limit` `:2467`:
  1. Direct substitution + simplify (`:2499`). If the result is finite and defined, done.
  2. Substitute into `partfrac(e)` (finds removable singularities).
  3. `limit_symbolic_preprocess` `:2283`: sinh/cosh/tanh with an infinite argument → exp; sums → Euler-Maclaurin;
     `sign` resolved through the first non-zero derivative.
  4. exp and ln of the limit; `pow2exp` + `tan2sincos`.
  5. Two-sided and analytic: series at the point with growing order (`:2625`). Leading term with exponent > 0 → 0,
     = 0 → coefficient, < 0 → ±∞ (only for even exponents; otherwise `unsigned_inf`).
  6. Otherwise `unidirectional_limit` `:2403`: map x → a + 1/x or a − 1/x or −x so the limit is at +∞, then
     `mrv_lead_term` `:2867` (Gruntz: `mrv` `:2749` finds the most rapidly varying subexpressions, rewrites them in
     terms of w → 0, expands in w, rescales ln x ↔ x).

  Bounded oscillation (`sin` at ∞) gives `bounded_function` (`check_bounded` `:2209`). If the two sides differ:
  error "Unidirectional limits are distinct". **No L'Hôpital anywhere.** FlowCE turns ∞-unsigned and "distinct"
  results into "does not exist: L from the left, R from the right" (`limit_dne` `F/answer.cc:1229`).
- **Sketch (ours: one task per strategy, first success wins, all inside a budget):**
  1. **Substitute** exactly (with one-sided handling of `abs`, `sign`, `floor` by the side). Finite → done.
  2. **Rational in x** (after `normal`): cancel, then substitute. At ±∞ compare degrees and leading coefficients.
  3. **Series** (3.2) of f at a (h → 0±) or at ∞ (h = 1/x → 0+). Leading term `c·h^v`: v > 0 → 0; v = 0 → c;
     v < 0 → ±∞ with the sign of `c·side^v`. A two-sided limit with odd v → DNE (−∞ on one side, +∞ on the other).
     This covers `sin x/x`, `(1−cos x)/x²`, `(e^x−1−x)/x²` and `√(x²+x)−x` at ∞.
  4. **Indeterminate-form rewrite + bounded L'Hôpital:** `0·∞` → quotient, `∞−∞` → one fraction (`normal`),
     `1^∞, 0^0, ∞^0` → `exp(lim g·ln f)`. Then up to 5 rounds of `f′/g′` with `simplify`. The limits of numerator and
     denominator at each round use only steps 1-3 (no nested L'Hôpital), so the task depth stays at 1.
  5. **Growth classes at ±∞** for products and quotients of `e^(p(x))`, `x^r`, `(ln x)^s`: compare the triples
     (exp degree, power, log power). This is a cheap stand-in for MRV.
  6. **Bounded × vanishing:** if f = g·b with |b| ≤ const (sin, cos of an argument → ∞) and g → 0, the limit is 0.
     If f is only bounded and oscillating → "does not exist (oscillates)".
  7. **Numeric:** f(a ± 10^(−k)) for k = 2..8 (fewer with single floats), or f(10^k) at ∞. Require the differences
     to shrink, use Richardson, and label the result ≈. Different one-sided values → "does not exist: L from the
     left, R from the right".
- **Subset:** all 7 steps, but step 4 only with the simplified forms, and step 5 only for single products and
  quotients.
- **Pitfalls:**
  - At −∞, `√(x²) = |x| = −x`: substitute x = −t, t → +∞, and keep `abs` aware of the sign.
  - Hidden 0/0 after a premature float evaluation: stay exact until step 7.
  - giac's first try compares exact and numeric values to catch a bad `normal` (`:2524`).
  - `x^x` at 0+ needs `exp(x ln x)`.
  - Limits of piecewise functions or `floor` at integers need one-sided substitution.

### 3.4 Indefinite integration

- **giac pipeline:** `_integrate` `G/kintg.cc:3125` → `integrate0` `:2980` → `linear_integrate` `:2898`
  (normalizes √, then `linear_apply` `:255` = linearity) → `integrate_id_rem` `:2319`:

  | step | giac | what |
  |---|---|---|
  | −3..0 | `:2330-2395`, `integrate_step0` `:2137` | piecewise/when; abs/sign → piecewise-constant sign symbols (assumes constant sign on intervals) |
  | 1 | `:2397` | `f(a·x+b)` for f in the table (sin cos tan exp sinh cosh tanh asin acos atan ln asinh acosh atanh) → `primitive_tab_primitive` `:1909` divided by a; `(ax+b)^n` (n = −1 → `ln|ax+b|`); surd/nth-root |
  | 2 | `:2453` | **u-substitution:** for each kernel u in rlvarx (not x itself), fu = normal(e/u′), then `is_rewritable_as_f_of(fu, u)` (`:2035`/`:1921`: replace u by X and check that x disappears; includes sin²↔cos², tan² rewrites and integer-power bases). Then also the inner argument of the kernel. Then (`:2617`) each factor v of a product or power: U = ∫v, check that e/U′ can be written in U. Bounded by `TRY_FU_UPRIME`. |
  | 3 | `:2700` | only x left → `integrate_rational` `:1548` |
  | sqrt | `:2712` | one power kernel → `integrate_sqrt` `:950` |
  | inv-trig/ln | `:2728` | `detect_inv_trigln` `:2202`: poly·ln(ax+b), asin, acos → change of variable t = ln(ax+b) etc. |
  | by parts | `:2732` | a product with an inverse-function factor (ln, asin, acos, atan, inverse_tab_op): integrate the rest R; if ∫R has no inverse functions, `R·g − ∫R·g′`. A lone inverse function: `x·g − ∫x·g′` (`:2787`) |
  | linearizable | `:2809` → `integrate_linearizable` `:709` | `lin` (exp linearization `G/klin.cc:134`) and `tlin` (trig products/powers → sums of multiple angles `:397`). Each term `poly·e^(ax+b)·{1, sin, cos}(cx+d)` is solved by `solve_aPprime_plus_P` `:678` with complex a ± ic. `e^(quadratic)` → erf. |
  | trig fraction | `:2835` → `integrate_trig_fraction` `:1269` | rational in sin/cos/tan of one linear argument → `halftan` (`G/ksubst.cc:1000`, t = tan(x/2)) → rational; rational in e^x → t = e^x |
  | Risch | `:2894` | stub (`G/krisch.cc:46`) |

  - `integrate_rational` `:1548`: x^a substitution when the exponent gaps share a gcd; symmetric patterns for
    trig fractions (from `:1660`); content → `sqff` → `partfrac` → `intreduce_pf` (`G/kgausspol.cc:5771` →
    `Tintreduce_pf` `G/poly.h:2326`, Hermite reduction loop for multiplicity > 1) → factor each remaining square-free
    denominator → `integrate_rational_end` `:1434`:
    - degree 1 → `num/lc · ln|fact|`;
    - degree 2 → ln part plus atan (Δ < 0) or `ln|(2ax+b−√Δ)/(2ax+b+√Δ)|/√Δ` (Δ > 0);
    - higher → `integrate_deno_length_2` `:458` for `x^n + c` denominators, otherwise the remainder.
  - `integrate_sqrt` `:950`:
    - `R(x, (ax+b)^(p/d))` → t^d = ax+b;
    - `R(x, ((ax+b)/(cx+d))^(1/d))`;
    - √(quadratic): split into α + β√y, Bezout against the denominator, then Ostrogradsky-type reduction
      `∫P/y^l·y^(−1/2) = Q·y^(1/2−l) + ∫C·y^(−1/2)`, solved as a **linear system** (`:1098-1186`). The leftover is
      done by an Euler substitution: a > 0: m = √y − √a·x → rational; a < 0: u = (D−2√(−a)√y)/(2ax+b) → asin.
  - FlowCE textbook layer (because giac was slow or ugly on the CE):
    - `table0` `F/answer.cc:924`: sec, csc, sec², csc², sec³, csc³, tan², cot² of a linear u, from templates.
    - `trig_powers` `:1053` with `trig_factor` `:1018`: sinᵐcosⁿ, tanᵐsecᵏ, cotᵐcscᵏ by the textbook substitution
      (u = tan for an even power of sec, u = sin for an odd power of cos, u = cos for an odd power of sin). The
      result is a polynomial in u expanded term by term (`sin⁹/27 − 2sin¹¹/33 + …`).
    - `usub` `:1641`: f = c·b′·b^e for some power or inverse b^e, with a numeric pre-check at x = 0.3271 and 0.7193
      before the exact `ratnormal`. Result: `c·b^(e+1)/(e+1)` or `c·ln|b|`, kept in the textbook form.
    - `numeric_hard_integrals` `:1707` and `hard_radicand` `:884`: a fractional power of a non-quadratic radicand
      (after removing even-power factors, `odd_factors` `:861`) is non-elementary, so go numeric at once. giac
      otherwise searched until memory ran out (ellipse perimeter took 80 s).
- **Recommended design (task machine, strategies in order, each a data-plus-code module):**
  - **S0 linearity:** a sum gives one task per term (AND: join the F's and R's). Pull out constant factors.
  - **S1 table on f(ax+b):** `TABLE[op]` → (template in u, divide by a). The entries:
    - xⁿ, 1/x, e^u, b^u, ln u, log u;
    - sin, cos, tan, cot, sec, csc, sec², csc², sec·tan, csc·cot;
    - asin, acos, atan; sinh, cosh;
    - the rational forms 1/(u²+k²), 1/(u²−k²), 1/√(k²−u²), 1/√(u²±k²), √(k²−u²), √(u²±k²) (k constant; complete the
      square first).

    The FlowCE `table0` entries come in here.
  - **S2 u-substitution:** candidate u = kernels of f (innermost first), the arguments of those kernels, the bases
    of powers, and denominators. Compute q = f/u′ (or f/(b^e·b′)). Do a numeric two-point check that q is a
    function of u, then exact: replace u by a fresh t, `normal`, and check `free_of(x)`. If it passes, push ∫g(t)dt
    plus a "back-substitute" continuation. Include giac's even-power trig rewrites (sin² = 1−cos² …). Depth guard ≤ 3.
  - **S3 poly × {e^(ax+b), sin, cos} and e^(ax)·sin/cos(bx):** the tabular (DI) method, iterative and without
    search: `∫Q·g = Σₖ (−1)^k Q^(k) G_(k+1)`, which ends at deg Q. G_k are the repeated antiderivatives: for e^(ax)
    divide by a; for sin/cos rotate with 1/b; for e^(ax)·(A·cos bx + B·sin bx) map the coefficient pair
    `(A, B) → (aA − bB, bA + aB)/(a²+b²)`. This is giac's `aP′+P=Q` in real form.
  - **S4 rational functions:**
    - polynomial division;
    - Yun on the denominator;
    - Hermite reduction loop (`Tintreduce_pf`) for the rational part, **or** full partial fractions (2.9);
    - then ln for linear factors;
    - ln + atan for irreducible quadratics with the reduction formula
      `I_k = t/(2a²(k−1)(t²+a²)^(k−1)) + (2k−3)/(2a²(k−1))·I_(k−1)`, `I_1 = atan(t/a)/a` (a loop from k down to 1);
    - quadratics with real irrational roots → giac's ln-ratio form;
    - irreducible cubic or higher factors → leave in R.
  - **S5 trig powers:** FlowCE `trig_powers` substitutions. Even·even → linearize: write sinᵐcosⁿ as a sum of
    cos(kx)/sin(kx) through the binomial expansion of `(e^(ix)−e^(−ix))^m (e^(ix)+e^(−ix))^n`, done with integer
    coefficient arrays, no complex numbers needed. Then S1 per term. Output like `3x/8 − sin(2x)/4 + sin(4x)/32`.
  - **S6 by parts (LIATE):** u ∈ {ln, log, asin, acos, atan, asinh} × dv = polynomial (or 1). v = ∫dv must succeed
    with no inverse functions. Push ∫v·u′. Repeated parts for `xⁿ·ln(x)^m` loop over m. Guard the depth.
  - **S7 radicals:**
    - `(ax+b)^(p/q)` → t-substitution (giac's first branch);
    - `P(x)/√(ax²+bx+c)` → the Ostrogradsky linear system `P = R′·y + R·y′/2 + λ`, then `λ∫1/√y` from the S1 table
      (a compact, general replacement for trig substitution, about 40 lines);
    - `√y·P` = `P·y/√y`.
  - **S8 last resort:** Weierstrass `t = tan(x/2)` for rational sin/cos, and t = e^x for rational exp. The output is
    ugly, so S5 runs first.
  - **S9 failure:** push f into R. The definite path goes numeric.
  - At the end: simplify with "keep the smallest", `ln|u|` in real mode, merge logs, add `+C` once at the top.
    Check (1.5).
- **Subset for T2:** S0-S7. S8 optional. Skip erf, Risch and Gaussian-integral forms.
- **Pitfalls:**
  - `ln|u|` vs `ln u`: giac `do_lnabs`, switched off under complex substitutions (`:2534`).
  - Two antiderivatives can differ by a constant (`sin²/2` vs `−cos²/2`). Tests compare derivatives, never strings.
  - u-substitution loops (u = x², then back): use a depth guard and a global task budget (giac uses
    `TRY_FU_UPRIME`).
  - Coefficient swell in partial fractions with large denominators.
  - Degree mode (giac `int_sin` and friends multiply by 180/π).
  - Do not `texpand` arguments that are not linear in x: the TICE note in giac (`:2459`) says it took more
    than 90 s.
  - abs in integrands: use only `|ax+b|` with the sign split at −b/a (giac `integrate_step0`). Anything else goes
    to R.
  - Check output from parameters: `∫x^n dx` with symbolic n needs n ≠ −1. Show the general case, as giac does.

### 3.5 Definite integrals

- **giac:** `_integrate` with 4 arguments (`G/kintg.cc:3245-3640`):
  - with numeric bounds, swap them if a > b; split at singular points of the powers in (a, b) (`:3235-3255`);
  - floor and piecewise splitting (`:3343-3470`);
  - period shift (`:3480`);
  - antiderivative → `limit(F, b, −1) − limit(F, a, +1)` (`:3528`);
  - singular points of F inside the interval from `find_singularities` (`G/ksolve.cc:319`: zeros of denominators,
    of ln and power arguments, and of cos for tan) → add the jump `F(s⁻) − F(s⁺)` (`:3594-3625`);
  - unresolved remainder → stays unevaluated;
  - finally `ck_int_numerically` (`:3014`).

  FlowCE: `table_definite` `F/answer.cc:1123` (F(b)−F(a) checked with 12-point Gauss-Legendre), `real_ftc`
  `:1207` (real odd roots in the bounds).
- **Sketch:**
  1. Find the singularities of f in [a, b] (solve the denominators, ln arguments, cos for tan/sec; numeric
     isolation if exact solving fails). If there is one inside or at an end, this is improper (4.1).
  2. F from 3.4. If R ≠ 0, go to step 5.
  3. Find the discontinuities of F in (a, b) (same rules on F). Total = F(b⁻) − F(a⁺) + Σ jumps, with one-sided
     limits (3.3) only where plain substitution fails.
  4. Simplify, then cross-check with quadrature. On mismatch, give the numeric value (≈) and do not show the exact
     one.
  5. No F: numeric quadrature (3.6), labelled ≈.
  6. Shortcut: an odd integrand on a symmetric interval gives 0. Check this numerically at 3 points before trusting it.
- **Subset:** all of it, plus symbolic bounds (no cross-check possible there) for multiple integrals (4.6).
- **Pitfalls:** Weierstrass antiderivatives jump at x = π (`∫₀^{2π} dx/(2+cos x)`): steps 3 and 4 must catch this.
  `atan` forms after Weierstrass. `|x|` integrands across 0. Bounds in degree mode. Symbolic bounds give no
  numeric check.

### 3.6 Numeric quadrature

- **giac:** `tegral` `G/kintg.cc:3785`: adaptive. Keep a list of intervals with error estimates and split the
  worst one in half. `tegral_util` `:3689` uses a 15-node Gauss rule (order 30) with embedded order-14 and order-6
  rules for the error estimate, `err1·(err1/err2)²`. Stop at `ERR/∫|f| < eps`, or after `nmax` intervals.
  `intnum` `:3888`: infinite bounds through x = tan t. `approxint_exact` `:3744`: for very simple f, use the exact
  antiderivative. FlowCE: `x = a + (b−a)·sin²(πt/2)` removes endpoint singularities
  (`numeric_hard_integrals` `F/answer.cc:1707`).
- **Sketch:**
  - **Compile once:** turn the node DAG into a Python expression string (`math.sin`, `**`, …), then
    `f = eval("lambda x:" + src)`. Each point runs at native speed. A shared subexpression can be bound with a
    default argument or recomputed.
  - **Method:** Gauss-Kronrod G7-K15 with a list-based worst-first split (≤ 200 intervals), **or** tanh-sinh (double
    exponential): one loop over levels h = 1, ½, ¼ …, no recursion, and robust to endpoint singularities and
    infinite intervals (x = t/(1−t²) or `exp(π/2·sinh t)` maps). Recommendation: tanh-sinh as the main method
    (simple, about 30 lines, handles √-type endpoint singularities and the improper cases of T3). Use G7-K15 when
    the integrand is smooth and periodic, or tanh-sinh as the only method if code size is tight.
  - Poll cancel every k evaluations. Report the error estimate to decide on ≈ precision.
- **Pitfalls:** single-precision floats limit the result to about 6 digits, so show fewer digits. Do not use
  10-digit display on 7-digit data. Interior singularities must be split first (3.5 step 1). Oscillatory integrals
  on infinite ranges (sin x/x) converge badly, so say "≈ (low accuracy)" or decline. An overflow at an endpoint
  node: catch it and nudge inward.

---

## 4. T3

### 4.1 Improper integrals (report divergence)

- **giac:** the same `_integrate` path. Infinite bounds and singular endpoints go through the one-sided
  `limit(primitive, …)` (`G/kintg.cc:3528`). An infinite result is shown as ±∞. No separate convergence test.
  FlowCE uses the integral test inside `known_sum` (`F/answer.cc:1567`).
- **Sketch:**
  1. List the improper points: ±∞ bounds, plus the singularities of f in [a, b] (3.5 step 1).
  2. Split into pieces, each improper at one end only.
  3. For each piece, F from 3.4, then a one-sided limit at the improper end (3.3).
  4. Any piece ±∞ or DNE → "diverges" (say which piece; ∞ − ∞ across pieces is still divergent: **no Cauchy
     principal value**).
  5. No F: numeric (tanh-sinh), with a divergence heuristic. Compare I(R), I(2R), I(4R) (or ε, ε/2, ε/4). If the
     values grow, or keep alternating, then say "appears to diverge" (≈). Use p-integral comparison when f ~ c/x^p
     (from the series at the end, 3.2).
- **Pitfalls:** `∫_{−1}^{1} 1/x² dx` has the singularity inside the interval (classic wrong answer −2).
  `∫₀^∞ sin x dx` → DNE, so "diverges". `∫₁^∞ sin(x)/x dx` converges, but numeric quadrature struggles: only ≈.

### 4.2 Symbolic and infinite sums

- **giac:**
  - `_sum` `G/kintg.cc:4658`: drops zero terms at the ends; integer bounds with < `max_sum_add` terms are summed
    directly (`seqprod`, `sum_loop` `:4466`, < 100 terms in `sum(e,x,a,b)` `:4480`).
  - `sumab` (`G/kintgab.cc:1872`, residues and partial fractions, heavy), then the discrete antiderivative
    `sum(e,x,rem)` `:4442`:
    - trig with a linear argument → complex exponentials;
    - `linear_apply` + `inner_sum` `:4419`, which uses `rational_sum` `:4033` or Gosper.
  - `rational_sum` `:4033`:
    - polynomial → `solveP_x_plus_1_minus_P_x` `:3988` (find P with P(x+1)−P(x) = Q through a linear system,
      i.e. Faulhaber);
    - rational → factor + partfrac, match shift-equivalent denominators (`is_shift_of` `:4018`), which gives
      telescoping, the rest goes to Psi.
  - Gosper: `is_hypergeometric` `:4374`, `AB2PQR` `:4247`, `gosper` `:4305`.
  - Result = `F(b+1) − F(a)`, or limits at infinite bounds.
  - FlowCE infinite sums (`known_sum` `F/answer.cc:1460`, `power_sum` `:1592`):
    - numeric n-th term test at n = 10³, 10⁴, 10⁵;
    - numeric ratio test at a+5 and a+10 ("geo" if r < 0.95);
    - ζ(2k) table `π^(2k)·{1/6, 1/90, 1/945, 1/9450}`;
    - alternating `1/n` → −ln 2; `1/(2n+1)` alternating → π/4;
    - harmonic-like (deg gap ≤ 1) → ∞;
    - `power_series` `:1327` (from `split_geo` `:1284`): `c·rⁿ/n → −c·ln(1−r)`, `c·n·rⁿ → c·r/(1−r)²`,
      `c·rⁿ → c·r^a/(1−r)`, `c·rⁿ/n! → c·e^r`, minus the terms before a;
    - `series_identify` `:1379`: numeric fit of a Maclaurin series to c·F(x)+d for F in {sin, cos, sinh, cosh, exp,
      atan, ln(1+x)};
    - p-series with non-integer p → ±∞ or 200 terms + an integral tail;
    - integral test;
    - `sum200` `:1438`: 200 terms added smallest-first, with tail averaging for alternating series.
- **Sketch (ours):**
  - **Finite, numeric bounds, ≤ 1000 terms:** add directly (exact rationals), with the cancel poll.
  - **Symbolic bound n:**
    - polynomial Q(k) → find P (deg + 1) with `P(k) − P(k−1) = Q(k)`, `P(a−1) = 0`, solved as a triangular linear
      system (Faulhaber);
    - `c·r^k` → geometric closed form;
    - `Q(k)·r^k` → find P with `r·P(k+1) − P(k) = Q(k)` (a linear system again; this is Gosper's special case);
    - rational R(k) → partial fractions, pair the terms whose denominators are shifts (`(k+s)` vs `(k)`) and
      telescope by subtracting the boundary terms (giac `rational_sum` shift loop).
  - **Infinite:**
    1. n-th term test (limit 3.3; numeric first as FlowCE does) → "diverges";
    2. geometric `|r| < 1` (else diverges);
    3. telescoping → limit of the partial sum;
    4. table: ζ(2), ζ(4), ζ(6), ζ(8), alternating harmonic, Leibniz, `rⁿ/n!`, `rⁿ/n`, `n·rⁿ` (power_series forms);
    5. p-series test (p ≤ 1 diverges);
    6. integral test and comparison for rational terms;
    7. otherwise a numeric value (≈): 200 terms plus the tail integral, or the averaged partial sums for
       alternating series.
- **Subset:** all of the above except Gosper (optional) and Psi results.
- **Pitfalls:**
  - The index `i` collides with the imaginary unit: FlowCE renames it to k/j/m (`sum_index_i` `F/answer.cc:1831`).
    Pick our own policy: e.g. inside `sum(…,i,…)`, treat i as a bound variable.
  - Off-by-one at the lower bound.
  - `(−1)^n` written as `cos(nπ)` (FlowCE rewrites it).
  - Exact huge terms (`(1−1/n)^(n²)` at n = 42 has 2900 digits): use floats for the tests (FlowCE `term` `:1427`).
  - Conditionally convergent series: give only a numeric value.

### 4.3 Riemann sums

- **giac:** `_plotarea` `G/kmisc.cc:7045`: left, right, midpoint and trapezoid loops over n panels (numeric).
  FlowCE users type `sum((i/n)^2/n, i, 1, n)` (see 4.2 index note).
- **Sketch:** `riemann(f, x, a, b, n, method)` with method ∈ {left, right, mid, trap}, Δ = (b−a)/n.
  - **numeric n:** a loop. Exact rationals when f is rational at rational points; otherwise the compiled float
    lambda (3.6).
  - **symbolic n:** build `Σ_{i=1..n} f(a + iΔ)·Δ` (shifted for left/mid). If f is polynomial (or the sum is
    polynomial in i), expand in i and apply Faulhaber (4.2). That gives a rational function of n. Offer
    `limit(n→∞)` (degree comparison), which must equal ∫ₐᵇ f; a good self-check.
- **Pitfalls:** for left vs right, check the index ranges carefully. Trapezoid with symbolic n is (left+right)/2.
  Non-polynomial f with symbolic n gives no closed form, so offer only the numeric table.

### 4.4 ODEs

- **giac:** `desolve_f` `G/kdesolve.cc:1004`:
  - order (`diffeq_order` `:394`);
  - linearity test by substituting y⁽ᵏ⁾ → dummy and calling `is_linear_wrt` (`is_linear_diffeq` `:426`);
  - linear → `desolve_linn` `:742`:
    - order 1: `desolve_lin1` `:692`, integrating factor `e^(∫b/a)`, cleanup of abs and constant factors with
      `desolve_cleanup` `:671`;
    - constant coefficients, n ≤ 3: roots of the characteristic polynomial (`solve`); conjugate pairs →
      `e^(αx)(C₁cos βx + C₂sin βx)`; a double root (n = 2) → `e^(rx)(C₁x + C₂)` with the particular solution from
      two integrals; distinct roots → variation of constants through a Vandermonde system (`:804`);
    - otherwise Laplace (`:830`);
    - variable-coefficient order 2 (Euler-type `k` invariant and polynomial-solution search, `:848-1000`);
  - non-linear order 1 (`:1127`):
    - solve for y′;
    - Lagrange/Clairaut;
    - **separable** through `factors` + `separate_variables` `:632` (each factor goes to the x side or the y side;
      fail if a factor contains both). Then `∫dy/g(y) = ∫f(x)dx + C`, with `lncollect` turning `ln y + C` into
      `ln(C·y)` (`:1204`), and solve for y (an implicit equation if that fails);
    - x-incomplete; linear substitution; homogeneous (y = t·x); exact equations.
  - Conditions: `in_desolve_with_conditions` `:478`: differentiate the general solution up to the highest
    condition order, substitute the points, solve for the constants, check.

  FlowCE prints the constants as C1, C2 (`textbook_constants`, `F/answer.cc:1873`).
- **Sketch (classifier = ordered checks, each a module function, no recursion):** normalize `F(x, y, y′, y″) = 0`.
  1. **Order 1, linear** (`y′ + p(x)y = q(x)` after dividing by the coefficient of y′): μ = `exp(∫p)`, simplified
     (`e^(ln x) = x`, drop abs and constant factors as `desolve_cleanup` does). Then `y = (∫μq dx + C)/μ`.
  2. **Order 1, separable:** solve for y′ = G. Factor G (2.8 on the `normal` numerator and denominator, or just its
     product structure) and split the factors by `free_of`. Then `∫dy/h(y) = ∫g(x)dx + C`, and try `solve` for y.
     Record the lost solutions h(y₀) = 0 (y = 0 for y′ = xy). Absorb constants: `ln|y| = F + C` → `y = C·e^F`.
  3. **Bernoulli** (`y′ + p y = q yⁿ`): v = y^(1−n) → step 1. This is cheap to add.
  4. **Order 2, constant coefficients** `a y″ + b y′ + c y = g(x)`: roots of `a r² + b r + c` exactly (quadratic
     formula, 2.10). The three cases: distinct real, double, complex `α ± βi`.
  5. **Particular solution, undetermined coefficients as an operator series.** For each term
     `P(x)·e^(αx)·{cos, sin}(βx)` of g, set λ = α + iβ, and compute `y_p = e^(λx)·[1/L(D+λ)]P(x)`:
     - write L(D+λ) = D^s·M(D), where s is the multiplicity of λ as a root;
     - invert M as a truncated power series in D (the recurrence of 3.2, truncated at deg P);
     - apply it to P (finite, since D^(deg P+1)P = 0);
     - integrate s times (polynomial integration).

     Take the real or imaginary part for cos or sin (Gaussian-rational arithmetic on coefficient pairs). This is
     about 40 lines, iterative, needs no linear system, and gives the textbook result. Fallback: variation of
     parameters with the integrator (`y_p = −y₁∫y₂g/(aW) + y₂∫y₁g/(aW)`).
  6. **Initial conditions:** substitute x₀ into y, y′ (and y″), solve the linear system for C₁, C₂ (Gauss-Jordan),
     substitute back, simplify.
- **Subset:** 1, 2, 4, 5, 6; 3 is cheap. Skip exact, homogeneous-substitution, Clairaut, Laplace, systems and
  variable coefficients.
- **Pitfalls:**
  - Constants: show C1 and C2. Absorbing ±e^C into C is a convention, so state it.
  - Separable solutions lost in the division (y = 0).
  - Implicit answers when solve for y fails: show `G(y) = F(x) + C`.
  - Resonance: s > 0 must come out right (`y″ + y = sin x` → −x·cos(x)/2).
  - Complex-root output in real form.
  - Initial conditions at x₀ ≠ 0. Inconsistent conditions → "no solution".
  - Parse `y'`, `y''` as derivative nodes, with y implicitly y(x).

### 4.5 Gradients

- **giac:** `_grad` `G/kderive.cc:679` = `derive(f, [x, y, z])`, a vector of partial derivatives (optional
  cylindrical and spherical scale factors). `_derive` with a variable list `:593`.
- **Sketch:** a list of 3.1 results, one per variable, each simplified. Optional extras: Hessian, directional
  derivative `∇f·u/|u|`, value at a point.
- **Pitfalls:** the variable list order. Symbols that are not in the list are constants. Vector output layout in
  the printer.

### 4.6 Multiple integrals

- **giac:** no special code. `integrate(integrate(f,y,g1(x),g2(x)),x,a,b)` nests `_integrate`. FlowCE notes that
  double integrals are "computed twice" and skips its definite fast path for them (`F/answer.cc:1130` comment).
- **Sketch:** iterated definite integration from the inside out. Each inner integration treats the outer variables
  as constants (`free_of` per variable), and the bounds can be expressions in the outer variables (substitute and
  simplify, no numeric cross-check). If any level leaves an R or a non-elementary form, compute the **whole**
  integral numerically: Gauss-Legendre product rule n×n (n = 8-12) on the mapped region `x ∈ [a,b]`,
  `y ∈ [g1(x), g2(x)]` (about 100-150 evaluations through the compiled lambda), or nested tanh-sinh with low levels.
  Optional helpers: polar `dA = r dr dθ`, triple integrals the same way.
- **Pitfalls:** the order of variables and bounds (dy dx vs dx dy). Bounds that depend on the inner variable are an
  error. Cost grows like n^d numerically, so limit the number of points.

### 4.7 Polar and parametric area, arc length

- **giac:** `arcLen` `G/kti89.cc:512` (`∫√(1+f′²)`, or the vector norm for curves). `plotarea` is graphic only.
  FlowCE `hard_radicand` / `odd_factors` / `quadratic_radicand` (`F/answer.cc:851-922`) decide whether an
  arc-length radicand is elementary: factor it, drop even powers, and check that the rest has degree ≤ 2.
  Otherwise go numeric at once.
- **Formulas:**
  - polar area `½∫_α^β r(θ)² dθ`, between curves `½∫(r₁²−r₂²)dθ`;
  - parametric area `∫ y(t)·x′(t) dt` (signed by orientation, take |…| or report the sign) or `½∫(x y′ − y x′)dt`
    for closed curves;
  - arc length: `∫√(1+f′²)dx`, `∫√(x′²+y′²)dt`, `∫√(r²+r′²)dθ`;
  - surface of revolution optional.
- **Sketch:** build the integrand, simplify. For arc length, `normal` the radicand, factor the numerator and
  denominator, and pull perfect squares out of √ (`√(u²) = |u|`). Decide the sign of u on the interval with a
  midpoint check, then drop the abs. This turns textbook arc lengths (`1 + (x − 1/(4x))² = (x + 1/(4x))²`) into
  elementary integrals. Then 3.5. If the radicand has an odd-power factor of degree > 2 → numeric straight away.
- **Pitfalls:**
  - Petal limits for `r = cos(3θ)`: find the zeros of r with `solve`, and show the intervals.
  - `r²` of a trig function needs S5 power reduction.
  - Overlapping traversal (a rose counts petals twice over [0, 2π]).
  - The orientation sign of parametric area.
  - Degree mode in polar formulas: convert to radians internally.

---

## 5. Priority and budget table

Lines are rough Python estimates; KB uses about 25 B per line. Check on the device (section 1.6).

| feature | subset to build | lines | KB | milestone | priority |
|---|---|---|---|---|---|
| node table, constructors, auto-simplify | 1.1, 2.4 constructors | 400 | 10 | T1 | P0 |
| rationals, radicals, special values | 2.1-2.3 | 300 | 8 | T1 | P0 |
| poly Z[x]: arithmetic, PRS gcd, Yun, Bezout | 2.6, 2.7 | 250 | 6 | T1 | P0 |
| normal / expand / simplify candidates | 2.4, 2.5 | 300 | 8 | T1 | P0 |
| factor: rational roots, shapes, Kronecker d ≤ 2 | 2.8 | 250 | 6 | T1 | P0 |
| solve: worklist, polynomial, inverses, radical, linear systems | 2.10 | 350 | 9 | T1 | P0 |
| Zassenhaus | 2.8 stretch | 250 | 6 | T1+ | P2 |
| diff + gradient + FTC | 3.1, 4.5 | 150 | 4 | T2 | P0 |
| series engine (recurrences, Laurent) | 3.2 | 300 | 8 | T2 | P0 |
| limits (7 steps) | 3.3 | 300 | 8 | T2 | P0 |
| integrate S0-S7 + tables + check | 3.4 | 800 | 20 | T2 | P0 |
| partial fractions (linear system) | 2.9 | 80 | 2 | T2 | P0 |
| definite + quadrature (tanh-sinh, lambda compile) | 3.5, 3.6 | 250 | 6 | T2 | P0 |
| improper + divergence | 4.1 | 120 | 3 | T3 | P1 |
| sums: finite closed forms + infinite table/tests | 4.2 | 350 | 9 | T3 | P1 |
| Riemann | 4.3 | 80 | 2 | T3 | P1 |
| ODEs: lin1, separable, const-coeff + operator particular, ICs | 4.4 | 350 | 9 | T3 | P1 |
| multiple integrals, polar/parametric/arc length | 4.6, 4.7 | 150 | 4 | T3 | P1 |
| Weierstrass, Bernoulli, Gosper | 3.4 S8, 4.4.3, 4.2 | 200 | 5 | T3+ | P2 |

**Skip outright:**
- Risch (FlowCE did fine without it);
- full Gruntz MRV;
- residue-based definite integrals and sums (`G/kintgab.cc` `intgab` `:816`, `sumab` `:1872`);
- RootOf and algebraic extensions beyond √;
- multivariate Hensel factoring;
- Laplace transforms;
- Psi, Zeta and erf results;
- inequality solving (giac `solve_inequation` `G/ksolve.cc:1165`, if it is wanted later).

---

## 6. Oracle test seeds (desktop, SymPy equivalence)

Compare with `sympy.simplify(ours − theirs) == 0`, or numerically at 3 random points. For antiderivatives compare
`d/dx ours − f`. Never compare strings, except in the golden-file printer tests.

- **2.2:** `sqrt(72)=6√2`, `sqrt(8/27)=2√6/9`, `(-8)^(1/3)=-2`, `sqrt(3+2√2)=1+√2`, `1/√2=√2/2`, `sqrt(-4)=2i`.
- **2.3:** `cos(5π/12)=(√6−√2)/4`, `tan(π/12)=2−√3`, `cos(π/5)=(1+√5)/4`, degree mode `sin(30)=1/2`, `atan(√3)=π/3`.
- **2.4/2.5:** `(x+1)^2−x^2−2x=1`, `x/x=1`, `expand((x+y)^3)`, `normal((x^2−1)/(x−1))=x+1`.
- **2.8:** `x^4+4=(x²−2x+2)(x²+2x+2)`, `x^6−1`, `6x^3−11x^2+6x−1=(x−1)(2x−1)(3x−1)`, `x^2−y^2`, `2x^3−4x^2−6x`, `x^5−x+1` (irreducible, complete).
- **2.10:** `x^2−5x+6`, `x^2+1` (none in real mode), `2^x=8 → 3`, `sin x=1/2`, `√(x+3)=x−3 → 6` (check rejects 1), `ln x = 2`, a 3×3 linear system.
- **3.1:** `d/dx x^x`, `d/dx ln(sec x+tan x)=sec x`, `d²/dx² sin(x)/x`, `d/dx ∫₀^{x²} sin(t²)dt`.
- **3.2:** `taylor(sin x,x,0,7)`, `taylor(tan x,…)`, `taylor(1/(1−x)^(1/2))`, at a=1 `ln x`, Laurent `1/sin x`.
- **3.3:** `sin x/x`, `(1−cos x)/x²`, `x ln x` at 0+, `(1+1/x)^x` at ∞, `x³/e^x`, `1/x` at 0 (DNE: −∞ / +∞), `|x|/x` (DNE −1/1), `sin(1/x)` (DNE oscillates), `√(x²+x)−x` at ±∞.
- **3.4:**
  - table: `x²`, `1/x`, `e^(3x)`, `sec²(2x)`, `sec³x`;
  - u-sub: `2x·cos(x²)`, `cos(3x)(2+sin 3x)^4`, `x/(x²+1)`;
  - parts: `x e^x`, `x² sin x`, `ln x`, `x ln x`, `atan x`, `e^x sin x`;
  - rational: `1/(x²−1)`, `(3x+5)/(x²+2x+5)`, `1/(x²+1)²`, `x³/(x−1)`;
  - trig powers: `sin³x cos²x`, `sin²x`, `tan³x`, `sin⁴x`;
  - radicals: `√(1−x²)`, `x√(x+1)`, `1/√(x²+4)`, `x²/√(1−x²)`;
  - failure: `e^(x²)` stays unevaluated.
- **3.5/3.6:** `∫₀^π sin`, `∫₀^{2π} 1/(2+cos x)=2π/√3` (jump check), `∫₀^1 √(1−x²)=π/4`, `∫₀^2 √(1+sin⁴x cos⁶x)` (≈).
- **4.1:** `∫₁^∞ 1/x²=1`, `∫₁^∞ 1/x` (diverges), `∫₋₁^1 1/x²` (diverges, interior singularity), `∫₀^1 1/√x=2`, `∫₀^∞ e^(−x)=1`.
- **4.2:** `Σk²` to n, `Σ1/(k(k+1))` to n and to ∞ (= 1), `Σ1/n²=π²/6`, `Σ(−1)^n/n` from 1 (= −ln 2), `Σ1/n` (diverges), `Σ x^n/n!`, `Σ k·2^k`.
- **4.3:** right sum of x² on [0,1] with symbolic n → `(n+1)(2n+1)/(6n²)` → limit 1/3.
- **4.4:** `y′=xy`, `y′+y=e^x`, `y″+y=0`, `y″−3y′+2y=e^(3x)`, `y″+y=sin x` (resonance), `y″+2y′+y=0` with y(0)=1, y′(0)=0.
- **4.5-4.7:** `grad(x²y+sin z)`, `∫₀^1∫₀^x xy dy dx = 1/8`, polar area of `r = 2cos θ` = π, cycloid arch area 3π, arc length of `y = x^(3/2)` on [0,4].
