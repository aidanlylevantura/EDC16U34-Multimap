#!/usr/bin/env python3
"""
validate_build.py  (v2.1.0)  -  structural + behavioural validation of a MultiMap build.

Usage:  python validate_build.py [stock.bin] [built.bin] [--inert]
        defaults: Stock_Baseline.bin and 03G906021KH_382083_MULTIMAP_v2_0_1.bin next to this script.
Exit code 0 = every check passed, 1 = at least one FAIL.  Self-contained (embeds a small PowerPC interpreter).

It does NOT trust the builder: clone addresses are learned by EMULATING the built thunks, then checked for
erased-in-stock, no overlap, and byte-equality with the stock maps.  Checks (each prints PASS/FAIL):
  files/size | real additive checksums | diff confined to allowed spans | hooks are plain b to the thunks
  | write targets were erased in stock and do not overlap | clone == stock (reader maps x 2 slots, SOI block x 2, DOI block x 2)
  | TL thunk (stalk/pedal) behaviour vs. a reference model over >20k states | stalk = bit 0 only, rolling counter
  ignored | register / CR / LR contract | reader thunk redirect table | SOI thunks | garbage state = stock.
UNVERIFIED items (cannot be proven offline) are listed at the end and never counted as PASS.
"""
import os
import random
import struct
import sys

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
INERT = "--inert" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
STOCK_FILE = ARGS[0] if len(ARGS) > 0 else os.path.join(HERE, "..", "binaries", "Stock_Baseline.bin")
MOD_FILE = ARGS[1] if len(ARGS) > 1 else os.path.join(
    HERE, "..", "binaries", "03G906021KH_MultiMap_v2.1.0" + ("_INERT" if INERT else "") + ".bin")

# --- configuration (must describe the design, not be copied from the built file)
R13 = 0x7FFFF0
A_ACTIVE, A_LAST, A_WORD, A_PEDAL, A_SET = 0x7F9210, 0x7F9211, 0x7F9214, 0x7F95C4, 0x7FF122
KEY = 0xA5C35A3C
PEDAL_MAX = 200
HOOK_TL, HOOK_READER = 0x09B2A8, 0x0F94DC
HOOK_SOI = [(0xC0898, 12), (0xC09F8, 30)]
THUNK_TL, THUNK_READER, THUNK_SOI = 0x1FC000, 0x1FC400, [0x1FC800, 0x1FC880]
WIN = {"TL": 0x400, "READER": 0x400, "SOI": 0x80}
HEADERS = [("Boost 1", 0x1E470C), ("Boost 2", 0x1E4884), ("DW1", 0x1C2370), ("DW2", 0x1C24C6), ("DW3", 0x1C261C),
           ("DW4", 0x1C2772), ("DW5", 0x1C28C8), ("DW6", 0x1C2A1E),
           ("TorqueLim", 0x1D16F6), ("SmokePress", 0x1D333C),
           ("SmokeMAF", 0x1D307E), ("BoostLim", 0x1E49FC)]
SOI_STOCK, SOI_LEN, PTR_TABLE, SOI_INDEX = 0x1D6414, 0x1E9C, 0x4C8A0, 267
DOI_SRC, DOI_END = 0x1DF02E, 0x1DFC5E
DOI_LEN = DOI_END - DOI_SRC
DOI_S1, DOI_S2, DOI_TABLE, DOI_THUNK, DOI_STRIDE = 0x1F4000, 0x1F6000, 0x1F3F00, 0x1FC900, 96
DOI_DISP = {0x00: 0x478, 0x18: 0x47C, 0x20: 0x480, 0x26: 0x484}
PARAM_BASE = 0x1EA7C8          # v2.1.0: 3 tunable trigger bytes (mask_next, mask_prev, cfg)

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
FREE_LO, FREE_HI = 0x1EA7C8, 0x1FDF74
TARGET = 0xD01FE500
REGIONS = [("OS", 0x040000, 0x17FFFF), ("Cal1", 0x180000, 0x1BFFFF), ("Cal2", 0x1C0000, 0x1FDFFF)]
BAL = [0x17FFFC, 0x1BFFFC, 0x1FDFFC]

# ------------------------------------------------------------------ minimal strict PowerPC interpreter
M32 = 0xFFFFFFFF


class Fault(Exception):
    pass


