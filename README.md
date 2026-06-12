# snell-server-updater

A CLI tool for automatically discovering, downloading, and upgrading the [Snell](https://kb.nssurge.com/surge-knowledge-base/release-notes/snell) server binary.

Features proper semantic version comparison (including beta/pre-release tags) and a one-shot systemd service deployment.

## Features

- 🔍 **Auto-discovery** — scrapes all available versions from the official release page
- 🧪 **Semantic versioning** — correctly parses and compares pre-release versions like `v6.0.0b1`
- 🖥️ **Architecture auto-detection** — supports `amd64` / `i386` / `aarch64` / `armv7l`, with manual override
- 🛡️ **Safe installation** — verifies the downloaded binary before replacing the existing one
- ⚡ **One-shot systemd deployment** — creates system user, config directory, interactive wizard, and unit files

## Dependencies

- **Python** 3.7+
- Standard library only — no third-party packages required

## Setup

```bash
git clone https://github.com/love4taylor/snell-server-updater.git
cd snell-server-updater
chmod +x snell-server-updater.py
```

## Usage

### Fresh install (first-time setup)

When Snell is **not yet installed** on your system, use `--install` to download the binary and set up the systemd service in one shot:

```bash
sudo python3 snell-server-updater.py --install
# or
sudo python3 snell-server-updater.py -i
```

This performs the following steps:
1. Downloads the latest stable `snell-server` binary to `/usr/local/bin/snell-server`
2. Creates a system user `snell` (shell: `/usr/sbin/nologin`)
3. Creates the config directory `/usr/local/etc/snell-server/`
4. Runs the interactive wizard to generate `server.conf`
5. Installs `snell-server.service` and `snell-server@.service`
6. Runs `systemctl daemon-reload`

After deployment, start the service with:

```bash
# Single instance
systemctl enable --now snell-server

# Multiple instances (via the @ template)
systemctl enable --now snell-server@myprofile
```

If you already have a config file or prefer to skip the interactive wizard:

```bash
sudo python3 snell-server-updater.py --install --skip-wizard
```

### Upgrade an existing installation

> **Requirement:** `snell-server` must already be present in `PATH` (e.g. from a previous manual install or `--install`).

```bash
sudo python3 snell-server-updater.py
```

The script automatically:
1. Detects the current CPU architecture
2. Locates the existing `snell-server` binary (searches `PATH`)
3. Reads the current version
4. Discovers the latest stable version from the official release page
5. Downloads and installs if a newer version is available

### Install a specific version

```bash
sudo python3 snell-server-updater.py --version v5.0.1
# The 'v' prefix is optional
sudo python3 snell-server-updater.py -V 6.0.0b1
```

### Include beta releases

```bash
sudo python3 snell-server-updater.py --beta
# or
sudo python3 snell-server-updater.py -b
```

### Override architecture

```bash
sudo python3 snell-server-updater.py --arch aarch64
```

### Force install (even if already up-to-date)

```bash
sudo python3 snell-server-updater.py --force
# or
sudo python3 snell-server-updater.py -f
```

### Dry run (preview only, no changes)

```bash
sudo python3 snell-server-updater.py --dry-run
# or
sudo python3 snell-server-updater.py -n
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--version VER` | `-V` | Install a specific version (e.g. `v5.0.1`, `v6.0.0b1`) |
| `--beta` | `-b` | Include beta/pre-release versions during auto-discovery |
| `--arch ARCH` | — | Override CPU architecture detection |
| `--dry-run` | `-n` | Preview actions without making any changes |
| `--force` | `-f` | Install even if the target version is not newer than the current one |
| `--install` | `-i` | Install/update the binary and set up the systemd service |
| `--skip-wizard` | — | Skip the interactive configuration wizard |

## systemd paths

| Path | Description |
|------|-------------|
| `/usr/local/bin/snell-server` | Installed binary |
| `/usr/local/etc/snell-server/` | Configuration directory |
| `/usr/local/etc/snell-server/server.conf` | Default configuration file |
| `/etc/systemd/system/snell-server.service` | Single-instance unit |
| `/etc/systemd/system/snell-server@.service` | Multi-instance template |

## Safety

- The downloaded binary is verified first (`snell-server -v`) — only after a successful check is the existing binary replaced.
- If verification fails, the current binary is left untouched.
- Use `--dry-run` to preview every action before committing.
- Missing parent directories for the install path are created automatically.

## Version comparison

Full semantic version comparison is implemented, supporting the following formats:

| Version | Type | Precedence |
|---------|------|------------|
| `v5.0.1` | Stable / final | Higher than any pre-release |
| `v6.0.0b1` | Beta 1 | `b` = beta |
| `v6.0.0-rc2` | Release Candidate 2 | `rc` > beta |
| `v6.0.0-alpha1` | Alpha 1 | `alpha` lowest |

Pre-release precedence order: `alpha` < `beta` < `rc` < `pre`

## License

MIT License — see [LICENSE](LICENSE) for details.
