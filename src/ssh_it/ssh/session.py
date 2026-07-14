"""Thread-isolated AsyncSSH session, SFTP, and forwarding controller."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import asyncssh
from PySide6.QtCore import QObject, Signal

from ssh_it.models import AuthMethod, ConnectionProfile, TunnelKind, TunnelSpec

if TYPE_CHECKING:
    from concurrent.futures import Future

_KNOWN_HOSTS: Final = Path.home() / ".ssh" / "known_hosts"
_DEFAULT_SSH_PORT: Final = 22


class SSHSessionController(QObject):
    """Expose one SSH connection to Qt without blocking GUI thread."""

    state_changed = Signal(str)
    connected = Signal()
    disconnected = Signal(str)
    output_received = Signal(str)
    error_occurred = Signal(str, str)
    unknown_host_key = Signal(str, int, str, str)
    transfer_progress = Signal(str, int, int)
    transfer_finished = Signal(str, bool, str)
    tunnel_started = Signal(str, int)
    tunnel_stopped = Signal(str)

    def __init__(self) -> None:
        """Start private asyncio event-loop thread."""
        super().__init__()
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, name="ssh-it-asyncio", daemon=True)
        self._connection: asyncssh.SSHClientConnection | None = None
        self._process: asyncssh.SSHClientProcess[str] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._listeners: dict[str, asyncssh.SSHListener] = {}
        self._terminal_size = (120, 40)
        self._pending_key: tuple[ConnectionProfile, asyncssh.SSHKey, str, str] | None = None
        self._pending_credentials: tuple[str | None, str | None] | None = None
        self._stopping = False
        self._thread.start()
        self._ready.wait(timeout=5)

    @property
    def is_connected(self) -> bool:
        """Return connection snapshot for UI enablement."""
        return self._connection is not None and not self._connection.is_closed()

    def connect_to(
        self,
        profile: ConnectionProfile,
        *,
        password: str | None = None,
        passphrase: str | None = None,
    ) -> None:
        """Begin verified SSH connection."""
        self._submit(self._connect(profile, password, passphrase))

    def answer_host_key(self, *, accept: bool) -> None:
        """Accept or reject pending first-use host key."""
        self._submit(self._answer_host_key(accept))

    def disconnect_from_host(self) -> None:
        """Begin orderly disconnect."""
        self._submit(self._disconnect("Disconnected by user"))

    def send(self, text: str) -> None:
        """Write text to remote PTY."""
        self._submit(self._send(text))

    def interrupt(self) -> None:
        """Send terminal interrupt byte to remote PTY."""
        self.send("\x03")

    def resize_terminal(self, columns: int, rows: int) -> None:
        """Notify remote PTY of character dimensions."""
        self._terminal_size = (max(columns, 20), max(rows, 5))
        self._submit(self._resize_terminal())

    def transfer(
        self,
        operation_id: str,
        *,
        upload: bool,
        local_path: Path,
        remote_path: str,
        recurse: bool = False,
    ) -> None:
        """Start SFTP upload or download on verified active connection."""
        self._submit(self._transfer(operation_id, upload, local_path, remote_path, recurse))

    def start_tunnel(self, spec: TunnelSpec) -> None:
        """Start SSH forwarding listener."""
        self._submit(self._start_tunnel(spec))

    def stop_tunnel(self, tunnel_id: str) -> None:
        """Stop named forwarding listener."""
        self._submit(self._stop_tunnel(tunnel_id))

    def shutdown(self, timeout: float = 4.0) -> None:
        """Disconnect, stop event loop, and join worker thread."""
        if self._stopping:
            return
        self._stopping = True
        future = asyncio.run_coroutine_threadsafe(
            self._disconnect("Application closing"), self._loop
        )
        with suppress(TimeoutError, OSError):
            future.result(timeout=timeout)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=timeout)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self._loop.close()

    def _submit(self, coroutine: Any) -> None:  # noqa: ANN401
        if self._stopping:
            coroutine.close()
            return
        future: Future[None] = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        future.add_done_callback(self._report_future_error)

    def _report_future_error(self, future: Future[None]) -> None:
        try:
            future.result()
        except asyncio.CancelledError:
            return
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            self.error_occurred.emit("Internal SSH error", type(error).__name__)

    async def _connect(
        self,
        profile: ConnectionProfile,
        password: str | None,
        passphrase: str | None,
    ) -> None:
        await self._disconnect("Replacing connection", emit_signal=False)
        self.state_changed.emit("connecting")
        try:
            self._connection = await asyncssh.connect(
                profile.host,
                port=profile.port,
                username=profile.username or (),
                known_hosts=self._known_hosts_source(),
                client_keys=self._client_keys(profile),
                password=password,
                passphrase=passphrase,
                preferred_auth=self._preferred_auth(profile),
                connect_timeout=profile.connect_timeout,
                keepalive_interval=30,
                keepalive_count_max=3,
                encoding="utf-8",
                errors="replace",
            )
            self._process = await self._connection.create_process(
                term_type="xterm-256color",
                term_size=self._terminal_size,
                encoding="utf-8",
                errors="replace",
            )
        except asyncssh.HostKeyNotVerifiable:
            await self._handle_unverified_key(profile, password, passphrase)
            return
        except asyncssh.PermissionDenied as error:
            self._connection = None
            self.state_changed.emit("error")
            self.error_occurred.emit("Authentication failed", str(error))
            return
        except (asyncssh.Error, OSError, TimeoutError) as error:
            self._connection = None
            self.state_changed.emit("error")
            self.error_occurred.emit("SSH connection failed", str(error))
            return
        self._pending_credentials = None
        self.state_changed.emit("connected")
        self.connected.emit()
        self._reader_task = asyncio.create_task(self._read_output())

    async def _handle_unverified_key(
        self,
        profile: ConnectionProfile,
        password: str | None,
        passphrase: str | None,
    ) -> None:
        try:
            options = asyncssh.SSHClientConnectionOptions(
                connect_timeout=profile.connect_timeout,
            )
            key = await asyncssh.get_server_host_key(
                profile.host,
                port=profile.port,
                options=options,
            )
        except (asyncssh.Error, OSError, TimeoutError) as error:
            self.state_changed.emit("error")
            self.error_occurred.emit("Could not inspect server host key", str(error))
            return
        if key is None:
            self.state_changed.emit("error")
            self.error_occurred.emit("Server did not present a host key", profile.host)
            return
        if self._known_entry_exists(profile):
            self.state_changed.emit("error")
            self.error_occurred.emit(
                "Host key changed or was revoked",
                "Connection blocked. Verify server independently and update known_hosts manually.",
            )
            return
        algorithm = key.get_algorithm()
        fingerprint = key.get_fingerprint("sha256")
        self._pending_key = (profile, key, algorithm, fingerprint)
        self._pending_credentials = (password, passphrase)
        self.state_changed.emit("host-key-prompt")
        self.unknown_host_key.emit(profile.host, profile.port, algorithm, fingerprint)

    async def _answer_host_key(self, accept: bool) -> None:
        pending = self._pending_key
        credentials = self._pending_credentials
        self._pending_key = None
        self._pending_credentials = None
        if pending is None:
            return
        profile, key, _, _ = pending
        if not accept:
            self.state_changed.emit("disconnected")
            self.disconnected.emit("Unknown host key rejected")
            return
        try:
            await asyncio.to_thread(self._append_known_host, profile, key)
        except OSError as error:
            self.state_changed.emit("error")
            self.error_occurred.emit("Could not save trusted host key", str(error))
            return
        password, passphrase = credentials or (None, None)
        await self._connect(profile, password, passphrase)

    async def _read_output(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            while not process.stdout.at_eof():
                data = await process.stdout.read(8192)
                if data:
                    self.output_received.emit(data)
        except (asyncssh.Error, OSError) as error:
            self.error_occurred.emit("SSH stream ended unexpectedly", str(error))
        finally:
            if self._process is process:
                self._process = None
                self.state_changed.emit("disconnected")
                self.disconnected.emit("Remote shell closed")

    async def _send(self, text: str) -> None:
        if self._process is None or self._process.stdin.is_closing():
            self.error_occurred.emit("Not connected", "Connect before sending terminal input.")
            return
        self._process.stdin.write(text)
        await self._process.stdin.drain()

    async def _resize_terminal(self) -> None:
        if self._process is not None:
            self._process.change_terminal_size(*self._terminal_size)

    async def _disconnect(self, reason: str, *, emit_signal: bool = True) -> None:
        self.state_changed.emit("disconnecting")
        for listener in self._listeners.values():
            listener.close()
        if self._listeners:
            await asyncio.gather(
                *(listener.wait_closed() for listener in self._listeners.values()),
                return_exceptions=True,
            )
        self._listeners.clear()
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None
        if self._process is not None:
            self._process.close()
            await self._process.wait_closed()
            self._process = None
        if self._connection is not None:
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None
        if emit_signal:
            self.state_changed.emit("disconnected")
            self.disconnected.emit(reason)

    async def _transfer(
        self,
        operation_id: str,
        upload: bool,
        local_path: Path,
        remote_path: str,
        recurse: bool,
    ) -> None:
        if self._connection is None:
            self.transfer_finished.emit(operation_id, False, "No active SSH connection")
            return

        def progress(_source: bytes, _destination: bytes, copied: int, total: int) -> None:
            self.transfer_progress.emit(operation_id, copied, total)

        try:
            async with self._connection.start_sftp_client() as sftp:
                if upload:
                    await sftp.put(
                        local_path,
                        remote_path,
                        preserve=True,
                        recurse=recurse,
                        progress_handler=progress,
                    )
                else:
                    await sftp.get(
                        remote_path,
                        local_path,
                        preserve=True,
                        recurse=recurse,
                        progress_handler=progress,
                    )
        except (asyncssh.Error, OSError) as error:
            self.transfer_finished.emit(operation_id, False, str(error))
            return
        self.transfer_finished.emit(operation_id, True, "Transfer completed")

    async def _start_tunnel(self, spec: TunnelSpec) -> None:
        if self._connection is None:
            self.error_occurred.emit("Cannot start tunnel", "No active SSH connection")
            return
        if spec.id in self._listeners:
            self.error_occurred.emit("Cannot start tunnel", "Tunnel ID already exists")
            return
        try:
            if spec.kind is TunnelKind.LOCAL:
                listener = await self._connection.forward_local_port(
                    spec.listen_host,
                    spec.listen_port,
                    spec.destination_host,
                    spec.destination_port,
                )
            elif spec.kind is TunnelKind.REMOTE:
                listener = await self._connection.forward_remote_port(
                    spec.listen_host,
                    spec.listen_port,
                    spec.destination_host,
                    spec.destination_port,
                )
            else:
                listener = await self._connection.forward_socks(
                    spec.listen_host,
                    spec.listen_port,
                )
        except (asyncssh.Error, OSError) as error:
            self.error_occurred.emit("Could not start tunnel", str(error))
            return
        self._listeners[spec.id] = listener
        self.tunnel_started.emit(spec.id, listener.get_port())

    async def _stop_tunnel(self, tunnel_id: str) -> None:
        listener = self._listeners.pop(tunnel_id, None)
        if listener is None:
            return
        listener.close()
        await listener.wait_closed()
        self.tunnel_stopped.emit(tunnel_id)

    @staticmethod
    def _client_keys(profile: ConnectionProfile) -> tuple[str, ...] | None:
        if profile.auth_method is AuthMethod.PRIVATE_KEY and profile.private_key is not None:
            return (str(profile.private_key),)
        if profile.auth_method is AuthMethod.PASSWORD:
            return ()
        return None

    @staticmethod
    def _preferred_auth(profile: ConnectionProfile) -> str:
        if profile.auth_method is AuthMethod.PASSWORD:
            return "password,keyboard-interactive"
        if profile.auth_method is AuthMethod.PRIVATE_KEY:
            return "publickey"
        return "publickey,hostbased"

    @staticmethod
    def _known_entry_exists(profile: ConnectionProfile) -> bool:
        if not _KNOWN_HOSTS.exists():
            return False
        try:
            known_hosts = asyncssh.read_known_hosts(str(_KNOWN_HOSTS))
            addresses = {profile.host}
            for info in socket.getaddrinfo(profile.host, profile.port, type=socket.SOCK_STREAM):
                addresses.add(str(info[4][0]))
            for address in addresses:
                match = known_hosts.match(profile.host, address, profile.port)
                if any(match[index] for index in range(5)):
                    return True
        except (OSError, socket.gaierror, asyncssh.Error):
            return True
        return False

    @staticmethod
    def _known_hosts_source() -> str | asyncssh.SSHKnownHosts:
        """Use known_hosts file when present, otherwise empty verified trust set."""
        if _KNOWN_HOSTS.exists():
            return str(_KNOWN_HOSTS)
        return asyncssh.import_known_hosts("")

    @staticmethod
    def _append_known_host(profile: ConnectionProfile, key: asyncssh.SSHKey) -> None:
        _KNOWN_HOSTS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        host_pattern = (
            profile.host
            if profile.port == _DEFAULT_SSH_PORT
            else f"[{profile.host}]:{profile.port}"
        )
        public_key = key.export_public_key("openssh").decode("ascii").strip()
        line = f"{host_pattern} {public_key}\n".encode()
        descriptor = os.open(_KNOWN_HOSTS, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, line)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
