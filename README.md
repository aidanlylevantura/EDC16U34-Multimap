# EDC16U34 MultiMap v2.0.1

Bosch EDC16U34, VAG `03G906021KH`, SW `1037382083` (Golf Mk5 1.9 TDI BXE).
Three slots - 0 = Stock, 1 = Stage 1, 2 = Eco - selected with the cruise-stalk SET
button, with a per-slot state word at `0x7F9214`.

> **Status: offline-validated only. Nothing here has run on a real ECU.**
> Read *Verification status* and *Known limitations* before flashing.

This is the only v2.0.1: everything before it is v2.0.0 lineage.

## What is switched

| Group | Mechanism | Count |
|---|---|---|
| Boost 1/2, Driver Wish 1-6 | 2D reader hook `0x0F94DC` (header compare) | 8 |
| Torque, smoke airflow/pressure, boost limiters | 2D reader hook `0x0F94DC` (header compare) | 4 |
| Start of injection 00-09 + Soi Selector | SOI block clone, base hooks `0x0C0898` / `0x0C09F8` | 10 |
| Duration 00-05 + Duration Selector + `InjVCD_*` parameters | DOI block clone, 18 block-load hooks | 6 + params |

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
thunks     TL 0x1FC000 (124 B)   reader 0x1FC400 (612 B)
           SOI 0x1FC800 / 0x1FC880 (60 B each)   DOI 0x1FC900 + i*0x60 (96 B each)
clones     12 maps     0x1F0000 (slot1) / 0x1F2000 (slot2)  4004 B/slot
           SOI block   0x1EB000 / 0x1ED000   0x1E9C B
           DOI block   0x1F4000 / 0x1F6000   0xC30 B
