#!/usr/bin/env python3
"""
EDC16U34 MultiMap builder v2.1.0  (VAG 03G906021KH / SW 1037382083)

Usage:  python build_multimap_770022.py [stock.bin] [output.bin] [--inert]

  stock.bin   default: Stock_Baseline.bin next to this script
  output.bin  default: 03G906021KH_382083_MULTIMAP_v2_0_1.bin (…_INERT.bin with --inert)
  --inert     same footprint (hooks, clones, thunks, checksums) but the stalk is never read, so the
              ECU always runs slot 0 (stock data). Flash this FIRST to test image acceptance.

No third-party dependencies (own PowerPC encoder; keystone is no longer required).

What changed in v2.1.0:
  * Stalk trigger rebased on the real switch-contact byte 0x7F9413 (sigs 0x156..0x161)
    instead of 0x7FF122, which is byte 2 of frame 0x7D0 and is not the stalk at all.
  * Three WinOLS-tunable parameters at 0x1EA7C8: MAPS_MASK_NEXT / MAPS_MASK_PREV /
    MAPS_CFG, so tip polarity can be determined in the car without a rebuild.
  * Gated on 0x7F953A == 0 (the firmware's own "cruise off" test at 0x0ACCCC).
  * Up = mask_next, down = mask_prev, both rising-edge only; CFG bit1 disables.

Earlier history, v2.0.1 vs v2.0.0 (all found by static analysis + emulation of the v2.0.0 binary):
  * Stalk test used rlwinm mask 24,24 (= 0x80, top bit of the rolling counter) -> slot cycled ~3x/s.
    Now bit 0 (31,31).
  * Slot-1 and slot-2 clone ranges overlapped (7 of 15 slot-2 clones corrupted) and the area
    0x1EA000-0x1EA7C7 held live calibration (9 OS pointer-table entries). Clones now live in
    verified-erased space, sized from each map's own header, with overlap/erased asserts.
  * SOI: v2.0.0 hooked lwz r,1064(r15) (index 266 = a 12-byte parameter record) but cloned the
    7.8 KB block of index 267 (0x1D6414). Now hooks the real consumers of index 267 (1068(r15)):
    0xC0898 and 0xC09F8, and clones 0x1D6414..0x1D82B0.
  * Reader addresses were not 2D headers (Duration/SVRL were data addresses, Boost 1 off by 4).
    Fixed; SVRL removed (no 2D header: not switchable through the 2D reader).
  * State is a single 32-bit word (KEY ^ slot). Garbage RAM can only select slot 1/2 with
    probability 2/2^32 per boot; invalid or zero state means stock data. No torn state.
"""
import os
import struct
import sys

# ------------------------------------------------------------------ configuration
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
INERT = "--inert" in sys.argv
# --src N overrides the trigger source default (0=0x7F9413, 1=0x7F9990, 2=0x7F935D)
SRC_OVERRIDE = None
for _i, _a in enumerate(sys.argv):
    if _a == "--src" and _i + 1 < len(sys.argv):
        SRC_OVERRIDE = int(sys.argv[_i + 1], 0)
HERE = os.path.dirname(os.path.abspath(__file__))
STOCK_FILE = ARGS[0] if len(ARGS) > 0 else os.path.join(HERE, "..", "binaries", "Stock_Baseline.bin")
OUTPUT_FILE = ARGS[1] if len(ARGS) > 1 else os.path.join(
    HERE, "..", "binaries", "03G906021KH_MultiMap_v2.1.0" + ("_INERT" if INERT else "") + ".bin")

# RAM state (all reached r13-relative; r13 = 0x7FFFF0 is set in the boot block and never written by the OS)
R13 = 0x7FFFF0
ADDR_ACTIVE_SLOT = 0x7F9210   # informational mirror (0/1/2). NOT used for decisions.
ADDR_LAST_STALK = 0x7F9211    # previous SET level (edge latch)
ADDR_SLOT_WORD = 0x7F9214     # authoritative: KEY32 ^ slot (32-bit, aligned, single store)
ADDR_PEDAL = 0x7F95C4         # s16, 0.01 % units, 0..10000 (identity = inference, see README)
ADDR_SET_BYTE = 0x7FF122      # DEPRECATED - byte 2 of frame 0x7D0, not the stalk. Kept for reference.
KEY32 = 0xA5C35A3C
PEDAL_MAX = 200               # switching only at pedal <= 200 raw (= 2.00 % if units are 0.01 %)