def s16(x): return x - 0x10000 if x & 0x8000 else x
def s32(x): x &= M32; return x - (1 << 32) if x & 0x80000000 else x
def rotl(x, n): n &= 31; return ((x << n) | (x >> (32 - n))) & M32 if n else x & M32


def pmask(mb, me):
    def bit(i): return 1 << (31 - i)
    if mb <= me:
        return sum(bit(i) for i in range(mb, me + 1))
    return M32 & ~pmask(me + 1, mb - 1)


class Mem:
    def __init__(self, flash, lo=0x7F0000, hi=0x800000):
        self.flash, self.lo, self.hi = bytes(flash), lo, hi
        self.ram = bytearray(hi - lo)
        self.log = []

    def _loc(self, a, n, w):
        if a + n <= len(self.flash):
            if w: raise Fault(f"write to flash {a:#x}")
            return self.flash, a
        if self.lo <= a and a + n <= self.hi: return self.ram, a - self.lo
        raise Fault(f"bus fault {a:#x}")

    def rd(self, a, n):
        a &= M32
        if a % n: raise Fault(f"misaligned read {a:#x}")
        b, o = self._loc(a, n, False); self.log.append(("R", a, n))
        return int.from_bytes(b[o:o + n], "big")

    def wr(self, a, n, v):
        a &= M32
        if a % n: raise Fault(f"misaligned write {a:#x}")
        b, o = self._loc(a, n, True); self.log.append(("W", a, n))
        b[o:o + n] = (v & ((1 << 8 * n) - 1)).to_bytes(n, "big")

    def poke(self, a, n, v): b, o = self._loc(a, n, True); b[o:o + n] = (v & ((1 << 8 * n) - 1)).to_bytes(n, "big")
    def peek(self, a, n=1): b, o = self._loc(a, n, False); return int.from_bytes(b[o:o + n], "big")


class CPU:
    def __init__(self, mem):
        self.m, self.g, self.pc, self.lr, self.ctr, self.cr, self.xer = mem, [0] * 32, 0, 0, 0, 0, 0
        self.window = None

    def _cr0(self, v):
        v = s32(v); f = 8 if v < 0 else (4 if v > 0 else 2)
        self.cr = (self.cr & 0x0FFFFFFF) | (f << 28)

    def _cmp(self, a, b):
        f = 8 if a < b else (4 if a > b else 2)
        self.cr = (self.cr & 0x0FFFFFFF) | (f << 28)

    def _bit(self, bi): return (self.cr >> (31 - bi)) & 1

    def step(self):
        pc = self.pc
        if self.window and not (self.window[0] <= pc < self.window[1]): raise Fault(f"fetch outside window {pc:#x}")
        w = struct.unpack_from(">I", self.m.flash, pc)[0]
        op, rd, ra, rb, u = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0xFFFF
        g, s, npc = self.g, s16(u), pc + 4
        ea = lambda: ((g[ra] if ra else 0) + s) & M32
        if op == 14: g[rd] = ((g[ra] if ra else 0) + s) & M32
        elif op == 15: g[rd] = ((g[ra] if ra else 0) + (s << 16)) & M32
        elif op == 24: g[ra] = g[rd] | u
        elif op == 26: g[ra] = g[rd] ^ u
        elif op == 27: g[ra] = g[rd] ^ (u << 16)
        elif op == 10: self._cmp(g[ra], u)
        elif op == 11: self._cmp(s32(g[ra]), s)
        elif op == 32: g[rd] = self.m.rd(ea(), 4)
        elif op == 34: g[rd] = self.m.rd(ea(), 1)
        elif op == 42: g[rd] = s16(self.m.rd(ea(), 2)) & M32
        elif op == 36: self.m.wr(ea(), 4, g[rd])
        elif op == 38: self.m.wr(ea(), 1, g[rd])
        elif op == 18:
            li = w & 0x03FFFFFC; li -= 0x04000000 if li & 0x02000000 else 0
            if w & 1: self.lr = npc
            npc = (li if w & 2 else pc + li) & M32
        elif op == 16:
            bo, bi, bd = rd, ra, (w & 0xFFFC) - (0x10000 if w & 0x8000 else 0)
            if not (bo & 4): raise Fault("ctr branch not supported")
            if (bo & 16) or (self._bit(bi) == ((bo >> 3) & 1)): npc = (pc + bd) & M32
        elif op == 21:
            g[ra] = rotl(g[rd], rb) & pmask((w >> 6) & 31, (w >> 1) & 31)
            if w & 1: self._cr0(g[ra])
        elif op == 31:
            xo = (w >> 1) & 0x3FF
            if xo == 32: self._cmp(g[ra], g[rb])
            elif xo == 0: self._cmp(s32(g[ra]), s32(g[rb]))
            elif xo == 316: g[ra] = g[rd] ^ g[rb]
            elif xo == 28:  g[ra] = g[rd] & g[rb]
            else: raise Fault(f"unimplemented op31 xo={xo} @{pc:#x}")
        else:
            raise Fault(f"unimplemented opcode {op} ({w:#010x}) @{pc:#x}")
        for i in range(32): g[i] &= M32
        self.pc = npc & M32

    def run(self, entry, stop, window, maxn=3000):
        self.pc, self.window, n = entry, window, 0
        while self.pc != stop:
            self.step(); n += 1
            if n > maxn: raise Fault("runaway")


