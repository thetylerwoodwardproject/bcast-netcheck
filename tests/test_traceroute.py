from bcast_netcheck.checks.traceroute import parse_hops


def test_hops():
    hops = parse_hops("traceroute to 192.0.2.20\n 1 192.0.2.1 1.2 ms\n 2 *\n 3 192.0.2.20 2.4 ms\n")
    assert len(hops) == 3
    assert hops[0]["addresses"] == ["192.0.2.1"]
    assert hops[1]["timeout"]
    assert hops[2]["rtt_ms"] == [2.4]
