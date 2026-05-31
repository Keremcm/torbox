# TorBox

`TorBox` is a simple tool designed to route all outgoing traffic through Tor on your Linux system. This project includes `main.py` and `install.sh`; `main.py` manages the Tor configuration and `iptables` rules, while `install.sh` installs only the missing packages (without reinstalling existing ones) and creates the `torbox` command at `/usr/local/bin/torbox`.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Testing and Verification](#testing-and-verification)
- [Stopping](#stopping)
- [Troubleshooting](#troubleshooting)
- [Distribution Compatibility](#distribution-compatibility)
- [Security](#security)
- [Notes](#notes)

---

## Features

- Routes all system outgoing TCP and DNS traffic through Tor
- Writes Tor configuration to `torrc.d/torbox.conf`
- Automatically adds `%include` directive to `/etc/tor/torrc` if missing
- Uses a dedicated chain (`TORBOX`) within `iptables`
- Protects existing Tor system traffic without over-blocking
- Idempotent `iptables` rules — no duplicate entries on repeated starts
- Waits for Tor to be fully active before applying rules (polling-based)
- Optional strict IPv6 leak protection via `--strict-ipv6` flag
- Rolls back `iptables` changes automatically on failure
- System-wide installation of the `torbox` command via `install.sh`
- Installs only missing packages without reinstalling existing ones

---

## Requirements

- Linux
- Terminal with `bash` support
- `python3`
- `systemd`-based service management (`systemctl`)
- `tor`
- `curl`
- `iptables`
- `ip6tables` (recommended, for IPv6 leak protection)
- `python3-requests` or `requests` as a package dependency
- Root privileges

> `install.sh` detects these packages and installs only the missing ones. It does not update package databases.

---

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Keremcm/torbox
cd torbox
```

2. Run the `install.sh` script:

```bash
sudo bash ./install.sh
```

3. After installation, the command can be used as follows:

```bash
sudo torbox start
sudo torbox stop
sudo torbox status
sudo torbox test
```

---

## Usage

### Starting

To start TorBox:

```bash
sudo torbox start
```

This command:

- Verifies root privileges
- Writes the Tor configuration to `TORRC_CUSTOM`
- Ensures `/etc/tor/torrc` includes the `torrc.d` directory
- Starts or restarts the Tor service and waits for it to become active
- Creates a dedicated chain named `TORBOX` within `iptables`
- Redirects TCP and DNS requests to Tor
- Runs a connectivity test

To start with strict IPv6 leak protection (blocks all IPv6 traffic):

```bash
sudo torbox start --strict-ipv6
```

> **Note:** In strict mode, sites that are IPv6-only or prefer IPv6 (e.g. some Google and YouTube endpoints) may become unreachable. Use this mode when anonymity is the priority.

### Stopping

To restore traffic to normal:

```bash
sudo torbox stop
```

This command:

- Removes the `OUTPUT` redirect for the `TORBOX` chain
- Flushes and deletes the `TORBOX` chain
- Removes IPv6 rules if strict mode was active
- Displays the current status

### Status

To check whether TorBox rules are active:

```bash
sudo torbox status
```

### Test

To test the Tor connection:

```bash
sudo torbox test
```

This command runs both a `curl`-based and a Python `requests`-based check (if `requests` is installed).

---

## How It Works

`main.py` follows these steps:

1. Creates a `TorTrafficRedirector` instance
2. When `start` is called:
   - Performs a root privilege check
   - Updates the Tor configuration and ensures `torrc.d` is included
   - Starts the Tor service and polls until it is fully active
   - Creates the `TORBOX` chain within `iptables`
   - Redirects all TCP and DNS traffic to Tor ports
   - Optionally blocks all IPv6 traffic (`--strict-ipv6`)
3. When `stop` is called:
   - Removes the `TORBOX` redirect from the `OUTPUT` chain
   - Deletes the `TORBOX` chain
   - Cleans up IPv6 rules if present
4. The `status` and `test` commands provide information about the system state

---

## Configuration

The Tor configuration is written by the project to `/etc/tor/torrc.d/torbox.conf`:

```
# TorBox - Required settings for Transparent Proxy
VirtualAddrNetworkIPv4 10.192.0.0/10
AutomapHostsOnResolve 1
TransPort 9040
DNSPort 5353
SocksPort 9050
ControlPort 9051
CookieAuthentication 1
ExitPolicy reject *:*
```

This file is automatically loaded when the Tor service restarts. If your system's `/etc/tor/torrc` does not already include a `%include /etc/tor/torrc.d/*.conf` directive, TorBox adds it automatically.

---

## Testing and Verification

### Manual Verification

After TorBox is running, you can use the following commands:

```bash
curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip
curl -s https://check.torproject.org/api/ip
```

The second command should show a Tor IP address. If `requests` is installed, `sudo torbox test` also performs an IP check over Tor.

---

## Stopping

The safe way to revert TorBox traffic:

```bash
sudo torbox stop
```

This command deletes the created `TORBOX` chain from the system `iptables` table and cleans up any IPv6 rules. It does not touch any other `nat` rules.

---

## Troubleshooting

### `torbox` command not found

- If `install.sh` ran correctly, `/usr/local/bin/torbox` should have been created.
- Verify the file exists with `ls -l /usr/local/bin/torbox`.

### `iptables` conflict with `iptables-nft`

- `install.sh` only installs missing packages without reinstalling existing ones.
- `pacman` users may encounter `iptables`/`iptables-nft` conflicts. Prefer the `iptables` package already running on your system.

### Python test is skipped if `requests` is missing

- `main.py` falls back to the `curl`-based test if `requests` is not installed.
- To install `requests`, use `sudo apt install python3-requests` or the appropriate package for your distribution.

### Tor service fails to start

- Check the service status with `sudo systemctl status tor`.
- Inspect error logs with `sudo journalctl -u tor -n 50`.

### Can't reach some websites after starting

- Sites like YouTube and Google serve traffic over IPv6. If you used `--strict-ipv6`, those connections are blocked by design.
- Restart without the flag to restore normal reachability: `sudo torbox stop && sudo torbox start`.

### `torrc.d` not loaded by Tor

- On some older distributions, `/etc/tor/torrc` may not include the `torrc.d` directory automatically.
- TorBox detects this and appends the `%include` line to `torrc` automatically on start.

---

## Distribution Compatibility

`install.sh` detects and supports the following package managers:

| Package Manager | Distributions |
|---|---|
| `apt` | Ubuntu, Debian |
| `dnf` | Fedora, CentOS, AlmaLinux, Rocky Linux |
| `pacman` | Arch, Manjaro, EndeavourOS |
| `zypper` | openSUSE, SLES |
| `apk` | Alpine |

---

## Security

TorBox includes several hardening measures:

- **DNS leak protection** — Both TCP and UDP port 53 traffic is redirected to Tor's `DNSPort`
- **IPv6 leak protection** — Optional `--strict-ipv6` mode blocks all outgoing IPv6 traffic that cannot be routed through Tor
- **Idempotent rules** — Each `iptables` rule is checked with `-C` before insertion; no duplicates are created
- **Failure rollback** — If any rule fails to apply, the entire `TORBOX` chain is removed to avoid a broken half-configured state
- **Tor service polling** — TorBox waits for Tor to be confirmed active before applying rules, rather than relying on a fixed sleep
- **`ExitPolicy reject *:*`** — Prevents the local Tor instance from being used as an exit relay
- **Dedicated `iptables` chain** — All rules are isolated in the `TORBOX` chain; existing `nat` rules are never modified

---

## Notes

- This project requires `root` privileges.
- `install.sh` does not update the package database; it only installs missing packages from the existing database.
- TorBox routes all your TCP and DNS traffic through the Tor network. Ensure your system and application configurations are Tor-compatible.
- Because this tool uses a dedicated `iptables` chain, it does not directly interfere with your other existing `nat` configurations.
