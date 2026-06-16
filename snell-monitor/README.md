# snell-monitor

[![Python](https://img.shields.io/badge/Python-3.9+-3c873a?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](../LICENSE)

A lightweight daemon that monitors [Snell](https://kb.nssurge.com/surge-knowledge-base/release-notes/snell) server journal logs in real time, detects connection failures, and sends batched alerts via a Telegram Bot. Designed to complement **snell-server-updater** by providing operational visibility into Snell proxy instances.

[Overview](#overview) • [Setup](#setup) • [Usage](#usage) • [Configuration](#configuration) • [How it works](#how-it-works)

## Overview

**snell-monitor** reads the systemd journal natively via `systemd.journal.Reader`, watching for error patterns in `snell-server` log output. When connection failures are detected (e.g. "connection refused"), alerts are batched, deduplicated, and forwarded to a Telegram chat.

Key design decisions:

- **Native journal access** — uses Python's `systemd.journal` bindings instead of shelling out to `journalctl`, avoiding subprocess overhead
- **Batched + deduplicated alerts** — bursts of errors from the same domain are grouped and rate-limited to prevent notification fatigue
- **Systemd hardening** — ships with a hardened service unit (`PrivateTmp`, `ProtectSystem=strict`, restricted read/write paths)

## Setup

**Requirements:** Python 3.9+, plus two dependencies:

```bash
apt install python3-systemd
pip install requests   # or: apt install python3-requests
```

**Installation:**

```bash
# Install the script
sudo install -m 755 snell-monitor /usr/local/bin/snell-monitor

# Install the configuration file
sudo install -m 644 -D snell-monitor.conf /usr/local/etc/snell-monitor.conf

# Edit the configuration with your Telegram credentials
sudo vim /usr/local/etc/snell-monitor.conf

# Install and enable the systemd service
sudo install -m 644 snell-monitor.service /etc/systemd/system/snell-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now snell-monitor
```

> [!NOTE]
> The monitor relies on `SyslogIdentifier=snell-server` being set in the Snell server service units. The `snell-server-updater` installer sets this automatically.

## Usage

### Run directly

```bash
/usr/local/bin/snell-monitor
```

### Test Telegram connectivity

Send a test message to verify your bot token and chat ID are configured correctly:

```bash
/usr/local/bin/snell-monitor --test-telegram
```

### Debug mode

Enable verbose logging that shows every journal entry as it is processed:

```bash
/usr/local/bin/snell-monitor --debug
```

### Manage via systemd

```bash
systemctl start snell-monitor
systemctl stop snell-monitor
systemctl restart snell-monitor

# View live logs
journalctl -u snell-monitor -f
```

## Configuration

Configuration is read from `/usr/local/etc/snell-monitor.conf`. Environment variables with the same names will override file values.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Telegram Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | ✅ | — | Target chat ID (user, group, or channel) |
| `MONITOR_ERRORS` | — | `connection refused` | Comma-separated error strings to watch for |
| `ALERT_COOLDOWN` | — | `3600` | Seconds before the same domain+error can re-alert |
| `STARTUP_LOOKBACK` | — | `0` | Minutes of history to scan on startup (`0` = disabled) |
| `POLL_INTERVAL` | — | `1.0` | Seconds between journal polls |
| `TIMEZONE` | — | `Asia/Shanghai` | Timezone for alert timestamps (e.g. `UTC`, `America/New_York`) |
| `LOG_LEVEL` | — | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Example: monitor multiple error types on UTC

```ini
MONITOR_ERRORS="connection refused, connection timed out, no route to host"
TIMEZONE="UTC"
```

## How it works

1. On startup, optionally scans recent journal entries (`STARTUP_LOOKBACK`) for missed alerts.
2. Enters a polling loop, reading new `snell-server` journal entries in real time.
3. Each log line is matched against `MONITOR_ERRORS` using a regex pattern.
4. Matched failures are deduplicated per domain + error via a cooldown window.
5. Alerts are batched and flushed every 30 seconds (or 5 seconds after the first alert arrives).
6. Batched messages are sent as HTML-formatted Telegram messages grouped by service unit.

### Alert format

Alerts are sent as Telegram HTML messages with the following structure:

```
⚠️ Snell Connection Alert
📅 2026-06-16 23:30:00
🖥 Host: myserver

📦 snell-server@ios.service
  ❗ Connection Refused:
    • dispatcher.is.autonavi.com

📦 snell-server@mac.service
  ❗ Connection Refused:
    • imap.forwardemail.net
    • smtp.example.com
  ❗ Connection Timed Out:
    • api.other.com
```

### Safety

- **Batched flushing** — sudden bursts of errors are grouped into a single message to reduce noise.
- **Cooldown deduplication** — the same domain + error type is suppressed within the configured interval.
- **Queue cap** — a hard limit on the pending alert queue prevents unbounded memory growth if Telegram is unreachable.
- **Graceful shutdown** — `SIGTERM`/`SIGINT` flush any remaining pending alerts before exiting.
- **Systemd hardening** — the service unit includes `PrivateTmp=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, and restricted read/write paths.

### systemd paths

| Path | Description |
|------|-------------|
| `/usr/local/bin/snell-monitor` | Monitor script |
| `/usr/local/etc/snell-monitor.conf` | Configuration file |
| `/etc/systemd/system/snell-monitor.service` | Systemd unit |
