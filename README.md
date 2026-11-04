# EDC16U34 MultiMap v2.1.0
## Identity
- **ECU** - Bosch **EDC16U34**
- **Part number** - **03G 906 021 KH**
- **Hardware number** - 03G 906 021 AN
- **Software number** - **1037382083**
- **Component** - R4 1,9L EDC G000AG  9245
- **Vehicle** - Golf Mk5 1.9 TDI BXE, DSG DQ250
## Background and analysis
The reverse-engineering work this build rests on lives in the companion
repository:
**<https://github.com/aidanlylevantura/EDC16U34-Complete-RE>**
Relevant documents there:
- **`CRUISE_CONTROL_RE.md`** - full FGR/GRA analysis - addresses, evidence, pitfalls
- **`CRUISE_CONTROL.c`** - annotated C reconstruction of the cruise subsystem
- **`RE_INDEX.md`** - address index, script inventory, open items
Everything about *why* an address is what it is belongs there. This README only
covers what the build does and how to use it.
Three slots - 0 = Stock, 1 = Stage 1, 2 = Eco - selected with the cruise stalk,
stored as a key-validated 32-bit word at `0x7F9214`.
> **Status: offline-validated only. Nothing here has run on a real ECU.**
> Read *Verification status* and *Known limitations* before flashing.
This is the only v2.1.0: everything before it is v2.0.0 lineage.
## What is switched
- **Boost 1/2, Driver Wish 1-6** - 2D reader hook `0x0F94DC` (header compare) - 8
- **Torque, smoke airflow/pressure, boost limiters** - 2D reader hook `0x0F94DC` (header compare) - 4
- **Start of injection 00-09 + Soi Selector** - SOI block clone, base hooks `0x0C0898` / `0x0C09F8` - 10
- **Duration 00-05 + Duration Selector + `InjVCD_*` parameters** - DOI block clone, 18 block-load hooks - 6 + params
The Duration maps are **not** reached through the 2D reader. The code builds six
pointers as `0x1DF054 + {0x1A,0x10E,0x390,0x612,0x894,0xB16}` at `0xC624C` and
filters them through the `InjVlv_numMI1_CUR` selector (`0x1DF062`), which is
indexed by **SOI angle**. That is why the DOI block is cloned and its 18 base
loads redirected.
The SOI map is chosen by **coolant temperature** through the Soi Selector at
`0x1D75EE` (10 points, -20 to 72 C, map 0 to 9).
## Addresses
```
hooks      TL 0x09B2A8   reader 0x0F94DC   SOI 0x0C0898, 0x0C09F8
DOI sites  0xC5108 0xC53A0 0xC56FC 0xC57E8 0xC5AC4 0xC5D50
           0xC5634 0xC58D4 0xC595C 0xC5BC8 0xC5E3C 0xC5F54 0xC60E0
           0xC6188 0xC61C0 0xE3124 0xC5FE0 0xC6244
thunks     TL 0x1FC000 (500 B)   reader 0x1FC400 (612 B)
           SOI 0x1FC800 / 0x1FC880 (60 B each)   DOI 0x1FC900 + i*0x60 (96 B each)
clones     12 maps     0x1F0000 (slot1) / 0x1F2000 (slot2)  4004 B/slot
           SOI block   0x1EB000 / 0x1ED000   0x1E9C B
           DOI block   0x1F4000 / 0x1F6000   0xC30 B
slot table 0x1F3F00 = {0x1DF02E, 0x1F4000, 0x1F6000, 0x1DF02E}
state      0x7F9214 = 0xA5C35A3C ^ slot   (0x7F9210 mirror, 0x7F9211 edge latch)
checksums  additive, target 0xD01FE500, words 0x17FFFC / 0x1BFFFC / 0x1FDFFC
```
## Files
- **`builders/build_multimap.py`** - Builder. `python builders/build_multimap.py [stock.bin] [out.bin] [--inert]`
- **`tools/validate_build.py`** - Validator. `python tools/validate_build.py [stock.bin] [built.bin] [--inert]`, exit 1 on failure
- **`mappack/EDC16U34_MultiMap_maps_v2.1.0.csv`** - WinOLS mappack: 149 rows (39 per slot), no DTCs, per-slot addresses
- **`binaries/Stock_Baseline.bin`** - Complete stock bin used as build input (see below)
- **`binaries/03G906021KH_MultiMap_v2.1.0.bin`** - Built image
- **`binaries/03G906021KH_MultiMap_v2.1.0_INERT.bin`** - Same footprint, stalk never read (flash first)
- **`docs/RE_Notes.txt`** - Address and analysis notes
`Stock_Baseline.bin` = complete read `VAG_BOSCH_EDC16U34_EXT FLASH_20261102134010.bin`
(sha `6b27b67e...`) with its calibration replaced by the factory calibration
`03G906021KH_9245_382083_PD105 Stock.Bin` (sha `d8545c99...`). OS untouched,
all three sums `D01FE500`.
## Baseline verification (independent source)
The baseline this project is built on was checked against a separate public
collection of 164 EDC16U34 dumps (`EDC16U34 Map packs`). Result:
```
bins compared                       164
exact matches with Stock_Baseline     0
382083 available twice      1B69 and 7EA1
```
Neither matched exactly, and the reason is instructive: those packs are
**calibration-only deliveries with the boot block erased**:
```
our stock   boot 0x0-0x3FFFF :  46.8 % 0xFF, 42.1 % real code
both packs  boot 0x0-0x3FFFF : 100.0 % 0xFF  (blank)
```
Comparing region by region against the `7EA1` dump:
```
            boot        OS          Cal1      Cal2      tail
7EA1      139,562        0            0         0         0
1B69      139,562    862,281          0         0         0
```
So **OS, Cal1 and Cal2 are byte-identical** to an independent dump of the same
software number. `1B69` has the same calibration but a different OS build
(862,281 bytes) behind the same SW label.
Everything this builder modifies is inside the verified regions:
- **OS hooks** - `0x09B2A8`, `0x0F94DC` - OS identical to 7EA1
- **SOI block** - `0x1D6414` + `0x1E9C` - Cal2 identical
- **DOI block** - `0x1DF02E` + `0xC30` - Cal2 identical
- **12 map headers** - `0x1E470C` … `0x1E49FC` - Cal1/Cal2 identical
- **boot** - differs - irrelevant to the build; ours is the complete image
The closest non-matching dump is `382414`, 9,398 bytes away - a different
software number, so 382083 and 382414 are neighbouring revisions.
**Do not flash a map pack.** Boot is erased in them; they are for map work only.
## Requirements
- Python 3.8 or newer, standard library only (no pip packages).
- A complete 2 MB read of the ECU (OS + calibration). `Stock_Baseline.bin` is the
  reference image this release was built from; it is third-party firmware, is not
  covered by the licence, and is included for development on your own ECU only.
