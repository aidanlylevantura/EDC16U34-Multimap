"""Enumerate measuring blocks (KWP2000 service 0x21) and flag the empty ones.

Needs python-can:   pip install python-can

Examples:
    python tools/probe_mb.py --interface slcan --channel COM5
    python tools/probe_mb.py --interface candle --channel 0 --list 1-40
    python tools/probe_mb.py --interface slcan --channel COM5 --session --csv out/mb.csv

Why: a "measuring block" is not a table in the flash image - it is a request the
ECU answers. So the only reliable way to learn which block numbers exist is to
ask for every one of them and look at the answer. A block is a candidate for
"empty / free" when the ECU either rejects it (0x7F 0x21 NRC) or answers with
all-zero values and zero format bytes.

Response layout (VAG, 4 display fields of 3 bytes each):
    61  v1h v1l f1   v2h v2l f2   v3h v3l f3   v4h v4l f4
The format byte is the scaling formula id (0x00 usually means "unscaled / unused").
"""
import argparse
import csv
import sys
import time

try:
    import can
except ImportError:
    sys.exit("pip install python-can")


def isotp_send(bus, txid, payload):
    if len(payload) <= 7:
        bus.send(can.Message(arbitration_id=txid,
                             data=bytes([len(payload)]) + payload,
                             is_extended_id=False))
        return
    bus.send(can.Message(arbitration_id=txid,
                         data=bytes([0x10 | (len(payload) >> 8), len(payload) & 0xFF]) + payload[:6],
                         is_extended_id=False))
    rest, seq = payload[6:], 1
    while rest:
        bus.send(can.Message(arbitration_id=txid,
                             data=(bytes([0x20 | (seq & 0xF)]) + rest[:7]).ljust(8, b"\x00"),
                             is_extended_id=False))
        rest, seq = rest[7:], seq + 1


def isotp_recv(bus, rxid, timeout=1.0):
    total, data = None, b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = bus.recv(timeout=0.2)
        if msg is None or msg.arbitration_id != rxid:
            continue
        pci = msg.data[0] >> 4
        if pci == 0:
            return bytes(msg.data[1:1 + (msg.data[0] & 0xF)])
        if pci == 1:
            total = ((msg.data[0] & 0xF) << 8) | msg.data[1]
            data = bytes(msg.data[2:8])
            bus.send(can.Message(arbitration_id=0x7E0, data=b"\x30\x00\x00",
                                 is_extended_id=False))
            continue
        if pci == 2:
            data += bytes(msg.data[1:8])
            if total is not None and len(data) >= total:
                return data[:total]
    return None


def parse_range(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out += list(range(int(a, 0), int(b, 0) + 1))
        elif part:
            out.append(int(part, 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interface", default="slcan")
    ap.add_argument("--channel", default="COM5")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--txid", type=lambda s: int(s, 0), default=0x7E0)
    ap.add_argument("--rxid", type=lambda s: int(s, 0), default=0x7E8)
    ap.add_argument("--list", default="1-255", help="groups to probe, e.g. 1-40 or 1-20,100-120")
    ap.add_argument("--session", action="store_true",
                    help="send StartDiagnosticSession 0x10 0x89 (or 0x81) first")
    ap.add_argument("--session-code", type=lambda s: int(s, 0), default=0x89)
    ap.add_argument("--delay", type=float, default=0.03)
    ap.add_argument("--csv", help="write the census to this CSV")
    args = ap.parse_args()

    bus = can.Bus(interface=args.interface, channel=args.channel, bitrate=args.bitrate)
    rows = []
    try:
        if args.session:
            isotp_send(bus, args.txid, bytes([0x10, args.session_code]))
            r = isotp_recv(bus, args.rxid, 2.0)
            print("session 0x10 0x%02X -> %s" % (args.session_code,
                                                 r.hex(" ") if r else "no reply"))

        for g in parse_range(args.list):
            isotp_send(bus, args.txid, bytes([0x21, (g >> 8) & 0xFF, g & 0xFF]))
            r = isotp_recv(bus, args.rxid, 1.0)
            if r is None:
                rows.append((g, "noreply", "", "", "", "", "", "", "", ""))
                print("%3d  no reply" % g)
                continue
            if r[0] == 0x7F:
                nrc = r[2] if len(r) > 2 else 0
                rows.append((g, "nrc%02X" % nrc, "", "", "", "", "", "", "", ""))
                print("%3d  NEGATIVE nrc=0x%02X" % (g, nrc))
                continue
            if r[0] != 0x61:
                rows.append((g, "odd", r.hex(" "), "", "", "", "", "", "", ""))
                print("%3d  unexpected %s" % (g, r.hex(" ")))
                continue
            body = r[1:]
            vals, fmts = [], []
            for i in range(4):
                if len(body) >= 3 * i + 3:
                    vals.append((body[3 * i] << 8) | body[3 * i + 1])
                    fmts.append(body[3 * i + 2])
                else:
                    vals.append(None)
                    fmts.append(None)
            nonzero = any(v not in (None, 0) for v in vals) or any(f not in (None, 0) for f in fmts)
            tag = "data" if nonzero else "ZERO"
            rows.append((g, tag, *(list(vals) + list(fmts))))
            print("%3d  %s  vals=%s fmts=%s" % (
                g, tag,
                ["--" if v is None else "%d" % v for v in vals],
                ["--" if f is None else "%02X" % f for f in fmts]))
            time.sleep(args.delay)
    finally:
        bus.shutdown()

    zero = [r[0] for r in rows if r[1] == "ZERO"]
    nrc = [r[0] for r in rows if str(r[1]).startswith("nrc")]
    print("\n%d probed | %d answered data | %d all-zero | %d rejected"
          % (len(rows), sum(1 for r in rows if r[1] == "data"), len(zero), len(nrc)))
    if zero:
        print("all-zero groups (candidates for an unused block): %s" % zero[:40])
    if nrc:
        print("rejected groups: %s" % nrc[:40])
    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["group", "status", "v1", "v2", "v3", "v4", "f1", "f2", "f3", "f4"])
            w.writerows(rows)
        print("csv written to", args.csv)


if __name__ == "__main__":
    main()
