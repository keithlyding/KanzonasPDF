"""TEMPORARY diagnostic (branch claude/mac-udp-probe only, never merged): which UDP set-ups
deliver a datagram to a socket on 127.0.0.1 on this machine. Always passes; prints a table."""
import platform
import select
import socket
import sys
import time
import unittest


def trial(sender_bind, recv_bind, ttl, blocking, dest_host="127.0.0.1"):
    r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    r.bind((recv_bind, 0))
    port = r.getsockname()[1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    note = ""
    try:
        s.setblocking(blocking)
        s.bind((sender_bind, 0))
        if ttl is not None:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        n = s.sendto(b"ping", (dest_host, port))
        note = "sent %d" % n
        ready, _w, _x = select.select([r], [], [], 1.0)
        if not ready:
            return "LOST (%s)" % note
        data, src = r.recvfrom(100)
        # and the answer back
        r.sendto(b"pong", src)
        ready, _w, _x = select.select([s], [], [], 1.0)
        back = s.recvfrom(100)[0] if ready else None
        return "ok from %s, answer %s" % (src, "ok" if back == b"pong" else "LOST")
    except OSError as e:
        return "ERROR %s (%s)" % (e, note)
    finally:
        s.close()
        r.close()


class Probe(unittest.TestCase):
    def test_print_udp_table(self):
        out = ["", "UDP PROBE on %s %s python %s" % (sys.platform, platform.mac_ver()[0] or
                                                    platform.release(), sys.version.split()[0])]
        for sb in ("0.0.0.0", "127.0.0.1"):
            for rb in ("127.0.0.1", "0.0.0.0"):
                for ttl in (None, 1, 255):
                    for blocking in (True, False):
                        out.append("  send bind %-9s recv bind %-9s ttl %-4s %-8s -> %s" % (
                            sb, rb, ttl, "blocking" if blocking else "nonblock",
                            trial(sb, rb, ttl, blocking)))
        try:
            lan = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            lan.connect(("192.0.2.1", 9))
            ip = lan.getsockname()[0]
            lan.close()
            out.append("  to own LAN address %s, recv bind 0.0.0.0 -> %s" % (
                ip, trial("0.0.0.0", "0.0.0.0", None, True, ip)))
        except OSError as e:
            out.append("  no LAN address: %s" % e)
        print("\n".join(out), file=sys.stderr, flush=True)
