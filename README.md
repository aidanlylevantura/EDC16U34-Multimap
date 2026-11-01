# EDC16U34 Multimap Release

Multimap tooling and candidate binary for Bosch EDC16U34 (VW Golf 5 / Seat Leon, VAG 03G906021KH, SW 382083).

Contents:
- build_multimap.py
- edc16_fix_checksum.py
- sanity_check_build.py
- 03G906021KH_382083_MULTIMAP_v3_R1_CANSTALK_CANDIDATE.bin

Do not upload Bosch/VAG proprietary stock firmware, WinOLS CSV files, original EEPROM dumps, or personal IMMO/VIN data.

Checksums: regions 0x040000-0x17FFFF (0x17FFFC), 0x180000-0x1BFFFF (0x1BFFFC), 0x1C0000-0x1FDFFF (0x1FDFFC) must sum to 0xD01FE500.

Status: software build and checksum validation complete. Bench testing pending.

