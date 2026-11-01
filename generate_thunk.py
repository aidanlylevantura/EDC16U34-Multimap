from keystone import Ks, KS_ARCH_PPC, KS_MODE_PPC32, KS_MODE_BIG_ENDIAN

THUNK1_ASM = """
    # Pedal Safety Gate (0x007F95C4)
    lis 11, 0x007F
    ori 11, 11, 0x95C4
    lha 12, 0(11)
    cmplwi 0, 12, 0x00C8
    bgt 0, use_current_map

    # Read Stalk State (0x007FF122)
    lis 11, 0x007F
    ori 11, 11, 0xF122
    lbz 12, 0(11)
    rlwinm. 12, 12, 0, 24, 24
    beq 0, stalk_released

    # Check LastStalk (0x007F9211)
    lis 11, 0x007F
    ori 11, 11, 0x9211
    lbz 12, 0(11)
    cmpwi 0, 12, 1
    beq 0, use_current_map

    # Edge detected
    li 12, 1
    stb 12, 0(11)

    # Increment ActiveSlot (0x007F9210)
    lis 11, 0x007F
    ori 11, 11, 0x9210
    lbz 12, 0(11)
    addi 12, 12, 1
    cmpwi 0, 12, 3
    blt 0, save_slot
    li 12, 0
save_slot:
    stb 12, 0(11)
    b use_current_map

stalk_released:
    lis 11, 0x007F
    ori 11, 11, 0x9211
    li 12, 0
    stb 12, 0(11)

use_current_map:
    lis 11, 0x007F
    ori 11, 11, 0x9210
    lbz 12, 0(11)
    cmpwi 0, 12, 1
    beq 0, slot1_map
    cmpwi 0, 12, 2
    beq 0, slot2_map

slot0_map:
    addi 5, 31, 382
    b 0x09B2AC

slot1_map:
    lis 5, 0x001E
    ori 5, 5, 0xB000
    b 0x09B2AC

slot2_map:
    lis 5, 0x001E
    ori 5, 5, 0xC000
    b 0x09B2AC
"""

THUNK2_ASM = """
    # Read ActiveSlot (0x007F9210) - no edge detection, no increment
    lis 11, 0x007F
    ori 11, 11, 0x9210
    lbz 12, 0(11)
    cmpwi 0, 12, 1
    beq 0, slot1_map
    cmpwi 0, 12, 2
    beq 0, slot2_map

slot0_map:
    addi 4, 31, 382
    b 0x0B973C

slot1_map:
    lis 4, 0x001E
    ori 4, 4, 0xB000
    b 0x0B973C

slot2_map:
    lis 4, 0x001E
    ori 4, 4, 0xC000
    b 0x0B973C
"""

def assemble(asm, addr):
    ks = Ks(KS_ARCH_PPC, KS_MODE_PPC32 | KS_MODE_BIG_ENDIAN)
    encoding, count = ks.asm(asm, addr=addr)
    return "".join(f"{b:02X}" for b in encoding), len(encoding), count

def main():
    h1, n1, c1 = assemble(THUNK1_ASM, 0x1FE200)
    h2, n2, c2 = assemble(THUNK2_ASM, 0x1FE400)
    print(f"THUNK1: {c1} instr, {n1} bytes")
    print(f"THUNK2: {c2} instr, {n2} bytes")
    print()
    print(f'THUNK1_HEX = "{h1}"')
    print(f'THUNK2_HEX = "{h2}"')

if __name__ == "__main__":
    main()