- Optionally a factory calibration for the same SW (`1037382083`) if you want to build
  a stock baseline the way `Stock_Baseline.bin` was made.
## Build and validate
```
python builders/build_multimap.py                        # -> binaries/03G906021KH_MultiMap_v2.1.0.bin
python builders/build_multimap.py --inert                # -> binaries/..._INERT.bin
python tools/validate_build.py                           # 72/72 expected
python tools/validate_build.py binaries/Stock_Baseline.bin binaries/03G906021KH_MultiMap_v2.1.0_INERT.bin --inert   # 65/65
```
The builder refuses another software version, and aborts if a write target is not
erased in stock, overlaps another, or falls outside the verified free run
`0x1EA7C8-0x1FDF73`.
## Changes since v2.0.1
### Stalk trigger rebased on the real switch contacts
v2.0.1 read `0x7FF122`, which is byte 2 of CAN frame `0x7D0`. Firmware analysis
of this calibration (SW `1037382083`) shows no cruise code touches that byte: it
is not the stalk. The stalk arrives on frame `0x360`, is decoded by
`FUN_000a984c` into a switch-contact byte at `0x7F9413`, and that byte is what
v2.1.0 reads.
```
0x7F9413   bit 7 = signal 0x15C      bit 6 = signal 0x15E
           bit 5 = 0x15D  bit 2 = 0x161  bit 1 = 0x158  bit 0 = 0x160  bit 4 = 0x15A
```
A second, independent byte `0x7F9412` holds the firmware's own "any stalk
contact active" flag; it is available as an alternative mask source.
### Four WinOLS-tunable parameters
Which contact means "next" and which means "previous" cannot be proven
statically: the firmware collapses all eight contacts into one flag, so no code
distinguishes them. Rather than hardcode a guess, v2.1.0 exposes the masks:
```
0x1EA7C8   MAPS_MASK_NEXT   default 0x80   bit of the source that means next
0x1EA7C9   MAPS_MASK_PREV   default 0x40   bit that means previous
0x1EA7CA   MAPS_CFG         default 0x01   bit0: 1 = only while cruise is OFF
                                            bit1: 1 = disable stalk switching
0x1EA7CB   MAPS_SRC          default 0x00   which byte the masks read:
                                              0 = 0x7F9413 (switch contacts)
                                              1 = 0x7F9990 high byte (rocker
                                                  bits 8/9/14 -> 0x01/0x02/0x40)
                                              2 = 0x7F935D (rocker mode 1,2,3,5,7)
```
Swapping the two mask bytes inverts the polarity, in the car, with no rebuild.
Any bit of `0x7F9413` may be used, so if the inferred tip pair is wrong the
parameter still lets the correct contact be found empirically.
**Never give both masks the same bit.** If `MAPS_MASK_NEXT == MAPS_MASK_PREV`,
both rising edges fire in the same call: the slot advances +1 and then +2, which
is +3 mod 3 - no net change. Harmless, but it looks like a dead trigger while
testing.
### Testing the ON / CANCEL / OFF rocker
The tip contacts (`0x7F9413`) are not the rocker. The rocker is decoded from
signals `0x60` / `0x61` / `0x66`, which land in bits 8, 9 and 14 of the 16-bit
switch word `0x7F9990`, and are then turned into the mode byte `0x7F935D`
(values 1, 2, 3, 5, 7).
To test whether a rocker position makes a usable trigger:
```
MAPS_SRC        = 1        read the high byte of 0x7F9990
MAPS_MASK_NEXT  = 0x01     try each of these in turn
MAPS_MASK_PREV  = 0x02
                  0x40     (bit 14)
```
Whichever value advances the slot identifies that contact. Then set the winning
pair as `DEF_MASK_NEXT` / `DEF_MASK_PREV` in `build_multimap.py`, delete the four
`MAPS_*` rows from the mappack, and rebuild.
Note the difference: `MAPS_CFG` and the two masks are pure calibration, but
`MAPS_SRC` selects a **different address** in the thunk, so hardwiring a
non-default source is a one-line builder change rather than a CSV edit.
### Pedal gate (`MAPS_PEDAL_MAX`, `0x1EA7CC`)
Map switching is blocked above a pedal threshold. The check runs first in the
thunk:
```
lha    r12, 0x7F95C4        signed load - negatives sign-extend
cmpwi  r12, 0
blt    <original>           negative pedal always blocked
lhz    r11, 0x1EA7CC        the u16 parameter
cmpwi  r11, 0
beq    <proceed>            threshold 0 = gate disabled
cmplw  r12, r11
bgt    <original>           pedal above threshold - blocked
```
Defaults: **`0x1EA7CC = 0x0000`**, i.e. the gate is disabled and switching works
at any pedal. Negative values are blocked regardless, so a corrupt or signed
wraparound value cannot enable switching.
In WinOLS the parameter is 16-bit with **factor 0.1**, so it reads as 0-100 %.
The raw value is compared directly, so the factor is presentation only. If the
pedal scale turns out to be 0..10000 rather than 0..1000, change the factor to
0.01 - no rebuild needed.
The pedal scale itself is **unresolved**, and the static route to it is dead
end for now. What is known:
`0x064790` is **not** a producer, it is a restore. The same function reads the
value at `0x064428` and stashes it on the stack, then writes it back at
`0x064790` - a save/restore around unrelated work.
`0x0FEBC0`, the function called just before, is a **descriptor-driven job
submitter**, not a scaler: 12-byte descriptors at `0x445CC` indexed by
`param_1 * 0xC`, a type byte from `0x4BCC2`, a data base pointer `0x7FEA04`, and
a four-entry completion ring at `0x7FF490` (index `0x7FD691`, size from
`0x44791`). Its switch copies bytes or runs a checksum (`0xFDB90`) and enters
critical sections - it never converts units.
There is **no other writer**: a scan for `r13`-relative stores and for absolute
`lis 0x7F / ori 0x95C4` formation finds nothing else. The value therefore most
likely arrives through that descriptor/transfer layer from the ADC, which is
the least reverse-engineered part of this ECU.
The reference A2L also contradicts itself - MEASUREMENT limits imply x0.01
(0..10000) while its `Prc` COMPU_METHOD computes y = 100x, implying a 0..1
ratio. Weak evidence for 0..10000 exists elsewhere: the pedal chain contains
`cmpwi ..., 0x2710` (10000) comparisons at `0x661B38`, `0x661D30`, `0x66950`,
`0x66988`, `0x669B8`.
So: measure it. Reading `0x7F95C4` at idle and at full throttle settles it in
one session - VCDS measuring block 054 or 062 also shows accelerator pedal
position, no CAN tooling required.
#### What was ruled out
Four independent checks, so nobody repeats them:
**The transfer engine cannot reach the address.** `FUN_000febc0` computes
`iVar4 = 0x7FEA04 + u16_offset + param_2`, so every write lands in
`0x7FEA04 .. 0x80EA03`. The pedal at `0x7F95C4` is `0x5440` below that base.
`param_2` is stored into a single byte, so it is a small offset, not a negative
gateway into lower RAM.
**That region is data, not missed code.** Entropy of `0x4BCA4..0x4BD40` is
4.40-4.88 bits/byte against 5.17 for known code. `0x4BCC2` is a type registry
interleaved with handler pointers (`0x4BCDC -> 0x0010F934`,
`0x4BCE0 -> 0x0010FA20`, `0x4BCE4 -> 0x0022FFF0`). Ghidra's `??` means
undefined, not undecoded.
**The engine is diagnostic transport, not sensor input.** `FUN_00004cbc` stages
code into `0x7FF000` / `0x7F8000` and executes it through a RAM trampoline - a
flash driver in RAM - writing status to `0x7FEF5D..0x7FEF60`. `FUN_000febc0`
tests `_DAT_007fefd4 == 2` from the **same block**, so its busy-wait is a boot
or programming state, not an ADC conversion.
**The knob is a restore.** `0x064790` writes the pedal back after `0x064428`
read it. It is not a producer.
What is left is the QADC/TPU layer. `FUN_00004cbc` drives memory-mapped
registers at `0x6FC004`, `0x700004`, `0x704800`, `0x704A00`, `0x704C00`,
`0x704E00`, `0x706806`, `0x706816` and `0x702000` - all outside the 2 MB flash,
with `0x2100` / `0x2101` / `0x3F` written at 256-byte strides. Identifying those
needs the MPC562 peripheral map, which is a datasheet question rather than a
disassembly one, and a much bigger job than this threshold warrants.
### Switching is inhibited unless cruise is off
`MAPS_CFG` bit 0 gates on `0x7F953A == 0`, which is the firmware's own
"cruise switch off" test at `0x0ACCCC`. Pressing SET/RES while cruise is active
therefore changes speed without changing maps.
### Rising-edge only
Both tips are edge-detected through separate latches at `0x7F9212` and
`0x7F9213`; holding a contact produces exactly one step. Next wraps
`0 -> 1 -> 2 -> 0`, previous wraps `0 -> 2 -> 1 -> 0`.
### Diagnostics
```
0x7F9210  active slot mirror (0/1/2)
0x7F9212  next-tip latch          0x7F9213  prev-tip latch
0x7F9218  last byte from the SELECTED source (0x7F9413 by default)
0x7F9219  last raw 0x7F953A (only written when the gate runs)
0x7F921A  trigger counter
0x7F921B  1 = the off-gate ran and passed, 0 = gate disabled or blocked
```
Read them with `tools/watch_ram.py` (KWP service `0x23`). `0x7F9218` is the one
to watch while pressing the stalk: if it never changes, the selected source or
mask is wrong - try another `MAPS_SRC` or another bit.
### Validation
`tools/validate_build.py` was rewritten for the new trigger: emulator gained the
`AND` instruction, the diff whitelist learned the parameter block, and the TL
tests are now enumerated behaviour instead of a reference model. Current result:
```
active  72/72 PASS
inert   65/65 PASS
```
### Trigger-source coverage
`MAPS_SRC` selects which byte the masks read, and all three paths are exercised
by the validator rather than assumed:
```
--src 0   -> 0x7F9413  switch contacts      diag mirror reads 0xA1   PASS
--src 1   -> 0x7F9990  rocker bits 8/9/14   diag mirror reads 0xB2   PASS
--src 2   -> 0x7F935D  decoded rocker mode  diag mirror reads 0xC3   PASS
```
The test pokes a *different* value into each of the three bytes, runs one thunk
call, and checks that the diagnostic mirror `0x7F9218` equals the value belonging
to the configured source. That distinguishes the three addresses - a wrong
displacement or the wrong byte of the 16-bit word shows as a mismatch, not a
pass. The inert build skips this test because it never reads the stalk.
Build a variant with `python builders/build_multimap.py --src 1`.
What this still does not prove: that the firmware really places the rocker in
bits 8/9/14 of `0x7F9990`, or that `0x7F935D` holds 1/2/3/5/7 at runtime. Both
are inferences from decompiled code, settled only by a bus capture or car test.
### Measuring blocks are not available
The diagnostics cannot be exposed as a KWP measuring block: the `0x21` response
builder assembles its fields from code and reads no per-group descriptor table,
so a block cannot be repointed by editing calibration. RAM reads remain the only
channel. The investigation is documented in the RE repository.
### Still unverified
Polarity and contact identity are hardware facts. The offline suite proves
structure, checksums and emulated behaviour - not that this car's stalk sets
bits 7/6 of `0x7F9413`. Verify by reading `0x7F9218` with ignition on, engine
off, pressing each stalk function in turn.
## Changes vs v2.0.0
### Defects fixed
The v2.0.0 audit found six defects. All six are addressed:
- **1** - Stalk masked `0x80` (top bit of the rolling counter) - `rlwinm r12,r12,0,31,31` at `0x1FC010`; SET = bit 0; counter bits never used
- **2** - Slot 1 and slot 2 clones overlapped (`0x1EA000-0x1EDC00` / `0x1EC000-0x1EFC00`) - 12 map clones at `0x1F0000+` / `0x1F2000+`, SOI at `0x1EB000` / `0x1ED000`, DOI at `0x1F4000` / `0x1F6000`; the builder asserts no overlap and the validator re-derives the clones by emulating the thunks
- **3** - Live calibration `0x1EA000-0x1EA7C8` destroyed in every slot - untouched (1,453 bytes still present); `FREE_LO = 0x1EA7C8`, lowest clone `0x1EB000`, every target asserted erased in stock
- **4** - SOI clone 12 bytes off (`0x1D6408` vs `0x1D6414`) and only half the sites hooked - pointer-table index 267 = `0x1D6414` is cloned exactly; both `1068(r15)` consumers (`0xC0898`, `0xC09F8`) are hooked; the `1064(r15)` sites (`0xC0454`, `0xC0610`, `0xC0664`, `0xC06B4`) are index 266 = `0x1D6408`, a different 12-byte record, correctly left alone
- **5** - Reader addresses were data addresses, not headers - true headers (dims read from each header), clones sized from the header, no fixed 0x400; Duration removed from the chain, SVRL address dropped
- **6** - Any nonzero slot selected slot 2 - one 32-bit word `0x7F9214 = 0xA5C35A3C ^ slot`; every consumer range-checks 0-2 and falls back to stock, so power-on garbage reads stock
Also from that report: the WinOLS parameter rows now carry real addresses. The old "Pedal Gate Threshold" row pointed at a `stb`; in v2.1.0 the pedal gate is a proper 16-bit parameter at `0x1EA7CC` (see *Pedal gate* above).
### Design changes
- **DOI block** (Duration 00-05, `InjVlv_numMI1_CUR` selector, `InjVCD_*` parameters) is cloned per slot and its 18 base loads redirected. The Duration maps are reached as `0x1DF054 + {0x1A,0x10E,0x390,0x612,0x894,0xB16}`, not through the 2D reader, so they switch without being in the reader chain.
- **Limiter maps in the reader chain**: torque limiter (`0x1D16F6`), smoke airflow (`0x1D307E`), smoke pressure (`0x1D333C`), boost limiter (`0x1E49FC`) - 12 reader maps total, so a slot's request and its limits move together.
- **SVRL** (`0x1DF052`) exposed per slot through the DOI block; **SVBL** (`0x1E4B74`) is not addressable by this software and stays a constant.
- **Mappack CSV**: 149 rows, per-slot selectors, per-slot limiter channels, no DTCs, no duplicate addresses.
- **Validator**: DOI pointer table, 18 sites/thunks, slot table and mapping; DOI clones and table included in the overlap and erased-in-stock checks; map counts are dynamic.
## Verification status
**Verified offline:**
- checksums (three regions, `0xD01FE500`);
- hooks are plain `b`, displaced instructions replayed;
- register/CR/LR/CTR/XER contract of every thunk;
- clone targets erased in stock, no overlap, byte-equal to the source maps;
- TL/stalk thunk behaviour against a reference model over 20k states;
- reader thunk redirects exactly the 12 headers, stock for slot 0 / invalid state;
- SOI thunks: slot 0/invalid -> stock pointer, 1/2 -> clone base;
- DOI: stock pointer table 286-289, 18 sites are `lwz rX,0x478/47C/480/484(r15)`, 18 thunks, slot table, and the six computed Duration pointers resolving into each slot's clone (51/51 checks);
- the build writes **no map data** - every map byte equals the source bin; the parameter block at `0x1EA7C8` is written last.
**Unverified (bench items):**
- which bit of `0x7F9413` is SET and which is RES (needs a capture of the stalk);
- how ON / CANCEL / OFF reach `0x7F9990` bits 8/9/14 (inference, not measured);
- the `0x7F95C4` pedal scale - `0..10000`, `0..1000` or `0..250`; see *Pedal gate*;
- whether the limiters in the torque chain mask Stage 1;
- reset/RAM-retention behaviour of the slot word;
- real-time cost of the reader/DOI thunks;
- integrity of the chained 136-byte tail blocks (`0x17FF74`, `0x1BFF74`, `0x1FDF74`) - unresolved and left unchanged. Do not assume "no P0601"; flash `--inert` first.
## Editing maps
Edit the built image directly in WinOLS with `mappack/EDC16U34_MultiMap_maps_v2.1.0.csv`
(shipped as a static file - it is not regenerated by the build):
slot 1 rows point at `0x1F0000+`, `0x1EB000+`, `0x1F4000+`; slot 2 at `0x1F2000+`,
`0x1ED000+`, `0x1F6000+`; slot 0 at the stock addresses. Do **not** re-run the
builder after editing - it re-copies the clones from `binaries/Stock_Baseline.bin`.
## Known limitations
- **SVBL (`0x1E4B74`) is not switchable.** No pointer, immediate, table entry or indexed access reaches it; the cell sits in a header-less array. It stays a constant in the mappack.
- **The stalk is also the cruise control**: with `MAPS_PEDAL_MAX = 0` (the default) any qualifying stalk press advances the slot. Set a threshold once the pedal scale is known.
- Switching takes effect between lookups; one cycle may mix slots.
- Slots 1 and 2 are exact copies of stock until you edit them.
- Full-dataset switching (rewriting `r15`) was analysed and rejected: 377 absolute `lis 0x1C-0x1F` sites bypass the base pointer.
## License
MIT for the source code and documentation (see `LICENSE`). Bosch/VAG firmware and
calibration images (`Stock_Baseline.bin`, the built `.bin` files) are third-party
material, are not licensed here, and remain the property of their respective owners.
Not affiliated with Volkswagen AG or Robert Bosch GmbH. Experimental software for
off-road/development use; no warranty, and you are responsible for any ECU you flash.
