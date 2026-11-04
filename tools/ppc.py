"""Minimal big-endian PowerPC (MPC5xx) disassembler for offline analysis.

Only decodes the instruction subset needed to read EDC16 firmware; unknown
opcodes are emitted as .word so nothing is silently misrepresented.
"""
import struct

SPR = {1: "xer", 8: "lr", 9: "ctr", 26: "srr0", 27: "srr1", 256: "vrsave",
       287: "pvr", 528: "ibat0u", 529: "ibat0l", 530: "ibat1u", 531: "ibat1l",
       532: "ibat2u", 533: "ibat2l", 534: "ibat3u", 535: "ibat3l",
       536: "dbat0u", 537: "dbat0l", 538: "dbat1u", 539: "dbat1l",
       540: "dbat2u", 541: "dbat2l", 542: "dbat3u", 543: "dbat3l"}

CR_FIELDS = ["lt", "gt", "eq", "so"]


def sx(v, bits):
    if v & (1 << (bits - 1)):
        v -= 1 << bits
    return v


def _cr(n):
    return "cr%d" % n if n else "cr0"


def decode(w, addr=0):
    op = w >> 26
    rd = (w >> 21) & 31
    ra = (w >> 16) & 31
    rb = (w >> 11) & 31
    simm = sx(w & 0xFFFF, 16)
    uimm = w & 0xFFFF
    if op == 18:  # b
        li = sx(w & 0x03FFFFFC, 26)
        lk = "l" if w & 1 else ""
        aa = "a" if w & 2 else ""
        return "b%s%s 0x%X" % (lk, aa, (li if w & 2 else addr + li) & 0xFFFFFFFF)
    if op == 16:  # bc
        bo = (w >> 21) & 31
        bi = (w >> 16) & 31
        bd = sx(w & 0xFFFC, 16)
        lk = "l" if w & 1 else ""
        aa = "a" if w & 2 else ""
        return "bc%s %d,%d,0x%X" % (lk, bo, bi, (bd if w & 2 else addr + bd) & 0xFFFFFFFF)
    if op == 15:
        if ra == 0:
            return "lis r%d, 0x%X" % (rd, uimm)
        return "addis r%d, r%d, 0x%X" % (rd, ra, uimm)
    if op == 14:  # addi
        if ra == 0:
            return "li r%d, %d" % (rd, simm)
        return "addi r%d, r%d, %d" % (rd, ra, simm)
    if op in (24, 25, 26, 27, 28, 29):  # ori oris xori xoris andi. andis.
        names = {24: "ori", 25: "oris", 26: "xori", 27: "xoris", 28: "andi.", 29: "andis."}
        return "%s r%d, r%d, 0x%X" % (names[op], ra, rd, uimm) if op not in (24, 25) else \
               "%s r%d, r%d, 0x%X" % (names[op], rd, ra, uimm)
    if op in (32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45):
        names = {32: "lwz", 33: "lwzu", 34: "lbz", 35: "lbzu", 36: "stw", 37: "stwu",
                 38: "stb", 39: "stbu", 40: "lhz", 41: "lhz", 42: "lha", 43: "lha",
                 44: "sth", 45: "sthu"}
        n = names[op]
        if n in ("lwzu", "lbzu", "stwu", "stbu", "sthu"):
            return "%s r%d, %d(r%d)" % (n, rd, simm, ra)
        return "%s r%d, %d(r%d)" % (n, rd, simm, ra)
    if op in (46, 47):
        return ("lmw" if op == 46 else "stmw") + " r%d, %d(r%d)" % (rd, simm, ra)
    if op in (10, 11):  # cmpli cmpi
        n = "cmplwi" if op == 10 else "cmpwi"
        return "%s cr%d, r%d, 0x%X" % (n, (w >> 23) & 7, ra, uimm)
    if op == 21:  # rlwinm
        sh = rb
        mb = (w >> 6) & 31
        me = (w >> 1) & 31
        return "rlwinm r%d, r%d, %d, %d, %d" % (ra, rd, sh, mb, me)
    if op == 20:
        sh = rb
        mb = (w >> 6) & 31
        me = (w >> 1) & 31
        return "rlwimi r%d, r%d, %d, %d, %d" % (ra, rd, sh, mb, me)
    if op == 23:
        return "rlwnm r%d, r%d, r%d, %d, %d" % (ra, rd, rb, (w >> 6) & 31, (w >> 1) & 31)
    if op == 31:
        xo = (w >> 1) & 0x3FF
        ra = (w >> 16) & 31
        if xo == 339:  # mfspr
            spr = ((w >> 16) & 0x1F) | ((w >> 6) & 0x3E0)
            return "mfspr r%d, %s" % (rd, SPR.get(spr, "%d" % spr))
        if xo == 467:
            spr = ((w >> 16) & 0x1F) | ((w >> 6) & 0x3E0)
            return "mtspr %s, r%d" % (SPR.get(spr, "%d" % spr), rd)
        if xo == 19:
            return "mfcr r%d" % rd
        if xo == 144:
            return "mtcrf 0x%X, r%d" % ((w >> 12) & 0xFF, rd)
        if xo == 0:
            return "cmp cr%d, r%d, r%d" % ((w >> 23) & 7, ra, rb) if ((w >> 23) & 7) else \
                   "cmp r%d, r%d" % (ra, rb)
        if xo == 32:
            return "cmpl cr%d, r%d, r%d" % ((w >> 23) & 7, ra, rb)
        if xo == 28:
            return "and r%d, r%d, r%d" % (ra, rd, rb)
        if xo == 444:
            return "or r%d, r%d, r%d" % (ra, rd, rb)
        if xo == 316:
            return "xor r%d, r%d, r%d" % (ra, rd, rb)
        if xo == 124:
            return "nor r%d, r%d, r%d" % (ra, rd, rb)
        if xo == 266:
            return "add r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 40:
            return "subf r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 235:
            return "mullw r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 491:
            return "divw r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 104:
            return "neg r%d, r%d" % (rd, ra)
        if xo == 24:
            return "slw r%d, r%d, r%d" % (ra, rd, rb)
        if xo == 536:
            return "srw r%d, r%d, r%d" % (ra, rd, rb)
        if xo == 792:
            return "sraw r%d, r%d, r%d" % (ra, rd, rb)
        if xo == 824:
            return "srawi r%d, r%d, %d" % (ra, rd, rb)
        if xo == 954:
            return "extsb r%d, r%d" % (ra, rd)
        if xo == 922:
            return "extsh r%d, r%d" % (ra, rd)
        if xo == 26:
            return "cntlzw r%d, r%d" % (ra, rd)
        if xo == 4:
            return "tw %d, r%d, r%d" % ((w >> 21) & 31, ra, rb)
        if xo == 598:
            return "sync"
        if xo == 306:
            return "tlbie r%d" % rb
        if xo in (23, 55):  # lwzx / lwzux
            return ("lwzx" if xo == 23 else "lwzux") + " r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 151:
            return "stwx r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 87:
            return "lbzx r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 215:
            return "stbx r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 279:
            return "lhzx r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 407:
            return "sthx r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 662:
            return "sthbrx r%d, r%d, r%d" % (rd, ra, rb)
        if xo == 918:
            return "sthbrx?" if False else "stwbrx r%d, r%d, r%d" % (rd, ra, rb)
        return ".long 0x%08X (op31 xo=%d)" % (w, xo)
    if op == 19:
        xo = (w >> 1) & 0x3FF
        if xo == 16:
            bo = (w >> 21) & 31
            bi = (w >> 16) & 31
            return "bclr %d,%d" % (bo, bi) + ("l" if w & 1 else "")
        if xo == 528:
            bo = (w >> 21) & 31
            bi = (w >> 16) & 31
            return "bcctr %d,%d" % (bo, bi) + ("l" if w & 1 else "")
        if xo == 50:
            return "rfi"
        if xo == 150:
            return "isync"
        if xo == 0:
            return "mcrf cr%d, cr%d" % ((w >> 23) & 7, (w >> 18) & 7)
        return ".long 0x%08X (op19 xo=%d)" % (w, xo)
    if op == 17:
        return ".long 0x%08X (sc)" % w
    return ".long 0x%08X" % w


class Image:
    def __init__(self, path):
        self.data = open(path, "rb").read()

    def word(self, addr):
        return struct.unpack_from(">I", self.data, addr)[0]

    def dis(self, addr, count=1, base=None):
        out = []
        base = addr if base is None else base
        for i in range(count):
            a = addr + 4 * i
            w = self.word(a)
            out.append("%06X: %08X  %s" % (a, w, decode(w, a)))
        return "\n".join(out)

    def dump(self, addr, count=32):
        return " ".join("%02X" % x for x in self.data[addr:addr + count])

    def find_word(self, value):
        pat = struct.pack(">I", value)
        res, s = [], 0
        while True:
            k = self.data.find(pat, s)
            if k < 0:
                return res
            if k % 4 == 0:
                res.append(k)
            s = k + 1
