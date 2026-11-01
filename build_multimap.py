"""Build the EDC16U34 3-slot multimap (v1.2).
Usage: python build_multimap.py [stock.ori] [output.bin]
Requires generate_thunk.py (and keystone-engine) alongside."""
import os, struct, sys
import generate_thunk as gt

STOCK_FILE  = sys.argv[1] if len(sys.argv) > 1 else "stock_382083.ori"
OUTPUT_FILE = sys.argv[2] if len(sys.argv) > 2 else "03G906021KH_382083_MULTIMAP_v1.2.bin"

HOOK_ADDR, HOOK_ORIG = 0x09B2A8, bytes.fromhex("38BF017E")   # addi r5,r31,382
STOCK_MAP, SLOT1, SLOT2 = gt.SLOT_PTRS
TARGET = 0xD01FE500
REGIONS = [(0x040000, 0x17FFFF), (0x180000, 0x1BFFFF), (0x1C0000, 0x1FDFFF)]  # csum word = last 4 bytes

def get_sum(d, a, b):
    t = 0
    for i in range(a, b + 1, 4):
        t = (t + int.from_bytes(d[i:i+4], "big")) & 0xFFFFFFFF
    return t

def b_insn(src, dst):          # plain relative branch, LK=0
    off = dst - src
    assert off % 4 == 0 and -0x2000000 <= off < 0x2000000
    return (0x48000000 | (off & 0x03FFFFFC)).to_bytes(4, "big")

def main():
    data = bytearray(open(STOCK_FILE, "rb").read())
    assert len(data) == 0x200000, "stock must be exactly 2 MB"
    assert data[HOOK_ADDR:HOOK_ADDR+4] == HOOK_ORIG, "unexpected instruction at hook - wrong SW?"
    assert get_sum(data, 0x040000, 0x17FFFF) == TARGET, "stock checksums not valid"

    # map size from its own header: nx, ny, axes, nx*ny halfword data
    nx, ny = struct.unpack(">HH", data[STOCK_MAP:STOCK_MAP+4])
    map_len = 2 * (2 + nx + ny + nx * ny)
    assert (nx, ny) == (4, 20) and map_len == 0xD4, f"map header unexpected: {nx}x{ny}"
    print(f"[*] Stock map {nx}x{ny} -> {map_len:#x} bytes")

    thunk, n = gt.assemble()
    for addr, ln in ((SLOT1, map_len), (SLOT2, map_len), (gt.THUNK_ADDR, len(thunk))):
        assert data[addr:addr+ln] == b"\xFF" * ln, f"{addr:#x} not erased in stock"
    m = bytes(data[STOCK_MAP:STOCK_MAP+map_len])
    data[SLOT1:SLOT1+map_len] = m
    data[SLOT2:SLOT2+map_len] = m
    data[gt.THUNK_ADDR:gt.THUNK_ADDR+len(thunk)] = thunk
    print(f"[+] Slots at {SLOT1:#x}/{SLOT2:#x}, thunk {len(thunk)} bytes at {gt.THUNK_ADDR:#x}")

    data[HOOK_ADDR:HOOK_ADDR+4] = b_insn(HOOK_ADDR, gt.THUNK_ADDR)
    print(f"[+] Hook {data[HOOK_ADDR:HOOK_ADDR+4].hex().upper()}")

    for a, b in REGIONS:
        cs = b - 3
        delta = (TARGET - get_sum(data, a, b)) & 0xFFFFFFFF
        if delta:
            old = int.from_bytes(data[cs:cs+4], "big")
            data[cs:cs+4] = ((old + delta) & 0xFFFFFFFF).to_bytes(4, "big")
        assert get_sum(data, a, b) == TARGET
        print(f"[+] Region {a:#08x}-{b:#08x} OK (delta {delta:#010x})")

    open(OUTPUT_FILE, "wb").write(data)
    print(f"[+] Wrote {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
