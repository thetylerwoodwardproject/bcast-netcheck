"""Non-overlapping reachability sampling and conservative interruption estimates."""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import replace
from datetime import datetime

from rich.console import Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from bcast_netcheck.models import CheckStatus as S
from bcast_netcheck.runner import run


class History:
    def __init__(self):
        self.events = deque(maxlen=20)
        self.states = {}
        self.outages = {}
        self.samples = defaultdict(lambda: deque(maxlen=60))
        self.previous_time = None
        self.max_gap = 0.0

    def update(self, result, now, timestamp):
        if self.previous_time is not None:
            self.max_gap = max(self.max_gap, now - self.previous_time)
        self.previous_time = now
        for check in result.checks:
            if check.name != "ICMP":
                continue
            key, status = check.endpoint, check.status
            self.samples[key].append((status, check.value))
            previous = self.states.get(key)
            label = check.label or key
            if status == S.FAIL:
                if key not in self.outages:
                    self.outages[key] = now
                if previous in (S.PASS, S.WARN):
                    self.events.append(f"{timestamp} {label} LOST")
            elif status in (S.PASS, S.WARN):
                if previous == S.FAIL and key in self.outages:
                    elapsed = now - self.outages[key]
                    self.events.append(
                        f"{timestamp} {label} RESTORED — interruption approximately "
                        f"{elapsed:.1f}s (sampling gap up to {self.max_gap:.1f}s)"
                    )
                self.outages.pop(key, None)
            else:
                # An execution gap is not evidence of uninterrupted downtime.
                self.outages.pop(key, None)
                if previous is not None and previous != status:
                    self.events.append(f"{timestamp} {label} UNKNOWN ({status})")
            if status == S.FAIL and key == "primary":
                backup = next(
                    (c for c in result.checks if c.endpoint == "backup" and c.name == "ICMP"), None
                )
                if previous in (S.PASS, S.WARN) and backup and backup.status in (S.PASS, S.WARN):
                    self.events.append(f"{timestamp} Backup path remains reachable")
            self.states[key] = status

    def metrics(self, key):
        samples = self.samples[key]
        known = [(s, rtt) for s, rtt in samples if s in (S.PASS, S.WARN, S.FAIL)]
        loss = 100 * sum(s == S.FAIL for s, _ in known) / len(known) if known else None
        variations = [
            abs(b[1] - a[1])
            for a, b in zip(samples, list(samples)[1:])
            if a[1] is not None and b[1] is not None
        ]
        jitter = sum(variations) / len(variations) if variations else None
        return loss, jitter


def render(result, history, interval):
    table = Table(title=Text(f"{result.site or result.target}  LIVE — reachability only"))
    for name in ("Endpoint", "State", "RTT", "Loss (60 samples)", "Jitter"):
        table.add_column(name)
    for c in result.checks:
        if c.name != "ICMP":
            continue
        loss, jitter = history.metrics(c.endpoint)
        state = (
            "UP" if c.status in (S.PASS, S.WARN) else "DOWN" if c.status == S.FAIL else "UNKNOWN"
        )
        table.add_row(
            Text(c.label or c.endpoint),
            state,
            f"{c.value:.1f} ms" if c.value is not None else "—",
            f"{loss:.2f}%" if loss is not None else "—",
            f"{jitter:.1f} ms" if jitter is not None else "—",
        )
    route_result = next((c for c in result.checks if c.name == "Route"), None)
    route_text = route_result.message if route_result else "Not measured"
    return Group(
        table,
        Text(f"{result.diagnosis.status.upper()}: {result.diagnosis.summary}"),
        Text(
            f"Last update: {result.timestamp} | Requested interval: {interval:g}s | "
            f"Largest observed gap: {history.max_gap:.1f}s"
        ),
        Text(f"Route: {route_text}"),
        Text("Recent events (round completion times):\n" + "\n".join(history.events)),
    )


async def watch(target, site, endpoints, settings, selected=False):
    history = History()
    sample_settings = replace(
        settings, ping_count=1, timeout=min(settings.timeout, settings.interval * 0.8)
    )
    with Live(refresh_per_second=4, transient=False) as live:
        while True:
            start = time.monotonic()
            result = await run(
                target, site, endpoints, sample_settings, selected, reachability_only=True
            )
            now = time.monotonic()
            history.update(result, now, datetime.now().strftime("%H:%M:%S.%f")[:-3])
            live.update(render(result, history, settings.interval))
            await asyncio.sleep(max(0, settings.interval - (now - start)))
