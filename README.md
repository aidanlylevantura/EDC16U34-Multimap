# EDC16U34 3-Slot Switchable Multimap (v1.2)

Target: Bosch EDC16U34, VAG 03G906021KH, SW 382083 (Golf Mk5 1.9 TDI).

## How it works
- **Hook:** at `0x09B2A8` the stock `addi r5,r31,382` (`38BF017E`) is replaced by a plain branch (`48162F58`) to a 184-byte thunk at `0x1FE200`. The thunk sets r5 to the selected map and branches back to `0x09B2AC`.
- **Map:** 4x20 two-axis map, 0xD4 bytes (size read from its own header). Slot 0 stock `0x1D16F6`, slot 1 `0x1EB000`, slot 2 `0x1EC000`. Slots 1 and 2 are exact copies of stock until you edit them.
- **Pedal gate:** reads s16 at `0x7F95C4` (`-0x6A2C(r13)`, r13 = `0x7FFFF0`); switching only when value <= 200 (`PEDAL_MAX`). The scale of this value is NOT verified.
- **Stalk:** reads byte `0x7FF122` bit 0 (CAN 0x38A byte 2). NOT confirmed on hardware. Edge-detected with latch `0x7F9211`; slot state in `0x7F9210` (0 -> 1 -> 2 -> 0).
- Registers used: r5, r11, r12 only (r11/r12 are dead after the hook).

## Files
- `generate_thunk.py` - assembles the thunk (needs `keystone-engine`); all addresses are constants at the top.
- `build_multimap.py` - `python build_multimap.py stock_382083.ori out.bin`; asserts stock hook bytes, erased target areas and map header, then fixes the 3 checksums.
- `sanity_check_build.py` - `python sanity_check_build.py stock_382083.ori out.bin`; diff must touch only the 6 expected blocks, hook must be a plain `b`, all 3 checksums = `0xD01FE500`.
- `edc16_fix_checksum.py` - standalone checksum fixer.

## Flashing
OBD/CAN flashing is not possible (RSA-signed finish command). A BDM tool is required. Bench-test on a spare ECU first and verify checksums before installing in a car.

## Validation and Emulation

This build (v1.2.0) has undergone rigorous static analysis and PowerPC emulation:

*   **Thunk Emulation:** The 184-byte assembly thunk was tested in a PowerPC emulator across 14 scenarios (slot cycling, button latching, safety gates, negative pedal values). All passed.
*   **Register Safety:** Verified that the callee at `0xF94DC` does not read `r11` or `r12`, so clobbering them in the thunk is safe.
*   **Hook:** Confirmed the hook is a plain `b` (Branch) to preserve the Link Register. The stock instruction was `38BF017E`.
*   **r13 Base Pointer:** Confirmed via the Leon bootloader that `r13` is initialized to `0x7FFFF0` (`lis r13, 0x0080` / `addi r13, r13, -0x10`). Therefore, the pedal address `-0x6A2C(r13)` is exactly `0x7F95C4`.
*   **Checksums:** All three FADECAFE regions sum perfectly to `0xD01FE500`. The build changes exactly 620 bytes, all within expected blocks.

**Remaining Hardware Validation Needed:**
*   The stalk CAN byte at `0x7FF122` (requires live CAN capture).
*   The pedal threshold scale (`PEDAL_MAX = 200`).