# ---- trigger (v2.1.0): real stalk contacts, WinOLS-tunable -----------------
# Verified against SW 1037382083: 0x7F9413 is the switch-contact byte assembled by
# FUN_000a984c from signals 0x156..0x161.  0x7F953A is the CC switch state, and the
# firmware's own "is cruise off?" test is (0x7F953A == 0) at 0x0ACCCC.
ADDR_TIPS      = 0x7F9413     # bit 7 = sig 0x15C, bit 6 = sig 0x15E (inferred tip pair)
ADDR_CC_STATE  = 0x7F953A     # 2-bit CC switch state; 0 = off
ADDR_LAST_NEXT = 0x7F9212     # edge latch, next-tip  (0/1)
ADDR_LAST_PREV = 0x7F9213     # edge latch, prev-tip  (0/1)
ADDR_DIAG_TIP  = 0x7F9218     # mirror: last raw 0x7F9413
ADDR_DIAG_CC   = 0x7F9219     # mirror: last raw 0x7F953A
ADDR_DIAG_CNT  = 0x7F921A     # mirror: triggers fired this session
ADDR_DIAG_FLG  = 0x7F921B     # mirror: bit0 = gate passed

# 3 tunable bytes in verified-erased filler (stock = FF FF FF).
PARAM_BASE     = 0x1EA7C8
ADDR_MASK_NEXT = PARAM_BASE + 0   # bit of 0x7F9413 that means "next map"
ADDR_MASK_PREV = PARAM_BASE + 1   # bit that means "previous map"
ADDR_MAPS_CFG  = PARAM_BASE + 2   # bit0: 1 = only while CC is off ; bit1: 1 = disable
ADDR_MAPS_SRC  = PARAM_BASE + 3   # which byte the masks read (see DEF_MAPS_SRC)
# NOTE: if MASK_NEXT == MASK_PREV both edges fire in the same call and the slot
# advances +1 then +2, i.e. +3 mod 3 = no change. Harmless, but while testing
# always give the two masks different bits.
DEF_MASK_NEXT  = 0x80
DEF_MASK_PREV  = 0x40
DEF_MAPS_CFG   = 0x01         # gate ON, triggers enabled
DEF_MAPS_SRC   = 0x00         # 0 = 0x7F9413 contact byte
                              # 1 = 0x7F9990 high byte (rocker bits 8/9/14 -> masks 01/02/40)
                              # 2 = 0x7F935D mode byte (decoded rocker position)
ADDR_SWITCH_WORD = 0x7F9990   # 16-bit raw switch word, high byte holds bits 8..15
ADDR_MODE_BYTE   = 0x7F935D   # decoded rocker mode: 1,2,3,5,7

# 2D map headers that the reader hook redirects (r5 == header address at entry of 0xF94DC).
# Duration maps are NOT here: they are reached through the DOI block (0x1DF054 + offsets),
# not through the 2D reader, so comparing them here would be dead code.
MAPS_READER = [
    ("Boost Map 1",   0x1E470C), ("Boost Map 2",   0x1E4884),
    ("Driver Wish 1", 0x1C2370), ("Driver Wish 2", 0x1C24C6), ("Driver Wish 3", 0x1C261C),
    ("Driver Wish 4", 0x1C2772), ("Driver Wish 5", 0x1C28C8), ("Driver Wish 6", 0x1C2A1E),
    ("Torque Limiter", 0x1D16F6), ("Smoke Limiter Pressure", 0x1D333C),
    ("Smoke Limiter Airflow", 0x1D307E), ("Boost Limiter", 0x1E49FC),
]
MAP_S1_AREA, MAP_S2_AREA, MAP_AREA_LEN = 0x1F0000, 0x1F2000, 0x2000

# SOI block = object of OS pointer-table index 267 (1068(r15))
PTR_TABLE, SOI_INDEX = 0x4C8A0, 267
SOI_STOCK_ADDR, SOI_LEN = 0x1D6414, 0x1E9C           # ends at next table object 0x1D82B0
SOI_S1_BASE, SOI_S2_BASE = 0x1EB000, 0x1ED000
HOOK_SOI = [(0xC0898, 12), (0xC09F8, 30)]             # (site, destination register)

