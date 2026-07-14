"""Cross-platform source and native-bundle launcher contract tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"


def _platform_launcher() -> list[str]:
    if os.name != "nt":
        return [str(_SCRIPTS / "launch.sh")]
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")
    return [powershell, "-NoLogo", "-NoProfile", "-File", str(_SCRIPTS / "launch.ps1")]


def _source_environment() -> dict[str, str]:
    return {
        **os.environ,
        "QT_QPA_PLATFORM": "offscreen",
        "SSH_IT_LAUNCH_MODE": "source",
    }


def test_launch_files_exist_with_safe_source_contract() -> None:
    """Every supported shell has an entry point and none performs implicit installation."""
    expected = {"launch.sh", "launch.command", "launch.ps1", "launch.cmd"}
    assert {path.name for path in _SCRIPTS.iterdir() if path.is_file()} == expected
    posix = (_SCRIPTS / "launch.sh").read_text(encoding="utf-8")
    powershell = (_SCRIPTS / "launch.ps1").read_text(encoding="utf-8")
    combined = f"{posix}\n{powershell}".casefold()
    assert "--frozen --no-sync" in posix
    assert "--frozen --no-sync" in powershell
    assert "curl " not in combined
    assert "invoke-webrequest" not in combined
    assert "pip install" not in combined
    if os.name != "nt":
        assert os.access(_SCRIPTS / "launch.sh", os.X_OK)
        assert os.access(_SCRIPTS / "launch.command", os.X_OK)


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell syntax check")
def test_posix_launchers_have_valid_shell_syntax() -> None:
    """Linux/macOS entry points parse under portable POSIX shell mode."""
    shell = shutil.which("sh")
    assert shell is not None
    for path in (_SCRIPTS / "launch.sh", _SCRIPTS / "launch.command"):
        subprocess.run([shell, "-n", str(path)], check=True, cwd=_ROOT)  # noqa: S603


def test_launcher_source_smoke_test_from_unrelated_directory(tmp_path: Path) -> None:
    """Platform launcher resolves repository location and forwards app arguments."""
    result = subprocess.run(  # noqa: S603
        [*_platform_launcher(), "--smoke-test"],
        cwd=tmp_path,
        env=_source_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name == "nt", reason="macOS/POSIX command wrapper")
def test_macos_command_wrapper_forwards_smoke_test(tmp_path: Path) -> None:
    """Finder-compatible command wrapper preserves working-directory independence and arguments."""
    result = subprocess.run(  # noqa: S603
        [str(_SCRIPTS / "launch.command"), "--smoke-test"],
        cwd=tmp_path,
        env=_source_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_powershell_launcher_source_smoke_test(tmp_path: Path) -> None:
    """PowerShell implementation parses, resolves repository root, and forwards arguments."""
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")
    result = subprocess.run(  # noqa: S603
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-File",
            str(_SCRIPTS / "launch.ps1"),
            "--smoke-test",
        ],
        cwd=tmp_path,
        env=_source_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows CMD wrapper")
def test_windows_cmd_wrapper_forwards_smoke_test(tmp_path: Path) -> None:
    """Command Prompt wrapper reaches PowerShell launcher and preserves exit status."""
    command_prompt = shutil.which("cmd.exe")
    assert command_prompt is not None
    result = subprocess.run(  # noqa: S603
        [
            command_prompt,
            "/d",
            "/s",
            "/c",
            str(_SCRIPTS / "launch.cmd"),
            "--smoke-test",
        ],
        cwd=tmp_path,
        env=_source_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_launcher_rejects_unknown_mode(tmp_path: Path) -> None:
    """Invalid resolution policy fails before any executable starts."""
    environment = {**os.environ, "SSH_IT_LAUNCH_MODE": "download"}
    result = subprocess.run(  # noqa: S603
        _platform_launcher(),
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 64
    assert "must be auto, bundle, or source" in result.stderr
