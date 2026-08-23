# SSH It

SSH It is a cross-platform PySide6 desktop workspace for secure, interactive SSH work.
It combines connection profiles, vendor-aware command discovery, context-ranked completion,
SFTP transfers, and local/remote/SOCKS port forwarding.

## Current feature set

- Interactive SSH PTY with a terminal screen and separate command composer.
- Bounded terminal scrollback export to UTF-8 plain text or escaped standalone HTML.
- Searchable, risk-labelled library with 300+ commands across 18 vendor/use-case libraries:
  Linux, Windows PowerShell, UniFi, Cisco IOS/IOS XE, NX-OS, ASA, Junos, Arista EOS, Aruba AOS-CX,
  Dell OS10, MikroTik RouterOS, FortiOS, PAN-OS, pfSense, Kubernetes, containers, secure files, and
  OpenSSH forwarding. See [LIBRARY.md](LIBRARY.md) for the audited matrix.
- Vendor selected before connection; blank selection searches every bundled library.
- Fuzzy completion ranked by typed text, active vendor, recent commands, tags, and command risk.
- Placeholder forms for reusable command templates such as `${interface}` or `${remote_port}`.
- Password, SSH agent, and private-key authentication. Passwords and key passphrases remain
  memory-only unless user opts into OS credential-vault storage. They are never written to
  profiles or logs.
- Always-visible Quick Connect, recent endpoints, favorite profiles, and favorite commands.
- Searchable side-panel library of 50+ product-scoped public factory references across 20+ vendor
  groups. Values are masked, sourced, never tried automatically, and fill Quick Connect only after
  an explicit click. See [CREDENTIALS.md](CREDENTIALS.md) for the audited matrix.
- Optional password save prompt at connection time; storage happens only after authentication
  succeeds and only through macOS Keychain, Windows Credential Locker, or Linux Secret Service.
- Strict OpenSSH-compatible `known_hosts` checking. First-use trust shows key type and SHA-256
  fingerprint; changed keys are rejected.
- Real SFTP upload/download and real local, remote, and dynamic SOCKS tunnel controls.
- Keyboard-first navigation, visible focus, accessible names/descriptions, informative tooltips,
  scalable layouts, and system-palette-aware styling.

## Quick start

Python 3.11 or newer is required.

```bash
uv sync --extra dev
uv run ssh-it
```

Without `uv`:

```bash
python -m venv .venv
python -m pip install -e '.[dev]'
ssh-it
```

After one setup, use repository launchers from any working directory:

| Platform | Launcher |
| --- | --- |
| Linux | `./scripts/launch.sh` |
| macOS terminal | `./scripts/launch.sh` |
| macOS Finder | Double-click `scripts/launch.command` |
| Windows PowerShell | `.\scripts\launch.ps1` |
| Windows Command Prompt | `scripts\launch.cmd` |

Launchers prefer matching native bundle, then prepared source environment. They never download or
install dependencies. See [LAUNCHING.md](LAUNCHING.md) for modes, argument forwarding, setup, and
troubleshooting.

Run quality gates:

```bash
uv run ruff format --check .
uv run ruff check .
uv run actionlint .github/workflows/ci.yml
uv run yamllint .github/workflows/ci.yml .yamllint.yaml
uv run pymarkdown --config .pymarkdown.json --strict-config scan \
  README.md DESIGN.md SECURITY.md LIBRARY.md CREDENTIALS.md
uv run mypy src tests
uv run pyright
uv run pylint src/ssh_it
uv run bandit -c pyproject.toml -r src
uv run pytest
uv run pip-audit
```

Pull-request or manually started CI repeats the full gate, tests Python 3.11 through 3.13 on Linux,
macOS, and Windows, builds a native one-folder bundle on every operating system, and executes its
resource-and-widget smoke test. Direct pushes do not start builds.

## Keyboard map

| Shortcut | Action |
| --- | --- |
| `Ctrl+L` | Focus connection host |
| `Ctrl+K` | Focus command library search |
| `Ctrl+Space` | Open completion suggestions |
| `Ctrl+Enter` | Run command composer text |
| `Ctrl+Shift+Enter` | Insert selected library command |
| `Ctrl+C` while composer focused and empty | Send interrupt |
| `Ctrl+Shift+D` | Disconnect |
| `F1` | Open help |

## Profiles, recents, favorites, and passwords

Quick Connect works without saving anything. Successful endpoints enter Recents, which stores
host, port, username, auth choice, key path, and library choice but never a secret. Save named
profiles or mark profiles and commands as favorites for one-click reuse.

For password authentication, SSH It can retrieve an existing password from the OS credential
vault. When a newly typed password is used, Connect asks whether it should be saved. A requested
save occurs only after successful SSH authentication. If no recommended OS vault is available,
SSH It explains the issue and keeps the password memory-only; it never falls back to plaintext.

The **Default Credentials** side tab is separate from saved personal secrets. It contains only
public vendor factory references with exact product scope, warnings, password type, research
review date, and an official documentation link. The bundle contains 50+ references across 20+
vendors spanning network devices, firewalls, storage, out-of-band controllers, and management
cards. A reference can fill only the username or both fields; it never starts a connection.
Device-specific label, serial, MAC-derived, Cloud Key, and generated passwords are not guessed.
An intentionally blank factory password is distinct from a missing password. Replace any factory
login immediately during onboarding. Defaults are not universal across a vendor, firmware, cloud
image, adopted device, or previously configured equipment.

## Packaging

PyInstaller must run separately on each target OS. Build on Linux, macOS, and Windows:

```bash
uv sync --extra packaging
uv run pyinstaller packaging/ssh_it.spec --noconfirm
QT_QPA_PLATFORM=offscreen "dist/SSH It/SSH It" --smoke-test  # Linux verification
```

After build, same platform launcher automatically finds artifact under `dist/`. Set
`SSH_IT_LAUNCH_MODE=bundle` to require packaged application or `source` to skip it.

Unsigned local builds are suitable for testing. Public distribution needs platform signing and,
on macOS, notarization. See [DESIGN.md](DESIGN.md), [SECURITY.md](SECURITY.md),
[CREDENTIALS.md](CREDENTIALS.md), [LAUNCHING.md](LAUNCHING.md), and [LIBRARY.md](LIBRARY.md).

## Scope note

Terminal rendering targets administration shells and network-device CLIs. It supports ANSI/VT
screen output and PTY resize, but the command composer intentionally owns local completion.
Mouse-heavy full-screen terminal applications are not the primary use case.

## Support this project

If this project saves you time, you can
[buy me a coffee](https://www.paypal.com/donate/?hosted_button_id=Q9VC7B42R7K82)
via PayPal. Thank you!