HOOK_TL, HOOK_READER = 0x09B2A8, 0x0F94DC
THUNK_TL, THUNK_READER = 0x1FC000, 0x1FC400
THUNK_SOI = [0x1FC800, 0x1FC880]
THUNK_LEN = {"TL": 0x400, "READER": 0x400, "SOI": 0x80}

# DOI parameter block: the duration calculation reads these fields every cycle
# (+0x0 +0x2 +0x6 +0x8 +0x14 +0x15 +0x16). Cloning the block per slot switches
# the DOI inputs; the selector and the six 2D maps inside it are not read.
DOI_SRC, DOI_END = 0x1DF02E, 0x1DFC5E
DOI_LEN = DOI_END - DOI_SRC
DOI_S1, DOI_S2 = 0x1F4000, 0x1F6000
DOI_TABLE = 0x1F3F00
DOI_THUNK = 0x1FC900
DOI_STRIDE = 96
# (site, destination register, offset inside the block)
DOI_SITES = [
    (0xC5108, 31, 0x00), (0xC53A0, 30, 0x00), (0xC56FC, 12, 0x00),
    (0xC57E8, 12, 0x00), (0xC5AC4, 12, 0x00), (0xC5D50, 12, 0x00),
    (0xC5634, 30, 0x18), (0xC58D4, 10, 0x18), (0xC595C, 26, 0x18),
    (0xC5BC8, 10, 0x18), (0xC5E3C, 10, 0x18), (0xC5F54, 3, 0x18),
    (0xC60E0, 3, 0x18), (0xC6188, 30, 0x18), (0xC61C0, 30, 0x18),
    (0xE3124, 27, 0x18),
    (0xC5FE0, 3, 0x20),
    (0xC6244, 31, 0x26),
]

FREE_LO, FREE_HI = 0x1EA7C8, 0x1FDF74                # erased run in Cal2 (tail block starts 0x1FDF74)
TARGET = 0xD01FE500
REGIONS = [(0x040000, 0x17FFFF, 0x17FFFC), (0x180000, 0x1BFFFF, 0x1BFFFC), (0x1C0000, 0x1FDFFF, 0x1FDFFC)]

# ------------------------------------------------------------------ tiny PowerPC encoder
def _d(op, rt, ra, imm): return (op << 26) | (rt << 21) | (ra << 16) | (imm & 0xFFFF)
def lis(r, i): return _d(15, r, 0, i)
def li(r, i): return _d(14, r, 0, i)
def addi(rt, ra, i): return _d(14, rt, ra, i)
def ori(ra, rs, i): return _d(24, rs, ra, i)
def xori(ra, rs, i): return _d(26, rs, ra, i)
def xoris(ra, rs, i): return _d(27, rs, ra, i)
def lwz(rt, ra, d): return _d(32, rt, ra, d)
def lbz(rt, ra, d): return _d(34, rt, ra, d)
def lha(rt, ra, d): return _d(42, rt, ra, d)
def stb(rs, ra, d): return _d(38, rs, ra, d)
def stw(rs, ra, d): return _d(36, rs, ra, d)
def cmplwi(ra, i): return (10 << 26) | (ra << 16) | (i & 0xFFFF)
def cmpwi(ra, i): return (11 << 26) | (ra << 16) | (i & 0xFFFF)
def cmplw(ra, rb): return (31 << 26) | (ra << 16) | (rb << 11) | (32 << 1)
def xor_(ra, rs, rb): return (31 << 26) | (rs << 21) | (ra << 16) | (rb << 11) | (316 << 1)
def and_(ra, rs, rb): return (31 << 26) | (rs << 21) | (ra << 16) | (rb << 11) | (28 << 1)
def rlwinm(ra, rs, sh, mb, me, rc=0): return (21 << 26) | (rs << 21) | (ra << 16) | (sh << 11) | (mb << 6) | (me << 1) | rc
def stwu(rs, ra, d): return _d(37, rs, ra, d)
def add(ra, rs, rb): return (31 << 26) | (rs << 21) | (ra << 16) | (rb << 11) | (266 << 1)
def mfcr(rd): return 0x7C000026 | (rd << 21)
def mtcrf(fxm, rs): return 0x7C000120 | (rs << 21) | (fxm << 12)

