"""Real local AsyncSSH integration for host trust, PTY, SFTP, and forwarding."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Protocol, cast

import asyncssh
import pytest

from ssh_it.models import AuthMethod, ConnectionProfile, TunnelKind, TunnelSpec
from ssh_it.ssh import session as session_module
from ssh_it.ssh.session import SSHSessionController

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from pytestqt.qtbot import QtBot


class PasswordServer(asyncssh.SSHServer):
    """Local password server accepting forwarding for integration tests."""

    def begin_auth(self, username: str) -> bool:
        """Require password authentication."""
        return True

    def password_auth_supported(self) -> bool:
        """Advertise password support."""
        return True

    def validate_password(self, username: str, password: str) -> bool:
        """Accept one deterministic integration credential."""
        return username == "tester" and password == "integration-secret"

    def connection_requested(
        self,
        dest_host: str,
        dest_port: int,
        orig_host: str,
        orig_port: int,
    ) -> bool:
        """Permit direct TCP forwarding in isolated local test."""
        return True


class SignalCapture(Protocol):
    """Typed view of pytest-qt signal blocker result."""

    args: list[object] | None


async def echo_process(process: asyncssh.SSHServerProcess[str]) -> None:
    """Provide tiny interactive PTY shell."""
    process.stdout.write("integration-ready$ ")
    async for line in process.stdin:
        process.stdout.write(f"echo:{line}")


class LocalSSHServer:
    """Own AsyncSSH acceptor on private event-loop thread."""

    def __init__(self, root: Path) -> None:
        """Start loop, generate key, and synchronously await listener readiness."""
        self.root = root
        self.key = asyncssh.generate_private_key(  # pyright: ignore[reportUnknownMemberType]
            "ssh-ed25519"
        )
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        assert self.ready.wait(timeout=5)
        future = asyncio.run_coroutine_threadsafe(self._start(), self.loop)
        self.acceptor = future.result(timeout=5)
        self.port = self.acceptor.get_port()

    async def _start(self) -> asyncssh.SSHAcceptor:
        def sftp_factory(channel: asyncssh.SSHServerChannel[str]) -> asyncssh.SFTPServer:
            return asyncssh.SFTPServer(channel, chroot=str(self.root).encode())

        return await asyncssh.create_server(
            PasswordServer,
            "127.0.0.1",
            0,
            server_host_keys=[self.key],
            process_factory=echo_process,
            sftp_factory=sftp_factory,
        )

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()
        self.loop.close()

    def close(self) -> None:
        """Close acceptor and event loop."""

        async def close_acceptor() -> None:
            self.acceptor.close()
            await self.acceptor.wait_closed()

        future = asyncio.run_coroutine_threadsafe(close_acceptor(), self.loop)
        future.result(timeout=5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)


@pytest.fixture
def local_ssh_server(tmp_path: Path) -> Generator[LocalSSHServer, None, None]:
    """Yield isolated SSH/SFTP server."""
    server = LocalSSHServer(tmp_path)
    yield server
    server.close()


def test_controller_first_use_pty_sftp_and_tunnel(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    local_ssh_server: LocalSSHServer,
) -> None:
    """Exercise security prompt, terminal echo, SFTP upload, and local forward lifecycle."""
    known_hosts = tmp_path / "known_hosts"
    monkeypatch.setattr(session_module, "_KNOWN_HOSTS", known_hosts)
    profile = ConnectionProfile(
        "Integration",
        "127.0.0.1",
        port=local_ssh_server.port,
        username="tester",
        auth_method=AuthMethod.PASSWORD,
    )
    controller = SSHSessionController()
    output: list[str] = []
    controller.output_received.connect(output.append)
    try:
        with qtbot.waitSignal(controller.unknown_host_key, timeout=5_000) as host_key_signal:
            controller.connect_to(profile, password="integration-secret")
        host_key_args = cast("SignalCapture", host_key_signal).args or []
        assert host_key_args[0] == "127.0.0.1"
        assert str(host_key_args[3]).startswith("SHA256:")
        with qtbot.waitSignal(controller.connected, timeout=5_000):
            controller.answer_host_key(accept=True)
        assert known_hosts.exists()
        assert b"ssh-ed25519" in known_hosts.read_bytes()

        controller.send("hello\n")
        qtbot.waitUntil(lambda: "echo:hello" in "".join(output), timeout=5_000)

        source = tmp_path / "source.txt"
        source.write_text("sftp payload", encoding="utf-8")
        with qtbot.waitSignal(controller.transfer_finished, timeout=5_000) as transfer_signal:
            controller.transfer(
                "transfer.integration",
                upload=True,
                local_path=source,
                remote_path="/uploaded.txt",
            )
        transfer_args = cast("SignalCapture", transfer_signal).args or []
        assert transfer_args == ["transfer.integration", True, "Transfer completed"]
        assert (tmp_path / "uploaded.txt").read_text(encoding="utf-8") == "sftp payload"

        tunnel = TunnelSpec(
            "tunnel.integration",
            TunnelKind.LOCAL,
            "127.0.0.1",
            0,
            "127.0.0.1",
            local_ssh_server.port,
        )
        with qtbot.waitSignal(controller.tunnel_started, timeout=5_000) as tunnel_signal:
            controller.start_tunnel(tunnel)
        tunnel_args = cast("SignalCapture", tunnel_signal).args or []
        assert cast("int", tunnel_args[1]) > 0
        with qtbot.waitSignal(controller.tunnel_stopped, timeout=5_000):
            controller.stop_tunnel(tunnel.id)
    finally:
        controller.shutdown()


def test_controller_reports_bad_password(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    local_ssh_server: LocalSSHServer,
) -> None:
    """Verified known host with wrong password emits categorized auth failure."""
    known_hosts = tmp_path / "known_hosts"
    public_key = local_ssh_server.key.export_public_key().decode("ascii").strip()
    known_hosts.write_text(
        f"[127.0.0.1]:{local_ssh_server.port} {public_key}\n",
        encoding="ascii",
    )
    monkeypatch.setattr(session_module, "_KNOWN_HOSTS", known_hosts)
    controller = SSHSessionController()
    profile = ConnectionProfile(
        "Integration",
        "127.0.0.1",
        port=local_ssh_server.port,
        username="tester",
        auth_method=AuthMethod.PASSWORD,
    )
    try:
        with qtbot.waitSignal(controller.error_occurred, timeout=5_000) as error_signal:
            controller.connect_to(profile, password="wrong")
        error_args = cast("SignalCapture", error_signal).args or []
        assert error_args[0] == "Authentication failed"
    finally:
        controller.shutdown()
