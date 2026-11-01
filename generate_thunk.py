from keystone import Ks, KS_ARCH_PPC, KS_MODE_PPC32, KS_MODE_BIG_ENDIAN

assembly = """
    # 1. Pedal Safety Gate (0x007F95BC)
    lis 11, 0x007F
    ori 11, 11, 0x95BC
    lhz 12, 0(11)      # Read pedal position
    cmplwi 0, 12, 0x00C8   # Compare with ~1% (200 decimal)
    bgt 0, use_current_map  # If pedal > 1%, force use current map

    # 2. Read Stalk State from CAN buffer (0x0070501C)
    lis 11, 0x0070
    ori 11, 11, 0x501C
    lhz 12, 0(11)      # Read stalk state
    rlwinm. 12, 12, 0, 17, 17 # Extract bit 14 (0x4000) and set CR0
    beq 0, stalk_released   # If not pressed, go to stalk_released

    # 3. Check LastStalk (0x007F9211)
    lis 11, 0x007F
    ori 11, 11, 0x9211
    lbz 12, 0(11)      # Read LastStalk
    cmpwi 0, 12, 1
    beq 0, use_current_map  # If already processed, do nothing

    # 4. Button edge detected! Update LastStalk = 1
    li 12, 1
    stb 12, 0(11)

    # 5. Increment ActiveSlot (0x007F9210) (0 -> 1 -> 2 -> 0)
    lis 11, 0x007F
    ori 11, 11, 0x9210
    lbz 12, 0(11)      # Read ActiveSlot
    addi 12, 12, 1
    cmpwi 0, 12, 3
    blt 0, save_slot
    li 12, 0            # Wrap around to 0
save_slot:
    stb 12, 0(11)
    b use_current_map

stalk_released:
    # 6. Button released. Update LastStalk = 0
    lis 11, 0x007F
    ori 11, 11, 0x9211
    li 12, 0
    stb 12, 0(11)

use_current_map:
    # 7. Load Map Pointer based on ActiveSlot
    lis 11, 0x007F
    ori 11, 11, 0x9210
    lbz 12, 0(11)
    cmpwi 0, 12, 1
    beq 0, stage1_map
    cmpwi 0, 12, 2
    beq 0, eco_map

stock_map:
    lis 5, 0x001D
    ori 5, 5, 0x16F6
    b 0x09B2AC

stage1_map:
    lis 5, 0x001E
    ori 5, 5, 0xB000
    b 0x09B2AC

eco_map:
    lis 5, 0x001E
    ori 5, 5, 0xC000
    b 0x09B2AC
"""

def generate_thunk():
    try:
        ks = Ks(KS_ARCH_PPC, KS_MODE_PPC32 | KS_MODE_BIG_ENDIAN)
        encoding, count = ks.asm(assembly, addr=0x1FE200)
        hex_string = "".join([f"{byte:02X}" for byte in encoding])
        
        print(f"Successfully assembled {count} instructions.")
        print(f"Thunk Size: {len(encoding)} bytes")
        print("\nCopy this hex into build_multimap.py:")
        print(f'THUNK_HEX = "{hex_string}"')
        
    except Exception as e:
        print(f"Assembly error: {e}")

if __name__ == "__main__":
    generate_thunk()