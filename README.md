# EDC16U34 Multimap v2.0.0

## Overview
This repository contains the source code and tools for the Bosch EDC16U34 (VAG 03G906021KH / SW 382083) 3-slot multimap architecture.

## Architecture
The system uses a **Triple-Hook** architecture to safely switch 25 maps without breaking the OS:
1. **Stalk/Pedal Logic (`0x09B2A8`)**: Reads the CAN stalk, checks the pedal, and updates `ActiveSlot` (0x7F9210).
2. **Main 2D Reader (`0x0F94DC`)**: Intercepts Boost, Driver Wish, Duration, and SVRL maps.
3. **SOI Pointer (`0x0C0454`)**: Intercepts the 7.8 KB Start of Injection block.

## Directory Structure
- `builders/`: Python scripts to generate the custom binaries and organize WinOLS CSVs.
- `tools/`: Validation scripts to verify hooks, clones, and checksums (0xD01FE500).
- `docs/`: Reverse Engineering notes and hook addresses.
- `binaries/`: Placeholder for `.bin` files (ignored by Git via `.gitignore`).

## How to Build
1. Ensure you have the baseline `Stock.bin` read.
2. Run `python builders/build_multimap.py` to generate the patched binary.
3. Run `python tools/validate_build.py` to verify the checksums and hooks.

## Safety
All builds are mathematically validated to ensure FADECAFE checksums balance to `0xD01FE500` and no out-of-bounds memory writes occur.
