# snell-monitor

A lightweight daemon that monitors [Snell](https://kb.nssurge.com/surge-knowledge-base/release-notes/snell) server journal logs in real time, detects connection failures (e.g. "connection refused"), and sends batched alerts via a Telegram Bot.

Designed to complement `snell-server-updater` by providing operational visibility into Snell proxy instances.

## Features

- 📡 **Real-time journal monitoring** — reads systemd journal natively via `systemd.journal.Reader` (no subprocess overhead)
- 🔔 **Telegram alerts** — sends rich HTML-formatted messages when monitored connection errors are detected
- 📦 **Batched flushing** — groups alerts that occur within a short window into a single message to reduce noise
- 🧊 **Cooldown deduplication** — suppresses repeat alerts for the same domain + error type within a configurable interval
- 🔙 **Startup lookback** — optionally scans the last N minutes of logs on startup to catch errors that occurred while the monitor was down
- 🏷️ **Service-aware** — distinguishes between `snell-server` and `snell-server@*.service` instances
- 🛡️ **Systemd security hardening** — ships with a hardened service unit (`PrivateTmp`, `ProtectSystem=strict`, etc.)

## Dependencies

- **Python** 3.9+
- **python3-systemd** — `apt install python3-systemd`
- **requests** — `pip install requests` or `apt install python3-requests`

## Setup

```bash
# Install the script
sudo install -m 755 snell-monitor /usr/local/bin/snell-monitor

# Install the configuration file (creates parent directories automatically)
sudo install -m 644 -D snell-monitor.conf /usr/local/etc/snell-monitor.conf

# Edit the configuration with your Telegram credentials
sudo vim /usr/local/etc/snell-monitor.conf

# Install and enable the systemd service
sudo install -m 644 snell-monitor.service /etc/systemd/system/snell-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now snell-monitor
```

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

Enable verbose logging that shows every journal entry being processed:

```bash
/usr/local/bin/snell-monitor --debug
```

### Manage via systemd

```bash
# Start / stop / restart
systemctl start snell-monitor
systemctl stop snell-monitor
systemctl restart snell-monitor

# View logs
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
3. Each log line is parsed against `MONITOR_ERRORS` using a regex pattern.
4. Matched failures are deduplicated per domain+error via a cooldown window.
5. Alerts are batched and flushed every 30 seconds (or after a 5-second initial delay once the first alert arrives).
6. Batched messages are sent as HTML-formatted Telegram messages grouped by service unit.

## systemd paths

| Path | Description |
|------|-------------|
| `/usr/local/bin/snell-monitor` | Monitor script |
| `/usr/local/etc/snell-monitor.conf` | Configuration file |
| `/etc/systemd/system/snell-monitor.service` | Systemd unit |

> **Note:** The monitor relies on `SyslogIdentifier=snell-server` being set in the Snell server service units. The `snell-server-updater` installer sets this automatically.

## Alert format

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

## Safety

- Alerts are **batched** — sudden bursts of errors will be grouped into a single message.
- **Deduplication** prevents flooding when a domain is persistently unreachable.
- A **hard cap** on the pending alert queue prevents unbounded memory growth if Telegram is unreachable.
- Graceful shutdown via `SIGTERM`/`SIGINT` flushes any remaining pending alerts before exiting.
- The systemd unit includes **security hardening** directives (`PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=yes`, restricted read/write paths).

## License

MIT License — see [../LICENSE](../LICENSE) for details.
