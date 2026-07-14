# Default credential reference coverage

SSH It's bundled factory-login data is a safety-labelled technician reference, not an automated
login list. Every entry is scoped to an exact product or software generation, cites vendor-owned
HTTPS documentation, explains the password form, and warns the operator to confirm ownership and
replace the default during onboarding. The research snapshot was reviewed **2026-07-13**.

## Audited bundle snapshot

| Vendor group | References | Static | Blank | Device-specific |
| --- | ---: | ---: | ---: | ---: |
| Aruba | 1 | 0 | 1 | 0 |
| Cisco | 4 | 3 | 0 | 1 |
| Citrix | 2 | 1 | 0 | 1 |
| Dell | 4 | 3 | 0 | 1 |
| Extreme Networks | 8 | 6 | 2 | 0 |
| Fortinet | 6 | 0 | 6 | 0 |
| HPE | 1 | 0 | 0 | 1 |
| Lenovo | 1 | 1 | 0 | 0 |
| MikroTik | 2 | 0 | 1 | 1 |
| NETGEAR | 1 | 0 | 1 | 0 |
| NVIDIA | 2 | 2 | 0 | 0 |
| Netgate | 2 | 2 | 0 | 0 |
| OPNsense | 2 | 2 | 0 | 0 |
| Oracle | 1 | 1 | 0 | 0 |
| Palo Alto Networks | 2 | 2 | 0 | 0 |
| QNAP | 2 | 0 | 0 | 2 |
| Schneider Electric APC | 1 | 1 | 0 | 0 |
| SonicWall | 1 | 1 | 0 | 0 |
| Sophos | 1 | 1 | 0 | 0 |
| Supermicro | 2 | 1 | 0 | 1 |
| TP-Link | 1 | 1 | 0 | 0 |
| UniFi | 5 | 5 | 0 | 0 |
| WatchGuard | 2 | 2 | 0 | 0 |
| **Total** | **54** | **35** | **11** | **8** |

Static means the cited product documentation publishes a literal initial value. Blank means the
source explicitly documents an empty initial password; the UI distinguishes this from missing
input. Device-specific means the value comes from a chassis label, serial, MAC, Cloud Key, or
generated deployment value. SSH It does not guess those values.

## Research and safety rules

- Use vendor-owned manuals or support documents. Community lists do not qualify as bundle sources.
- Split current, legacy, virtual-appliance, and hardware behavior into separate references.
- Keep a review date and regression tests for entry count, vendor breadth, official-source breadth,
  unique IDs, warnings, password-kind consistency, and command-library mappings.
- Never probe, cycle, spray, or auto-connect. Filling a reference and connecting are separate user
  actions, and factory values are never offered for personal-vault storage.
- A default is not evidence that a device still uses it. Confirm product, firmware, authorization,
  and change-control scope first; then replace the default immediately.

The exact source URL is stored with every entry and opens from the application's details panel.
