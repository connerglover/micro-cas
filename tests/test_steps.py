"""Step-by-step working (docs/notes/STEPS.md).

A steps job parses a history entry again and explains its last command; it records nothing
while ordinary commands run and changes nothing in the session. Every line the walkers show is
checked here against the engine: a derivative line by evaluating both sides, an integral line
by differentiating them.
"""
import pytest

import cascheck as C
import keyscript as KS
import node as K
import run as R
import sdiff as SD


NONE = 'No steps for this one'


@pytest.fixture(autouse=True)
def fresh():
    C.fresh()
    del R.STEPS[:]


def steps(text):
    """The (title, line) steps of text's working, or the message when there are none."""
    C.answer(text)
    rec = R.go(('steps', len(R.HIST) - 1))
    assert K.NN == K.BASE
    if rec[0] != 'ans':
        assert R.STEPS == []
        return rec[1]
    out = R.STEPS[1:]
    del R.STEPS[:]
    return out


def titles(text):
    return [s[0] for s in steps(text)]


def split(line):
    """lhs, rhs of a step line: cut at the first '=' outside parentheses."""
    d = 0
    for j, ch in enumerate(line):
        d += (ch == '(') - (ch == ')')
        if ch == '=' and not d:
            return line[:j], line[j + 1:]
    raise AssertionError(line)


DIFFS = ['diff(x^2*sin(x),x)', 'diff(sin(x^2)/x,x)', 'diff(3*x^4-2*x+7,x)',
         'diff(e^(2*x)*ln(x),x)', 'diff(sqrt(x^2+1),x)', 'diff(x^x,x)', 'diff(2^x,x)',
         'diff(tan(3*x)^2,x)', 'diff(x*e^x*cos(x),x)', 'diff(ln(x)/(x^2+1),x)',
         'diff(atan(x/2),x)', 'diff(a*x^3+b,x)', 'diff(1/sin(x),x)']
INTS = ['integrate(x^2+3*x,x)', 'integrate(x*cos(x^2),x)', 'integrate(x*e^x,x)',
        'integrate(1/(x^2-1),x)', 'integrate(sin(x)^2,x)', 'integrate(ln(x),x)',
        'integrate(2*x/(x^2+1),x)', 'integrate((x+1)/(x^2-x),x)', 'integrate(5,x)',
        'integrate(x^3+3*x^2-sin(x)+e^x+1/x,x)', 'integrate(e^(3*x)*sin(x),x)',
        'integrate(sqrt(4*x^2+1),x)', 'integrate(cos(x)*e^(sin(x)),x)']


@pytest.mark.parametrize('text', DIFFS)
def test_every_derivative_line_is_an_identity(text):
    got = steps(text)
    assert type(got) is list and len(got) >= 2
    assert got[-1][0] == 'Answer'
    for title, line in got:
        lhs, rhs = split(line)
        assert C.answer('simplify(' + lhs + '-(' + rhs + '))') == '0', (title, line)


@pytest.mark.parametrize('text', INTS)
def test_every_integral_line_is_an_identity(text):
    got = steps(text)
    assert type(got) is list and len(got) >= 2
    assert got[-1][0] == 'Answer' and got[-1][1].endswith('+C')
    for title, line in got:
        lhs, rhs = split(line)
        if title == 'Substitution':             # u=g(x): a definition, not an identity
            assert lhs in ('u', 'w', 't')
            continue
        if title == 'Partial fractions':        # the integrand, rewritten
            assert C.answer('simplify(' + lhs + '-(' + rhs + '))') == '0', line
            continue
        if title == 'Rewrite the integral':     # checked by the 'Substitute back' line
            continue
        if rhs.endswith('+C'):
            rhs = rhs[:-2]
        v = lhs[lhs.rindex(',') + 1:-1]
        delta = 'diff(' + lhs + '-(' + rhs + '),' + v + ')'
        assert C.answer('simplify(' + delta + ')') == '0', (title, line)


def test_derivative_rules_are_named():
    assert titles('diff(x^2*sin(x),x)') == ['Product rule', 'Power rule', 'Known derivative',
                                            'Answer']
    assert titles('diff(sin(x^2)/x,x)')[:2] == ['Quotient rule', 'Chain rule']
    assert titles('diff(3*x^4-2*x+7,x)') == ['Sum rule', 'Power rule', 'Answer']
    assert titles('diff(x^5,x,3)') == ['Differentiate', 'Differentiate again',
                                       'Differentiate again', 'Answer']


def test_integral_methods_are_named():
    assert titles('integrate(x*cos(x^2),x)') == [
        'Substitution', 'Rewrite the integral', 'Constant multiple', 'Known integral',
        'Substitute back', 'Answer']
    assert titles('integrate(x*e^x,x)') == ['Integration by parts', 'Answer']
    assert 'Partial fractions' in titles('integrate((x+1)/(x^2-x),x)')
    assert titles('integrate(sin(x)^2,x)') == ['Trig identities', 'Answer']