BNE, BEQ, BGT, BLE, BLT = (4, 2), (12, 2), (12, 1), (4, 1), (12, 0)


def disp(addr):
    x = addr - R13
    assert -0x8000 <= x < 0x8000, hex(addr)
    return x


class Asm:
    def __init__(self, base):
        self.base, self.w, self.lab, self.fix = base, [], {}, []

    def e(self, x): self.w.append(x & 0xFFFFFFFF)

    def L(self, n):
        assert n not in self.lab, n
        self.lab[n] = len(self.w)

    def bc(self, cond, name): self.fix.append((len(self.w), "bc", cond, name)); self.w.append(0)
    def b(self, name): self.fix.append((len(self.w), "b", None, name)); self.w.append(0)

    def done(self):
        for i, kind, cond, name in self.fix:
            pc = self.base + 4 * i
            tgt = name if isinstance(name, int) else self.base + 4 * self.lab[name]
            off = tgt - pc
            assert off % 4 == 0
            if kind == "bc":
                assert -0x8000 <= off < 0x8000
                self.w[i] = (16 << 26) | (cond[0] << 21) | (cond[1] << 16) | (off & 0xFFFC)
            else:
                assert -0x2000000 <= off < 0x2000000
                self.w[i] = (18 << 26) | (off & 0x03FFFFFC)
        return b"".join(struct.pack(">I", x) for x in self.w)


def hi(x): return (x >> 16) & 0xFFFF
def lo(x): return x & 0xFFFF
KH, KL = hi(KEY32), lo(KEY32)


def slot_to_r(a, r):
    """r = (SlotWord ^ KEY32): 0/1/2 for a valid state, anything else = invalid."""
    a.e(lwz(r, 13, disp(ADDR_SLOT_WORD))); a.e(xoris(r, r, KH)); a.e(xori(r, r, KL))


