"""Try KWP2000 ReadMemoryByAddress (service 0x23) over CAN.

Needs python-can:   pip install python-can

Examples:
    python tools/kwp_ram.py --interface slcan --channel COM5 --addr 0x7F8000 --len 16
    python tools/kwp_ram.py --interface candle --channel 0 --addr 0x9FE000 --len 16

A positive answer (0x63 ...) means this ECU exposes RAM over diagnostics and we
can do the whole RAM census without a debugger. A negative answer (0x7F 23 xx)
means it is locked in the normal session.
"""
import argparse
import sys
import time

try:
    import can
except ImportError:
    sys.exit("pip install python-can")


def isotp_send(bus, txid, payload):
    if len(payload) <= 7:
        bus.send(can.Message(arbitration_id=txid, data=bytes([len(payload)]) + payload,
                             is_extended_id=False))
        return
    first = bytes([0x10 | (len(payload) >> 8), len(payload) & 0xFF]) + payload[:6]
    bus.send(can.Message(arbitration_id=txid, data=first, is_extended_id=False))
    rest = payload[6:]
    seq = 1
    while rest:
        chunk = bytes([0x20 | (seq & 0xF)]) + rest[:7]
        bus.send(can.Message(arbitration_id=txid, data=chunk.ljust(8, b"\x00"),
                             is_extended_id=False))
        rest = rest[7:]
        seq += 1


def isotp_recv(bus, rxid, timeout=2.0):
    total, data, seq = None, b"", 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = bus.recv(timeout=0.2)
        if msg is None or msg.arbitration_id != rxid:
            continue
        pci = msg.data[0] >> 4
        if pci == 0:                      # single frame
            n = msg.data[0] & 0xF
            return bytes(msg.data[1:1 + n])
        if pci == 1:                      # first frame
            total = ((msg.data[0] & 0xF) << 8) | msg.data[1]
            data = bytes(msg.data[2:8])
            bus.send(can.Message(arbitration_id=0x7E0, data=b"\x30\x00\x00",
                                 is_extended_id=False))
            continue
        if pci == 2:                      # consecutive frame
            seq = msg.data[0] & 0xF
            data += bytes(msg.data[1:8])
            if total is not None and len(data) >= total:
                return data[:total]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interface", default="slcan")
    ap.add_argument("--channel", default="COM5")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--txid", type=lambda s: int(s, 0), default=0x7E0)
    ap.add_argument("--rxid", type=lambda s: int(s, 0), default=0x7E8)
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x7F8000)
    ap.add_argument("--len", type=int, default=1)
    ap.add_argument("--session", action="store_true",
                    help="send StartDiagnosticSession 0x10 0x81 first")
    ap.add_argument("--out", help="write the positive response payload to this file")
    args = ap.parse_args()

    bus = can.Bus(interface=args.interface, channel=args.channel,
                  bitrate=args.bitrate)
    try:
        if args.session:
            isotp_send(bus, args.txid, bytes([0x10, 0x81]))
            print("session 0x10 0x81 ->", (isotp_recv(bus, args.rxid) or b"").hex(" ") or "no reply")

        req = bytes([0x23,
                     (args.addr >> 16) & 0xFF,
                     (args.addr >> 8) & 0xFF,
                     args.addr & 0xFF,
                     args.len & 0xFF])
        print("TX", req.hex(" "))
        isotp_send(bus, args.txid, req)
        resp = isotp_recv(bus, args.rxid, timeout=3.0)
        if resp is None:
            print("no reply")
            return
        print("RX", resp.hex(" "))
        if resp and resp[0] == 0x63:
            print("POSITIVE - %d bytes:" % (len(resp) - 1), resp[1:].hex(" "))
            if args.out:
                open(args.out, "wb").write(resp[1:])
                print("payload written to", args.out)
        elif resp and resp[0] == 0x7F:
            print("NEGATIVE - service 0x%02X, NRC 0x%02X" % (resp[1], resp[2]))
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
