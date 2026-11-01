from keystone import Ks, KS_ARCH_PPC, KS_MODE_PPC32, KS_MODE_BIG_ENDIAN

# We use relative branches (b) and pass the base address (0x1FE200) 
# to Keystone so it calculates the jump offsets correctly.

assembly = """
    # 1. Pedal Safety Gate
    lis 11, 0x7F95
    ori 11, 11, 0xC4
    lhz 12, 0(11)
    cmplwi 0, 12, 0x1388
    bgt 0, stock_map

    # 2. Read Active Slot
    lis 11, 0x7F92
    ori 11, 11, 0x10
    lbz 12, 0(11)

    cmpwi 0, 12, 1
    beq 0, stage1_map
    cmpwi 0, 12, 2
    beq 0, eco_map

    # 3. Load Map Pointers
stock_map:
    lis 5, 0x1D16
    ori 5, 5, 0xF6
    b 0x09B2AC

stage1_map:
    lis 5, 0x1EB0
    ori 5, 5, 0x0000
    b 0x09B2AC

eco_map:
    lis 5, 0x1EC0
    ori 5, 5, 0x0000
    b 0x09B2AC
"""

def generate_thunk():
    try:
        ks = Ks(KS_ARCH_PPC, KS_MODE_PPC32 | KS_MODE_BIG_ENDIAN)
        
        # Pass the base address so relative branches calculate correctly
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