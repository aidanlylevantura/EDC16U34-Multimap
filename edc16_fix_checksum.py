import struct
import sys

TARGET_CONSTANT = 0xD01FE500
MAGIC = b"\xFA\xDE\xCA\xFE\xCA\xFE\xAF\xFE"

def fix_checksums(filepath):
    print(f"=== Processing: {filepath} ===")
    try:
        with open(filepath, "rb") as f:
            data = bytearray(f.read())
    except Exception as e:
        print(f"[-] Error reading file: {e}")
        return

    # Find all occurrences of the magic bytes
    magic_indices = []
    start_search = 0
    while True:
        idx = data.find(MAGIC, start_search)
        if idx == -1:
            break
        magic_indices.append(idx)
        start_search = idx + 1

    if not magic_indices:
        print("[-] No FADECAFE magic bytes found. Is this the right file?")
        return

    regions_fixed = 0
    for magic_idx in magic_indices:
        # The magic is at region_start + 0x3C
        region_start = magic_idx - 0x3C
        
        # Region boundaries are immediately before the magic (+0x34 and +0x38)
        # Note: These are stored as big-endian 32-bit addresses
        start_addr = int.from_bytes(data[region_start + 0x34 : region_start + 0x38], "big")
        end_addr = int.from_bytes(data[region_start + 0x38 : region_start + 0x3C], "big")
        
        # Sanity check: Ensure the addresses match the offset in the file
        if start_addr != region_start:
            print(f"[!] Warning: Magic at 0x{magic_idx:06X} indicates start 0x{start_addr:06X}, but calculated offset is 0x{region_start:06X}. Skipping.")
            continue
            
        # Calculate checksum for this region
        # Checksum word is the last 4 bytes of the region (end + 1 - 4)
        checksum_offset = end_addr - 3
        
        total_sum = 0
        for i in range(start_addr, end_addr + 1, 4):
            word = int.from_bytes(data[i:i+4], "big")
            total_sum = (total_sum + word) & 0xFFFFFFFF

        old_checksum = int.from_bytes(data[checksum_offset:checksum_offset+4], "big")
        
        print(f"\nRegion found at 0x{start_addr:06X} to 0x{end_addr:06X}")
        print(f"  Checksum Offset: 0x{checksum_offset:06X}")
        print(f"  Old Checksum:    0x{old_checksum:08X}")
        print(f"  Current Sum:     0x{total_sum:08X}")

        if total_sum == TARGET_CONSTANT:
            print("  [+] Sum already matches target. No fix needed.")
            continue

        # Calculate delta and new checksum
        delta = (TARGET_CONSTANT - total_sum) & 0xFFFFFFFF
        new_checksum = (old_checksum + delta) & 0xFFFFFFFF

        # Write new checksum
        data[checksum_offset:checksum_offset+4] = new_checksum.to_bytes(4, "big")
        print(f"  Delta:           0x{delta:08X}")
        print(f"  New Checksum:    0x{new_checksum:08X} -> [FIXED]")
        regions_fixed += 1

    if regions_fixed > 0:
        out_path = filepath.replace(".bin", "_FIXED.bin")
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"\n[+] Successfully wrote patched file to: {out_path}")
    else:
        print("\n[+] File is already valid. No changes written.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        fix_checksums(sys.argv[1])
    else:
        print("Usage: python edc16_fix_checksum.py <path_to_flash.bin>")
        print("Example: python edc16_fix_checksum.py Golf_KH_Flash_Patched.bin")