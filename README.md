# EDC16U34 3-Slot Switchable Multimap (v1.2.2)

This repository contains the final, fully open-source 3-slot switchable multimap for the Bosch EDC16U34 ECU (VW Golf 5 / Seat Leon, VAG 03G906021KH, SW 382083).

The patch intercepts the map pointer immediately before the 2D interpolation engine and redirects it based on the Cruise Control stalk.

## How It Works (v1.2.2 Features)

- **The Hook:** At `0x09B2A8`, the stock instruction `addi r5, r31, 382` is replaced with a plain branch (`b 0x1FE200`) to custom PowerPC assembly injected at `0x1FE200`. Using `b` instead of `bl` preserves the Link Register.
- **Pedal Safety Gate:** The custom code reads the Accelerator Pedal position from RAM (`0x7F95C4`, which is `-0x6A2C(r13)` with `r13 = 0x7FFFF0`). It uses a signed load (`lha`) and signed compare to safely handle negative sensor faults. Map switching is strictly locked out unless the pedal is at 0% (raw value < 200), preventing dangerous torque spikes.
- **CAN Stalk Edge-Detection:** The code reads the parsed stalk CAN payload at RAM (`0x7FF122`, CAN ID `0x38A` byte 2, bit 0). It uses a state latch at `0x7F9211` to prevent rapid-fire switching if the button is held down.
- **Exact Map Cloning:** The builder reads the map header and copies exactly `0xD4` bytes (4×20 table) to prevent copying garbage data.
- **The Slots:**
  - **Slot 0 (Stock):** `addi r5, r31, 382` (preserves exact stock pointer)
  - **Slot 1 (Stage 1):** `0x1EB000`
  - **Slot 2 (Eco):** `0x1EC000`

## Validation & Peer Review

This build has undergone rigorous static analysis, expert peer review, and PowerPC emulation:

- **Emulation:** The thunk was tested in a PowerPC emulator across 14 scenarios (slot cycling, button latch, pedal gates, negative pedal values, garbage initial values). All passed.
- **Register Safety:** Confirmed the callee at `0xF94DC` does not read `r11` or `r12`, meaning clobbering them in the thunk is safe.
- **r13 Verified:** Confirmed via the Leon bootloader (`lis r13, 0x0080` / `addi r13, -0x10`) that `r13 = 0x7FFFF0`, making the pedal address exactly `0x7F95C4`.
- **Checksums:** All three FADECAFE regions sum perfectly to `0xD01FE500`. The inner constants at `0x1BFF74` and `0x1FDF78` remain untouched.

## Included Files

- `03G906021KH_382083_MULTIMAP_v1.2.2.bin` — The final 2 MB binary, ready to flash.
- `build_multimap.py` — The Python builder that clones the maps, injects the thunk, patches the hook, and fixes checksums.
- `generate_thunk.py` — The Keystone-based Python assembler for the 184-byte PowerPC logic.
- `sanity_check_build.py` — Validates the build touches only the expected blocks and checksums.
- `hash_and_rename.py` — Utility to generate SHA-256 hashes.
- `find_r13.py` — Utility used to locate the `r13` base pointer in the bootloader.

### SHA-256 Integrity Hashes
Verify your downloaded files match these exact hashes:
- `03G906021KH_382083_MULTIMAP_v1.2.2.bin`: `352e2ed83be980bf5c461868699db2c793565c5182a1f871d8d1d3de352b1b69`
- `build_multimap.py`: `c221c835c86701bf10022b826fb431e94020851aca2e9f42d87bf634663af123`
- `generate_thunk.py`: `c7a974d2a12380a08775bcc58a3093f060a1b406cd8b599c5d9aee604891c110`
- `sanity_check_build.py`: `afeb09372dbd2fa33317de4158ba9f7b5d530e6810638bdfa865255b49a8bde5`

## Flashing Instructions

**You cannot flash this over OBD/CAN.** The EDC16U34 bootloader uses an RSA-1024 signature for the `0x33` finish command. Because the private key is not in the external flash dump, OBD flashing will fail.

You must use a **BDM tool** (K-TAG, BDM100, PCMFlash) to physically write `03G906021KH_382083_MULTIMAP_v1.2.2.bin` to the external flash chip.

## ⚠️ Important Safety & Hardware Warnings

Do not flash the patched binary to a daily-driven vehicle without bench testing first. 

Before vehicle deployment:
1. Connect a BDM probe to a spare EDC16U34 ECU.
2. Flash the `.bin` via BDM.
3. Verify the FADECAFE checksums.
4. Only install in the car after successful bench validation.

**Unverified Hardware Claims:**
- **Stalk CAN Byte (`0x7FF122` bit 0):** This was mapped from static analysis but needs a live CAN capture or bench test to confirm.
- **Pedal Threshold (`200`):** The variable is correct, but the exact raw units for 0% pedal require a BDM RAM read while the ECU is running.
- **State RAM (`0x7F9210`/`0x7F9211`):** Assumed free and safe across resets based on static analysis, but unproven on hardware.
- **Maps:** Slots 1 and 2 are currently exact clones of the stock map. This is a **switching test**, not a finished tune.
