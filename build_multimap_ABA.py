import sys

THUNK1_HEX = "3D60007F616B95C4A98B0000280C00C8418100683D60007F616BF122898B0000558C0631418200443D60007F616B9211898B00002C0C00014182004039800001998B00003D60007F616B9210898B0000398C00012C0C00034180000839800000998B0000480000143D60007F616B921139800000998B00003D60007F616B9210898B00002C0C0001418200142C0C00024182001838BF017E4BE9D0143CA0001E60A5B0004BE9D0083CA0001E60A5C0004BE9CFFC"
THUNK2_HEX = "3D60007F616B9210898B00002C0C0001418200142C0C000241820018389F017E4BEBB31C3C80001E6084B0004BEBB3103C80001E6084C0004BEBB304"

def get_sum(data, start, end):
    total = 0
    for i in range(start, end + 1, 4):
        total = (total + int.from_bytes(data[i:i+4], "big")) & 0xFFFFFFFF
    return total

def fix_checksums(data):
    target = 0xD01FE500
    regions = [(0x040000, 0x17FFFF, 0x17FFFC), (0x180000, 0x1BFFFF, 0x1BFFFC), (0x1C0000, 0x1FDFFF, 0x1FDFFC)]
    for start, end, csum_off in regions:
        current_sum = get_sum(data, start, end)
        if current_sum != target:
            delta = (target - current_sum) & 0xFFFFFFFF
            old_csum = int.from_bytes(data[csum_off:csum_off+4], "big")
            new_csum = (old_csum + delta) & 0xFFFFFFFF
            data[csum_off:csum_off+4] = new_csum.to_bytes(4, "big")

def main():
    if len(sys.argv) != 4:
        print("Usage: python build_multimap_ABA.py <stock.bin> <stage1.bin> <output.bin>")
        return

    stock_path = sys.argv[1]
    stage1_path = sys.argv[2]
    output_path = sys.argv[3]

    original_stock_data = bytearray(open(stock_path, "rb").read())
    stage1_data = open(stage1_path, "rb").read()
    working_data = bytearray(original_stock_data)

    MAP_ADDR = 0x1D16F6
    MAP_LEN = 0xD4

    print("[*] Building consistent 3-slot A/B/A multimap...")

    stage1_map = stage1_data[MAP_ADDR:MAP_ADDR+MAP_LEN]
    working_data[0x1EB000:0x1EB000+MAP_LEN] = stage1_map
    print("  [+] Slot 1 (Stage 1) at 0x1EB000")

    stock_map = original_stock_data[MAP_ADDR:MAP_ADDR+MAP_LEN]
    working_data[0x1EC000:0x1EC000+MAP_LEN] = stock_map
    print("  [+] Slot 2 (Stock) at 0x1EC000")

    t1 = bytes.fromhex(THUNK1_HEX)
    working_data[0x1FE200:0x1FE200+len(t1)] = t1
    print(f"  [+] Thunk 1 at 0x1FE200 ({len(t1)} bytes)")

    t2 = bytes.fromhex(THUNK2_HEX)
    working_data[0x1FE400:0x1FE400+len(t2)] = t2
    print(f"  [+] Thunk 2 at 0x1FE400 ({len(t2)} bytes)")

    working_data[0x09B2A8:0x09B2A8+4] = bytes.fromhex("48162F58")
    print("  [+] Hook 1 patched at 0x09B2A8")

    working_data[0x0B9738:0x0B9738+4] = bytes.fromhex("48144CC8")
    print("  [+] Hook 2 patched at 0x0B9738")

    fix_checksums(working_data)
    open(output_path, "wb").write(working_data)
    print(f"[+] Saved to {output_path}")

if __name__ == "__main__":
    main()