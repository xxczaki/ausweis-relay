# ausweis-relay

Use your phone as an ID card reader ("Smartphone als Kartenleser") with AusweisApp on a Mac whose firewall blocks all incoming connections, for example a company-managed Mac where you can't change the firewall.

## The problem

The phone announces itself with a UDP packet to port 24727. If the macOS firewall is set to "Block all incoming connections" (often enforced by MDM), it drops that packet before AusweisApp sees it, so the phone never shows up.

## How it works

- `tcpdump` reads packets before the firewall drops them.
- The script resends each AusweisApp announcement to `127.0.0.1:24727`. The firewall doesn't filter loopback traffic.
- Since AusweisApp 2.3.2 the announcement carries the phone's own address (`"addresses": ["wss://<ip>:<port>"]`), and the Mac uses that instead of the sender. So the Mac still connects to the phone.
- That connection is outbound from the Mac, which the firewall allows.

No system settings are changed. It only runs while you keep it open.

## Usage

Needs Python 3 (built into macOS) and sudo for `tcpdump`. Phone and Mac must be on the same network.

1. On the phone: AusweisApp → Card reader → "Use smartphone as card reader". Keep the screen on.
2. On the Mac: open AusweisApp.
3. Run:

   ```bash
   python3 ausweis-relay.py        # Wi-Fi is usually en0
   python3 ausweis-relay.py en1    # other interface
   ```

4. Wait for `Relaying '<phone name>' from <phone ip> ...`. The phone should now appear in AusweisApp on the Mac. Pair it, then keep the script running while you use it.

Stop with Ctrl+C.

## License

MIT
