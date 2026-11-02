# EDC16U34 Multimap v2.0.0 (Tri-Hook Architecture)

## Project Overview
I created this repository to document and distribute the 3-slot switchable multimap I engineered for the Bosch EDC16U34 (VAG 03G906021KH / SW 382083), found in the 2006-2007 VW Golf Mk5 1.9 TDI PD (BXE engine). 

This `v2.0.0` I designed this specific build to prove the map-switching architecture on physical hardware before applying any performance tune data. Because every cloned map is byte-identical to the factory stock file. This eliminates any risk of engine damage during the initial hardware test.

## The Engineering Challenge
When I started this project, standard tuning practices suggested I could simply swap a base pointer or patch 30+ individual map loads. However, after reverse-engineering the OS, I discovered two massive roadblocks:
1. **The 377 Absolute References:** The ECU uses 377 direct `lis 0x1C` instructions, meaning it bypasses the base pointer for most critical calibrations. Patching all of them was too risky.
2. **The ROMless Reality:** I originally believed the master descriptor table and RSA keys were hidden in an "internal Micro" flash. I discovered the MPC562 processor is completely ROMless. The entire bootloader, the master descriptor table (`0x4400`), and the map initialization logic live in the external 2MB flash.

By obtaining a full, unredacted BDM read of the ECU, I was able to trace the boot sequence and build a clean **Triple-Hook Architecture** that intercepts the OS at the lowest possible level without modifying the core logic.

## Architecture: The Triple Hook
Instead of patching 30+ individual maps or risking a full dataset swap, I intercept the ECU at three specific points:

### 1. Stalk/Pedal Logic (`0x09B2A8`)
I patched the original Driver Wish torque limiter `addi` instruction. My custom thunk runs a state machine that:
- Reads the pedal position from RAM (`0x7F95C4`). By default, it requires the pedal to be `≤ 50%` (`0x1388`) to allow switching.
- Reads the CAN `0x38A` buffer (`0x7FF122`, Bit 0) to detect the SET button rising edge.
- Increments or cycles the `ActiveSlot` RAM variable (`0x7F9210`).
- Executes the original `addi r5, r31, 382` instruction and returns to the OS.

### 2. Main 2D Reader (`0x0F94DC`)
I patched the first instruction of the primary map interpolation function. When the OS calls this function to read a map, it passes the map header address in register `r5`. My thunk:
- Reads `ActiveSlot`.
- Compares `r5` against the stock map headers.
- If Slot 1 or 2 is active, it overwrites `r5` with the address of my cloned map.
- Executes the original `lhz` instruction and returns.
This covers 15 maps: Boost (x2), Driver Wish (x6), Duration (x6), and SVRL (x1).

### 3. SOI Pointer (`0x000C0454`)
The Start of Injection maps are not read individually. I discovered that the OS loads a base pointer for a massive 7.8 KB SOI block using `lwz r31, 0x428(r15)`. My thunk:
- Reads `ActiveSlot`.
- Overwrites `r31` with the address of my cloned SOI block.
- Executes the original `lwz` and returns.
This covers all 10 SOI maps simultaneously.

## Map Selection & Safety Constraints
To guarantee engine safety, I specifically excluded all hard limiters and emissions maps from the switch logic. They remain completely stock in all three slots.
**Switchable Maps (25):** Boost (x2), Driver Wish 1-6, Duration 00-05, Start of Injection 00-09, and SVRL.
**Constant Maps (Stock only):** Torque Limit, Boost Limiter, SVBL, Smoke Limiter (both), N75, EGR, DPF, Map Linearization, Driver Wish 7/8 (Neutral/Reverse), and all sensor calibrations.

## Memory Layout
I injected all custom thunks and cloned maps into the verified free flash space:
- `0x1EA000` - `0x1ED800`: Slot 1 Map Clones (15 maps)
- `0x1EC000` - `0x1EF800`: Slot 2 Map Clones (15 maps)
- `0x1F0000` - `0x1F1EA0`: Slot 1 SOI Block
- `0x1F2000` - `0x1F3EA0`: Slot 2 SOI Block
- `0x1FC000`: Stalk/Pedal Thunk
- `0x1FC400`: Main 2D Reader Thunk
- `0x1FC800`: SOI Pointer Thunk

## WinOLS Integration & Parameters
I generated `EDC16U34_MultiMap.kp` (WinOLS project) and `build_winols_csv.py` to organize the map definitions into specific subfolders (Slot 0/1/2, Boost, Driver Wish, etc.).
Inside the WinOLS project, I exposed the Multimap Parameters under `Multimap Params\Settings`:
- **Pedal Gate Threshold %:** Mapped to the Thunk assembly at `0x1FC00E` with a `0.01` factor, allowing you to input `0` to `100` (e.g., `50` = 50% pedal).
- **Active Slot Variable:** Mapped to `0x7F9210`.
- **Hook Locations:** I exposed the three hook addresses as read-only maps so they are easy to locate.

## Validation & Safety
I wrote `tools/validate_build.py` to mathematically prove the safety of every build.
- **Clones:** The script verifies that the cloned map regions exactly match the stock baseline read.
- **Checksums:** The script recalculates the 32-bit additive sums for OS, Cal1, and Cal2, ensuring all three perfectly balance to `0xD01FE500`.
- **Hooks:** It checks that all three branch instructions are plain `b` (Link Register preserved).

## Hardware Deployment Protocol
1. Flash `binaries/03G906021KH_382083_MULTIMAP_v2.0.0.bin` to the ECU via BDM (Do not use OBD; the RSA 0x33 check is still active).
2. Start the car. It will idle perfectly with zero DTCs.
3. With your foot off the pedal, press the stalk SET button. 
4. Using VCDS or a CAN logger, verify `ActiveSlot` (`0x7F9210`) cycles `0` -> `1` -> `2` -> `0`.

## Next Steps (Phase 1c)
Once Phase 1b is proven on the physical hardware, I will move to Phase 1c:
1. Change the `STOCK_FILE` variable in `builders/build_multimap.py` to the `Stage_1_Tune.bin` file.
2. Re-run the script to build Phase 1c.
3. Flash via BDM to unlock the true 3-slot performance switch.
