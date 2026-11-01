"""Verify a multimap build against stock.
Usage: python sanity_check_build.py [stock.ori] [multimap.bin]"""
import sys

ORIG = sys.argv[1] if len(sys.argv) > 1 else "stock_382083.ori"
MOD  = sys.argv[2] if len(sys.argv) > 2 else "03G906021KH_MULTIMAP_ABA_CONSISTENT.bin"
TARGET = 0xD01FE500
REGIONS = [(0x040000, 0x17FFFF), (0x180000, 0x1BFFFF), (0x1C0000, 0x1FDFFF)]

EXPECTED = [
    (0x09B2A8, 4,    "hook 1"),
    (0x0B9738, 4,    "hook 2"),
    (0x17FFFC, 4,    "csum region 1"),
    (0x1EB000, 0xD4, "slot 1 (stage 1)"),
    (0x1EC000, 0xD4, "slot 2 (stock)"),
    (0x1FDFFC, 4,    "csum region 3"),
    (0x1FE200, 180,  "thunk 1"),
    (0x1FE400, 60,   "thunk 2"),
]

def get_sum(d, a, b):
    t = 0
    for i in range(a, b + 1, 4):
        t = (t + int.from_bytes(d[i:i+4], "big")) & 0xFFFFFFFF
    return t

o, m = open(ORIG, "rb").read(), open(MOD, "rb").read()
ok = len(o) == len(m) == 0x200000
print("size 2 MB:", ok)

changed = {i for i in range(len(o)) if o[i] != m[i]}
allowed = {i for s, l, _ in EXPECTED for i in range(s, s + l)}
stray = sorted(changed - allowed)
print("changed bytes:", len(changed), "| outside expected blocks:", len(stray))
if stray:
    print("  first stray:", hex(stray[0]))
    ok = False

for s, l, name in EXPECTED:
    n = sum(1 for i in range(s, s + l) if o[i] != m[i])
    print(f"  {name:20s} 0x{s:06X} +0x{l:X}: {n} bytes differ")

for hname, haddr in [("hook 1", 0x09B2A8), ("hook 2", 0x0B9738)]:
    hook = m[haddr:haddr+4]
    lk = hook[3] & 1
    good = hook[0] == 0x48 and not lk
    ok &= good
    print(f"  {hname:6s} 0x{haddr:06X}: {hook.hex().upper()} -> {'plain b' if good else 'BAD'}")

print("  slot 2 == stock map:", m[0x1EC000:0x1EC0D4] == o[0x1D16F6:0x1D16F6+0xD4])

for a, b in REGIONS:
    s = get_sum(m, a, b)
    good = s == TARGET
    ok &= good
    print(f"  checksum 0x{a:06X}-0x{b:06X}: 0x{s:08X} [{'OK' if good else 'FAIL'}]")

for off in (0x1BFF74, 0x1FDF78):
    same = o[off:off+4] == m[off:off+4]
    print(f"  inner const 0x{off:06X}: {m[off:off+4].hex().upper()} [{'unchanged' if same else 'CHANGED'}]")

print("\nRESULT:", "PASS" if ok else "FAIL")