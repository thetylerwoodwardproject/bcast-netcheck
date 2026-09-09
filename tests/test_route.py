from bcast_netcheck.checks.route import parse_route


def test_route():
    assert parse_route(
        '[{"dst":"192.0.2.20","gateway":"192.0.2.1","dev":"eth0","prefsrc":"192.0.2.2"}]'
    ) == {
        "destination": "192.0.2.20",
        "next_hop": "192.0.2.1",
        "interface": "eth0",
        "source": "192.0.2.2",
    }
