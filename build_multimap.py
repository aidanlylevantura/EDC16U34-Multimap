import os

# --- CONFIGURATION ---
STOCK_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\stock_382083.ori"
OUTPUT_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\EDC16U34-Multimap-Release\03G906021KH_382083_MULTIMAP_BUILT.bin"

# The FINAL 184-byte safety-gated PowerPC thunk
THUNK_HEX = "3D607F95616B95BCA18B0000280C00C8418100683D600070616B501CA18B0000558C0463418200443D607F92616B0011898B00002C0C00014182004039800001998B00003D607F92616B0010898B0000398C00012C0C00034180000839800000998B0000480000143D607F92616B001139800000998B00003D607F92616B0010898B00002C0C0001418200182C0C00024182001C3CA01D1660A500F64BE9D0103CA01EB060A500004BE9D0043CA01EC060A500004BE9CFF8"

def get_sum(data, start_addr, end_addr):
    total = 0
    for i in range(start_addr, end_addr + 1, 4):
        word = int.from_bytes(data[i:i+4], "big")
        total = (total + word) & 0xFFFFFFFF
    return total

def fix_checksums(data):
    target = 0xD01FE500
    regions = [
        (0x040000, 0x17FFFF, 0x17FFFC),
        (0x180000, 0x1BFFFF, 0x1BFFFC),
        (0x1C0000, 0x1FDFFF, 0x1FDFFC)
    ]
    print("\n[*] Fixing FADECAFE Checksums...")
    for start, end, csum_off in regions:
        current_sum = get_sum(data, start, end)
        if current_sum == target:
            print(f"  Region 0x{start:06X} already valid.")
            continue
            
        delta = (target - current_sum) & 0xFFFFFFFF
        old_csum = int.from_bytes(data[csum_off:csum_off+4], "big")
        new_csum = (old_csum + delta) & 0xFFFFFFFF
        data[csum_off:csum_off+4] = new_csum.to_bytes(4, "big")
        print(f"  Region 0x{start:06X}-0x{end:06X} fixed. Delta: 0x{delta:08X}")

def main():
    if not os.path.exists(STOCK_FILE):
        print(f"[-] Stock file not found: {STOCK_FILE}")
        return

    print(f"[*] Loading {STOCK_FILE}...")
    with open(STOCK_FILE, "rb") as f:
        data = bytearray(f.read())

    if len(data) != 0x200000:
        print("[-] File must be exactly 2MB.")
        return

    # 1. Clone the Maps
    print("\n[*] Cloning Maps to Empty Flash...")
    map_length = 0x400 
    stock_map = data[0x1D16F6:0x1D16F6+map_length]
    
    data[0x1EB000:0x1EB000+map_length] = stock_map
    print("  [+] Slot 1 injected at 0x1EB000")
    
    data[0x1EC000:0x1EC000+map_length] = stock_map
    print("  [+] Slot 2 injected at 0x1EC000")

    # 2. Inject the Thunk
    print("\n[*] Injecting Map Redirect Thunk...")
    thunk_bytes = bytes.fromhex(THUNK_HEX)
    data[0x1FE200:0x1FE200+len(thunk_bytes)] = thunk_bytes
    print(f"  [+] Thunk injected at 0x1FE200 ({len(thunk_bytes)} bytes)")

    # 3. Patch the OS Hook
    print("\n[*] Patching OS Hook at 0x09B2A8...")
    hook_bytes = bytes.fromhex("48162F59")
    data[0x09B2A8:0x09B2A8+4] = hook_bytes
    print("  [+] Hook patched.")

    # 4. Fix Checksums
    fix_checksums(data)

    # 5. Save
    print(f"\n[*] Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "wb") as f:
        f.write(data)
    print("[+] Multimap Build Complete!")

if __name__ == "__main__":
    main()