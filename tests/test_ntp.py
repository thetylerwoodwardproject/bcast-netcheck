import pytest

from bcast_netcheck.checks.ntp import interpret, timestamp
from bcast_netcheck.models import CheckStatus as S


def reply(t1, t2, t3):
    packet = bytearray(48)
    packet[0], packet[1] = 0x24, 2
    packet[24:32] = timestamp(t1)
    packet[32:40] = timestamp(t2)
    packet[40:48] = timestamp(t3)
    return packet


def test_offset_and_threshold():
    t1 = 1800000000.0
    packet = reply(t1, t1 + 0.014, t1 + 0.014)
    status, offset, details, _ = interpret(packet, timestamp(t1), t1, t1 + 0.020, 100)
    assert status == S.PASS
    assert offset == pytest.approx(4, abs=0.001)
    assert details["round_trip_ms"] == pytest.approx(20, abs=0.001)
    assert interpret(packet, timestamp(t1), t1, t1 + 0.020, 1)[0] == S.WARN


def test_invalid_and_unsynchronized():
    packet = reply(1800000000, 1800000001, 1800000001)
    with pytest.raises(ValueError):
        interpret(packet, bytes(8), 1800000000, 1800000002, 100)
    packet[0] |= 0xC0
    assert interpret(packet, packet[24:32], 1800000000, 1800000002, 100)[0] == S.FAIL


def test_ntp_era_rollover():
    future = 2300000000.0
    packet = reply(future, future + 0.01, future + 0.01)
    assert interpret(packet, timestamp(future), future, future + 0.02, 100)[1] == pytest.approx(
        0, abs=0.001
    )
