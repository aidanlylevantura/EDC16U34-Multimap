import struct

# Path to the Leon BDM dump (contains the bootloader at 0x0 - 0x40000)
path = r"C:\Users\user\Documents\Complete ECU Disassembly\Seat Leon 1.9 TDI 105 hp 2006 EDC16U34 03G906021LK 0281013279 1037382081 bdm.bin"
d = open(path, "rb").read()

print("Scanning Leon bootloader for r13 initialization (lis r13)...")
for i in range(0, 0x40000, 4):
    w = struct.unpack(">I", d[i:i+4])[0]
    op = (w >> 26) & 0x3F
    # lis r13, 0xXXXX (opcode 15, RT=13, RA=0)
    if op == 15 and ((w >> 21) & 0x1F) == 13 and ((w >> 16) & 0x1F) == 0:
        hi = w & 0xFFFF
        print(f"\n[+] Found 'lis r13, 0x{hi:04X}' at 0x{i:06X}")
        # Print next 4 instructions to find the 'ori r13, r13' or 'addi r13, r13'
        for j in range(i, i+20, 4):
            w2 = struct.unpack(">I", d[j:j+4])[0]
            print(f"    0x{j:06X}: {w2:08X}")