slot table 0x1F3F00 = {0x1DF02E, 0x1F4000, 0x1F6000, 0x1DF02E}
state      0x7F9214 = 0xA5C35A3C ^ slot   (0x7F9210 mirror, 0x7F9211 edge latch)
checksums  additive, target 0xD01FE500, words 0x17FFFC / 0x1BFFFC / 0x1FDFFC
```

## Files

| File | Purpose |
|---|---|
| `builders/build_multimap.py` | Builder. `python builders/build_multimap.py [stock.bin] [out.bin] [--inert]` |
| `tools/validate_build.py` | Validator. `python tools/validate_build.py [stock.bin] [built.bin] [--inert]`, exit 1 on failure |
| `mappack/03G906021KH_MultiMap_v2.0.1_maps.csv` | WinOLS mappack: 144 rows (39 per slot), no DTCs, per-slot addresses |
| `binaries/Stock_Baseline.bin` | Complete stock bin used as build input (see below) |
| `binaries/03G906021KH_MultiMap_v2.0.1.bin` | Built image |
| `binaries/03G906021KH_MultiMap_v2.0.1_INERT.bin` | Same footprint, stalk never read (flash first) |
| `docs/RE_Notes.txt` | Address and analysis notes |

`Stock_Baseline.bin` = complete read `VAG_BOSCH_EDC16U34_EXT FLASH_20261102134010.bin`
(sha `6b27b67e...`) with its calibration replaced by the factory calibration
`03G906021KH_9245_382083_PD105 Stock.Bin` (sha `d8545c99...`). OS untouched,
all three sums `D01FE500`.

## Requirements

- Python 3.8 or newer, standard library only (no pip packages).
- A complete 2 MB read of the ECU (OS + calibration). `Stock_Baseline.bin` is the
  reference image this release was built from; it is third-party firmware, is not
  covered by the licence, and is included for development on your own ECU only.
- Optionally a factory calibration for the same SW (`1037382083`) if you want to build
  a stock baseline the way `Stock_Baseline.bin` was made.

## Build and validate

```
python builders/build_multimap.py                        # -> binaries/03G906021KH_MultiMap_v2.0.1.bin
python builders/build_multimap.py --inert                # -> binaries/..._INERT.bin
python tools/validate_build.py                           # 69/69 expected
python tools/validate_build.py binaries/Stock_Baseline.bin binaries/03G906021KH_MultiMap_v2.0.1_INERT.bin --inert   # 66/66
```

The builder refuses another software version, and aborts if a write target is not
erased in stock, overlaps another, or falls outside the verified free run
`0x1EA7C8-0x1FDF73`.

## Changes vs v2.0.0

### Defects fixed

The v2.0.0 audit found six defects. All six are addressed:

| # | v2.0.0 defect | Current design |
|---|---|---|
| 1 | Stalk masked `0x80` (top bit of the rolling counter) | `rlwinm r12,r12,0,31,31` at `0x1FC010`; SET = bit 0; counter bits never used |
| 2 | Slot 1 and slot 2 clones overlapped (`0x1EA000-0x1EDC00` / `0x1EC000-0x1EFC00`) | 12 map clones at `0x1F0000+` / `0x1F2000+`, SOI at `0x1EB000` / `0x1ED000`, DOI at `0x1F4000` / `0x1F6000`; the builder asserts no overlap and the validator re-derives the clones by emulating the thunks |
| 3 | Live calibration `0x1EA000-0x1EA7C8` destroyed in every slot | untouched (1,453 bytes still present); `FREE_LO = 0x1EA7C8`, lowest clone `0x1EB000`, every target asserted erased in stock |
| 4 | SOI clone 12 bytes off (`0x1D6408` vs `0x1D6414`) and only half the sites hooked | pointer-table index 267 = `0x1D6414` is cloned exactly; both `1068(r15)` consumers (`0xC0898`, `0xC09F8`) are hooked; the `1064(r15)` sites (`0xC0454`, `0xC0610`, `0xC0664`, `0xC06B4`) are index 266 = `0x1D6408`, a different 12-byte record, correctly left alone |
| 5 | Reader addresses were data addresses, not headers | true headers (dims read from each header), clones sized from the header, no fixed 0x400; Duration removed from the chain, SVRL address dropped |
| 6 | Any nonzero slot selected slot 2 | one 32-bit word `0x7F9214 = 0xA5C35A3C ^ slot`; every consumer range-checks 0-2 and falls back to stock, so power-on garbage reads stock |

Also from that report: the WinOLS "Pedal Gate Threshold" row pointed at a `stb`; it now points at the `cmplwi` immediate at `0x1FC006`, and the other multimap parameter rows carry real addresses.

### Design changes

- **DOI block** (Duration 00-05, `InjVlv_numMI1_CUR` selector, `InjVCD_*` parameters) is cloned per slot and its 18 base loads redirected. The Duration maps are reached as `0x1DF054 + {0x1A,0x10E,0x390,0x612,0x894,0xB16}`, not through the 2D reader, so they switch without being in the reader chain.
- **Limiter maps in the reader chain**: torque limiter (`0x1D16F6`), smoke airflow (`0x1D307E`), smoke pressure (`0x1D333C`), boost limiter (`0x1E49FC`) - 12 reader maps total, so a slot's request and its limits move together.
- **SVRL** (`0x1DF052`) exposed per slot through the DOI block; **SVBL** (`0x1E4B74`) is not addressable by this software and stays a constant.
- **Mappack CSV**: 144 rows, per-slot selectors, per-slot limiter channels, no DTCs, no duplicate addresses.
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
- the build writes **no map data** - every map byte equals the source bin.

**Unverified (bench items):**
- CAN `0x38A` byte 2 bit 0 = SET (needs a capture of the stalk);
- `0x7F95C4` = accelerator pedal in 0.01 % units (inference);
- whether the limiters in the torque chain mask Stage 1;
- reset/RAM-retention behaviour of the slot word;
- real-time cost of the reader/DOI thunks;
- integrity of the chained 136-byte tail blocks (`0x17FF74`, `0x1BFF74`, `0x1FDF74`) - unresolved and left unchanged. Do not assume "no P0601"; flash `--inert` first.

## Editing maps

Edit the built image directly in WinOLS with `mappack/03G906021KH_MultiMap_v2.0.1_maps.csv`
(shipped as a static file - it is not regenerated by the build):
slot 1 rows point at `0x1F0000+`, `0x1EB000+`, `0x1F4000+`; slot 2 at `0x1F2000+`,
`0x1ED000+`, `0x1F6000+`; slot 0 at the stock addresses. Do **not** re-run the
builder after editing - it re-copies the clones from `binaries/Stock_Baseline.bin`.

## Known limitations

- **SVBL (`0x1E4B74`) is not switchable.** No pointer, immediate, table entry or indexed access reaches it; the cell sits in a header-less array. It stays a constant in the mappack.
- **SET is also the cruise button**: every SET press with pedal <= gate advances the slot.
- Switching takes effect between lookups; one cycle may mix slots.
- Slots 1 and 2 are exact copies of stock until you edit them.
- Full-dataset switching (rewriting `r15`) was analysed and rejected: 377 absolute `lis 0x1C-0x1F` sites bypass the base pointer.

## License

MIT for the source code and documentation (see `LICENSE`). Bosch/VAG firmware and
calibration images (`Stock_Baseline.bin`, the built `.bin` files) are third-party
material, are not licensed here, and remain the property of their respective owners.

Not affiliated with Volkswagen AG or Robert Bosch GmbH. Experimental software for
off-road/development use; no warranty, and you are responsible for any ECU you flash.
