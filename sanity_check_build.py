"""Verify a multimap build against stock.
Usage: python sanity_check_build.py [stock.ori] [multimap.bin]"""
import sys
ORIG = sys.argv[1] if len(sys.argv) > 1 else "stock_382083.ori"
MOD  = sys.argv[2] if len(sys.argv) > 2 else "03G906021KH_382083_MULTIMAP_v1.2.bin"
TARGET = 0xD01FE500
REGIONS = [(0x040000, 0x17FFFF), (0x180000, 0x1BFFFF), (0x1C0000, 0x1FDFFF)]
# expected change blocks: (start, length, description)
EXPECTED = [(0x09B2A8, 4, "hook"), (0x17FFFC, 4, "csum region 1"),
            (0x1EB000, 0xD4, "slot 1"), (0x1EC000, 0xD4, "slot 2"),
            (0x1FDFFC, 4, "csum region 3"), (0x1FE200, 184, "thunk")]

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
if stray: print("  first stray:", hex(stray[0])); ok = False
for s, l, name in EXPECTED:
    n = sum(1 for i in range(s, s + l) if o[i] != m[i])
    print(f"  {name:14s} {s:#08x} +{l:#x}: {n} bytes differ")
hook = m[0x9B2A8:0x9B2AC]
lk = hook[3] & 1
print("hook", hook.hex().upper(), "-> plain b" if (hook[0] == 0x48 and not lk) else "-> NOT a plain b (LK set or wrong opcode)")
ok &= hook[0] == 0x48 and not lk
print("slot 1 == stock map:", m[0x1EB000:0x1EB0D4] == o[0x1D16F6:0x1D16F6+0xD4],
      "| slot 2:", m[0x1EC000:0x1EC0D4] == o[0x1D16F6:0x1D16F6+0xD4])
for a, b in REGIONS:
    s = get_sum(m, a, b); good = s == TARGET; ok &= good
    print(f"checksum {a:#08x}-{b:#08x}: {s:#010x} [{'OK' if good else 'FAIL'}]")
for off in (0x1BFF74, 0x1FDF78):
    same = o[off:off+4] == m[off:off+4]
    print(f"inner const {off:#08x}: {m[off:off+4].hex().upper()} [{'unchanged' if same else 'CHANGED'}]")
print("\nRESULT:", "PASS" if ok else "FAIL")