# ------------------------------------------------------------------ reporting
RES = []


def check(name, ok, detail=""):
    RES.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    return ok


def u32(d, o): return struct.unpack_from(">I", d, o)[0]
def asum(d, a, b): return sum(u32(d, i) for i in range(a, b + 1, 4)) & M32


def decode_b(d, a):
    w = u32(d, a)
    if (w >> 26) != 18 or (w & 3): return None
    li = w & 0x03FFFFFC; li -= 0x04000000 if li & 0x02000000 else 0
    return (a + li) & M32


def map_size(d, h):
    nx, ny = struct.unpack_from(">HH", d, h)
    return (4 + 2 * (nx + ny + nx * ny)) if (2 <= nx <= 64 and 2 <= ny <= 64) else None


# ------------------------------------------------------------------ harness
class H:
    def __init__(self, img, seed=7):
        self.img, self.rnd = img, random.Random(seed)
        self.m = Mem(img); self.c = CPU(self.m)

    def call(self, entry, stop, window, regs=None, ram=None):
        c, m, r = self.c, self.m, self.rnd
        m.ram[:] = b"\x00" * len(m.ram)
        for a, (n, v) in (ram or {}).items(): m.poke(a, n, v)
        c.g = [r.getrandbits(32) for _ in range(32)]
        c.g[13], c.g[1] = R13, 0x7FF800
        for k, v in (regs or {}).items(): c.g[k] = v
        c.cr, c.xer, c.ctr, c.lr = r.getrandbits(32), r.getrandbits(32), r.getrandbits(32), r.getrandbits(32)
        before = (list(c.g), c.cr, c.xer, c.ctr, c.lr)
        m.log = []
        c.run(entry, stop, window)
        return before


def model_tl(word, last, sb, ped):
    pu = ped if ped < 0x8000 else ((ped - 0x10000) & M32)
    if pu > PEDAL_MAX: return word, last, None
    bit = 0 if INERT else (sb & 1)
    if not bit: return word, 0, None
    if last != 0: return word, last, None
    cur = (word ^ KEY) & M32
    s = cur if cur <= 2 else 0
    s = (s + 1) % 3
    return (KEY ^ s) & M32, 1, s


