# FlowCE answer formatting: reference

How FlowCE (TI-84 Plus CE, giac-based) turns a giac result into the textbook answer the user
sees. This is an algorithm and behaviour reference for cas-evo. It is not a spec. Where FlowCE
and the settled cas-evo decisions differ, the difference is marked **cas-evo:**.

Source root: `C:\Users\conner\.cache\cas-evo-ref\FlowCE\src`. Citations are `file:line` in that
directory. giac citations are `giac/<file>:line` in `C:\Users\conner\.cache\cas-evo-ref\ti-ce-giac`.

---

## 0. Architecture in one page

The answer pipeline, as run by `do_run` (`main.cc:1083-1307`):

1. **Ans substitution.** Each `ans()` in the typed text is replaced by `(<last output line text>)`.
   This happens only if that text is < 400 chars and has no space, so messages never become Ans
   (`main.cc:1084-1110`).
2. **Input pre-pass.** This adds TI implicit multiplication and paper notation, makes `log(`
   into `log10(`, and renames a sum's index `i` (`answer.cc:2976-2984`, `tiinput.cc:1-41`).
3. **Parse, then `answer_before`.** This step does the following (`answer.cc:3053-3108`):
   - A lone equation is solved for its only unassigned unknown.
   - Table integrals, known sums and "hard" definite integrals are short-circuited.
   - It records context flags (`answer_ctx`, `answer.h:10-22`).
4. **giac eval** (`main.cc:1202-1208`).
5. **`answer_after`** (`answer.cc:3110-3234`). Either it puts a plain **message** in `msg`, or it
   rewrites the result tree into textbook form: normalization, `positive_first` ordering, and
   solutions as `x=...`.
6. **`result_approx`.** This computes the decimal value line, but only for exact numeric results
   (`main.cc:1218-1219`, `answer.cc:1774-1801`).
7. **`answer_print`.** The tree is printed by giac as a 1D string, then string passes are applied:
   `textbook()`, `textbook_constants()`, solution parens, and chained inequalities
   (`answer.cc:3236-3259`).
8. The **1D string is stored** as the history output line. That string is the canonical answer
   and is what Ans pastes.
9. **Drawing.** `focus.cc` re-parses that 1D string with the same 2D layout engine used for input
   (`mathinput.cc`, flag `MI_F_IMPLDOT`) and draws it with `ui_math.cc`
   (`focus.cc:206,224,407-418`). View-only decorations are added at draw time and are **not**
   part of the answer text:
   - `+ C`
   - `≈ <decimal>`
   - the F4 forms chip

Consequences worth copying:

- **One 2D engine for input and output.** A result is formatted as a *string in the input
  language*. The renderer is a parser of that string, so results, history and Ans all share one
  representation.
- **Two-stage formatting.** First tree rewrites (ordering, signs, quotients). Then cheap string
  rewrites on the printed text (`p/q*m -> p*m/q`, `exp(1) -> e`, `O()`, `c_0 -> C1`).
- **Messages are plain strings.** The view tells them from math with a heuristic (`focus.cc:96-108`).

