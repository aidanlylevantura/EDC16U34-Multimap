import os

# --- CONFIGURATION ---
STOCK_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\stock_382083.ori"
OUTPUT_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\03G906021KH_382083_MULTIMAP_BUILT.bin"

# The hex bytes for your custom assembly thunk (the map switcher)
# If you have the exact hex from your v3 build, paste it here. 
# For now, this is a placeholder that just returns the stock map pointer.
THUNK_HEX = "38A0017E4E800020" 

def get_sum(data, start_addr, end_addr):
    total = 0
    for i in range(start_addr, end_addr + 1, 4):
        word = int.from_bytes(data[i:i+4], "big")
        total = (total + word) & 0xFFFFFFFF
    return total

def fix_checksums(data):
    target = 0xD01FE500
    regions = [
        (0x180000, 0x1BFFFF, 0x1BFFFC),
        (0x1C0000, 0x1FDFFF, 0x1FDFFC)
    ]
    print("\n[*] Fixing Checksums...")
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
    # Copy the Torque Limiter Map (Header at 0x1D16F6, data at 0x1D172A)
    # We'll copy a 0x400 byte chunk starting from 0x1D16F6
    print("\n[*] Cloning Maps to Empty Flash...")
    
    # Stock map structure starts at 0x1D16F6
    map_length = 0x400 
    stock_map = data[0x1D16F6:0x1D16F6+map_length]
    
    # Slot 1 (Stage 1) at 0x1EB000
    data[0x1EB000:0x1EB000+map_length] = stock_map
    print("  [+] Slot 1 injected at 0x1EB000")
    
    # Slot 2 (Eco) at 0x1EC000
    data[0x1EC000:0x1EC000+map_length] = stock_map
    print("  [+] Slot 2 injected at 0x1EC000")

    # 2. Inject the Thunk (Assembly)
    print("\n[*] Injecting Map Redirect Thunk...")
    thunk_bytes = bytes.fromhex(THUNK_HEX)
    # We inject at 0x1FE200
    data[0x1FE200:0x1FE200+len(thunk_bytes)] = thunk_bytes
    print(f"  [+] Thunk injected at 0x1FE200 ({len(thunk_bytes)} bytes)")

    # 3. Patch the Hook
    print("\n[*] Patching OS Hook at 0x09B2A8...")
    # Original: addi r5, r31, 382 (0x38BF017E)
    # New: bl 0x1FE200 (0x4BFFF959) - The offset is calculated as (0x1FE200 - 0x09B2A8) / 4 = 0x162F58
    # Opcode: 48 (bl) | 0x162F58 = 0x48162F58 (Wait, earlier we verified 0x48162F59)
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