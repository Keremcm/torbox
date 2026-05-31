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
- [Notes](#notes)

---

## Features

- Routes all system outgoing traffic through Tor
- Writes Tor configuration to `torrc.d/torbox.conf`
- Uses a dedicated chain (`TORBOX`) within `iptables`
- Protects existing Tor system traffic without over-blocking
- System-wide installation of the `torbox` command via `install.sh`
- Installs only missing packages without reinstalling existing ones during setup

---

## Requirements

- Linux
- Terminal with `bash` support
- `python3`
- `systemd`-based service management (`systemctl`)
- `tor`
- `curl`
- `iptables`
- `python3-requests` or `requests` as a package dependency
- Root privileges

> `install.sh` detects these packages and installs only the missing ones. It does not update package databases.

---

## Installation

1. Download or clone the repository:

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
- Starts or restarts the Tor service
- Creates a dedicated chain named `TORBOX` within `iptables`
- Redirects TCP and DNS requests to Tor
- Runs a connectivity test

### Stopping

To restore traffic to normal:

```bash
sudo torbox stop
```

This command:

- Removes the `OUTPUT` redirect for the `TORBOX` chain
- Flushes and deletes the `TORBOX` chain
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
   - Performs a fallback root check
   - Updates the Tor configuration
   - Starts the Tor service
   - Creates the `TORBOX` chain within `iptables`
   - Redirects all TCP and DNS traffic to Tor ports
3. When `stop` is called:
   - Removes the `TORBOX` redirect from the `OUTPUT` chain
   - Deletes the `TORBOX` chain
4. The `status` and `test` commands provide information about the system state

---

## Configuration

The Tor configuration is written by the project to `/etc/tor/torrc.d/torbox.conf`:

```text
# Required settings for Transparent Proxy
VirtualAddrNetworkIPv4 10.192.0.0/10
AutomapHostsOnResolve 1
TransPort 9040
DNSPort 5353
SocksPort 9050
ControlPort 9051
CookieAuthentication 1
```

This file is automatically loaded when the Tor service restarts.

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

This command deletes the created `TORBOX` chain from the system `iptables` table. It does not touch any other `nat` rules.

---

## Troubleshooting

### `torbox` command not found

- If `install.sh` ran correctly, `/usr/local/bin/torbox` should have been created.
- If not, verify the file exists after installation with `ls -l /usr/local/bin/torbox`.

### `iptables` conflict with `iptables-nft`

- `install.sh` only installs missing packages without reinstalling existing ones.
- However, `pacman` users may encounter `iptables`/`iptables-nft` conflicts. In this case, prefer the `iptables` package already running on your system.

### Python test is skipped if `requests` is missing

- `main.py` falls back to the `curl`-based test if `requests` is not installed.
- To install `requests`, use `sudo apt install python3-requests` or the appropriate package for your distribution.

### Tor service fails to start

- Check the service status with `sudo systemctl status tor`.
- Inspect error logs with `sudo journalctl -u tor -n 50`.

---

## Distribution Compatibility

`install.sh` detects and supports the following package managers:

- `apt` (Ubuntu, Debian)
- `dnf` (Fedora, CentOS, AlmaLinux, Rocky Linux)
- `pacman` (Arch, Manjaro)
- `zypper` (openSUSE, SLES)
- `apk` (Alpine)

---

## Notes

- This project requires `root` privileges.
- `install.sh` does not update the package database; it only installs missing packages from the existing database.
- TorBox routes all your TCP and DNS traffic through the Tor network; ensure your system and application configurations are Tor-compatible to enhance connection security.
- Because this tool uses a dedicated `iptables` chain, it does not directly interfere with your other existing `nat` configurations.
