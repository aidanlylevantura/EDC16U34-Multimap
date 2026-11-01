import os

# Original stock file
ORIG = r"C:\Users\user\Documents\Complete ECU Disassembly\stock_382083.ori"
# Your exact v3 Multimap Candidate
MULTIMAP = r"C:\Users\user\Documents\Complete ECU Disassembly\03G906021KH_382083_MULTIMAP_v3_R1_CANSTALK_CANDIDATE.bin"
TARGET_CONSTANT = 0xD01FE500

def get_sum(data, start_addr, end_addr):
    total = 0
    for i in range(start_addr, end_addr + 1, 4):
        word = int.from_bytes(data[i:i+4], "big")
        total = (total + word) & 0xFFFFFFFF
    return total

def main():
    if not os.path.exists(MULTIMAP):
        print(f"[-] Cannot find {MULTIMAP}")
        return
    if not os.path.exists(ORIG):
        print(f"[-] Cannot find original file at {ORIG}")
        return

    orig_data = open(ORIG, "rb").read()
    mod_data = open(MULTIMAP, "rb").read()

    print("=== 1. Diff Check ===")
    changes = 0
    for i in range(min(len(orig_data), len(mod_data))):
        if orig_data[i] != mod_data[i]:
            if changes < 15: # Print first 15 changes
                print(f"  Byte changed at 0x{i:06X}: {orig_data[i]:02X} -> {mod_data[i]:02X}")
            changes += 1
    print(f"Total bytes changed: {changes}")

    print("\n=== 2. Inner Checksum Verification ===")
    for offset in [0x1BFF74, 0x1FDF78]:
        orig_word = orig_data[offset:offset+4].hex().upper()
        mod_word = mod_data[offset:offset+4].hex().upper()
        match = "OK" if orig_word == mod_word else "MISMATCH! (May cause boot failure)"
        print(f"  0x{offset:06X}: Orig {orig_word} | Mod {mod_word} [{match}]")

    print("\n=== 3. Outer FADECAFE Sum Verification ===")
    for start, end, csum_off in [(0x180000, 0x1BFFFF, 0x1BFFFC), (0x1C0000, 0x1FDFFF, 0x1FDFFC)]:
        mod_sum = get_sum(mod_data, start, end)
        match = "OK" if mod_sum == TARGET_CONSTANT else "FAILED (Run edc16_fix_checksum.py)"
        print(f"  Region 0x{start:06X}-0x{end:06X}: Sum = 0x{mod_sum:08X} [{match}]")
        print(f"    Checksum word at 0x{csum_off:06X}: {mod_data[csum_off:csum_off+4].hex().upper()}")

if __name__ == "__main__":
    main()