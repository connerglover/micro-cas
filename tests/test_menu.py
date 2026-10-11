"""Modal menus use real keys and preserve session state until local confirmation."""
import pytest
import ti_system as TS
import run as R
import cascheck as C


@pytest.fixture(autouse=True)
def session():
    C.fresh()


def menu(kind, keys, command=''):
    m = R.need('menu')
    TS.load(keys)
    return m.open(kind, '', 0, command)


def test_test_picker():
    assert menu('test', [93])[0] == '!='
    assert menu('test', [26, 26, 105])[0] == '<'
    assert menu('test', [45]) is None


def test_calculus_template():
    result = menu('calculus', [105])
    assert result[0].startswith('diff(') and result[1]
    assert result[0][result[2]] in ',)'


def test_recall_ans():
    C.answer('2/3')
    assert menu('recall', [105])[0] == 'ans()'


def test_setup_angle_and_theme():
    menu('setup', [105, 34, 105, 45])
    assert R.SET == {'deg': 1, 'theme': 1}


def test_help_example():
    result = menu('help', [105], 'diff')
    assert result[0].startswith('diff(') and not result[1]


def test_catalog_every_command_and_macro():
    cat = R.need('cat').CAT
    names = [row[0].split('(')[0] for row in cat]
    assert set(R.CMDS) | set(R.MACROS) <= set(names)
    assert all(len(row) == 5 and all(row) for row in cat)
