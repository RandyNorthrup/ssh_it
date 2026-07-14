# Security policy and model

## Report a vulnerability

Do not publish credentials, private keys, hostnames, or exploit details in a public issue. Send a
minimal private report to the project maintainer with affected version and reproduction steps.

## Trust boundaries

SSH It trusts the local desktop user, installed Python/Qt dependencies, explicitly accepted SSH
host keys, and authenticated remote account. It does not treat command-library text or remote
terminal output as trusted executable data. Commands only run after a user action.

## Credential handling

- Passwords and private-key passphrases are never stored in app settings or files.
- Opt-in password persistence uses only a recommended OS credential-vault backend. SSH It refuses
  null, fail, plaintext, and third-party alternate-file backends.
- Save is requested at connection time but performed only after successful authentication.
- Saved profiles contain host, port, username, auth method, private-key path, and library choice.
- Recents and favorites contain the same non-secret connection metadata.
- Bundled factory credentials are public, product-scoped reference data, not user secrets. The UI
  masks literal values, cites vendor documentation, requires an explicit fill action, and never
  probes a target or connects automatically. Factory values are not offered for vault storage.
- Blank factory passwords are accepted only after an explicit selection of a matching documented
  entry. An untouched empty password field remains an error.
- Private keys stay in their original files and are read by AsyncSSH.
- Terminal output can contain secrets produced by a remote command; users must handle copied or
  exported output accordingly. SSH It does not write terminal transcripts by default. Exports use
  escaped HTML or plain text and atomic owner-only files where the operating system supports POSIX
  permissions.

## Host keys

The app uses `~/.ssh/known_hosts`. Unknown hosts show SHA-256 fingerprint and key algorithm before
trust. Accepted public keys append using OpenSSH format. Existing mismatches stop the connection.
Verify first-use fingerprints through a separate trusted channel.

## Command and forwarding safety

Library entries have visible risk labels. Destructive commands require confirmation at execution.
Local forwarding and SOCKS bind to `127.0.0.1` by default. Binding to `0.0.0.0`, `::`, or another
non-loopback address can expose services and requires explicit acknowledgement.

Factory references are convenience data, not authorization. Users must confirm device ownership,
exact product/firmware scope, and network safety, then replace defaults immediately. The library
does not perform credential spraying, fallback attempts, discovery, or background authentication.

## Dependency and release controls

CI runs lint, type checks, tests, Bandit, and dependency audit. Release builders run on each target
OS because Python desktop bundles are platform-specific. Production installers should be signed;
macOS builds should also be notarized.

## Launcher safety

Cross-platform launchers resolve repository root from their own file location, not current working
directory. Auto mode runs only expected platform bundle or already-prepared source environment.
Source fallback uses locked `uv` metadata with synchronization disabled. Launchers never run package
installation, download commands, environment files, `eval`, or shell-generated command text.

`launch.cmd` starts repository-owned `launch.ps1` with process-scoped PowerShell execution-policy
bypass. This avoids machine policy changes and does not weaken policy for later PowerShell sessions.
Use signed scripts for public Windows distribution.

## Release safety checklist

- Host-key mismatch and unknown-key rejection paths pass integration tests.
- Passwords never appear in settings, profiles, recents, logs, or transcript exports unless a
  remote system itself prints them.
- Factory references never trigger probing, fallback attempts, automatic connection, or vault save.
- Parameter validation blocks multiline values, shell and option injection in unquoted template
  tokens, unsafe URLs, and invalid ports. A new connection clears prior-target transcript state.
- Destructive library actions require typed confirmation; non-loopback forwarding requires warning.
- HTML export treats all terminal content as hostile and escapes it before rendering.
- Launchers reject unknown resolution modes and pass source and bundle smoke tests.
- Bandit, dependency audit, strict types, lint, coverage, and a real localhost SSH/SFTP/tunnel test
  must pass before release.