def test_definite_integral_ends_at_the_entry_answer():
    got = steps('integrate(x^2,x,0,1)')
    assert got == [('Power rule', 'integrate(x^2,x)=x^3/3'),
                   ('Evaluate at the bounds', 'integrate(x^2,x,0,1)=1/3')]


def test_macros_explain_their_integral():
    got = steps('arclen(x^2,x,0,1)')
    assert got[-1][0] == 'Evaluate at the bounds'
    assert got[-1][1].startswith('integrate(sqrt(4*x^2+1),x,0,1)=')


def test_solve_factor_quadratic_and_linear():
    assert steps('solve(x^2-5*x+6=0,x)') == [
        ('Factor', 'x^2-5*x+6=(x-2)*(x-3)'), ('A factor is zero', 'x-3=0'),
        ('A factor is zero', 'x-2=0'), ('Solve each equation', 'x=2,x=3')]
    got = steps('solve(x^2+x-1=0,x)')
    assert got == [('Standard form', 'x^2+x-1=0'), ('Read off a, b, c', 'a=1,b=1,c=-1'),
                   ('Quadratic formula', 'x=-(b-sqrt(b^2-4*a*c))/(2*a)'),
                   ('Discriminant', 'b^2-4*a*c=5'), ('With these numbers', 'x=(sqrt(5)-1)/2'),
                   ('And with the other sign', 'x=-(sqrt(5)+1)/2'),
                   ('Simplify', 'x=-(sqrt(5)+1)/2,x=(sqrt(5)-1)/2')]
    assert steps('solve(2*x+3=7,x)') == [
        ('Move all terms to one side', '2*x-4=0'), ('Isolate the variable term', '2*x=4'),
        ('Divide both sides', 'x=2')]
    assert steps('solve(1/x=2,x)')[1] == ('Multiply by the denominator', '2*x-1=0')


def test_a_lone_equation_is_solved_and_explained():
    got = steps('x^2=4')
    assert got[0] == ('Move all terms to one side', 'x^2-4=0')
    assert got[-1] == ('Solve each equation', 'x=-2,x=2')


def test_limits_direct_and_lhopital():
    assert steps('limit(x^2+1,x,2)') == [('Direct substitution', 'x=2'),
                                         ('Evaluate', 'limit(x^2+1,x,2)=5')]
    got = steps('limit((1-cos(x))/x^2,x,0)')
    assert [s[0] for s in got] == ["L'Hopital's rule: 0/0", "L'Hopital's rule: 0/0",
                                   'Direct substitution', 'Evaluate']
    assert got[-1][1].endswith('=1/2')
    assert titles('limit(e^x/x^2,x,oo)')[0] == "L'Hopital's rule: oo/oo"


@pytest.mark.parametrize('text', ['integrate(e^(-x^2),x)', 'solve(sin(x)=0,x)', 'factor(x^2-1)',
                                  '2+3', 'solve([x+y=2,x-y=0],[x,y])', 'limit(abs(x)/x,x,0,1)',
                                  'taylor(sin(x),x,3)'])
def test_no_steps_is_a_message(text):
    assert steps(text) == NONE


def test_a_steps_job_leaves_the_session_alone():
    C.answer('a=3')
    C.answer('diff(a*x^2,x)')
    hist = [list(e) for e in R.HIST]
    ans, vs = R.ANS, dict(R.VARS)
    rec = R.go(('steps', 1))
    assert rec[0] == 'ans' and R.STEPS[0] == 'diff'
    assert [list(e) for e in R.HIST] == hist and R.ANS == ans and R.VARS == vs
    R.go(('eval', '1+1'))                       # the next command clears the working
    assert R.STEPS == []


def test_entries_that_would_run_twice_are_refused():
    C.answer('x^3')
    C.answer('diff(ans(),x)')
    assert R.go(('steps', 1)) == ('msg', NONE, None, 0)   # Ans has moved on
    R.go(('eval', 'f(x)=x^2'))
    assert R.go(('steps', 2))[0] == 'msg' and 'f' in R.FUNCS   # a definition: not run again
    R.go(('eval', 'purge(f)'))
    C.answer('f=5')
    assert R.go(('steps', 3))[0] == 'msg' and R.VARS['f'] == '5'  # nor a purge
    assert R.STEPS == [] and len(R.HIST) == 5


def test_the_first_steps_job_warms_up_once():
    C.answer('diff(x^2,x)')
    del R.WARM[:]
    C.answer('1+1')
    R.need('fact')                              # a lazy pack of an earlier command
    assert R.go(('steps', 0))[0] == 'ans' and R.WARM == [1]
    assert 'fact' not in R.LOADED               # the heap was emptied before the warm-up
    assert 'stepv' not in R.LOADED and 'menu' not in R.LOADED   # imported once, then let go
    R.need('fact')
    assert R.go(('steps', 0))[0] == 'ans' and R.WARM == [1]
    assert 'fact' in R.LOADED                   # only once a session


