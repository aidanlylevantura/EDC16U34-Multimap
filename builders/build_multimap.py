import struct
from keystone import Ks, KS_ARCH_PPC, KS_MODE_PPC32, KS_MODE_BIG_ENDIAN

STOCK_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\New folder\VAG_BOSCH_EDC16U34_EXT FLASH_20261102134010.bin"
OUTPUT_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\New folder\03G906021KH_PHASE1B.bin"

MAPS_READER = [
    ("Boost Map 1",   0x1E4710, 0x000), ("Boost Map 2",   0x1E4884, 0x400),
    ("Driver Wish 1", 0x1C2370, 0x800), ("Driver Wish 2", 0x1C24C6, 0xC00),
    ("Driver Wish 3", 0x1C261C, 0x1000), ("Driver Wish 4", 0x1C2772, 0x1400),
    ("Driver Wish 5", 0x1C28C8, 0x1800), ("Driver Wish 6", 0x1C2A1E, 0x1C00),
    ("Duration 00",   0x1DF09A, 0x2000), ("Duration 01",   0x1DF1AA, 0x2400),
    ("Duration 02",   0x1DF42C, 0x2800), ("Duration 03",   0x1DF6AE, 0x2C00),
    ("Duration 04",   0x1DF930, 0x3000), ("Duration 05",   0x1DFB96, 0x3400),
    ("SVRL",          0x1DF01E, 0x3800),
]

SLOT1_BASE, SLOT2_BASE = 0x1EA000, 0x1EC000
SOI_STOCK_ADDR, SOI_LEN = 0x1D6414, 0x1EA0
SOI_S1_BASE, SOI_S2_BASE = 0x1F0000, 0x1F2000

HOOK_TL = 0x09B2A8      # Used for Stalk/Pedal Thunk
HOOK_READER = 0x0F94DC  # Used for Map Reader Thunk
HOOK_SOI = 0x000c0454   # Used for SOI Thunk

THUNK_TL = 0x1FC000
THUNK_READER = 0x1FC400
THUNK_SOI = 0x1FC800

def get_sum(data, start, end):
    total = 0
    for i in range(start, end + 1, 4):
        total = (total + int.from_bytes(data[i:i+4], "big")) & 0xFFFFFFFF
    return total

def fix_checksums(data):
    target = 0xD01FE500
    for start, end, off in [(0x040000, 0x17FFFF, 0x17FFFC), (0x180000, 0x1BFFFF, 0x1BFFFC), (0x1C0000, 0x1FDFFF, 0x1FDFFC)]:
        s = get_sum(data, start, end)
        if s != target:
            delta = (target - s) & 0xFFFFFFFF
            old = int.from_bytes(data[off:off+4], "big")
            data[off:off+4] = ((old + delta) & 0xFFFFFFFF).to_bytes(4, "big")

