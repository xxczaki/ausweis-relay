#!/usr/bin/env python3
"""
Relay AusweisApp "Smartphone als Kartenleser" discovery to the local AusweisApp.

Why this works:
- The iPhone announces itself with a UDP packet to port 24727.
- The macOS app firewall (block all incoming) drops it before AusweisApp sees it.
- tcpdump reads packets before the firewall, and loopback traffic is not filtered.
- Since AusweisApp 2.3.2 the packet carries the phone's own address
  ("addresses": ["wss://<ip>:<port>"]), and the Mac uses that instead of the
  sender address. So re-sending it from 127.0.0.1 still points the Mac at the phone.
- The Mac then opens an OUTBOUND connection to the phone, which the firewall allows.

Usage:  python3 ausweis-relay.py [interface]     (default en0, asks for sudo once)
Stop with Ctrl+C. Nothing is changed on the system.
"""
import json
import socket
import struct
import subprocess
import sys

IFACE = sys.argv[1] if len(sys.argv) > 1 else "en0"
PORT = 24727
TARGETS = [(socket.AF_INET, ("127.0.0.1", PORT)), (socket.AF_INET6, ("::1", PORT))]


def read_exact(f, n):
    buf = b""
    while len(buf) < n:
        chunk = f.read(n - len(buf))
        if not chunk:
            raise EOFError
        buf += chunk
    return buf


def udp_payload(frame):
    """Ethernet frame -> (source ip, udp payload) or None."""
    if len(frame) < 14:
        return None
    ethertype = struct.unpack("!H", frame[12:14])[0]
    off = 14
    if ethertype == 0x8100:  # 802.1Q tag
        ethertype = struct.unpack("!H", frame[16:18])[0]
        off = 18
    if ethertype == 0x0800:  # IPv4
        if frame[off + 9] != 17:
            return None
        src = socket.inet_ntop(socket.AF_INET, frame[off + 12:off + 16])
        off += (frame[off] & 0x0F) * 4
    elif ethertype == 0x86DD:  # IPv6, no extension headers
        if frame[off + 6] != 17:
            return None
        src = socket.inet_ntop(socket.AF_INET6, frame[off + 8:off + 24])
        off += 40
    else:
        return None
    length = struct.unpack("!H", frame[off + 4:off + 6])[0]
    return src, frame[off + 8:off + length]


def main():
    socks = []
    for family, addr in TARGETS:
        try:
            socks.append((socket.socket(family, socket.SOCK_DGRAM), addr))
        except OSError:
            pass

    cmd = ["sudo", "tcpdump", "-i", IFACE, "-U", "-s", "0", "-w", "-", f"udp dst port {PORT}"]
    print(f"Listening on {IFACE} for AusweisApp discovery (sudo may ask for your password)...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    f = proc.stdout

    header = read_exact(f, 24)
    magic = header[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    else:
        sys.exit(f"Unexpected capture format (magic {magic.hex()}).")
    linktype = struct.unpack(endian + "I", header[20:24])[0]
    if linktype != 1:
        sys.exit(f"Interface {IFACE} is not Ethernet-like (linktype {linktype}).")

    seen = set()
    count = 0
    try:
        while True:
            _, _, incl_len, _ = struct.unpack(endian + "IIII", read_exact(f, 16))
            parsed = udp_payload(read_exact(f, incl_len))
            if not parsed:
                continue
            src, payload = parsed
            if b"REMOTE_IFD" not in payload:
                continue
            for s, addr in socks:
                try:
                    s.sendto(payload, addr)
                except OSError:
                    pass
            count += 1
            try:
                msg = json.loads(payload)
                key = (msg.get("IFDName"), tuple(msg.get("addresses") or []), msg.get("pairing"))
            except ValueError:
                msg, key = {}, (src,)
            if key not in seen:
                seen.add(key)
                addrs = msg.get("addresses")
                print(f"Relaying '{msg.get('IFDName')}' from {src} "
                      f"pairing={msg.get('pairing')} addresses={addrs}")
                if not addrs:
                    print("  Warning: no 'addresses' field. The Mac would try 127.0.0.1 and fail. "
                          "Update AusweisApp on the iPhone.")
            elif count % 20 == 0:
                print(f"  ...{count} packets relayed")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        proc.terminate()
        print("Stopped.")


if __name__ == "__main__":
    main()