# ------------------------------------------------------------------ thunks
def tl_thunk(displaced):
    """Stalk trigger.

    Reads the real switch-contact byte 0x7F9413 and, when the gate allows it,
    advances (+) or retreats (-) the slot on a rising edge of the configured
    contact bit.  Both masks are flash parameters so the tip polarity can be
    determined in the car without rebuilding.
    """
    a = Asm(THUNK_TL); E = a.e

    def load_src(reg, tag):
        """reg = one byte from the selected source (MAPS_SRC)."""
        E(lis(12, hi(ADDR_MAPS_SRC))); E(ori(12, 12, lo(ADDR_MAPS_SRC))); E(lbz(12, 12, 0))
        E(cmpwi(12, 1)); a.bc(BEQ, "s%s1" % tag)
        E(cmpwi(12, 2)); a.bc(BEQ, "s%s2" % tag)
        E(lbz(reg, 13, disp(ADDR_TIPS))); a.b("s%sd" % tag)
        a.L("s%s1" % tag); E(lbz(reg, 13, disp(ADDR_SWITCH_WORD))); a.b("s%sd" % tag)
        a.L("s%s2" % tag); E(lbz(reg, 13, disp(ADDR_MODE_BYTE)))
        a.L("s%sd" % tag)
    E(lha(12, 13, disp(ADDR_PEDAL))); E(cmplwi(12, PEDAL_MAX)); a.bc(BGT, "orig")     # signed negatives -> huge -> blocked
    if INERT:
        E(li(12, 0))
        E(stb(12, 13, disp(ADDR_LAST_NEXT))); E(stb(12, 13, disp(ADDR_LAST_PREV)))
        a.b("orig")
    else:
        # ---- kill switch: MAPS_CFG bit 1
        E(lis(12, hi(ADDR_MAPS_CFG))); E(ori(12, 12, lo(ADDR_MAPS_CFG))); E(lbz(12, 12, 0))
        E(rlwinm(12, 12, 0, 30, 30, rc=1)); a.bc(BNE, "clear")
        # ---- gate: MAPS_CFG bit 0 -> only while the CC switch state is 0 (off)
        E(lis(12, hi(ADDR_MAPS_CFG))); E(ori(12, 12, lo(ADDR_MAPS_CFG))); E(lbz(12, 12, 0))
        E(rlwinm(12, 12, 0, 31, 31, rc=1)); a.bc(BEQ, "nogate")
        E(lbz(11, 13, disp(ADDR_CC_STATE))); E(stb(11, 13, disp(ADDR_DIAG_CC)))
        E(cmpwi(11, 0)); a.bc(BNE, "clear")
        E(li(12, 1)); E(stb(12, 13, disp(ADDR_DIAG_FLG))); a.b("srcsel")
        a.L("nogate"); E(li(12, 0)); E(stb(12, 13, disp(ADDR_DIAG_FLG)))
        a.L("srcsel")
        load_src(11, "a"); E(stb(11, 13, disp(ADDR_DIAG_TIP)))

        # ---- NEXT (+1)
        E(lis(12, hi(ADDR_MASK_NEXT))); E(ori(12, 12, lo(ADDR_MASK_NEXT))); E(lbz(12, 12, 0))
        E(and_(12, 11, 12)); E(cmpwi(12, 0)); a.bc(BEQ, "relnext")
        E(lbz(12, 13, disp(ADDR_LAST_NEXT))); E(cmpwi(12, 0)); a.bc(BNE, "done")
        E(li(12, 1)); E(stb(12, 13, disp(ADDR_LAST_NEXT)))
        slot_to_r(a, 12)
        E(cmplwi(12, 2)); a.bc(BLE, "vn"); E(li(12, 0))
        a.L("vn"); E(addi(12, 12, 1)); E(cmplwi(12, 3)); a.bc(BLT, "sn"); E(li(12, 0))
        a.L("sn"); E(stb(12, 13, disp(ADDR_ACTIVE_SLOT)))
        E(lis(11, KH)); E(ori(11, 11, KL)); E(xor_(11, 11, 12)); E(stw(11, 13, disp(ADDR_SLOT_WORD)))
        E(lbz(12, 13, disp(ADDR_DIAG_CNT))); E(addi(12, 12, 1)); E(stb(12, 13, disp(ADDR_DIAG_CNT)))
        a.b("done")
        a.L("relnext"); E(li(12, 0)); E(stb(12, 13, disp(ADDR_LAST_NEXT)))

        # ---- PREV (-1)
        a.L("done")
        load_src(11, "b")
        E(lis(12, hi(ADDR_MASK_PREV))); E(ori(12, 12, lo(ADDR_MASK_PREV))); E(lbz(12, 12, 0))
        E(and_(12, 11, 12)); E(cmpwi(12, 0)); a.bc(BEQ, "relprev")
        E(lbz(12, 13, disp(ADDR_LAST_PREV))); E(cmpwi(12, 0)); a.bc(BNE, "orig")
        E(li(12, 1)); E(stb(12, 13, disp(ADDR_LAST_PREV)))
        slot_to_r(a, 12)
        E(cmplwi(12, 2)); a.bc(BLE, "vp"); E(li(12, 0))
        a.L("vp"); E(addi(12, 12, 2)); E(cmplwi(12, 3)); a.bc(BLT, "sp"); E(addi(12, 12, -3))
        a.L("sp"); E(stb(12, 13, disp(ADDR_ACTIVE_SLOT)))
        E(lis(11, KH)); E(ori(11, 11, KL)); E(xor_(11, 11, 12)); E(stw(11, 13, disp(ADDR_SLOT_WORD)))
        E(lbz(12, 13, disp(ADDR_DIAG_CNT))); E(addi(12, 12, 1)); E(stb(12, 13, disp(ADDR_DIAG_CNT)))
        a.b("orig")
        a.L("relprev"); E(li(12, 0)); E(stb(12, 13, disp(ADDR_LAST_PREV)))
        a.b("orig")

        # ---- gate/kill blocked: drop the latches so a later press is a fresh edge
        a.L("clear")
        E(li(12, 0)); E(stb(12, 13, disp(ADDR_DIAG_FLG)))
        E(stb(12, 13, disp(ADDR_LAST_NEXT))); E(stb(12, 13, disp(ADDR_LAST_PREV)))
    a.L("orig"); E(displaced); a.b(HOOK_TL + 4)
    return a.done()


