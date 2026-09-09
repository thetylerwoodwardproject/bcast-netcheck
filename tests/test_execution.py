import asyncio

import pytest

from bcast_netcheck.checks import common
from bcast_netcheck.models import CheckStatus as S


async def test_deadline_and_exception_redaction():
    async def hangs():
        await asyncio.Event().wait()

    result = await common.guarded("Test", "192.0.2.20", hangs, 0.01)
    assert result.status == S.ERROR

    async def error():
        raise ValueError("sensitive content")

    result = await common.guarded("Test", "192.0.2.20", error, 1)
    assert "sensitive" not in str(result)


async def test_cancel_kills_and_reaps_subprocess(monkeypatch):
    started = asyncio.Event()
    stopped = asyncio.Event()

    class Process:
        returncode = None
        killed = False
        waited = False

        async def communicate(self):
            started.set()
            await stopped.wait()
            return b"", b""

        def kill(self):
            self.killed = True
            self.returncode = -9
            stopped.set()

        async def wait(self):
            self.waited = True
            return self.returncode

    proc = Process()

    async def create(*args, **kwargs):
        assert "shell" not in kwargs
        assert kwargs["env"].keys() == {"PATH", "LC_ALL"}
        return proc

    monkeypatch.setattr(common.platform, "system", lambda: "Linux")
    monkeypatch.setattr(common.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    task = asyncio.create_task(common.command(["ping", "192.0.2.20"], 1))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.killed and proc.waited


async def test_missing_utility_is_skip(monkeypatch):
    monkeypatch.setattr(common.platform, "system", lambda: "Linux")
    monkeypatch.setattr(common.shutil, "which", lambda _: None)
    result = await common.guarded("Route", "192.0.2.20", lambda: common.command(["ip"], 1), 1)
    assert result.status == S.SKIP
