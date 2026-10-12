# Module-level entry loop: no main wrapper consumes an EVO Python frame. Only the UI loads
# here; U.engine() imports the engine on first use (docs/notes/FASTBOOT.md).
import time
T0 = None           # the boot clock: the same source as ui.clock()
if hasattr(time, 'monotonic'):
    T0 = time.monotonic()
elif hasattr(time, 'ticks_ms'):
    T0 = time.ticks_ms()
import ti_system as TS
import ui as U

R = None            #@lazy run
U.boot(T0)
while True:
    try:
        k = TS.wait_key()
        a = U.key(k)
        if a is U.QUIT:
            break
        if a is not None:
            R = U.engine()
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