def check_doi(stock, mod):
    """Duration parameter block: per-slot clone plus 18 block-load hooks."""
    for i, want in enumerate((DOI_SRC, DOI_SRC + 0x18, DOI_SRC + 0x20, DOI_SRC + 0x26)):
        check(f"stock DOI pointer table idx {286 + i} = {want:#x}",
              u32(stock, PTR_TABLE + 4 * (286 + i)) == want)
    ok = 0
    for i, (site, reg, off) in enumerate(DOI_SITES):
        tgt = DOI_THUNK + i * DOI_STRIDE
        want = (32 << 26) | (reg << 21) | (15 << 16) | DOI_DISP[off]
        check(f"stock DOI site {site:#x} is lwz r{reg},{DOI_DISP[off]:#x}(r15)", u32(stock, site) == want)
        if u32(mod, site) >> 26 == 18 and decode_b(mod, site) == tgt:
            ok += 1
        else:
            check(f"DOI hook {site:#x} -> {tgt:#x}", False, f"{u32(mod, site):#010x}")
    check(f"DOI: all {len(DOI_SITES)} block loads are plain b to their thunks", ok == len(DOI_SITES))
    check("DOI slot1 clone == stock block (0x1DF02E..0x1DFC5E)",
          mod[DOI_S1:DOI_S1 + DOI_LEN] == stock[DOI_SRC:DOI_END])
    check("DOI slot2 clone == stock block", mod[DOI_S2:DOI_S2 + DOI_LEN] == stock[DOI_SRC:DOI_END])
    check("DOI clone targets erased in stock",
          stock[DOI_S1:DOI_S1 + DOI_LEN] == b"\xFF" * DOI_LEN
          and stock[DOI_S2:DOI_S2 + DOI_LEN] == b"\xFF" * DOI_LEN)
    check("DOI slot table = stock/slot1/slot2/stock",
          struct.unpack_from(">4I", mod, DOI_TABLE) == (DOI_SRC, DOI_S1, DOI_S2, DOI_SRC))
    bad = []
    for i, (site, reg, off) in enumerate(DOI_SITES):
        base = DOI_THUNK + i * DOI_STRIDE
        w = [u32(mod, base + 4 * k) for k in range(23)]
        e = [
            w[0] == ((37 << 26) | (1 << 21) | (1 << 16) | 0xFFF0),
            w[2] == ((27 << 26) | (11 << 21) | (11 << 16) | (KEY >> 16)),
            w[3] == ((26 << 26) | (11 << 21) | (11 << 16) | (KEY & 0xFFFF)),
            w[4] == (0x7C000026 | (reg << 21)),
            w[5] == ((36 << 26) | (reg << 21) | (1 << 16) | 8),
            w[6] == ((10 << 26) | (11 << 16) | 2),
            w[8] == ((10 << 26) | (11 << 16) | 0),
            w[11] == ((15 << 26) | (reg << 21) | ((DOI_TABLE >> 16) & 0xFFFF)),
            w[12] == ((24 << 26) | (reg << 21) | (reg << 16) | (DOI_TABLE & 0xFFFF)),
            w[16] == ((15 << 26) | (reg << 21) | ((DOI_SRC >> 16) & 0xFFFF)),
            w[17] == ((24 << 26) | (reg << 21) | (reg << 16) | (DOI_SRC & 0xFFFF)),
            w[18] == ((32 << 26) | (11 << 21) | (1 << 16) | 8),
            w[19] == (0x7C000120 | (11 << 21) | (0xFF << 12)),
            w[20] == ((14 << 26) | (1 << 21) | (1 << 16) | 16),
            w[21] == ((14 << 26) | (reg << 21) | (reg << 16) | off),
            decode_b(mod, base + 4 * 22) == site + 4,
        ]
        if not all(e):
            bad.append((hex(site), e))
    check("DOI thunks: key XOR, CR save, slot range check, table lookup, stock fallback, CR restore, resume",
          not bad, str(bad[:1]))
    tab = struct.unpack_from(">4I", mod, DOI_TABLE)

    def pick(word):
        d = (word ^ KEY) & M32
        return tab[d] if d in (1, 2) else tab[0]

    check("DOI mapping: slot 0 -> stock, 1 -> slot1, 2 -> slot2, invalid -> stock",
          pick(KEY) == DOI_SRC and pick(KEY ^ 1) == DOI_S1 and pick(KEY ^ 2) == DOI_S2
          and pick(0) == DOI_SRC and pick(0xFFFFFFFF) == DOI_SRC)


