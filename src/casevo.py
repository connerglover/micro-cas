# Module-level entry loop: no main wrapper consumes an EVO Python frame.
import ti_system as TS
import node as K
import alg as A
import parse as P
import printer as PR
import run as R
import draw as D
import ui as U

U.boot()
while True:
    try:
        k = TS.wait_key()
        a = U.key(k)
        if a is U.QUIT:
            break
        if a is not None:
            r = R.go(a)
            U.show(a, r)
    except MemoryError:
        U.panic(0)
    except KeyboardInterrupt:
        U.panic(1)
    except RuntimeError:
        U.panic(2)
    except Exception:
        U.panic(3)
