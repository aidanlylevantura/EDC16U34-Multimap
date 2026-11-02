import re

INPUT_FILE = r"C:\Users\user\Documents\Complete ECU Disassembly\WinOLS (VW (Original) - 380437).csv"
OUTPUT_CSV = r"C:\Users\user\Documents\Complete ECU Disassembly\Master_Multimap_WinOLS.csv"

# The 25 switchable map addresses and their subfolders
SWITCHABLE_MAPS = {
    0x1E4744: "Boost Maps", 0x1E48BC: "Boost Maps",
    0x1C23A4: "Driver Wish", 0x1C24FA: "Driver Wish", 0x1C2650: "Driver Wish", 
    0x1C27A6: "Driver Wish", 0x1C28FC: "Driver Wish", 0x1C2A52: "Driver Wish",
    0x1DF09A: "Duration", 0x1DF1AA: "Duration", 0x1DF42C: "Duration", 
    0x1DF6AE: "Duration", 0x1DF930: "Duration", 0x1DFB96: "Duration",
    0x1D6418: "Start of Injection", 0x1D65D8: "Start of Injection", 
    0x1D6798: "Start of Injection", 0x1D6958: "Start of Injection", 
    0x1D6B18: "Start of Injection", 0x1D6CD8: "Start of Injection", 
    0x1D6E98: "Start of Injection", 0x1D7058: "Start of Injection", 
    0x1D7218: "Start of Injection", 0x1D73D8: "Start of Injection",
    0x1DF052: "Limiters"
}

# The 28 Constant maps (from your original 53-map list)
CONSTANT_MAPS = [
    0x1CA6C2, 0x1D1240, 0x1DF062, 0x1DFC76, 0x1DEFAE, 0x1DEEA6, 0x1D3696, 
    0x1D3874, 0x1D3A52, 0x1C3296, 0x1D75EE, 0x1C4C18, 0x1C6EC0, 0x1C6F64, 
    0x1C6FB6, 0x1C7008, 0x1C705A, 0x1D30BC, 0x1D3378, 0x1E4B74, 0x1D172A, 
    0x1D3FE2, 0x1E3794, 0x1E3972, 0x1E3B4E, 0x1C2BA8, 0x1C2CFE
]

def get_constant_folder(name):
    name_lower = name.lower()
    if any(k in name_lower for k in ["egr", "abgas", "dpf", "hysteresis", "recirculation"]):
        return "Emissions"
    if any(k in name_lower for k in ["limit", "begrenzung", "svbl", "smoke"]):
        return "Limiters"
    if any(k in name_lower for k in ["linear", "calibration", "lambda", "maf", "fuel temp", "volume"]):
        return "Calibration"
    return "Misc"

def main():
    output_lines = []
    
    with open(INPUT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        line = line.strip()
        if not line: continue
        
        parts = line.split(";")
        if i == 0 or "Name;" in line:
            output_lines.append(line)
            continue
            
        if len(parts) < 3: continue

        m = re.search(r"\$([0-9A-Fa-f]{6})", line)
        if not m: continue
        
        addr = int(m.group(1), 16)
        
        if addr in SWITCHABLE_MAPS:
            subfolder = SWITCHABLE_MAPS[addr]
            for slot_name in ["Slot 0 (Stock)", "Slot 1 (Stage 1)", "Slot 2 (Eco)"]:
                new_parts = list(parts)
                new_parts[2] = f"{slot_name}\\{subfolder}"
                output_lines.append(";".join(new_parts))
                
        elif addr in CONSTANT_MAPS:
            folder = get_constant_folder(parts[0])
            new_parts = list(parts)
            new_parts[2] = f"Constant (All Slots)\{folder}"
            output_lines.append(";".join(new_parts))

    # Add Multimap Parameters (Pseudo-maps for WinOLS)
    # These point to the Flash Thunk area where the assembly code lives
    params = [
        # Name, ID, Folder, Address, Description
        ("Pedal Gate Threshold", "MULTI_Pedal", "Multimap Params\\Settings", 0x1FC040, "Max raw pedal value to allow switching (Default 200)"),
        ("Active Slot Variable", "MULTI_Slot", "Multimap Params\\Settings", 0x7F9210, "RAM variable: 0=Stock, 1=Stage1, 2=Eco"),
        ("CAN Stalk Buffer", "MULTI_CAN", "Multimap Params\\Settings", 0x7FF122, "CAN 0x38A Frame (Bit 0 = SET)"),
        ("Main Reader Hook", "MULTI_Hook1", "Multimap Params\\Hooks", 0x0F94DC, "Original instruction patched to branch to Thunk"),
        ("SOI Pointer Hook", "MULTI_Hook2", "Multimap Params\\Hooks", 0x0C0454, "Original SOI lwz patched to branch to Thunk")
    ]

    for name, mid, folder, addr, desc in params:
        # 17 base columns + 1 for description
        line = f"{name};{mid};{folder};eEindim;eViewText;eBars;eHiLo;0;0;0;0;0;0;1;1;10;;-1;0;0;{desc};raw;1;0;${addr:06X};;;;;;;"
        output_lines.append(line)

    with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"[+] Successfully generated CLEAN TUNING CSV: {OUTPUT_CSV}")
    print(f"[+] Total lines: {len(output_lines)}")

if __name__ == "__main__":
    main()