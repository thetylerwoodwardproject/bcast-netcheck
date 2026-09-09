"""One SNTP exchange; estimates server-minus-local clock offset, never sets time."""

import asyncio
import socket
import struct
import time

from bcast_netcheck.checks.route import address
from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S

EPOCH = 2208988800
ERA = 2**32


def timestamp(unix):
    ntp = unix + EPOCH
    return struct.pack("!II", int(ntp) % ERA, int((ntp % 1) * ERA))


def decode_timestamp(raw, reference):
    sec, fraction = struct.unpack("!II", raw)
    base = sec + fraction / ERA - EPOCH
    return base + round((reference - base) / ERA) * ERA


def interpret(packet, origin, t1, t4, threshold):
    if len(packet) < 48:
        raise ValueError("Truncated NTP reply")
    leap, version, mode = packet[0] >> 6, (packet[0] >> 3) & 7, packet[0] & 7
    if version not in (3, 4) or mode != 4 or packet[24:32] != origin:
        raise ValueError("Invalid NTP reply or mismatched origin")
    if leap == 3 or packet[1] == 0 or packet[1] > 15:
        return S.FAIL, None, {"stratum": packet[1]}, "Server unsynchronized or refused query"
    if packet[32:40] == bytes(8) or packet[40:48] == bytes(8):
        raise ValueError("Missing NTP timestamp")
    t2 = decode_timestamp(packet[32:40], t1)
    t3 = decode_timestamp(packet[40:48], t1)
    delay = (t4 - t1) - (t3 - t2)
    if t3 < t2 or delay < -0.001:
        raise ValueError("Invalid NTP timing")
    offset = ((t2 - t1) + (t3 - t4)) * 500
    return (
        S.WARN if abs(offset) > threshold else S.PASS,
        offset,
        {"stratum": packet[1], "round_trip_ms": max(0, delay * 1000)},
        "Estimated server minus local clock offset",
    )


async def check(host, settings):
    destination = await address(host)
    family = socket.AF_INET6 if ":" in destination else socket.AF_INET
    loop = asyncio.get_running_loop()
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        await loop.sock_connect(sock, (destination, 123))
        t1 = time.time()
        origin = timestamp(t1)
        request = bytes([0x23]) + bytes(39) + origin
        try:
            await loop.sock_sendall(sock, request)
            packet = await asyncio.wait_for(loop.sock_recv(sock, 512), settings.timeout * 0.9)
            t4 = time.time()
        except (TimeoutError, OSError):
            return CheckResult("NTP", S.FAIL, host, message="NTP server did not respond")
    try:
        status, offset, details, message = interpret(packet, origin, t1, t4, settings.ntp_warn_ms)
    except ValueError:
        return CheckResult("NTP", S.FAIL, host, message="Invalid or mismatched NTP response")
    return CheckResult("NTP", status, host, offset, "ms", message, details)
