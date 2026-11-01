\# EDC16U34 3-Slot Switchable Multimap (v1.1.0)



This repository contains the final, fully open-source 3-slot switchable multimap for the Bosch EDC16U34 ECU (VW Golf 5 / Seat Leon, VAG 03G906021KH, SW 382083).



The patch intercepts the map pointer immediately before the 2D interpolation engine and redirects it based on the Cruise Control stalk.



\## How It Works (v1.1.0 Features)



\- \*\*The Hook\*\*: At `0x09B2A8`, the stock instruction `addi r5, r31, 382` is replaced with a branch to custom PowerPC assembly injected at `0x1FE200`.

\- \*\*Pedal Safety Gate\*\*: The custom code reads the Accelerator Pedal position from RAM (`0x7F95BC`). Map switching is strictly locked out unless the pedal is at 0% (under 1% raw value), preventing dangerous torque spikes mid-acceleration.

\- \*\*CAN Stalk Edge-Detection\*\*: The code reads the raw stalk CAN payload at RAM (`0x70501C`). It looks for a press of the SET button (Bit 14) and uses a state latch (`0x7F9211`) to prevent rapid-fire switching if the button is held down.

\- \*\*The Slots\*\*:

&#x20; - \*\*Slot 0 (Stock)\*\*: `0x1D16F6`

&#x20; - \*\*Slot 1 (Stage 1)\*\*: `0x1EB000`

&#x20; - \*\*Slot 2 (Eco)\*\*: `0x1EC000`



\## Included Files



\- `03G906021KH\_382083\_MULTIMAP\_BUILT.bin` — The final 2 MB binary, ready to flash (Checksums validated to `0xD01FE500`).

\- `build\_multimap.py` — The Python builder that clones the maps, injects the 184-byte thunk, patches the hook, and fixes the checksums.

\- `generate\_thunk.py` — The Keystone-based Python assembler that generates the final PowerPC logic.

\- `edc16\_fix\_checksum.py` — The script used to fix the three FADECAFE checksum regions.



\## Flashing Instructions



\*\*You cannot flash this over OBD/CAN.\*\* The EDC16U34 bootloader uses an RSA-1024 signature for the `0x33` finish command. Because the private key is not in the external flash dump, OBD flashing will fail.



You must use a \*\*BDM tool\*\* (K-TAG, BDM100, PCMFlash) to physically write `03G906021KH\_382083\_MULTIMAP\_BUILT.bin` to the external flash chip.



\## Important Safety Warning



Do not flash the patched binary to a daily-driven vehicle without bench testing first. 



Before vehicle deployment:

1\. Connect a BDM probe to a spare EDC16U34 ECU.

2\. Flash `03G906021KH\_382083\_MULTIMAP\_BUILT.bin` via BDM.

3\. Verify the FADECAFE checksums.

4\. Only install in the car after successful bench validation.

