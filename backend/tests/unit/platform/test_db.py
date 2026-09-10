"""UnitOfWork commit and rollback semantics with a fake session."""

import pytest

from nuroli.platform.db import UnitOfWork


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def commit(self) -> None:
        self.calls.append("commit")

    async def rollback(self) -> None:
        self.calls.append("rollback")

    async def close(self) -> None:
        self.calls.append("close")


async def test_commit_marks_the_unit_committed_and_close_does_not_roll_back() -> None:
    session = FakeSession()
    unit = UnitOfWork(session)
    await unit.commit()
    assert unit.committed is True
    await unit.close()
    assert session.calls == ["commit", "close"]


async def test_close_without_commit_rolls_back() -> None:
    session = FakeSession()
    unit = UnitOfWork(session)
    await unit.close()
    assert session.calls == ["rollback", "close"]


async def test_explicit_rollback_clears_the_committed_flag() -> None:
    session = FakeSession()
    unit = UnitOfWork(session)
    await unit.commit()
    await unit.rollback()
    assert unit.committed is False
    await unit.close()
    assert session.calls == ["commit", "rollback", "rollback", "close"]


async def test_close_always_closes_even_when_rollback_fails() -> None:
    class FailingSession(FakeSession):
        async def rollback(self) -> None:
            self.calls.append("rollback")
            raise RuntimeError("connection lost")

    session = FailingSession()
    unit = UnitOfWork(session)
    with pytest.raises(RuntimeError):
        await unit.close()
    assert session.calls == ["rollback", "close"]