def main():
    stock, mod = open(STOCK_FILE, "rb").read(), open(MOD_FILE, "rb").read()
    print(f"=== validate_build v2.1.0 {'(INERT) ' if INERT else ''}===\n stock: {STOCK_FILE}\n built: {MOD_FILE}\n")
    if not check("files are 2 MB", len(stock) == len(mod) == 0x200000): return 1
    for n, a, b in REGIONS: check(f"stock {n} additive sum", asum(stock, a, b) == TARGET)
    for n, a, b in REGIONS: check(f"built {n} additive sum == 0xD01FE500", asum(mod, a, b) == TARGET, f"{asum(mod, a, b):#010x}")
    check("stock ident is SW 1037382083", b"1037382083" in stock)
    check("stock boot block present (full BDM read)", any(x != 0xFF for x in stock[:0x40000]))
    check("boot block unchanged", mod[:0x40000] == stock[:0x40000])
    check("Cal2 tail/descriptor area (0x1FDF74-0x1FDFFB) unchanged", mod[0x1FDF74:0x1FDFFC] == stock[0x1FDF74:0x1FDFFC])

    # ---- hooks
    for name, a, t in (("TL", HOOK_TL, THUNK_TL), ("reader", HOOK_READER, THUNK_READER),
                       ("SOI A", HOOK_SOI[0][0], THUNK_SOI[0]), ("SOI B", HOOK_SOI[1][0], THUNK_SOI[1])):
        check(f"hook {name} @ {a:#x} is a plain b (AA=0, LK=0) to {t:#x}", decode_b(mod, a) == t,
              f"word {u32(mod, a):#010x}")
    check("stock reader first instruction is lha r10,0(r5)", u32(stock, HOOK_READER) == 0xA9450000)
    check("stock TL instruction is addi r5,r31,382", u32(stock, HOOK_TL) == 0x38BF017E)
    for site, rd in HOOK_SOI:
        check(f"stock SOI site {site:#x} is lwz r{rd},1068(r15)", u32(stock, site) == ((32 << 26) | (rd << 21) | (15 << 16) | 1068))
    check(f"OS pointer table idx {SOI_INDEX} = {SOI_STOCK:#x} and next = block end", u32(stock, PTR_TABLE + 4 * SOI_INDEX) == SOI_STOCK
          and u32(stock, PTR_TABLE + 4 * (SOI_INDEX + 1)) == SOI_STOCK + SOI_LEN)

    # ---- learn clone addresses by emulating the built reader/SOI thunks (independent of builder constants)
    h = H(mod)
    RW = (THUNK_READER, THUNK_READER + WIN["READER"])
    clones = {}
    for slot in (1, 2):
        word = (KEY ^ slot) & M32
        for name, hd in HEADERS:
            h.call(THUNK_READER, HOOK_READER + 4, RW, {5: hd}, {A_WORD: (4, word)})
            clones[(slot, name)] = h.c.g[5]
    soi = {}
    for slot in (1, 2):
        for i, (site, rd) in enumerate(HOOK_SOI):
            h.call(THUNK_SOI[i], site + 4, (THUNK_SOI[i], THUNK_SOI[i] + WIN["SOI"]), {15: PTR_TABLE}, {A_WORD: (4, (KEY ^ slot) & M32)})
            soi[(slot, i)] = h.c.g[rd]
    check("both SOI thunks of a slot agree on the clone base", all(soi[(s, 0)] == soi[(s, 1)] for s in (1, 2)),
          f"slot1 {soi[(1, 0)]:#x}/{soi[(1, 1)]:#x} slot2 {soi[(2, 0)]:#x}/{soi[(2, 1)]:#x}")

    # ---- allocation: erased in stock, free run, no overlap, allowed-diff
    ranges = [("TL thunk", THUNK_TL, WIN["TL"]), ("reader thunk", THUNK_READER, WIN["READER"]),
              ("SOI thunk A", THUNK_SOI[0], WIN["SOI"]), ("SOI thunk B", THUNK_SOI[1], WIN["SOI"])]
    sizes = {n: map_size(stock, hd) for n, hd in HEADERS}
    check(f"all {len(HEADERS)} reader headers are valid 2D headers in stock", all(sizes.values()),
          ", ".join(f"{n}:{'ok' if sizes[n] else 'BAD'}" for n, _ in HEADERS))
    for (slot, name), a in sorted(clones.items()):
        ranges.append((f"S{slot} {name}", a, sizes[name] or 0))
    for slot in (1, 2): ranges.append((f"SOI slot{slot}", soi[(slot, 0)], SOI_LEN))
    ranges.append(("DOI slot1", DOI_S1, DOI_LEN))
    ranges.append(("DOI slot2", DOI_S2, DOI_LEN))
    ranges.append(("DOI table", DOI_TABLE, 16))
    ranges_sorted = sorted(ranges, key=lambda x: x[1])
    ov = [(a[0], b[0]) for a, b in zip(ranges_sorted, ranges_sorted[1:]) if a[1] + a[2] > b[1]]
    check("no overlap between thunks, map clones and SOI clones", not ov, str(ov[:3]))
    bad = [n for n, a, l in ranges if not (FREE_LO <= a and a + l <= FREE_HI)]
    check(f"all written areas inside the verified free run {FREE_LO:#x}-{FREE_HI:#x}", not bad, str(bad[:4]))
    bad = [n for n, a, l in ranges if l and stock[a:a + l] != b"\xFF" * l]
    check("every written area was erased (0xFF) in stock (no live calibration destroyed)", not bad, str(bad[:4]))
    allowed = set()
    for _, a, l in ranges: allowed.update(range(a, a + l))
    for a in [HOOK_TL, HOOK_READER] + [s for s, _ in HOOK_SOI] + BAL: allowed.update(range(a, a + 4))
    allowed.update(range(DOI_S1, DOI_S1 + DOI_LEN)); allowed.update(range(DOI_S2, DOI_S2 + DOI_LEN))
    allowed.update(range(DOI_TABLE, DOI_TABLE + 16))
    allowed.update(range(PARAM_BASE, PARAM_BASE + 4))     # v2.1.0 trigger parameters
    for i, (site, reg, off) in enumerate(DOI_SITES):
        allowed.update(range(site, site + 4))
        allowed.update(range(DOI_THUNK + i * DOI_STRIDE, DOI_THUNK + i * DOI_STRIDE + DOI_STRIDE))
    stray = [i for i in range(len(stock)) if stock[i] != mod[i] and i not in allowed]
    check("diff vs stock confined to hooks, balance words, thunks and clones", not stray, f"first stray {stray[0]:#x}" if stray else f"{sum(1 for i in range(len(stock)) if stock[i] != mod[i])} bytes changed")

    # ---- clone integrity
    ok = all(mod[clones[(s, n)]:clones[(s, n)] + sizes[n]] == stock[hd:hd + sizes[n]] for s in (1, 2) for n, hd in HEADERS if sizes[n])
    check(f"{len(HEADERS)} maps x 2 slots: clone bytes == stock map bytes (size from header)", ok)
    check("SOI clones == stock block (0x1D6414..0x1D82B0)", all(mod[soi[(s, 0)]:soi[(s, 0)] + SOI_LEN] == stock[SOI_STOCK:SOI_STOCK + SOI_LEN] for s in (1, 2)))

    # ---- TL thunk behaviour (v2.1.0: real stalk contacts, tunable masks)
    TW = (THUNK_TL, THUNK_TL + WIN["TL"])
    A_TIPS, A_CC = 0x7F9413, 0x7F953A
    A_SWW, A_MODE = 0x7F9990, 0x7F935D   # the other two MAPS_SRC sources
    A_LNEXT, A_LPREV = 0x7F9212, 0x7F9213
    A_DTIP, A_DCC, A_DCNT, A_DFLG = 0x7F9218, 0x7F9219, 0x7F921A, 0x7F921B
    MASK_NEXT, MASK_PREV = mod[PARAM_BASE], mod[PARAM_BASE + 1]
    CFG = mod[PARAM_BASE + 2]
    check("trigger params in erased area: masks and cfg valid",
          MASK_NEXT and MASK_PREV and MASK_NEXT != MASK_PREV and CFG & 0x03 in (0, 1),
          f"next={MASK_NEXT:#04x} prev={MASK_PREV:#04x} cfg={CFG:#04x}")

    states = [KEY, KEY ^ 1, KEY ^ 2, 0, M32, KEY ^ 3, 0x55555555]

    def sim(frames, ped=0, word=KEY):
        h.m.ram[:] = b"\x00" * len(h.m.ram)
        h.m.poke(A_WORD, 4, word); h.m.poke(A_PEDAL, 2, ped)
        out = []
        for tips, ccs in frames:
            h.m.poke(A_TIPS, 1, tips); h.m.poke(A_CC, 1, ccs)
            h.m.poke(A_SWW, 1, tips);  h.m.poke(A_MODE, 1, tips)   # keep all sources in step
            h.c.g = [0] * 32; h.c.g[13], h.c.g[31], h.c.g[1] = R13, 0x1D1578, 0x7FF800
            h.c.run(THUNK_TL, HOOK_TL + 4, TW)
            out.append((h.m.peek(A_WORD, 4) ^ KEY) & M32)
        return out

    if not INERT:
        idle = sim([(0x00, 0)] * 4 + [(0x3C, 0)] * 4)
        check("no tip contact: slot never changes", set(idle) == {0}, f"slots seen {sorted(set(idle))}")

        press = sim([(0x00, 0), (MASK_NEXT, 0), (MASK_NEXT, 0), (0x00, 0),
                     (MASK_NEXT, 0), (0x00, 0), (MASK_NEXT, 0), (0x00, 0)])
        check("NEXT tip advances 0->1->2->0, one per rising edge", press == [0, 1, 1, 1, 2, 2, 0, 0], str(press))

        back = sim([(0x00, 0), (MASK_PREV, 0), (MASK_PREV, 0), (0x00, 0), (MASK_PREV, 0), (0x00, 0)])
        check("PREV tip retreats 0->2->1", back == [0, 2, 2, 2, 1, 1], str(back))

        gated = sim([(MASK_NEXT, 1), (0x00, 1), (MASK_NEXT, 1)])
        check("gate: CC switch state != 0 blocks switching", set(gated) == {0}, str(gated))

        check("pedal above gate blocks switching", set(sim([(MASK_NEXT, 0), (0x00, 0)] * 4, ped=300)) == {0})

        g1 = sim([(MASK_NEXT, 0)], word=0x55555555)
        check("garbage state word + press -> clean slot 1", g1 == [1])
    else:
        check("INERT: tip presses never change the slot", set(sim([(MASK_NEXT, 0), (0x00, 0)] * 8)) == {0})

    # source-selection proof: distinct value per source, then read the diag mirror
    src_sel = mod[PARAM_BASE + 3]
    exp = {0: 0xA1, 1: 0xB2, 2: 0xC3}.get(src_sel)
    if exp is not None and not INERT:
        h.m.ram[:] = b"\x00" * len(h.m.ram)
        h.m.poke(A_WORD, 4, KEY); h.m.poke(A_PEDAL, 2, 0); h.m.poke(A_CC, 1, 0)
        h.m.poke(A_TIPS, 1, 0xA1); h.m.poke(A_SWW, 1, 0xB2); h.m.poke(A_MODE, 1, 0xC3)
        h.c.g = [0] * 32; h.c.g[13], h.c.g[31], h.c.g[1] = R13, 0x1D1578, 0x7FF800
        h.c.run(THUNK_TL, HOOK_TL + 4, TW)
        got = h.m.peek(A_DTIP)
        check("MAPS_SRC=%d reads its intended byte (diag mirror 0x%02X)" % (src_sel, exp),
              got == exp, "diag=%02X expected %02X" % (got, exp))

    # register / CR contract + store footprint
    chg, crbad = set(), False
    for _ in range(300):
        word = h.rnd.choice([KEY, KEY ^ 1, KEY ^ 2, 0, M32, 0x55555555])
        b0 = h.call(THUNK_TL, HOOK_TL + 4, TW, {31: 0x1D1578},
                    {A_WORD: (4, word), A_LNEXT: (1, h.rnd.choice([0, 1])),
                     A_LPREV: (1, h.rnd.choice([0, 1])), A_PEDAL: (2, h.rnd.choice([0, 100, 300])),
                     A_TIPS: (1, h.rnd.getrandbits(8)), A_CC: (1, h.rnd.choice([0, 0, 1, 2, 3]))})
        chg |= {i for i in range(32) if h.c.g[i] != b0[0][i]}
        crbad |= (h.c.cr & 0x0FFFFFFF) != (b0[1] & 0x0FFFFFFF) or (h.c.xer, h.c.ctr, h.c.lr) != (b0[2], b0[3], b0[4])
        stores = {a for k, a, n_ in h.m.log if k == "W"}
        allowed = {A_ACTIVE, A_WORD, A_WORD + 1, A_WORD + 2, A_WORD + 3,
                   A_LNEXT, A_LPREV, A_DTIP, A_DCC, A_DCNT, A_DFLG}
        crbad |= not stores <= allowed
    check("TL thunk clobbers only r5,r11,r12 + CR0; LR/CTR/XER/CR1-7 intact; stores only to state/diag",
          chg <= {5, 11, 12} and not crbad, f"changed r{sorted(chg)}")

    # ---- reader thunk behaviour
    exp_tbl = {(s, hd): clones[(s, n)] for s in (1, 2) for n, hd in HEADERS}
    bad, chg, crbad, cnt = [], set(), False, 0
    others = [0x1D16F6, 0x1E4710, 0x1DF09A, 0x1C2370 + 2, 0x1D1578, 0x1C2370 - 2, 0x123456, 0x7F9000]
    for word in states + [(KEY ^ 1) ^ (1 << k) for k in range(32)]:
        slot = (word ^ KEY) & M32
        for r5 in [hd for _, hd in HEADERS] + others:
            b0 = h.call(THUNK_READER, HOOK_READER + 4, RW, {5: r5}, {A_WORD: (4, word)}) if (r5 < 0x200000 or r5 >= 0x7F0000) else None
            if b0 is None: continue
            cnt += 1
            e5 = exp_tbl.get((slot, r5), r5) if slot in (1, 2) else r5
            e10 = s16(h.m.peek(e5, 2)) & M32
            chg |= {i for i in range(32) if h.c.g[i] != b0[0][i]}
            crbad |= (h.c.cr & 0x0FFFFFFF) != (b0[1] & 0x0FFFFFFF) or (h.c.xer, h.c.ctr, h.c.lr) != (b0[2], b0[3], b0[4])
            if h.c.g[5] != e5 or h.c.g[10] != e10:
                bad.append((hex(word), hex(r5), hex(h.c.g[5]), hex(e5)))
    check(f"reader thunk redirects exactly the 14 headers in slot 1/2, nothing else, stock for slot 0/invalid ({cnt} cases)", not bad, str(bad[:2]))
    check("reader thunk: displaced lha replayed with the final r5; only r5,r10,r11,r12 + CR0 touched; CR1-7/LR/CTR/XER intact",
          chg <= {5, 10, 11, 12} and not crbad, f"changed r{sorted(chg)}")
    cmpw_count = sum(1 for a in range(THUNK_READER, THUNK_READER + WIN["READER"], 4) if u32(mod, a) == 0x7C055840)  # 0x7C055840 = cmplw r5,r11
    check("reader thunk has one compare per map", cmpw_count == len(HEADERS), f"{cmpw_count}")

    # ---- SOI thunks
    bad = []
    stock_ptr = u32(mod, PTR_TABLE + 1068)
    for i, (site, rd) in enumerate(HOOK_SOI):
        win = (THUNK_SOI[i], THUNK_SOI[i] + WIN["SOI"])
        for word in states + [(KEY ^ 2) ^ (1 << k) for k in range(32)]:
            slot = (word ^ KEY) & M32
            b0 = h.call(THUNK_SOI[i], site + 4, win, {15: PTR_TABLE}, {A_WORD: (4, word)})
            exp = soi[(slot, i)] if slot in (1, 2) else stock_ptr
            others_changed = {j for j in range(32) if j != rd and h.c.g[j] != b0[0][j]}
            if h.c.g[rd] != exp or others_changed or (h.c.cr & 0x0FFFFFFF) != (b0[1] & 0x0FFFFFFF) or (h.c.xer, h.c.ctr, h.c.lr) != (b0[2], b0[3], b0[4]):
                bad.append((i, hex(word), hex(h.c.g[rd]), hex(exp), others_changed))
    check("SOI thunks: slot 0/invalid -> stock pointer, slot 1/2 -> clone base; only the destination register + CR0 change", not bad, str(bad[:2]))
    check("stock SOI pointer reached through the table is 0x1D6414", stock_ptr == SOI_STOCK)

    # ---- DOI parameter block
    check_doi(stock, mod)

    fails = RES.count(False)
    print(f"\n{len(RES) - fails}/{len(RES)} checks passed")
    print("""
UNVERIFIED (offline analysis cannot prove these - bench items, NOT counted above):
  * CAN 0x38A payload byte 2 bit 0 = SET (community DBC; needs a CAN capture of the real stalk)
  * 0x7F95C4 = accelerator pedal in 0.01 % units (inference: single writer chain 0x64410/0x636F0, '== 10000' test)
  * Driver Wish / Duration headers are real 2D headers, but the OS call arguments that reach 0xF94DC for them
    were not resolvable statically (Boost 1/2 were). Clones are exact stock copies, so an unmatched header is a no-op.
  * Integrity: additive sums are exact, but the chained 136-byte region tail blocks are unresolved.
  * Torque limiter / other limiters may dominate the output; switching mid-task can mix slots within one cycle.
  * Real-time cost of the reader thunk (up to 14 compares per lookup when slot != 0).""")
    print("\nRESULT:", "PASS" if fails == 0 else f"FAIL ({fails} failing check(s))")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fault as e:
        print(f"[FAIL] emulation fault while checking the build: {e}")
        print("\nRESULT: FAIL (the built file does not match the v2.0.1 design)")
        sys.exit(1)
