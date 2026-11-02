import struct

STOCK_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\New folder\VAG_BOSCH_EDC16U34_EXT FLASH_20261102134010.bin"
MOD_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\New folder\03G906021KH_PHASE1B.bin"

def get_sum(d, a, b):
    t = 0
    for i in range(a, b + 1, 4):
        t = (t + int.from_bytes(d[i:i+4], "big")) & 0xFFFFFFFF
    return t

o = open(STOCK_FILE, "rb").read()
m = open(MOD_FILE, "rb").read()

print("=== PHASE 1B FINAL VALIDATION ===")

print("\n1) Hook Check")
for name, addr in [("Stalk/Pedal", 0x09B2A8), ("Main Reader", 0x0F94DC), ("SOI Pointer", 0x000C0454)]:
    word = int.from_bytes(m[addr:addr+4], "big")
    op = (word >> 26) & 0x3F
    lk = word & 1
    print(f"  0x{addr:06X} {name}: 0x{word:08X} -> {'PASS' if op == 18 and lk == 0 else 'FAIL'}")

print("\n2) Checksums")
for start, end, name in [(0x040000, 0x17FFFF, "OS"), (0x180000, 0x1BFFFF, "Cal1"), (0x1C0000, 0x1FDFFF, "Cal2")]:
    s = get_sum(m, start, end)
    print(f"  {name}: 0x{s:08X} -> {'PASS' if s == 0xD01FE500 else 'FAIL'}")