"""Validate the Duration-map path end to end.

The duration code at 0xC6244 loads r15[289] (0x1DF054) and builds six map
pointers as base + {0x1A,0x10E,0x390,0x612,0x894,0xB16}. This script checks
that after the hooks those pointers land inside the slot's DOI clone and that
the clone bytes equal the stock maps.

Usage: python tools/validate_doi_path.py [stock.bin] [build.bin]
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.join(HERE, "..", "binaries", "Stock_Baseline.bin")
BUILD = os.path.join(HERE, "..", "binaries", "03G906021KH_MultiMap_v2.0.1.bin")

DOI_SRC = 0x1DF02E
DOI_S1, DOI_S2 = 0x1F4000, 0x1F6000
TABLE = 0x1F3F00
SITE = 0xC6244            # lwz r31, 0x484(r15)
KEY = 0xA5C35A3C
BLOCK_OFF = 0x1DF054 - DOI_SRC   # 0x26

DUR = [(0x1DF06E, 0x1A, 244), (0x1DF162, 0x10E, 642), (0x1DF3E4, 0x390, 642),
       (0x1DF666, 0x612, 642), (0x1DF8E8, 0x894, 642), (0x1DFB6A, 0xB16, 244)]

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    print(("[PASS] " if cond else "[FAIL] ") + name + (("  -- " + detail) if detail else ""))
    if cond:
        ok += 1
    else:
        fail += 1


def u32(b, a):
    return struct.unpack_from(">I", b, a)[0]


def slot_base(word):
    d = (word ^ KEY) & 0xFFFFFFFF
    tab = (DOI_SRC, DOI_S1, DOI_S2, DOI_SRC)
    return tab[d] if d in (1, 2) else tab[0]


def main():
    stock = open(sys.argv[1] if len(sys.argv) > 1 else STOCK, "rb").read()
    build = open(sys.argv[2] if len(sys.argv) > 2 else BUILD, "rb").read()

    # 1. the site is hooked and the stock instruction is the expected load
    w = u32(build, SITE)
    tgt = (SITE + ((w & 0x03FFFFFC) - (0x04000000 if w & 0x02000000 else 0))) & 0xFFFFFFFF
    check("0xC6244 is a plain b to its DOI thunk", (w >> 26) == 18, "-> %#x" % tgt)
    check("stock 0xC6244 is lwz r31,0x484(r15)",
          u32(stock, SITE) == ((32 << 26) | (31 << 21) | (15 << 16) | 0x484))

    # 2. the stock pointer arithmetic still builds the six Duration headers
    addrs = [0xC624C, 0xC6250, 0xC625C, 0xC6260, 0xC6264, 0xC6268]
    for (hdr, off, size), a in zip(DUR, addrs):
        w = u32(stock, a)
        got = (0x1DF054 + (w & 0xFFFF)) & 0xFFFFFFFF
        check("stock %#x builds %#x (+%#x)" % (a, hdr, off), got == hdr, "got %#x" % got)

    # 3. slot bases and the six pointers land inside the clone with stock bytes
    for slot, word in ((0, KEY), (1, KEY ^ 1), (2, KEY ^ 2)):
        base = slot_base(word)
        check("slot %d block base = %#x" % (slot, base), base in (DOI_SRC, DOI_S1, DOI_S2))
        for hdr, off, size in DUR:
            p = (base + BLOCK_OFF + off) & 0xFFFFFFFF
            exp = hdr - DOI_SRC + base
            check("slot %d +%#x -> %#x serves %#x" % (slot, off, p, hdr), p == exp)
            check("slot %d data at %#x == stock %#x" % (slot, p, hdr),
                  build[p:p + size] == stock[hdr:hdr + size])

    # 4. the selector curve header is inside the clone too
    for slot in (1, 2):
        base = DOI_S1 if slot == 1 else DOI_S2
        p = base + BLOCK_OFF
        check("slot %d selector curve %#x == stock 0x1DF054" % (slot, p),
              build[p:p + 28] == stock[0x1DF054:0x1DF054 + 28])

    # 5. the reader call at 0xC629C still gets r4 = the block base
    check("stock 0xC62A0 is bl to the 1D reader", (u32(stock, 0xC62A0) >> 26) == 18)

    # 6. no changes outside the expected regions
    allowed = set()
    for a, n in ((DOI_S1, 0xC30), (DOI_S2, 0xC30), (TABLE, 16)):
        allowed.update(range(a, a + n))
    for a in [0x09B2A8, 0x0F94DC, 0xC0898, 0xC09F8] + [s for s, _, _ in
            [(0xC5108, 0, 0), (0xC53A0, 0, 0), (0xC56FC, 0, 0), (0xC57E8, 0, 0),
             (0xC5AC4, 0, 0), (0xC5D50, 0, 0), (0xC5634, 0, 0), (0xC58D4, 0, 0),
             (0xC595C, 0, 0), (0xC5BC8, 0, 0), (0xC5E3C, 0, 0), (0xC5F54, 0, 0),
             (0xC60E0, 0, 0), (0xC6188, 0, 0), (0xC61C0, 0, 0), (0xE3124, 0, 0),
             (0xC5FE0, 0, 0), (0xC6244, 0, 0)]]:
        allowed.update(range(a, a + 4))
    for start, length in ((0x1FC000, 0x400), (0x1FC400, 0x400), (0x1FC800, 0x60),
                          (0x1FC880, 0x60), (0x1FC900, 0x6C0),
                          (0x1F0000, 0x2000), (0x1F2000, 0x2000),
                          (0x1EB000, 0x1E9C), (0x1ED000, 0x1E9C)):
        allowed.update(range(start, start + length))
    allowed.update(range(0x17FFFC, 0x180000))
    allowed.update(range(0x1BFFFC, 0x1C0000))
    allowed.update(range(0x1FDFFC, 0x1FE000))
    stray = [i for i in range(len(stock)) if stock[i] != build[i] and i not in allowed]
    check("diff vs stock only in hooks, thunks, clones, table, sums",
          not stray, ("first stray %#x" % stray[0]) if stray else
          "%d bytes changed" % sum(1 for i in range(len(stock)) if stock[i] != build[i]))

    print("\n%d passed, %d failed" % (ok, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