def reader_thunk(displaced, s1, s2):
    a = Asm(THUNK_READER); E = a.e
    slot_to_r(a, 12)
    E(cmplwi(12, 2)); a.bc(BGT, "orig")           # invalid -> stock
    E(cmplwi(12, 0)); a.bc(BEQ, "orig")           # slot 0 -> stock
    for i, (name, header) in enumerate(MAPS_READER):
        E(lis(11, hi(header))); E(ori(11, 11, lo(header))); E(cmplw(5, 11)); a.bc(BNE, f"next{i}")
        E(cmpwi(12, 1)); a.bc(BEQ, f"s1_{i}")
        E(lis(5, hi(s2[i]))); E(ori(5, 5, lo(s2[i]))); a.b("orig")
        a.L(f"s1_{i}"); E(lis(5, hi(s1[i]))); E(ori(5, 5, lo(s1[i]))); a.b("orig")
        a.L(f"next{i}")
    a.L("orig"); E(displaced); a.b(HOOK_READER + 4)
    return a.done()


def soi_thunk(base, site, rd, displaced):
    a = Asm(base); E = a.e
    slot_to_r(a, rd)
    E(cmplwi(rd, 1)); a.bc(BEQ, "s1"); E(cmplwi(rd, 2)); a.bc(BEQ, "s2")
    E(displaced); a.b(site + 4)                                                   # slot 0 / invalid: stock pointer
    a.L("s1"); E(lis(rd, hi(SOI_S1_BASE))); E(ori(rd, rd, lo(SOI_S1_BASE))); a.b(site + 4)
    a.L("s2"); E(lis(rd, hi(SOI_S2_BASE))); E(ori(rd, rd, lo(SOI_S2_BASE))); a.b(site + 4)
    return a.done()


def doi_thunk(addr, site, reg, off):
    """Redirect one Duration block load to the active slot's copy."""
    a = Asm(addr); E = a.e
    E(stwu(1, 1, -16))
    E(lwz(11, 13, disp(ADDR_SLOT_WORD)))
    E(xoris(11, 11, KH)); E(xori(11, 11, KL))
    E(mfcr(reg)); E(stw(reg, 1, 8))                     # CR0 is live across the load
    E(cmplwi(11, 2)); a.bc(BGT, "stock")
    E(cmplwi(11, 0)); a.bc(BEQ, "stock")
    E(rlwinm(11, 11, 2, 0, 29))
    E(lis(reg, hi(DOI_TABLE))); E(ori(reg, reg, lo(DOI_TABLE)))
    E(add(reg, reg, 11)); E(lwz(reg, reg, 0)); a.b("done")
    a.L("stock"); E(lis(reg, hi(DOI_SRC))); E(ori(reg, reg, lo(DOI_SRC)))
    a.L("done"); E(lwz(11, 1, 8)); E(mtcrf(0xFF, 11)); E(addi(1, 1, 16))
    E(addi(reg, reg, off)); a.b(site + 4)
    return a.done()


# ------------------------------------------------------------------ helpers
def u32(d, o): return struct.unpack_from(">I", d, o)[0]


def get_sum(d, a, b):
    return sum(u32(d, i) for i in range(a, b + 1, 4)) & 0xFFFFFFFF


def fix_checksums(d):
    for a, b, off in REGIONS:
        delta = (TARGET - get_sum(d, a, b)) & 0xFFFFFFFF
        if delta:
            d[off:off + 4] = struct.pack(">I", (u32(d, off) + delta) & 0xFFFFFFFF)
        assert get_sum(d, a, b) == TARGET, f"checksum {a:#x} not balanced"


def map_size(d, h):
    nx, ny = struct.unpack_from(">HH", d, h)
    assert 2 <= nx <= 64 and 2 <= ny <= 64, f"{h:#x}: not a 2D map header (nx={nx}, ny={ny})"
    return 4 + 2 * (nx + ny + nx * ny)


def b_insn(src, dst):
    off = dst - src
    assert off % 4 == 0 and -0x2000000 <= off < 0x2000000
    return struct.pack(">I", 0x48000000 | (off & 0x03FFFFFC))


