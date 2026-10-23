from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _lab_approval_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPROVAL_STATE_KEY", "lab-simulated-not-a-secret")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
