# snell-server-updater

[![Python](https://img.shields.io/badge/Python-3.7+-3c873a?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![Standard Library](https://img.shields.io/badge/dependencies-0-brightgreen?style=flat-square)]()

A CLI tool to automatically discover, download, and upgrade the [Snell](https://kb.nssurge.com/surge-knowledge-base/release-notes/snell) server binary. Includes semantic version comparison (beta/pre-release aware), architecture auto-detection, and one-shot systemd service deployment.

[Overview](#overview) • [Setup](#setup) • [Usage](#usage) • [Options](#options) • [How it works](#how-it-works)

## Overview

**snell-server-updater** scrapes the official Snell release page, discovers all available versions, and handles the full upgrade lifecycle — from binary download and verification to systemd service provisioning. It replaces shell-based update scripts with proper semantic version parsing so that versions like `v6.0.0b1` are discovered and compared correctly.

The tool is designed for two main workflows:

- **Fresh installs** — run once to download the binary, create a system user, generate a config via interactive wizard, and install systemd units.
- **Ongoing upgrades** — run periodically (e.g. cron) to check for new releases and apply them safely.

All network operations use the Python standard library only — no third-party packages are required.

## Features

- **Semantic version comparison** — correctly parses and compares pre-release versions (`alpha`, `beta`, `rc`, `pre`)
- **Architecture auto-detection** — supports `amd64`, `i386`, `aarch64`, and `armv7l`, with manual override
- **Safe binary replacement** — verifies the downloaded binary (`snell-server -v`) before replacing the existing one
- **One-shot systemd deployment** — creates system user, config directory, wizard-generated config, and unit files
- **Dry-run mode** — preview every action without making changes
- **Force install** — reinstall even when already up-to-date
- **Beta channel** — optionally include pre-release versions during auto-discovery

## Setup

**Requirements:** Python 3.7+. No third-party packages needed — standard library only.

```bash
git clone https://github.com/love4taylor/snell-server-updater.git
cd snell-server-updater
chmod +x snell-server-updater.py
```

## Usage

### Fresh install (first-time setup)

When Snell is **not yet installed**, use `--install` to download the binary and set up the systemd service in one shot:

```bash
sudo python3 snell-server-updater.py --install
```

This performs the following steps:

1. Downloads the latest stable `snell-server` binary to `/usr/local/bin/snell-server`
2. Creates a system user `snell` (shell: `/usr/sbin/nologin`)
3. Creates the config directory `/usr/local/etc/snell-server/`
4. Runs the interactive wizard to generate `server.conf`
5. Installs `snell-server.service` and `snell-server@.service`
6. Runs `systemctl daemon-reload`

After deployment, start the service:

```bash
# Single instance
systemctl enable --now snell-server

# Multiple instances (via the @ template)
systemctl enable --now snell-server@myprofile
```

> [!TIP]
> If you already have a config or want to skip the interactive wizard, pass `--skip-wizard`:
> ```bash
> sudo python3 snell-server-updater.py --install --skip-wizard
> ```

### Upgrade an existing installation

> [!IMPORTANT]
> `snell-server` must already be present in `PATH` (e.g. from a previous manual install or `--install`).

```bash
sudo python3 snell-server-updater.py
```

The script automatically detects your current architecture, locates the existing binary, reads its version, discovers the latest stable release, and upgrades if a newer version is available.

### Install a specific version

```bash
sudo python3 snell-server-updater.py --version v5.0.1

# The 'v' prefix is optional
sudo python3 snell-server-updater.py -V 6.0.0b1
```

### Include beta releases

```bash
sudo python3 snell-server-updater.py --beta
```

### Override architecture

```bash
sudo python3 snell-server-updater.py --arch aarch64
```

### Force install (even if already up-to-date)

```bash
sudo python3 snell-server-updater.py --force
```

### Dry run (preview only, no changes)

```bash
sudo python3 snell-server-updater.py --dry-run
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--version VER` | `-V` | Install a specific version (e.g. `v5.0.1`, `v6.0.0b1`) |
| `--beta` | `-b` | Include beta/pre-release versions during auto-discovery |
| `--arch ARCH` | — | Override CPU architecture detection (`amd64`, `i386`, `aarch64`, `armv7l`) |
| `--dry-run` | `-n` | Preview actions without making any changes |
| `--force` | `-f` | Install even if already up-to-date |
| `--install` | `-i` | Download binary and set up the systemd service |
| `--skip-wizard` | — | Skip the interactive configuration wizard (only with `--install`) |

## How it works

### Version comparison

Full semantic version comparison is implemented, supporting the following formats:

| Version | Type | Precedence |
|---------|------|------------|
| `v5.0.1` | Stable / final | Higher than any pre-release |
| `v6.0.0b1` | Beta 1 | `b` = beta |
| `v6.0.0-rc2` | Release Candidate 2 | `rc` > beta |
| `v6.0.0-alpha1` | Alpha 1 | `alpha` lowest |

Pre-release precedence order: `alpha` < `beta` < `rc` < `pre`

### Safety

- The downloaded binary is verified first (`snell-server -v`) — only after a successful check is the existing binary replaced.
- If verification fails, the current binary is left untouched.
- Use `--dry-run` to preview every action before committing.
- Missing parent directories for the install path are created automatically.

### systemd paths

| Path | Description |
|------|-------------|
| `/usr/local/bin/snell-server` | Installed binary |
| `/usr/local/etc/snell-server/` | Configuration directory |
| `/usr/local/etc/snell-server/server.conf` | Default configuration file |
| `/etc/systemd/system/snell-server.service` | Single-instance unit |
| `/etc/systemd/system/snell-server@.service` | Multi-instance template |