def test_the_walk_is_no_command_to_type():
    C.answer('diff(x^2,x)')
    assert R.go(('steps', 0))[0] == 'ans'
    assert '?' not in R.CMDS                    # the job's own registry entry is gone again
    assert R.go(('eval', '?(x^2,x)'))[0] == 'msg' and R.okname('steps')


def test_the_entry_mode_is_used_not_the_current_one():
    R.SET['deg'] = 1
    try:
        C.answer('diff(sin(x),x)')
    finally:
        R.SET['deg'] = 0
    rec = R.go(('steps', 0))
    assert rec[0] == 'ans'
    assert R.STEPS[-1][1] == 'diff(sin(x),x)=' + R.HIST[0][1]
    assert 'pi' in R.STEPS[-1][1]


def test_the_last_step_is_the_exact_answer_whatever_form_is_shown():
    C.answer('limit((1-cos(x))/x^2,x,0)')
    assert R.go(('form', 0))[1].startswith('0.5')       # F5: the decimal form
    assert R.go(('steps', 0))[0] == 'ans'               # the chain still ends at 1/2
    assert R.STEPS[-1] == ('Evaluate', 'limit(-(cos(x)-1)/x^2,x,0)=1/2')


def test_the_walk_is_bounded():
    text = 'diff(' + '+'.join('sin(%d*x)^%d' % (k, k) for k in range(2, 16)) + ',x)'
    got = steps(text)
    assert len(got) <= SD.MAXSTEPS + 2 and got[-1][0] == 'Answer'
    assert sum(len(s[1]) for s in got) <= 2400 and all(len(s[1]) <= 150 for s in got)


def test_cancel_and_failure_leave_no_working():
    C.answer('diff(x*cos(x^2),x)')
    assert R.go(('steps', 0))[0] == 'ans'       # a session's first steps job empties the heap
    M = R.need('sdiff')                         # of lazy packs (go): patch the copy after it
    m = M.MAXSTEPS
    M.MAXSTEPS = -1                             # a walk that explains nothing
    try:
        assert R.go(('steps', 0))[1] == NONE
    finally:
        M.MAXSTEPS = m
    assert R.STEPS == [] and K.NN == K.BASE
    assert R.go(('steps', 0))[0] == 'ans'       # and the next job works


# -- the screen ------------------------------------------------------------------------------

def test_the_hint_row_offers_steps():
    s = KS.run('diff(x^2,x){enter}{snap:a}{clear}{snap:b}')
    assert 'ENTER: steps' in s.snaps[0][1]
    assert 'ENTER: steps' not in s.snaps[1][1]          # CLEAR dismissed the answer
    s = KS.run('2+3{enter}{snap}')
    assert 'ENTER: steps' not in s.snaps[0][1]
    s = KS.run('integrate(x^2,x,0,1){enter}{snap}')     # beside the decimal line
    assert '~ 0.3333333333  ENTER: steps' in s.snaps[0][1]


def test_enter_on_the_empty_line_opens_the_steps():
    s = KS.run('diff(x^2*sin(x),x){enter}{enter}{snap:one}{right}{snap:two}{left}{snap:back}'
               '{clear}{snap:home}')
    one, two, back, home = [x[1] for x in s.snaps]
    assert one.startswith('Steps 1-1 of 4') and '1 Product rule' in one
    assert 'CLEAR: back' in one
    assert two.startswith('Steps 2-') and '2 Power rule' in two
    assert back == one
    assert 'ENTER: steps' in home and 'Alg Calc Trig More Forms' in home
    R = s.mods['run']
    assert R.STEPS == [] and len(R.HIST) == 1


def test_enter_still_repeats_an_entry_without_steps():
    s = KS.run('2+3{enter}{enter}')
    assert [e[0] for e in s.mods['run'].HIST] == ['2+3', '2+3']
    s = KS.run('diff(x^2,x){enter}{clear}{enter}')      # dismissed: ENTER repeats, as before
    assert len(s.mods['run'].HIST) == 2


def test_no_steps_is_shown_in_the_status_row():
    s = KS.run('integrate(e^(-x^2),x){enter}{enter}{snap}')
    assert s.snaps[0][1].split('\n')[0].startswith('RAD No steps for this one')
    assert len(s.mods['run'].HIST) == 1


def test_a_key_that_moves_nothing_repaints_nothing():
    s = KS.run('limit(x^2+1,x,2){enter}{enter}{snap:a}{down}{up}{left}{snap:b}')
    assert s.snaps[0][1] == s.snaps[1][1]
    assert s.snaps[0][2] == s.snaps[1][2]               # no draw call between the two