def main():
    stock = open(STOCK_FILE, "rb").read()
    assert len(stock) == 0x200000, "stock must be exactly 2 MB"
    for a, b, _ in REGIONS:
        assert get_sum(stock, a, b) == TARGET, f"stock checksum {a:#x} invalid (wrong or damaged file)"
    d = bytearray(stock)

    # ---- stock assumptions (fail loudly on a different software version)
    tl_orig, rd_orig = u32(stock, HOOK_TL), u32(stock, HOOK_READER)
    assert tl_orig == 0x38BF017E, "0x9B2A8 is not addi r5,r31,382 - wrong SW?"
    assert (rd_orig >> 26) not in (16, 18, 19), "reader displaced instruction is a branch"
    assert rd_orig == 0xA9450000, "0xF94DC first instruction is not lha r10,0(r5) - wrong SW?"
    assert u32(stock, PTR_TABLE + 4 * SOI_INDEX) == SOI_STOCK_ADDR, "SOI pointer index mismatch"
    assert u32(stock, PTR_TABLE + 4 * (SOI_INDEX + 1)) == SOI_STOCK_ADDR + SOI_LEN, "SOI length mismatch"
    soi_words = []
    for site, rd in HOOK_SOI:
        w = u32(stock, site)
        assert w == _d(32, rd, 15, 1068), f"{site:#x}: not lwz r{rd},1068(r15)"
        soi_words.append(w)

    # ---- allocation (sizes from each map's own header)
    sizes = [map_size(stock, h) for _, h in MAPS_READER]
    s1, s2, off1, off2 = [], [], 0, 0
    for sz in sizes:
        s1.append(MAP_S1_AREA + off1); s2.append(MAP_S2_AREA + off2)
        off1 += (sz + 3) & ~3; off2 += (sz + 3) & ~3
    assert off1 <= MAP_AREA_LEN and off2 <= MAP_AREA_LEN, "clone area too small"

    tl_code = tl_thunk(tl_orig)
    rd_code = reader_thunk(rd_orig, s1, s2)
    soi_code = [soi_thunk(THUNK_SOI[i], HOOK_SOI[i][0], HOOK_SOI[i][1], soi_words[i]) for i in range(2)]
    assert len(tl_code) <= THUNK_LEN["TL"] and len(rd_code) <= THUNK_LEN["READER"]
    assert all(len(c) <= THUNK_LEN["SOI"] for c in soi_code)

    # ---- DOI block: clone per slot and redirect the 18 block-pointer loads
    doi_disp = {0x00: 0x478, 0x18: 0x47C, 0x20: 0x480, 0x26: 0x484}
    for i, want in enumerate((DOI_SRC, DOI_SRC + 0x18, DOI_SRC + 0x20, DOI_SRC + 0x26)):
        assert u32(stock, PTR_TABLE + 4 * (286 + i)) == want, "DOI pointer table mismatch"
    doi_code = []
    for i, (site, reg, off) in enumerate(DOI_SITES):
        assert u32(stock, site) == _d(32, reg, 15, doi_disp[off]), \
            f"{site:#x}: not lwz r{reg},{doi_disp[off]:#x}(r15)"
        code = doi_thunk(DOI_THUNK + i * DOI_STRIDE, site, reg, off)
        assert len(code) <= DOI_STRIDE, f"DOI thunk {i} too long: {len(code)}"
        doi_code.append(code)

    alloc = [("TL thunk", THUNK_TL, len(tl_code)), ("reader thunk", THUNK_READER, len(rd_code)),
             ("SOI thunk A", THUNK_SOI[0], len(soi_code[0])), ("SOI thunk B", THUNK_SOI[1], len(soi_code[1])),
             ("SOI slot1", SOI_S1_BASE, SOI_LEN), ("SOI slot2", SOI_S2_BASE, SOI_LEN),
             ("DOI slot1", DOI_S1, DOI_LEN), ("DOI slot2", DOI_S2, DOI_LEN),
             ("DOI table", DOI_TABLE, 16)]
    for i, code in enumerate(doi_code):
        alloc.append((f"DOI thunk {i}", DOI_THUNK + i * DOI_STRIDE, len(code)))
    for i, (n, h) in enumerate(MAPS_READER):
        alloc += [(f"S1 {n}", s1[i], sizes[i]), (f"S2 {n}", s2[i], sizes[i])]
    alloc.sort(key=lambda x: x[1])
    for (n, a, l), (n2, a2, l2) in zip(alloc, alloc[1:]):
        assert a + l <= a2, f"OVERLAP: {n} [{a:#x},{a+l:#x}) vs {n2} [{a2:#x},{a2+l2:#x})"
    for n, a, l in alloc:
        assert FREE_LO <= a and a + l <= FREE_HI, f"{n} outside verified free run"
        assert stock[a:a + l] == b"\xFF" * l, f"{n} @{a:#x}+{l:#x} is NOT erased in stock"

    # ---- write
    for i, (n, h) in enumerate(MAPS_READER):
        d[s1[i]:s1[i] + sizes[i]] = stock[h:h + sizes[i]]
        d[s2[i]:s2[i] + sizes[i]] = stock[h:h + sizes[i]]
    for base in (SOI_S1_BASE, SOI_S2_BASE):
        d[base:base + SOI_LEN] = stock[SOI_STOCK_ADDR:SOI_STOCK_ADDR + SOI_LEN]
    d[DOI_S1:DOI_S1 + DOI_LEN] = stock[DOI_SRC:DOI_END]
    d[DOI_S2:DOI_S2 + DOI_LEN] = stock[DOI_SRC:DOI_END]
    d[DOI_TABLE:DOI_TABLE + 16] = struct.pack(">4I", DOI_SRC, DOI_S1, DOI_S2, DOI_SRC)
    for i, code in enumerate(doi_code):
        base = DOI_THUNK + i * DOI_STRIDE
        d[base:base + len(code)] = code
    for i, (site, reg, off) in enumerate(DOI_SITES):
        d[site:site + 4] = b_insn(site, DOI_THUNK + i * DOI_STRIDE)
    d[THUNK_TL:THUNK_TL + len(tl_code)] = tl_code
    d[THUNK_READER:THUNK_READER + len(rd_code)] = rd_code
    for i in range(2):
        d[THUNK_SOI[i]:THUNK_SOI[i] + len(soi_code[i])] = soi_code[i]
    d[HOOK_TL:HOOK_TL + 4] = b_insn(HOOK_TL, THUNK_TL)
    d[HOOK_READER:HOOK_READER + 4] = b_insn(HOOK_READER, THUNK_READER)
    for i, (site, _) in enumerate(HOOK_SOI):
        d[site:site + 4] = b_insn(site, THUNK_SOI[i])
    # ---- trigger parameters (WinOLS-tunable, in verified-erased filler)
    assert FREE_LO <= PARAM_BASE and PARAM_BASE + 4 <= FREE_HI, "parameter area outside free run"
    assert stock[PARAM_BASE:PARAM_BASE + 4] == b"\xFF" * 4, "parameter area is not erased in stock"
    _src = DEF_MAPS_SRC if SRC_OVERRIDE is None else SRC_OVERRIDE
    d[PARAM_BASE:PARAM_BASE + 4] = bytes([DEF_MASK_NEXT, DEF_MASK_PREV, DEF_MAPS_CFG, _src])
    fix_checksums(d)
    open(OUTPUT_FILE, "wb").write(d)

    print(f"[+] {'INERT ' if INERT else ''}build written: {OUTPUT_FILE}")
    print(f"    thunks: TL {len(tl_code)} B, reader {len(rd_code)} B, SOI {len(soi_code[0])}+{len(soi_code[1])} B")
    print(f"    clones: {len(MAPS_READER)} maps x 2 slots ({off1} B/slot) + SOI block {SOI_LEN:#x} B x 2")
    print(f"    DOI: block {DOI_LEN:#x} B x 2, table @{DOI_TABLE:#x}, {len(DOI_SITES)} block-load hooks")
    print(f"    changed bytes vs stock: {sum(1 for i in range(len(d)) if d[i] != stock[i])}")
    print("    map layout (name header -> slot1 / slot2 / size):")
    for i, (n, h) in enumerate(MAPS_READER):
        print(f"      {n:14s} {h:#08x} -> {s1[i]:#08x} / {s2[i]:#08x}  {sizes[i]} B")
    print("    NOTE: run validate_build.py before flashing; see README 'Verification status'.")


if __name__ == "__main__":
    main()
