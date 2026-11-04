"""Poll a RAM range over KWP2000 and print which bytes change.

Built for the multimap trigger work: point it at the CAN receive buffers
(0x7FF100-0x7FF140) and press the cruise stalk - the byte that flips tells you
both the payload offset inside the 12-byte buffer and which bit is the button.

Needs python-can.

Example:
    python tools/watch_ram.py --interface candle --channel 0 \
        --addr 0x7FF100 --len 0x40 --interval 0.15 --seconds 60

Interpretation for CAN buffers
------------------------------
Buffers sit at 0x7FF024 + 12*i.  Frame 0x38A owns 0x7FF114, frame 0x7D0 owns
0x7FF120.  If a byte inside 0x7FF114..0x7FF11B toggles when you press SET:
    toggle at +0..+7  -> payload starts at buffer+0
    toggle at +4..+11 -> payload starts at buffer+4
and the bit that toggles is the button bit.
"""
import argparse
import sys
import time

try:
    import can
except ImportError:
    sys.exit("pip install python-can")

from kwp_ram import isotp_send, isotp_recv


def read_ram(bus, txid, rxid, addr, length):
    req = bytes([0x23,
                 (addr >> 16) & 0xFF,
                 (addr >> 8) & 0xFF,
                 addr & 0xFF,
                 length & 0xFF])
    isotp_send(bus, txid, req)
    resp = isotp_recv(bus, rxid, timeout=2.0)
    if not resp:
        return None
    if resp[0] == 0x63:
        return resp[1:]
    if resp[0] == 0x7F:
        print("negative response: service 0x%02X NRC 0x%02X" % (resp[1], resp[2]))
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interface", default="slcan")
    ap.add_argument("--channel", default="COM5")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--txid", type=lambda s: int(s, 0), default=0x7E0)
    ap.add_argument("--rxid", type=lambda s: int(s, 0), default=0x7E8)
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x7FF100)
    ap.add_argument("--len", type=lambda s: int(s, 0), default=0x40)
    ap.add_argument("--interval", type=float, default=0.15)
    ap.add_argument("--seconds", type=float, default=60.0)
    args = ap.parse_args()

    bus = can.Bus(interface=args.interface, channel=args.channel,
                  bitrate=args.bitrate)
    print("polling %06X..%06X every %.2fs - press the stalk now"
          % (args.addr, args.addr + args.len - 1, args.interval))
    first = read_ram(bus, args.txid, args.rxid, args.addr, args.len)
    if first is None:
        print("read failed - this ECU probably does not expose ReadMemoryByAddress")
        bus.shutdown()
        return
    prev = first
    print("base: " + prev.hex(" "))
    t0 = time.time()
    try:
        while time.time() - t0 < args.seconds:
            time.sleep(args.interval)
            cur = read_ram(bus, args.txid, args.rxid, args.addr, args.len)
            if cur is None or len(cur) != len(prev):
                continue
            diffs = [(i, prev[i], cur[i]) for i in range(len(cur)) if prev[i] != cur[i]]
            if diffs:
                stamp = time.time() - t0
                for i, old, new in diffs:
                    print("  t=%6.2f  %06X  %02X -> %02X   bit(s) %s"
                          % (stamp, args.addr + i, old, new,
                             ",".join(str(b) for b in range(8) if ((old ^ new) >> b) & 1)))
            prev = cur
    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
