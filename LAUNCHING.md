# Cross-platform launching

SSH It includes location-independent launchers for source checkouts and native bundles. Scripts
forward every application argument, preserve exit code, and never perform dependency installation.

## One-time source setup

Install `uv`, clone repository, then prepare locked environment:

```bash
uv sync --locked
```

Launchers intentionally fail with setup guidance when neither native bundle nor prepared source
environment exists. This keeps startup deterministic and prevents surprise network or file changes.

## Platform entry points

### Linux

```bash
./scripts/launch.sh
```

### macOS

From terminal:

```bash
./scripts/launch.sh
```

From Finder, double-click `scripts/launch.command`. Both paths prefer
`dist/SSH It.app/Contents/MacOS/SSH It` when present.

### Windows PowerShell

```powershell
.\scripts\launch.ps1
```

### Windows Command Prompt or double-click

```bat
scripts\launch.cmd
```

CMD wrapper prefers PowerShell 7 (`pwsh.exe`) and falls back to Windows PowerShell. Its execution
policy override applies only to wrapper process. It does not change user or machine policy.

## Resolution modes

`SSH_IT_LAUNCH_MODE` controls selection:

| Mode | Behavior |
| --- | --- |
| `auto` | Use native bundle when present; otherwise use prepared source environment. |
| `bundle` | Require native bundle for current operating system; fail if absent. |
| `source` | Skip native bundle and require prepared source environment. |

POSIX examples:

```bash
SSH_IT_LAUNCH_MODE=bundle ./scripts/launch.sh
SSH_IT_LAUNCH_MODE=source ./scripts/launch.sh --smoke-test
```

PowerShell examples:

```powershell
$env:SSH_IT_LAUNCH_MODE = "bundle"
.\scripts\launch.ps1
Remove-Item Env:SSH_IT_LAUNCH_MODE
```

Command Prompt example:

```bat
set SSH_IT_LAUNCH_MODE=bundle
scripts\launch.cmd
```

Any other value fails before executable starts.

## Expected native artifact paths

| Platform | Path relative to repository |
| --- | --- |
| Linux | `dist/SSH It/SSH It` |
| macOS | `dist/SSH It.app/Contents/MacOS/SSH It` |
| Windows | `dist\SSH It\SSH It.exe` |

Create current-platform artifact:

```bash
uv sync --locked --extra packaging
uv run pyinstaller packaging/ssh_it.spec --noconfirm --clean
```

PyInstaller builds only for host operating system. Use CI matrix or native builders for all three.
Packaging CI exercises each launcher in `bundle` mode before uploading artifact.

## Troubleshooting

- `Permission denied` on Linux/macOS: run
  `chmod 0755 scripts/launch.sh scripts/launch.command`.
- `native bundle not found`: build on current platform or use `source` after `uv sync --locked`.
- `no prepared source environment`: run `uv sync --locked`; launcher does not do this for you.
- PowerShell policy error: use `scripts\launch.cmd`, or sign script for managed deployment.
- Diagnose without opening GUI: append `--smoke-test`; successful validation exits with status zero.