**cas-evo:** every recursive pass named below (`positive_first`, `map_nodes`, `normal_args`,
`neg_sum`, mathinput's recursive-descent parser, `measure`/`place`) must be rewritten with an
explicit stack because of the ~10-frame cap.

---

## 1. Term and factor ordering (`positive_first`, `answer.cc:416-640`)

`positive_first` is applied to every symbolic result whose size (`taille`) is < 200 and that
holds no `order_size`, so series keep giac's order (`answer.cc:3218-3219`). It is also applied
to every F4 form (`answer.cc:2592-2593`). It works bottom-up (children first, `answer.cc:428`).

### 1.1 Sums

**Polynomial in one variable, > 2 terms: descending powers.** Each term gets its monomial degree
`mono_deg` (`answer.cc:155-189`). This accepts `c`, `x`, `x^k` (k a positive integer), `-t`,
`1/n` (n an integer), `t/n` and products of these. The terms are then sorted by degree,
descending, with a stable insertion sort. This works for up to 64 terms (`answer.cc:429-446`).
Example: giac's `20x^11+88x^9+...+11x^12/2` becomes `11x^12/2+20x^11+...`.

**Not a polynomial, > 2 terms.** The key is `x_power` (`answer.cc:385-398`). The key is 60 × the
rational exponent of the variable power found in the term (floored). It looks into
`/`, unary minus and product factors. Other terms get key 0. The sort is descending and stable.
Result: `2x^(3/2)-3x+6sqrt(x)`, and `x^2*e^x-2x*e^x+2e^x`.

**Exactly 2 terms.** Two rules apply:

- Put the **positive term first** when the first is negative and the second is not
  (`answer.cc:447-450`). So `4-x^2`, not `-x^2+4`. Also `ln|x-2|-ln|x+2|`, and `x-ln(e^x+1)`.
  This ignores degree. A 3-term sum such as `-x^3+3x^2-2` keeps its descending order.
- **Real part first** for complex numbers: if only the first term contains `i`, swap
  (`answer.cc:451-454`). So `1+i*sqrt(3)`.

**What is a "negative" term** (`neg_term`, `answer.cc:106-115`):

- a negative number
- a unary `-t`
- a product whose first factor is negative

**Flip negated differences inside sums** (`answer.cc:455-471`). Take a term `-(P)*rest` where
factor `P` has a "negative lead" (`lead_negative`, `answer.cc:192-212`). A negative lead is the
highest-degree term being negative (polynomial case), or most terms being negative. The term
becomes `+(-P)*rest`, with `-P` distributed by `neg_sum` (`answer.cc:214-234`). Example:
`2x*cos(x)+(x^2-2)*sin(x)`, not `2x*cos(x)-(2-x^2)*sin(x)`.

**Negated product holding a 2-term difference** (`answer.cc:472-484`):
`-(cos(x)-sin(x))*u` becomes `(sin(x)-cos(x))*u`. This is skipped when both terms have the same
sign or both are monomials, so `-(x-2)(x-3)` stays.

### 1.2 Powers

- `(x^(1/3))^2` becomes `x^(2/3)`. `(x^(1/3))^-2` becomes `1/x^(2/3)` (`answer.cc:485-495`).
- In products, `b^(-q)` (q a positive rational) becomes `1/b^q`. It moves to the denominator:
  `3x^2/(2sqrt(x^3+1))`, not `3x^2*(x^3+1)^(-1/2)/2` (`answer.cc:509-517`).
- Powers of one variable are merged: `x*x^(1/3)` becomes `x^(4/3)`, and `x^2/x^2` becomes 1
  (`answer.cc:560-585`).
- Powers of one function with exponents in x are merged: `sin(2x)^x*(sin(2x)^x)^3` becomes
  `sin(2x)^(4x)` (`answer.cc:544-559`).

### 1.3 Products (`answer.cc:496-638`)

The steps run in this order:

1. **Flatten** nested products. A division `1/d` becomes `inv(d)`, so it rejoins the
   denominator logic below (`answer.cc:498-508`).
2. **`x^2*sign(x)` becomes `x*|x|`** (`answer.cc:518-531`).
3. **Pull rational content out of sum factors** with `sum_content` (`answer.cc:270-322,532-543`).
   This takes the gcd of the numerators over the lcm of the denominators, and makes it negative
   when every term is negative:
   - `e^(2x)*(2sin(3x)/13-3cos(3x)/13)` becomes `e^(2x)(2sin(3x)-3cos(3x))/13`
   - `e^(-x)(-x^2-2x-2)` becomes `-e^(-x)(x^2+2x+2)`
4. **Sort the factors** with a stable insertion sort using `factor_before`
   (`answer.cc:363-383,588-592`). Ranks (`factor_rank`, `answer.cc:118-134`):

   | rank | factor kind | example |
   |---|---|---|
   | 0 | numbers, `inv(integer)` | `3`, `1/2` |
   | 1 | `pi` | `2*pi*x` |
   | 2 | a variable or its power | `x`, `x^2` |
   | 3 | `exp(...)` | `e^x*cos(x)` (not `cos(x)*e^x`) |
   | 4 | everything else (functions, sums) | `sin(x)`, `(x+1)` |
   | 5 | lists or vectors (kept in order; matrices do not commute) | |

   Tie-breaks within a rank:
   - **Trig (any rank):** the smaller argument first, then
     sin < cos < sec < csc < tan < cot (`trig_key`, `answer.cc:351-362`). So `2sin(x)cos(x)`,
     `sec(x)tan(x)` and `-csc(x)cot(x)`.
   - **Rank 4:** a one-variable polynomial goes before a non-polynomial:
     `(x^2-2)sin(x)`. Two polynomials in the same variable are ordered by
     (`poly_key`, `answer.cc:326-348`):
     1. lower degree first
     2. then smaller |constant term|
     3. then negative constant first

     This gives `(x-2)(x+2)(x^2+4)` and `(x-2)(x-3)`. Different variables keep their order:
     `(x+1)(y-1)`.
5. **Multiply adjacent numeric factors**: `3*2*x` becomes `6*x`. Drop a leading `1`
   (`answer.cc:593-598`).
6. **Build one fraction when there are two or more denominators**, or a fraction coefficient
   plus one `inv` (`answer.cc:601-622`). For example `(18x-7)*inv(9)*inv(x^2+9)` becomes
   `(18x-7)/(9(x^2+9))`, and `3x^2/(2sqrt(x^3+1))`.
7. **Move a fraction coefficient below the bar** (`answer.cc:623-633`):
   - `1/2*(x+1)` becomes `(x+1)/2`, so `arctan((x+1)/2)`
   - `3/2*u` becomes `3u/2`
   - `7/9*inv(x^2)` becomes `7/(9x^2)`
8. **`-1*rest` becomes `-(rest)`** (`answer.cc:634-637`).

**Sign in front of a quotient** (`tb_quotient`, `answer.cc:136-152`): a negative integer
numerator or leading coefficient becomes `-(n/d)`. So `-3/(16(x-1))`, never `(-3)/...`. Inside a
sum this prints as `... - 3/(...)`.

### 1.4 Long polynomial over an integer (`answer.cc:3244-3254`)

This applies when the printed text is longer than 70 characters and the result is
`(sum)/integer` (not a series). The result is then expanded term by term and re-ordered:
`x^14/14+...`, not `(13x^14+...)/182`, which cannot be wrapped.

---

## 2. Normalization before ordering (`answer_after`)

These steps decide which equivalent form is shown. Order of application: `answer.cc:3110-3233`.

**`auto_simplify`** (`answer.cc:781-841`). It runs only when `a.autosimp`: the input was not an
explicit `factor/expand/...` form, except `diff`, which always runs (`answer.cc:3101-3107`). It
also needs the result size < 100 and `simplify_candidate` true (`answer.cc:80-103`): the result
has a sum, an `inv`, a `tan`, a negative power, or a numeric radical other than `sqrt(n)`.

- **Stay factored if already factored** (`keep_factored`, `answer.cc:689-716`). A product of
  numbers and at least 2 polynomial factors, one of them a sum, keeps its structure. Its numbers
  are multiplied and each base is normalized: `6*x*(x^2+1)^2`.
- **Otherwise `ratnormal`.** The denominator is then factored: `1/(x+1)^2`, not
  `1/(x^2+2x+1)` (`answer.cc:799-808`). The new form is kept only if not bigger
  (`answer.cc:810-811`).
- **Trig answers** (tan, or a power of sin or cos, and no radicals). The candidates are:
  in sin, in cos (sin²+cos²=1), and `tlin`. The smallest is kept (`answer.cc:812-828`). Example:
  d/dx ln(sec x + tan x) gives `1/cos(x)`.
- **One square root:** `normal`, kept if smaller (`answer.cc:829-834`). Several root kinds are
  never normalized (`radicals`, `answer.cc:732-755`) because that was too slow.
- **`merge_sqrt`**: `(p/u)*u^(3/2)` becomes `p*sqrt(u)` (`answer.cc:835-839`).
- After that: `collect_rational(power_sums(g))`.
  - `power_sums` (`answer.cc:2895-2908`) combines the power-rule terms of a sum of fractional
    powers of x.
  - `collect_rational` (`answer.cc:758-780`) merges the rational-in-x terms of a sum, if that is
    shorter.

**`normal_args`** (`answer.cc:2663-2689`) puts function arguments in lowest terms:
- `atan((2x-1)/sqrt(3))`, not `atan((x-1/2)/(1/2*sqrt(3)))`
- `ln(x^2)` becomes `2*ln(|x|)` when the base is linear in one variable
- the ln of a constant is expanded when that is shorter: `-ln(2)/2`, not `ln(sqrt(2)/2)`

**`textbook_powers`** (`answer.cc:2690-2696`): `exp(x*ln(2))` becomes `2^x`.

**Numeric results** (`answer.cc:3211-3216`): `ln(4)` becomes `2*ln(2)` (`ln_power`,
`answer.cc:2922-2934`), then the terms are collected. Example: `12ln(2)-6ln(4)+3` becomes `3`.

**Other rewrites:**
- `-3/-4` becomes `3/4` (telescoping sums) (`answer.cc:3157-3158`).
- Finite sums to `n`: the result is factored, so `n(n+1)/2` (`answer.cc:3178-3182`).
- `simplify(...)` that brings in a `tan` not typed: the sin, cos or tlin forms are preferred.
  `sin(x)^4-cos(x)^4` gives `-cos(2x)` (`answer.cc:3183-3191`).
- **sec, csc, cot typed**: the answer is rewritten with them (`sec_only`, `answer.cc:2396-2452`,
  `answer.cc:3209-3210`). `1/cos(u)^n` becomes `sec(u)^n`. `sin(u)*sec(u)^n` becomes
  `tan(u)*sec(u)^(n-1)`. The rewrite is used only if no sin or cos is left.
- **"Simplify answers" mode off**: no normalization at all (giac's `autosimplify(0)`). The status
  bar shows `SIMPLIFY OFF` (`answer.h:24-33`, `focus.cc:507`).

---

## 3. Antiderivatives and `+ C`

**When `+ C` is shown.** The test is on the **input** text: it starts with `integrate(` or
`int(` and has at most one top-level comma, so 1 or 2 arguments (`is_antideriv`,
`focus.cc:110-121`). A definite integral has 4 arguments and gets no `+ C`. An **unevaluated**
`integrate(f,x)` result is drawn as `∫ f dx` and **also gets `+ C`**, because the test only looks
at the input.

**How `+ C` is drawn.** It is a decoration, never part of the result string. The plain `+ ` is
upright and `C` is italic, both in the secondary color `UC_SUB`, placed right after the answer:
- History rows: 17 px faces, reserved at the right edge (`focus.cc:208-214`).
- Hero (large last result): 24 px faces, 6 px after the math. The answer box shrinks from 292 to
  256 px to make room (`focus.cc:406-423`). When the result wraps, `+ C` follows the last line.

So Ans, history recall and F4 never see `+ C`.

**Constant terms go into + C** (`drop_constants`, `answer.cc:2936-2973`). Terms of the numerator
(or of its normal form) whose quotient by the denominator is constant in x are dropped, if that
makes the result smaller:
- `-sqrt(x^2+4)/(4x)`, not `(-sqrt(x^2+4)-x)/(4x)`
- `sqrt(x^2-1)/x`

This applies only to `integrate(f,x)` results not found in a table (`answer.cc:3197-3205`).

**Conjugate logs** (`ln_conjugate`, `answer.cc:2698-2745`). `ln|sqrt(P)-Q|` becomes
`ln|c| - ln|sqrt(P)+Q|` when `c = P-Q²` is constant. The constant is then dropped:
`-ln(sqrt(x^2+9)-x)` becomes `ln(x+sqrt(x^2+9))`. The `|..|` is kept only when `c<0`.

**Exponential antiderivatives are factored** when that is smaller and adds no radical:
`e^x(sin(x)+cos(x))/2` (`answer.cc:3199-3203`).

**Table antiderivatives use textbook strings** (`answer.cc:988-990`):

| integrand | antiderivative |
|---|---|
| `sec(u)` | `ln(abs(sec(u)+tan(u)))` |
| `sec(u)^2` | `tan(u)` |
| `sec(u)^3` | `(sec(u)tan(u)+ln(abs(sec(u)+tan(u))))/2` |
| `csc(u)` | `ln(abs(csc(u)-cot(u)))` |
| `csc(u)^2` | `-cot(u)` |
| `csc(u)^3` | `(-csc(u)cot(u)+ln(abs(csc(u)-cot(u))))/2` |

Each is divided by `u'`, and `tan(u)^2` gives `tan(u)/a - x`. The `trig_powers` results are
written in ascending powers of the substituted function, as textbooks do: `sin(x)-2sin(x)^3/3+sin(x)^5/5`
(`answer.cc:1087-1095`). u-substitution keeps `b^k/k` as written: `(x^2+9)^(3/2)/3`
(`answer.cc:1669-1671`). `ln|x^2+1|` is kept as `ln(abs(...))`.

**ODE constants.** giac's `c_0, c_1, ...` print as `C1, C2, ...` (word boundaries respected)
(`textbook_constants`, `answer.cc:1872-1898`). A `desolve` result containing `c_0` that is not a
sum is expanded first (`answer.cc:3173-3177`).

---

## 4. log / ln / e / i / angle conventions

- **log is base 10.** In Focus, the pre-pass rewrites each `log(` that is not part of a longer
  name and not in a string to `log10(` (`answer.cc:1808-1824,2980-2983`). The renderer shows
  `log10` as **`log`** (`mathinput.cc:236`). `ln` stays `ln`. So users type and see `log` for
  base 10 and `ln` for natural.
- **Function display names** (`mathinput.cc:235-241`):

  | stored | shown |
  |---|---|
  | `asin` | `arcsin` |
  | `acos` | `arccos` |
  | `atan` | `arctan` |
  | `log10` | `log` |
  | `ans` | `Ans` |

  `ans()` is drawn as `Ans` with its parentheses hidden (`mathinput.cc:310`).
- **e**:
  - `exp(1)` is rewritten to `e` in the text, except inside longer names like `myexp(1)`
    (`answer.cc:1961-1968`).
  - `exp(a)` is drawn as `e` with superscript `a` (`mathinput.cc:39,547-554`).
  - The `e` glyph is italic (`ui_math.cc:52`).
- **i** is the imaginary unit:
  - A sum's index named `i` in `sum(`, `seq(` or `product(` is renamed `k`, `j` or `m`
    (`answer.cc:1828-1870`).
  - Greek names are kept whole: `phi` is not `p*h*i` (`tiinput.cc:187-188`).
  - Complex answers put the real part first (§1.1).
  - With `MI_F_IMPLDOT`, `sqrt(3)*i` draws as `√3 i` (dot hidden before a letter).
- **Real odd roots.** If no `i` was typed, `(-8)^(1/3)` is `-2` and `(-1)^(2/3)` is `1`
  (`answer.cc:1176-1204,3060-3062`).
- **Angle mode** is in the status bar as `RAD    EXACT` or `DEG    EXACT` (`focus.cc:503`). Exact
  trig values come from giac.
- **pi** is drawn `π`. Before a letter `pi` is split off (`2pir` is `2πr`), but not before `(`
  (`mathinput.cc:154-158,352`). `infinity`, `oo` and `inf` are drawn `∞`. `theta` is drawn `θ`
  (`mathinput.cc:353-354`).

---

## 5. Exact answer + decimal line

### 5.1 Which results get a decimal line (`result_approx`, `answer.cc:1774-1801`)

It is computed only when there is no message and no interruption (`main.cc:1218-1219`).

It is **not** shown when the result is any of:
- an integer
- a double
- a float
- a string or message
- a list or sequence (so never for solve output)
- a result with size >= 64
- a result containing `sum(`
- a Gaussian integer such as `5+5i`

Otherwise `evalf` must give a real or complex double, or nothing is shown.

### 5.2 Number format

- **6 significant digits.** `decimal_digits` is temporarily set to 6, which gives giac's
  `%.6g`-style print (`answer.cc:1789-1792`, `giac/kgen.cc:11504-11537`). Examples: `1.41421`,
  `0.333333`, `1.23457e+10`.
- For `1e5 <= |d| < 1e6` the value is printed as a rounded integer, `862519`, not `8.62519e5`
  (`plain_decimal`, `answer.cc:1753-1762`). The result line uses the same rule (`answer.cc:3239`).
- Complex: a trailing `*i` becomes `i` (`1.5+0.5i`). A `.0` before `+` or `-` is dropped
  (`1+1.73205i`) (`answer.cc:1794-1800`).
- giac's raw double printing adds `.0` to integral doubles (`2.0`) (`giac/kgen.cc:11533-11537`).

**cas-evo:** we use 10 significant digits, with scientific notation when |x| >= 1e10 or < 1e-4.

### 5.3 How it is drawn (`focus.cc:425-440`)

Only the **hero** (the last result, shown large) has the footer. History rows never show it. The
footer is one centered row, 13 px above the bottom of the hero area. It holds:

1. `≈ <value>`: the literal `"\xe2\x89\x88 "` (≈ and a space) then the value, in the 10 px text
   face, secondary color.
2. Then, 12 px later, the **forms chip**: a rounded pill in the soft accent color. It contains the
   current form name (bold 9 px, accent color) and then `F4` (secondary color).

The chip shows `exact` for the original answer. If the result itself is a plain decimal (only the
characters `0-9 . - + e`) the chip says `decimal` instead (`focus.cc:428-429`).

The decimal belongs to the exact text it was computed for. `console_approx_for` holds that text,
and the footer is shown only if the output line still equals it (`answer.cc:1763-1773`,
`focus.cc:430`). After F4 replaces the line with another form, the `≈` disappears.

**Decimal-only results** have no `≈` prefix in FlowCE: numeric definite-integral fallbacks,
numeric infinite sums, and floats. They are shown as the bare decimal with the chip labelled
`decimal`.

**cas-evo:** label such fallbacks with `≈`.

---

## 6. F4: the answer-form cycle

Declared in `answer.h:46-76`. Implemented in `answer.cc:2071-2658` and driven by
`console_cycle_form` (`main.cc:579-627`).

### 6.1 Triggers (`console.cc:2356-2364,2518-2522`)

F4 works on the result **selected in the history**, or on the **last result shown large**
(`focus_result_line`, `focus.cc:897-901`). With neither, F4 opens the symbols popover. The F4
tab label becomes `forms` when a result is available (`focus.cc:609-623`).

### 6.2 Form names and order (`answer.cc:2146-2149`)

Names: `simplified`, `one fraction`, `factored`, `expanded`, `trig combined`, `trig expanded`,
`in terms of sin`, `in terms of cos`, `in terms of tan`, `decimal`. The original is labelled
`exact` (Focus chip). The classic UI shows `original` and the status text
`form: <name>    F4: next` (`main.cc:620-626`).

| result kind | cycle order after the original |
|---|---|
| exact **number** (it had a `≈` line) | decimal, simplified, one fraction, factored, expanded |
| expression containing sin, cos or tan | trig combined, trig expanded, in terms of sin, in terms of cos, in terms of tan, simplified, one fraction, factored, expanded, decimal |
| any other expression | simplified, one fraction, factored, expanded, decimal |

### 6.3 Computation (`form_op`, `answer.cc:2453-2476`)

Each form is one giac command on the **original** result, never on the previous form: `simplify`,
`ratnormal` (one fraction), `factor`, `expand`, `tlin`, `texpand`, `trigsin`, `trigcos`,
`trigtan`, `evalf`. The original is re-parsed from the output text (`answer.cc:2611-2613`). Each
form is computed once and cached per result, so a second round is instant (`answer.h:56-57`).

**Opaque function nodes.** For the algebra forms (one fraction, factored, expanded), every
non-arithmetic function node is first replaced by a placeholder name `fn__k`, and then put back
(`function_nodes`, `answer.cc:2372-2393`). Examples are `ln(...)`, `|...|`, `sin(...)`, `e^(...)`
and `atan(...)`. So "factored" factors the algebra *around* the functions, and does not rewrite
`ln|sec+tan|` into `1/cos`. For the trig forms only non-trig functions are opaque. If every trig
function sits inside a `ln`, nothing is made opaque.

### 6.4 When a form is offered (`form_compute`, `answer.cc:2478-2604`)

A form is **skipped** (empty text) when any of these hold:

- **simplified**:
  - the result has a radical, or
  - it is trig and (no trig below a fraction bar, or size > 12) (`2487-2488`), or
  - the simplified text is not strictly smaller than the original (`2569-2572`)
- **trig combined / trig expanded**: trig below a bar, or trig of a non-polynomial argument
  (`2489-2490`). trig expanded is also skipped for a multiple angle over 6, such as `sin(7x)`
  (`2491-2492`).
- **any trig form**:
  - the size is over 60 (`2495-2496`)
  - it rewrites no trig node, judged by the set of printed trig calls (`2583-2584`)
  - it puts trig below a bar where there was none (unless only tan is left), or it grows past
    4×size+40, unless it is shorter (`2587-2588`)
- **trig result whose trig is all inside ln**: only `in terms of sin` and `decimal`, and only when
  size <= 20 (`2497-2498`).
- **one fraction** (non-number):
  - the top is not a sum with at least one term that has a denominator (`2501-2510`), or
  - the result has functions and a denominator in x would appear (`2534-2539`).
  - Otherwise its denominator is factored when that is not bigger: `(...)/(2(x^2+1))`
    (`2540-2549`).
- **factored**:
  - the top is not a product: there must be 2+ factors with variables above or below the bar, or
    a power of a sum (`top_product`, `2305-2334,2532`), or
  - factoring added radicals the original lacked, e.g. `(cos(x)+sqrt(2)/2)(...)` (`2576-2577`).
  - `merge_sqrt` is applied: `(1-25x^2)^(3/2)` (`2525-2526`).
- **expanded**: the top is not a sum, or the sum is not "fully expanded": a term still has a sum
  factor, or every term shares one denominator in x (`fully_expanded`, `2270-2299,2580-2581`).
- **decimal** (non-number):
  - the result has a variable exponent (`2^x`) or size > 40 (`2513-2514`), or
  - it has no irrational constant (`irrational_constant`, `2220-2235,2517-2518`). An irrational
    constant is pi, e, `sqrt(2)`, `ln(2)`, an atan of a number, or a double. So `x^3/3` is never
    shown as `0.333333x^3`.
  - Polynomials are expanded before `evalf`. `x^0.5` is shown as `sqrt(x)` (`2520-2521,2236-2247`).
- **in terms of tan**: tan is not the only trig function left (`2556-2567`). The denominator is
  factored: `tan(x)^4/(tan(x)^2+1)^2`.
- **in terms of sin/cos/tan**: the result has `ln` with trig below a bar and is bigger
  (`2578-2579`).
- **any form whose text is long** (>= 90 chars) with no top-level `+` or `-`, which cannot be
  wrapped (`long_one_term`, `2132-2143,2600-2601`).
- **unevaluated results**: when the original text contains `sum(`, `integrate(` or `limit(` there
  are no forms at all (`2609-2619`).

**Post-processing of an offered form:**
- `sec_only` if the original had sec, csc or cot (factored/expanded) (`2550-2551`)
- `normal_args` (`2552-2553`)
- `positive_first` (`2592-2593`)
- printed, then `textbook()` + `textbook_constants()` (`2595-2597`)
- for decimal forms, `.0` is stripped from `2.0cos(x)` (`no_point_zero`, `2105-2116,2598-2599`)

### 6.5 Cycling and duplicate removal (`answer_forms_next`, `answer.cc:2628-2658`)

- Position 0 is the original. Each F4 moves to the next offered form that is **new in this
  round**.
- A form is not new when its text uses the same multiset of characters as the current text or
  any text shown earlier in the round (`reordered`, `2094-2104`). So `2cos(x)sin(x)` equals
  `2sin(x)cos(x)`. Decimal forms are also compared with `.0` removed.
- After the last form the cycle returns to the original and a new round starts.
- While a form is computed the status says `computing...` (`main.cc:590`).
- CLEAR or ON, or running out of memory, returns to the original. The status shows
  `Out of memory` in the OOM case (`main.cc:607-611,624`).
- The output line's text is **replaced** by the form's text (`console_replace_result`,
  `console.cc:1539-1560`). Ans then uses the form shown.

---

## 7. Messages instead of a result: exact strings

FlowCE's own message strings (`msg` replaces the result; `main.cc:1245-1246`):

| situation | exact text | source |
|---|---|---|
| two-sided limit with different one-sided limits, or giac gives unsigned ∞ | `does not exist: <L> from the left, <R> from the right` (each side cut at 40 chars, giac's print, e.g. `-infinity`, `+infinity`, `-1`) | `answer.cc:1220-1263` |
| limit oscillates (giac `bounded_function`), when `limit(` was typed | `no limit (it oscillates)` | `answer.cc:3117-3118` |
| infinite sum fails the n-th term test, or oscillates, when `sum(` was typed | `diverges (the terms do not go to 0)` | `answer.cc:1505-1507,3118` |
| definite integral, giac returns `undef`, a bound is ±∞ | `diverges (the improper integral does not converge)` | `main.cc:1227-1232` |
| definite integral, giac returns `undef`, finite bounds | `diverges (the integrand is unbounded on the interval)` | `main.cc:1227-1232` |
| solve or system with no solutions (empty list) | `no solution` | `answer.cc:3222-3233` |
| ON pressed during eval | `Interrupted` | `main.cc:1213,1221` |
| memory ran out (eval, simplify or F4) | `Out of memory` | `main.cc:1213,1221,1233-1235,624` |
| no memory for the input buffer | `Memory full` (a confirm box) | `main.cc:1116` |
| result too large to print (`taille >= 256`) | `Done` | `main.cc:1259-1260` |
| `f(x):=...` or `f(x)=...` defined | `<f(x)> defined` (the text before `:=`) | `main.cc:1238-1242` |
| plot result | `Graphic object` | `main.cc:1256` |
| busy (> 0.4 s) | `Calculating` with 3 animated dots | `focus.cc:751-784` |
| while evaluating (status bar) | `ON or clear: stop` | `main.cc:491` |
| graph key without a usable expression | `Type a function of x first` / `Not a function of x` | `console.cc:2401` |
| invalid store target | `Invalid variable name` | `console.cc:821` |

Divergent **series** are not always a message:
- Rational-term sums with degree gap <= 1, such as Σ1/n, return `+infinity` or `-infinity`,
  drawn `+∞` (`answer.cc:1516-1517`).
- So do p-series with p <= 1 (`answer.cc:1623-1624`) and integral-test divergence
  (`answer.cc:1570-1571`).

Convergent sums with no closed form return a decimal: 200 terms plus the tail integral, or the
averaged partial sums for an alternating series (`answer.cc:1530-1545,1557-1584`).

**giac's own errors** arrive as strings beginning `// `, e.g.
`// <fn> Error: Bad Argument Type`, `// Error: Bad Argument Value`,
`// Error: Invalid dimension` (`giac/kgen.cc:570-637`). The print form has the quotes: `"// ..."`.

**How messages are drawn** (`focus.cc:96-108,131-150,195-204`). A result line is treated as a
message when it matches any of these:
- it is empty
- it starts with `"//`
- it contains a space followed by a letter (not after a comma)
- it is a single capitalized word of 3+ letters

Message display:
- The leading `"`, the `//` and the spaces after it are stripped.
- History: drawn right-aligned in the 10 px text face, secondary color. Text wider than 280 px is
  cut with `...`.
- Hero: word-wrapped and centered on up to 4 lines of 296 px (12 px face), secondary color.
- Messages contain spaces, so they never become Ans (§0 step 1).

**Unevaluated results are not messages.** giac's leftover `integrate(f,x)`, `sum(...)` and
`limit(...)` print as calls and are drawn with the integral, Σ and lim templates (§9.4). An
indefinite one also gets `+ C` (§3).

**Numeric fallbacks:**
- **Hard definite integrals.** Constant bounds and a non-quadratic radicand with no
  u-substitution are integrated numerically (`numeric_hard_integrals`, `answer.cc:1707-1732`,
  substitution `x = a+(b-a)sin²(πt/2)`). The answer is a bare decimal with the chip `decimal`.
- **By-parts definite integrals** whose antiderivative disagrees with quadrature also fall back
  to the numeric value (`answer.cc:2816-2839`).
- **FlowCE has no numeric fallback for limits.** An unevaluated limit is shown as the lim
  template.

**cas-evo:** limits fall back to a numeric estimate labelled `≈`. Definite integrals label their
numeric fallback with `≈`.

---

## 8. solve() output

**Implicit solve** (`answer.cc:1734-1749,3063-3070`). An equation typed alone with exactly one
unassigned identifier (excluding pi, ∞ and undef) is turned into `solve(eq, x)`. A plain `x=5`
stores into `x` instead (`equaltosto`). An exception: `x=(-x/2)^2` has x on both sides and is
solved. `solve(expr)` with no variable solves for `x`.

**Decimal coefficients** are solved exactly and then `evalf`'d (`answer.cc:3080-3083`).

**Single variable** (`solutions_as_equations`, `answer.cc:1991-2000`). Each solution `v` becomes
`x=v`. Entries that contain x, such as inequality solutions, are kept as they are. One solution
gives `x=2`. Several give a sequence printed `x=-sqrt(2),x=sqrt(2)`, with no brackets and no ±.

**Systems** (`system_as_equations`, `answer.cc:2001-2020`). `solve([x+y=3,x-y=1],[x,y])` gives
`[[2,1]]`, shown `x=2,y=1`. Several solutions give `[x=..,y=..],[x=..,y=..]`.

**Text clean-up** (`answer.cc:3240-3243`):
- giac's parentheses around a whole right side are removed: `x=(-sqrt(2))` becomes
  `x=-sqrt(2)` (`strip_equation_parens`, `answer.cc:1974-1989`).
- Inequalities: `((x>-2) and (x<2))` becomes `-2<x<2`, also with `<=` or `>=`
  (`chain_inequalities`, `answer.cc:2022-2068`).
- A printed `list[...]` is shown as `[...]` (`focus.cc:33`).

**2D look.**
- `=` has `opgap` space on each side (`mathinput.cc:28,663`).
- `,` is followed by half an advance of space (`mathinput.cc:664`).
- So the answer reads `x = −√2, x = √2`.
- `<=`, `>=`, `!=` are drawn `≤ ≥ ≠` (`ui_math.cc:34`).

---

## 9. 2D layout rules (`mathinput.cc` + `ui_math.cc`)

Results are laid out from their 1D text by `mi_build` with flag `MI_F_IMPLDOT`
(`focus.cc:181,206,407`). History inputs use `MI_F_TIDY`. Coordinates: y grows down and the
baseline is y=0.

### 9.1 Sizes and metrics

- Size levels (px): `34, 28, 24, 20, 17, 14, 12, 10` (`ui_math.cc:12`). A **script** (exponent,
  bound, index) uses level+2, clamped to the smallest (`ui_math.cc:16`).
- Per level, with `s` the pixel size (`ui_math.cc:84-106`):

  | metric | value |
  |---|---|
  | spacing advance `adv` | 50% of s |
  | opgap | 22% of s |
  | fraction bar | 2 px if s >= 26, else 1 |
  | gap | max(2, 13% of s) |
  | radical sign width `rad` | 56% of s |
  | integral sign width `isw` | 50% of s |
  | stroke | 2 / 1.5 / 1.125 px for s >= 26 / >= 17 / smaller (`ui_math.cc:192`) |

  Glyph widths are proportional (`wf`).
- Fixed-width fallback metrics: big `{adv 8, asc 14, desc 4}`, small `{6, 9, 3}`, opgap 2, bar 1,
  gap 2, rad 6, isw 6 (`mathinput.cc:997`, `mathinput.h:20-23`).
- **Math axis** = `asc/3` above the baseline. Fraction bars and d/dx sit on it
  (`mathinput.cc:26,526`).
- **Fitting** (`ui_math_fit`, `ui_math.cc:108-122`) uses the largest level <= `maxlv` whose
  layout fits w×h, or the smallest level. Width is assumed to scale linearly, so the search jumps
  close to the estimate.

  | place | max level | box |
  |---|---|---|
  | hero result | 0 (34 px) | 292 px wide (256 with `+ C`) |
  | history result | 3 (20 px) | 292×64 |
  | history input | 5 | 286×34 |

  (`focus.cc:40-41,181,407`)

### 9.2 Text and operators

- **Styles** (`mathinput.cc:464-467`, `ui_math.cc:1-3,19-27`):
  - variable names are *italic*
  - numbers and function names are upright
  - a one-letter name before `(` stays italic: `f(x)`, `x(x+1)`
  - uppercase letters exist only in the italic face, digits only in the upright face
- **Glyph substitutions** (`ui_math.cc:30-56`):

  | text | glyph |
  |---|---|
  | `-` | − (U+2212) |
  | `<=` | ≤ |
  | `>=` | ≥ |
  | `!=` | ≠ |
  | `->` and `=>` | → |
  | `pi` | π |
  | `oo`, `infinity`, `inf` | ∞ |
  | `theta` | θ (italic) |
  | `\x1e` | → |

- **Precedence**, low to high (`mathinput.cc:15-17,175-184`):
  1. `;` `,`
  2. `:=` `=>` `->`
  3. `=` `==` `!=` `<` `>` `<=` `>=`
  4. binary `+` `-`
  5. `*` `/` and implicit multiplication
  6. prefix `-` `+` `!` `'`
  7. `^` (right associative)
  8. postfix `!` `'`
  9. primary

  Levels 1-5 are flat rows.
- **Spacing** (`mathinput.cc:28-29,657-666,779`):
  - binary `+ - = == != < > <= >= := => ->` get `opgap` on each side
  - `,` and `;` are followed by `adv/2`
  - a blank is `adv/2`
- **Multiplication** `*` is a centered dot. Its box is `adv/2+2` wide and the dot sits at
  `y = -asc/4-1`. The dot is 3 px when s >= 24, else 2 px (`ui_math.cc:195`). With
  `MI_F_IMPLDOT` (results) the dot is **hidden** when a letter or `(` follows, leaving a 1 px
  gap: `2x`, `xy`, `2(x+1)`, `sin(x)cos(x)`. Before a digit the dot stays: `2·3`
  (`mathinput.cc:24-26,468-473`). Typed implicit multiplication is a 1 px gap
  (`mathinput.cc:677,812`).

### 9.3 Fractions (`mathinput.cc:405-424,532-546`)

- **Numerator** = the whole current level-5 term, from the last `+ - = ,` at that level up to the
  `/`. **Denominator** = the next factor only: prefix ops, primary, postfix and `^`. So `a*b/c*d`
  is `(ab/c)·d`. This is why the string passes rewrite `1/6*x^3` to `x^3/6` (§10).
- **Bar**: width `max(num.w, den.w) + 2·gap`, at `y = -axis`, thickness `bar`. Both parts are
  centered. The numerator's descent bottom is at `-axis-gap`. The denominator's ascent top is at
  `-axis+bar+gap`. Both stay **the same size** as the parent (no shrinking).
- **Leading minus**: with proportional fonts, `-a/b` draws the minus *before* the bar, not in the
  numerator (`mathinput.cc:409-413`).
- **In a script** (an exponent): a fraction is drawn inline as `a/b` (`mathinput.cc:534-541`). So
  `x^(1/3)` shows a small `1/3` exponent.
- **Hidden parentheses**: an operand of `/` or the exponent of `^` that is exactly `( … )` is
  drawn without its parentheses (`mathinput.cc:32,219,379,419`). In `MI_F_TIDY` a doubled group
  `((x+1))` loses both pairs (`mathinput.cc:220-226`).

### 9.4 Other constructs (`mathinput.cc:34-42,274-277,524-641`)

The special calls below must have **exactly** the listed argument count. Any other count is drawn
as a plain call (e.g. 4-argument one-sided `limit`).

- **Power `a^b`** (`547-554`):
  - `b` is in the script font
  - its baseline is at `-(0.45·base.asc) - b.desc`, so the exponent's bottom sits at 45% of the
    base's ascent
  - there is a gap of `max(1, adv/10)` between base and exponent
  - `sin^2(x)` style is recognized for sin cos tan sec csc cot sinh cosh tanh ln log
    (`mathinput.cc:340-346,356`)
- **`exp(a)`**: an italic `e` with exponent `a`, same rule.
- **`sqrt(a)`** (`555-562`, drawing `ui_math.cc:197-204`):
  - The sign is `rad` wide. The content starts at `rad+1`. Total width = `content + rad + 2`.
  - The sign spans from `gap` above the content's ascent to the content's descent.
  - It is drawn as four strokes:
    1. a short tick, from 26% to 34% of the size above the bottom (thin)
    2. a heavy down-stroke to `(rad·9/16, bottom)`
    3. an up-stroke to the top right
    4. an overbar of thickness `bar` running to the right edge
- **`surd(a,n)`**: a radical with index `n` in the script font, up and left of the sign. The
  overhang is `max(0, n.w - rad/2)`. (giac results use `x^(1/3)`, so this is mostly for input.)
- **`abs(a)`** (`563-569`): vertical bars with box width `max(1, adv/2-1)`. Each bar is 1-2 px
  (`ui_math.cc:247`) and as tall as the content. So `ln(abs(x))` draws as `ln(|x|)`.
- **Grouping `( [ {`**: delimiter boxes `adv/2+1` wide, as tall as the content (at least the
  font). The drawn shape depends on height (`ui_math.cc:218-246`):
  - up to 115% of the font height: the font glyph
  - up to 3× the glyph height: the glyph stretched
  - taller: two cubic Béziers

  Brackets are drawn as lines and braces as a polyline. A call `name(args)` is the upright name,
  parentheses, and arguments separated by `,` plus `adv/2` (`mathinput.cc:672-684,800-820`).
- **`integrate(f,x)` / `integrate(f,x,a,b)`** (also `int`) (`570-586`):
  - The sign is `isw` wide and spans `gap` above and below the content.
  - It is drawn as an elongated S: a top hook Bézier, a slanted thick stroke, and a bottom hook
    Bézier (`ui_math.cc:205-212`).
  - Bounds use the script font, at `x = isw+1`, with `u = (desc-asc)/2`:
    - the lower bound baseline is `max(desc+gap-lo.desc, u+1+lo.asc)`
    - the upper bound baseline is `min(-asc-gap+hi.asc, u-1-hi.desc)`
  - Then the integrand, `gap`, an upright `d`, the variable, and a trailing 2 px.
- **`diff(f,x)`** (`587-600`): a fraction `d / dx` on the axis. The bar width is
  `d.w + x.w + 2·gap`. Then `f`, which gets visible parentheses if it is a row with a top-level
  operator or comma (`needp`, `487-492`).
- **`sum(f,k,a,b)`** (`601-613`, drawing `ui_math.cc:213-217`):
  - Σ is `2·asc` tall, 85% of the size wide, centered on the axis.
  - `k=a` sits below in the script font. `b` sits above.
  - The body starts at `column width + 2`.
  - Σ is drawn as a polyline: top bar, a diagonal in to 55% of the width, a diagonal back, and a
    bottom bar.
- **`limit(f,x,a)`** (`628-639`): upright `lim`, with `x→a` in the script font below it. The body
  starts `adv/2` after the column.
- **`series(f,x,a,n)`** (`614-627`): upright `taylor`, with `x→a deg n` in the script font below.
- **Robustness limits** (`mathinput.cc:22-24,67`). Any of the following draws the rest as plain
  text:
  - nesting deeper than 24
  - more than about 176 nodes
  - more than about 384 ops
  - layout depth over 52

### 9.5 Placement, wrapping and overflow

- **History**: results are right-aligned 12 px from the edge. A result too wide even at 10 px
  shows its **end**, clipped, with `...` at the left (`focus.cc:193-225`).
- **Hero**: centered. A result is wrapped when it is wider than the box, or would need level >= 5
  (`focus.cc:302-357,410-418`). Wrapping rules:
  - cut only at top-level `+` and `-` that do not follow one of `^ * / ( e = ,`
  - pack greedily into up to **6 lines** at one common level, trying levels 3..max
  - lines after the first are indented 10 px
  - `+ C` goes after the last line
- **Colors**: ink `UC_INK` for results; `UC_SUB` for inputs, messages, `+ C` and `≈`; `UC_ACC` for
  selection and the chip. Themes Paper and Night (`focus.h:66-67`).

---

## 10. String passes on the printed answer (`textbook`, `answer.cc:1803-1971`)

Pass 1 runs only when the text has `/`, `order_size(` or `exp(1)` and is < 1024 chars. It splits
the text into top-level terms at `+ - , =`. A `+` or `-` right after one of `^ * / ( e =`, or a
`,`, is not a split (so exponents and `1e-5` survive). Inside brackets nothing changes. Then:

| rule | example in | example out |
|---|---|---|
| `p/q*m` becomes `p*m/q` | `1/6*x^3`, `3/40*x^5` | `x^3/6`, `3*x^5/40` |
| `p/q/m` becomes `p/(q*m)` | `1/8/tan(2*x^4)` | `1/(8*tan(2*x^4))` |
| `m*order_size(v)` becomes `O(m)`; a bare `order_size` becomes `O(1)` | `x-1/6*x^3+x^6*order_size(x)` | `x-x^3/6+O(x^6)` |
| `exp(1)` becomes `e` (not inside longer names) | `exp(1)` | `e` |

Pass 2: `textbook_constants` turns `c_0` into `C1` (§3).

Solution strings also get the parenthesis strip and inequality chaining (§8). Long integer-
denominator polynomials are expanded (§1.4).

---

## 11. Rendering notes per item

- **Fractions**: rationals print as `p/q` and draw stacked. A negative fraction has its minus
  before the bar. A coefficient goes into the numerator: `3x^2/2`. There are no mixed numbers.
- **Radicals**:
  - giac simplifies to `k*sqrt(n)`, drawn `k√n`
  - `sqrt(2)/2` draws as a stacked fraction
  - roots other than square roots stay powers, `x^(2/3)`, with an inline small fraction exponent
  - with a variable exponent, giac's `x^(1/3)*x` is merged to `x^(4/3)` (§1.2)
- **pi**: `π`. `2*pi` draws `2π` and `pi/2` draws `π` over `2`. Ordering: number, then π, then
  variables (`2πx`).
- **e**: §4. `e^x` sorts before other functions: `e^x cos(x)`.
- **i**: `a+bi` order, `i` italic, implicit-multiplication gap.
- **Negative signs**: §1.1 and §1.3. Leading terms are positive in 2-term sums. Polynomials keep
  descending order even with a negative lead. The minus sits outside quotients. The minus is
  drawn as U+2212.
- **abs**: `|…|` bars; `x^2*sign(x)` becomes `x|x|`.
- **Piecewise**: **FlowCE has no piecewise rendering.** A giac `piecewise(...)` or `when(...)`
  result would draw as an ordinary call (`mathinput.cc:155` only notes that `piecewise` is a
  name). **cas-evo:** we design our own (a brace plus a case list would fit the existing
  `MI_LBRACE` primitive).
- **± solution lists**: **FlowCE never prints ±.** Each root is a separate `x=…` joined by
  commas (§8).
- **Unevaluated `integrate`, `sum`, `limit`**: drawn with the ∫, Σ and lim templates (§9.4). F4
  forms are disabled (§6.4).
- **Lists**: `list[a,b]` is shown `[a,b]`.

---

## 12. Implications for cas-evo

1. **Store the answer as 1D text in our own input language.** Render it with the same 2D
   layout engine as input; that engine is the future 2D editor. Make `+ C`, `≈ value` and the
   form chip view decorations keyed to the answer text. FlowCE does this with
   `console_approx_for`.
2. **Split formatting in two:**
   - a **tree pass** for order and signs (the `positive_first` rules above)
   - a small **string or print-time pass**, `p/q*m -> p*m/q` and friends

   The cheaper option is to fold the `textbook()` rules into our printer: print a rational
   coefficient times `m` as `p*m/q` directly. FlowCE needs a string pass only because giac's
   printer is fixed.
3. **Implement the ordering rules data-driven.** Factor rank, the trig order, the polynomial
   key, and descending degree become sort keys over our flat n-ary lists. The insertion sorts
   are stable, and stability matters. Note: Python's `sorted(key=)` costs a frame per key call.
   Precompute the keys into tuples and sort plain tuples.
4. **F4** is a list of `(name, op, offer-predicate)` entries over the *original* answer. Each is
   computed lazily, cached, and deduplicated by character multiset. The three orders (number,
   trig, plain) are data. Each form must poll for cancel.
5. **Keep the message strings as data.** Reuse FlowCE's wording where it fits: `does not exist:
   L from the left, R from the right`, `diverges (...)`, `no solution`, `Interrupted`,
   `Out of memory`, `Done`. Our extra decisions on top:
   - `≈` labels for numeric fallbacks
   - 10-digit decimals with the 1e10 / 1e-4 scientific thresholds
   - an explicit piecewise layout
6. **The 2D engine fits a small budget.** It is a node pool, measure (bottom up), place (top
   down) and a flat display list, all with fixed metric formulas (§9.1). Its recursion (parser,
   measure, place) must become explicit-stack. FlowCE's own caps (24 nesting levels, about 176
   nodes, about 400 ops, fall back to plain text) are a good model for our heap limits.