def main():
    stock = bytearray(open(STOCK_FILE, "rb").read())
    working = bytearray(stock)
    
    for name, header, offset in MAPS_READER:
        s1, s2 = SLOT1_BASE + offset, SLOT2_BASE + offset
        working[s1:s1+0x400] = stock[header:header+0x400]
        working[s2:s2+0x400] = stock[header:header+0x400]
    working[SOI_S1_BASE:SOI_S1_BASE+SOI_LEN] = stock[SOI_STOCK_ADDR:SOI_STOCK_ADDR+SOI_LEN]
    working[SOI_S2_BASE:SOI_S2_BASE+SOI_LEN] = stock[SOI_STOCK_ADDR:SOI_STOCK_ADDR+SOI_LEN]

    ks = Ks(KS_ARCH_PPC, KS_MODE_PPC32 | KS_MODE_BIG_ENDIAN)

    # 1. THUNK 1: Pedal & Stalk Logic (Hooked to TL)
    # We don't switch TL, we just read the stalk, update ActiveSlot, and return original TL.
    first_tl_instr = struct.unpack(">I", stock[HOOK_TL:HOOK_TL+4])[0]
    asm_tl = """
        lis 11, 0x007F
        ori 11, 11, 0x95C4
        lha 12, 0(11)
        cmplwi 0, 12, 0x00C8
        bgt 0, original_tl
        
        lis 11, 0x007F
        ori 11, 11, 0xF122
        lbz 12, 0(11)
        rlwinm. 12, 12, 0, 24, 24
        beq 0, stalk_released
        
        lis 11, 0x007F
        ori 11, 11, 0x9211
        lbz 12, 0(11)
        cmpwi 0, 12, 1
        beq 0, original_tl
        
        li 12, 1
        stb 12, 0(11)
        
        lis 11, 0x007F
        ori 11, 11, 0x9210
        lbz 12, 0(11)
        addi 12, 12, 1
        cmpwi 0, 12, 3
        blt 0, save_slot
        li 12, 0
    save_slot:
        stb 12, 0(11)
        b original_tl
        
    stalk_released:
        lis 11, 0x007F
        ori 11, 11, 0x9211
        li 12, 0
        stb 12, 0(11)
        
    original_tl:
    """
    enc_tl, _ = ks.asm(asm_tl, addr=THUNK_TL)
    logic_tl = bytes(enc_tl)
    b_enc_tl, _ = ks.asm(f"b 0x{HOOK_TL + 4:06X}", addr=THUNK_TL + len(logic_tl) + 4)
    final_tl = logic_tl + struct.pack(">I", first_tl_instr) + bytes(b_enc_tl)
    
    working[THUNK_TL:THUNK_TL+len(final_tl)] = final_tl
    working[HOOK_TL:HOOK_TL+4] = (0x48000000 | ((THUNK_TL - HOOK_TL) & 0x03FFFFFC)).to_bytes(4, "big")
    print("  [+] Patched Stalk/Pedal Thunk at 0x09B2A8")

    # 2. THUNK 2: Reader (Boost, DW, Duration, SVRL)
    first_reader_instr = struct.unpack(">I", stock[HOOK_READER:HOOK_READER+4])[0]
    asm_reader = """
        lis 11, 0x007F
        ori 11, 11, 0x9210
        lbz 12, 0(11)
        cmpwi 0, 12, 0
        beq 0, original_reader
    """
    for i, (name, header, offset) in enumerate(MAPS_READER):
        s1, s2 = SLOT1_BASE + offset, SLOT2_BASE + offset
        asm_reader += f"""
        lis 11, 0x{(header >> 16) & 0xFFFF:04X}
        ori 11, 11, 0x{header & 0xFFFF:04X}
        cmpw 0, 5, 11
        bne 0, check_{i+1}
        cmpwi 0, 12, 1
        beq 0, slot1_{i}
        lis 5, 0x{(s2 >> 16) & 0xFFFF:04X}
        ori 5, 5, 0x{s2 & 0xFFFF:04X}
        b original_reader
    slot1_{i}:
        lis 5, 0x{(s1 >> 16) & 0xFFFF:04X}
        ori 5, 5, 0x{s1 & 0xFFFF:04X}
        b original_reader
    check_{i+1}:
        """
    asm_reader += "\n    original_reader:\n"
    enc_rdr, _ = ks.asm(asm_reader, addr=THUNK_READER)
    logic_rdr = bytes(enc_rdr)
    b_enc_rdr, _ = ks.asm(f"b 0x{HOOK_READER + 4:06X}", addr=THUNK_READER + len(logic_rdr) + 4)
    final_rdr = logic_rdr + struct.pack(">I", first_reader_instr) + bytes(b_enc_rdr)
    working[THUNK_READER:THUNK_READER+len(final_rdr)] = final_rdr
    working[HOOK_READER:HOOK_READER+4] = (0x48000000 | ((THUNK_READER - HOOK_READER) & 0x03FFFFFC)).to_bytes(4, "big")
    print("  [+] Patched Main Reader Thunk at 0x0F94DC")

    # 3. THUNK 3: SOI
    first_soi_instr = struct.unpack(">I", stock[HOOK_SOI:HOOK_SOI+4])[0]
    asm_soi = f"""
        lis 11, 0x007F
        ori 11, 11, 0x9210
        lbz 12, 0(11)
        cmpwi 0, 12, 0
        beq 0, original_soi
        cmpwi 0, 12, 1
        beq 0, slot1_soi
        lis 31, 0x{(SOI_S2_BASE >> 16) & 0xFFFF:04X}
        ori 31, 31, 0x{SOI_S2_BASE & 0xFFFF:04X}
        b 0x{HOOK_SOI + 4:06X}
    slot1_soi:
        lis 31, 0x{(SOI_S1_BASE >> 16) & 0xFFFF:04X}
        ori 31, 31, 0x{SOI_S1_BASE & 0xFFFF:04X}
        b 0x{HOOK_SOI + 4:06X}
    original_soi:
    """
    enc_soi, _ = ks.asm(asm_soi, addr=THUNK_SOI)
    logic_soi = bytes(enc_soi)
    b_enc_soi, _ = ks.asm(f"b 0x{HOOK_SOI + 4:06X}", addr=THUNK_SOI + len(logic_soi) + 4)
    final_soi = logic_soi + struct.pack(">I", first_soi_instr) + bytes(b_enc_soi)
    working[THUNK_SOI:THUNK_SOI+len(final_soi)] = final_soi
    working[HOOK_SOI:HOOK_SOI+4] = (0x48000000 | ((THUNK_SOI - HOOK_SOI) & 0x03FFFFFC)).to_bytes(4, "big")
    print("  [+] Patched SOI Thunk at 0x0C0454")

    fix_checksums(working)
    open(OUTPUT_FILE, "wb").write(working)
    print(f"\n[+] Saved fixed Phase 1b binary: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()