# SSH It design plan

## Product intent

Make frequent SSH administration safer and faster without hiding what will run. User chooses an
optional vendor/library before connecting. Blank means all libraries. Search and completion remain
available before and during a session, so commands can be prepared without a live device.

## UX structure

1. **Quick Connect bar** — recent/favorite profile, host, port, user, auth, key, secret, vendor,
   save/favorite actions, and connection state. It remains visible while other docks move.
2. **Terminal workspace** — terminal screen, command composer, ranked completion popup, bounded
   history, interrupt controls, and safe plain-text/HTML transcript export.
3. **Libraries dock** — tabbed command search and product-scoped factory credential references.
   Commands have text/vendor/category/risk filters, explanations, sources, and insert actions.
   Credentials have text/vendor filters, masked values, exact scope, warning, source, and explicit
   username-only or login fill actions.
4. **Operations tabs** — SFTP upload/download and local/remote/SOCKS forwarding with live status.
5. **Help and status** — keyboard map, security explanation, non-colour status text, and errors.

Narrow windows stack connection fields and allow dock/tab resizing. Controls use standard Qt
widgets so screen readers receive native roles. Every editable field and icon-only action receives
an accessible name, accessible description, buddy label, tooltip, and keyboard path. Status never
depends on colour alone.

## Architecture

```text
Qt main thread
  MainWindow
    ConnectionPanel ── ConnectionProfile
    TerminalPane ───── CompletionEngine ── CommandLibrary
    LibraryPanel ───── CommandLibrary
    CredentialLibraryPanel ── CredentialLibrary
    TransferPanel ┐
    TunnelPanel   ┴──── SSHSessionController
                              │ thread-safe asyncio loop
                              ├─ AsyncSSH connection + PTY
                              ├─ SFTP client operations
                              └─ forwarding listeners
```

- `models.py`: immutable validated domain values.
- `library.py`: package-data loading, schema validation, filters, deterministic ranking.
- `completion.py`: token-aware ranking across commands, templates, and session history.
- `credentials.py`: validated public factory references, precise scope, and deterministic search.
- `settings.py`: versioned profiles and preferences; no secrets.
- `secrets.py`: OS credential-vault adapter; recommended secure backends only.
- `ssh/session.py`: isolated asyncio lifecycle with Qt signals and cleanup.
- `terminal.py`: VT screen adapter and bounded transcript handling.
- `ui/`: Qt widgets, actions, dialogs, responsive layouts, accessibility metadata.
- `scripts/`: location-independent Linux, macOS, PowerShell, and Command Prompt launchers.

## Launch resolution

Launchers use deterministic `auto`, `bundle`, or `source` policy. Auto mode checks only native
artifact path for current operating system, then prepared project environment. Source execution
uses `.venv` directly or `uv run --frozen --no-sync`; launcher never changes lockfile, creates an
environment, or installs packages. All application arguments pass through unchanged. Tests run
launchers outside repository working directory and exercise app's noninteractive smoke mode.

## Security decisions

- OpenSSH `known_hosts` is mandatory. Unknown keys require explicit fingerprint confirmation.
- Changed host keys stop connection; app never offers a one-click silent replacement.
- Secrets are passed directly to AsyncSSH and cleared from UI after connection attempt. Optional
  persistence uses OS credential vault only, is user-confirmed, and happens after successful auth.
- Agent forwarding and X11 forwarding are absent because both expand remote-host trust.
- Forward listeners default to loopback. Non-loopback binds show a warning.
- Command metadata includes `safe`, `caution`, or `destructive`. Destructive run requires exact
  confirmation; inserting text never executes it.
- SFTP uses current verified SSH connection. No shell interpolation is used for file transfers.
- Logs contain state and error categories, not credentials or command content.
- Public factory references never trigger connection attempts, are not saved to the vault, and are
  separated visually and structurally from personal credentials. Documented empty passwords need
  an explicit library fill; a normal empty field still fails validation.
- Launchers never evaluate configuration text, source shell files, or fetch code. Native bundle
  path and source interpreter path derive only from launcher location.

## Completion model

Candidate score combines exact prefix, substring, token overlap, fuzzy similarity, active vendor,
recent use, and risk. Local library suggestions are deterministic and never execute automatically.
Template placeholders use `${name}` syntax and open a labelled form before insertion/run. Session
history is memory-only by default.

## Command data contract

Bundled JSON is validated at startup. Each item has unique ID, title, command, explanation,
vendor list, categories, tags, risk, connection requirement, platforms, and official source URL
when available. A bad item fails closed with a clear startup error. Tests enforce schema, unique
IDs, placeholder syntax, risk labels, and enterprise minimum coverage: 300 commands, 18 libraries,
150 categories, 65 parameterized templates, and at least ten commands in every library. The
audited matrix is documented in `LIBRARY.md`.

## Factory credential data contract

Each entry has a unique ID, vendor, matching command-library vendor, product scope, username,
password kind, explanation, safety warning, and HTTPS vendor source. Password kind is one of
static, intentionally blank, or device-specific. Validation rejects contradictory values. The
app never cycles entries against a host; fill and connect are separate user actions. Bundled data
also carries an ISO review date, and breadth tests retain at least 50 references across 20 vendors.

## Delivery phases

- Phase 1: secure connection, PTY, base UI, profiles, command schema/search/completion.
- Phase 2: SFTP, tunnels, host-key trust workflow, destructive-command guardrails.
- Phase 3: Quick Connect, recents/favorites, credential vault, accessibility/UI tests, SSH
  integration tests, strict static analysis, packaging matrix.
- Phase 4: signed installers, translated library/help, optional user-authored library import.

Phase 1–3 are implemented in this repository. Signing and notarization require publisher
certificates and remain release work.
