# Key-code probe: prints each key's code. Press the same key twice in a row to stop.
import ti_system as ts

print("Same key twice = stop")
last = None
while True:
    k = ts.wait_key()
    print(k, end=" ")
    if k == last:
        break
    last = k
print()
