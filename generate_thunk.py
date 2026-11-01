"""Assemble the EDC16U34 multimap thunk (v1.2). Requires: pip install keystone-engine"""
from keystone import Ks, KS_ARCH_PPC, KS_MODE_PPC32, KS_MODE_BIG_ENDIAN

THUNK_ADDR = 0x1FE200
RETURN_ADDR = 0x09B2AC          # instruction after the hook
PEDAL_ADDR = 0x7F95C4           # -0x6A2C(r13), r13 = 0x7FFFF0 (s16)
PEDAL_MAX = 200                 # switching allowed only at/below this raw value (scale UNVERIFIED)
STALK_ADDR = 0x7FF122           # CAN 0x38A byte 2, bit 0 (UNCONFIRMED on hardware)
STALK_MASK = 0x01
ACTIVE_SLOT = 0x7F9210
LAST_STALK = 0x7F9211
SLOT_PTRS = (0x1D16F6, 0x1EB000, 0x1EC000)   # stock, slot 1, slot 2

def lo(a): return a & 0xFFFF
def hi(a): return (a >> 16) & 0xFFFF

def source():
    return f"""
    lis 11, {hi(PEDAL_ADDR):#x}
    ori 11, 11, {lo(PEDAL_ADDR):#x}
    lha 12, 0(11)
    cmpwi 0, 12, {PEDAL_MAX}
    bgt 0, use_current_map
    lis 11, {hi(STALK_ADDR):#x}
    ori 11, 11, {lo(STALK_ADDR):#x}
    lbz 12, 0(11)
    andi. 12, 12, {STALK_MASK}
    beq 0, stalk_released
    lis 11, {hi(LAST_STALK):#x}
    ori 11, 11, {lo(LAST_STALK):#x}
    lbz 12, 0(11)
    cmpwi 0, 12, 1
    beq 0, use_current_map
    li 12, 1
    stb 12, 0(11)
    lis 11, {hi(ACTIVE_SLOT):#x}
    ori 11, 11, {lo(ACTIVE_SLOT):#x}
    lbz 12, 0(11)
    addi 12, 12, 1
    cmpwi 0, 12, 3
    blt 0, save_slot
    li 12, 0
save_slot:
    stb 12, 0(11)
    b use_current_map
stalk_released:
    lis 11, {hi(LAST_STALK):#x}
    ori 11, 11, {lo(LAST_STALK):#x}
    li 12, 0
    stb 12, 0(11)
use_current_map:
    lis 11, {hi(ACTIVE_SLOT):#x}
    ori 11, 11, {lo(ACTIVE_SLOT):#x}
    lbz 12, 0(11)
    cmpwi 0, 12, 1
    beq 0, slot1
    cmpwi 0, 12, 2
    beq 0, slot2
    lis 5, {hi(SLOT_PTRS[0]):#x}
    ori 5, 5, {lo(SLOT_PTRS[0]):#x}
    b {RETURN_ADDR:#x}
slot1:
    lis 5, {hi(SLOT_PTRS[1]):#x}
    ori 5, 5, {lo(SLOT_PTRS[1]):#x}
    b {RETURN_ADDR:#x}
slot2:
    lis 5, {hi(SLOT_PTRS[2]):#x}
    ori 5, 5, {lo(SLOT_PTRS[2]):#x}
    b {RETURN_ADDR:#x}
"""

def assemble():
    ks = Ks(KS_ARCH_PPC, KS_MODE_PPC32 | KS_MODE_BIG_ENDIAN)
    enc, n = ks.asm(source(), addr=THUNK_ADDR)
    return bytes(enc), n

if __name__ == "__main__":
    enc, n = assemble()
    print(f"{n} instructions, {len(enc)} bytes")
    print(f'THUNK_HEX = "{enc.hex().upper()}"')
