# Command library coverage

SSH It's bundled command library is a curated technician reference, not a blind command runner.
Every entry includes an explanation, platform, vendor/use-case library, category, risk level, and
HTTPS documentation source. Commands with required values use typed `${parameter}` fields so the
composer can select each field, explain its expected format, validate it, and rank contextual
values.

## Audited bundle snapshot

| Library | Commands | Main technician workflows |
| --- | ---: | --- |
| Arista EOS | 12 | system, interfaces, routing, discovery, configuration |
| Aruba AOS-CX | 20 | interfaces, VLAN, LACP, VSX, routing, BGP, OSPF, PoE |
| Cisco IOS / IOS XE | 12 | system, interfaces, VLAN, routing, configuration |
| Cisco NX-OS | 20 | Nexus hardware, interfaces, vPC, L2, routing, environment |
| Cisco Secure Firewall ASA | 20 | policy, NAT, connections, VPN, HA, packet tracing |
| Containers | 12 | Docker/Podman inventory, logs, storage, networking, Compose lifecycle |
| Dell SmartFabric OS10 | 20 | interfaces, VLT, EVPN, L2, BGP, OSPF, hardware |
| Fortinet FortiOS | 12 | system, interfaces, routing, sessions, BGP, VPN, diagnostics |
| General Linux | 12 | host, processes, storage, network, DNS, services, logs |
| Juniper Junos | 13 | system, interfaces, L2, routing, neighbors, hardware, commit safety |
| Kubernetes | 20 | context, nodes, workloads, logs, events, network, storage, RBAC |
| MikroTik RouterOS | 12 | system, interfaces, L2, routing, firewall, health, export |
| Netgate pfSense | 20 | PF rules/states/NAT, capture, interfaces, routes, DNS, logs |
| Palo Alto PAN-OS | 20 | system, interfaces, routes, sessions, counters, HA, VPN |
| Secure File Operations | 10 | SFTP/SCP/rsync, hashing, permissions, archives |
| SSH / OpenSSH | 10 | connection, jump hosts, local/remote/SOCKS forwarding |
| UniFi | 39 | AP, switch, gateway, packet capture, adoption, logs, legacy USG, server |
| Windows PowerShell | 20 | system, network, DNS, services, events, storage, SMB |

Current audited totals: **304 commands**, **18 libraries**, **208 categories**, **214 safe**,
**80 caution**, **10 destructive**, and **83 parameterized templates**. Automated tests enforce
minimums of 300 commands, 18 libraries, 150 categories, ten commands per library, 65 parameterized
templates, full ID uniqueness, valid schema, risk depth, and HTTPS sources. These are regression
floors, not growth limits.

## Enterprise-use safeguards

- Library text never executes automatically. Insert and connect remain separate actions.
- Destructive items require an exact `RUN` confirmation after the target is connected.
- Caution identifies sensitive output, long-running inspection, simulations, or session impact.
- Vendor selection narrows both search and IntelliSense before or during a connection.
- Product/firmware variants can differ. The explanation and source help the technician verify the
  exact platform and privilege mode before execution.
- The app does not claim that a successful command is safe for every environment. Change control,
  authorization, backups, redundancy, and maintenance windows remain operator responsibilities.

## Coverage model

The bundle deliberately spans campus and data-center switching, routing, firewalls, VPNs,
wireless/device adoption, Linux and Windows servers, containers and Kubernetes, secure file
operations, SSH tunneling, observability, storage, DNS, packet capture, high availability, and
configuration review. Read-only diagnosis dominates the bundle; disruptive lifecycle actions are
few, clearly labelled, and confirmation-gated.
