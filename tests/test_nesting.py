"""T1 end-to-end nesting uses the fixed trampoline depth, not Python recursion."""
import pytest
import cascheck as C
import node as K
import run as R


@pytest.mark.parametrize('command', ['expand', 'factor', 'together'])
def test_t1_command_nesting(command, evodepth):
    peaks = []
    for depth in (1, 8, 31):  # outer command consumes the 32nd parser nesting slot
        C.fresh()
        expr = 'x'
        for _ in range(depth):
            expr = 'sin(' + expr + ')'
        record, peak, _ = evodepth.measure(R.go, ('eval', command + '(' + expr + ')'))
        assert record[0] == 'ans', record
        assert K.NN == K.BASE
        peaks.append(peak)
    assert len(set(peaks)) == 1, peaks
