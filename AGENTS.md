<!-- FOR AI AGENTS - Human readability is a side effect, not a goal -->
<!-- Managed by agent: keep sections and order; edit content, not structure -->
<!-- Last updated: 2026-06-21 | Last verified: 2026-06-21 -->

# AGENTS.md

**Precedence:** the closest `AGENTS.md` to the files you're changing wins. Root holds global defaults. The `snell-monitor/` subdirectory has its own README with component-specific docs.

## Index of scoped AGENTS.md

| Scope | AGENTS.md | Contents |
|-------|-----------|----------|
| Root | `./AGENTS.md` | Global rules, both tools |
| `snell-monitor/` | `./snell-monitor/README.md` | Monitor-specific setup, config, and behavior |

## Overview

A pair of Python CLI tools for managing [Snell](https://kb.nssurge.com/surge-knowledge-base/release-notes/snell) proxy server instances on Linux:

| Tool | File | Python | Purpose |
|------|------|--------|---------|
| **snell-server-updater** | `snell-server-updater.py` | 3.7+ | Discover, download, upgrade snell-server binary + systemd service setup |
| **snell-monitor** | `snell-monitor/snell-monitor` | 3.9+ | Real-time journal log monitor → Telegram alerts on connection errors |

Zero third-party dependencies for the updater. The monitor needs `requests` and `python3-systemd`.

## Commands

> Source: README — no CI or build system present

| Task | Command | ~Time |
|------|---------|-------|
| Check Python syntax | `python3 -c "import ast; ast.parse(open('snell-server-updater.py').read())"` | <1s |
| Check both files | `python3 -m py_compile snell-server-updater.py && python3 -m py_compile snell-monitor/snell-monitor` | <1s |
| Run updater (dry) | `sudo python3 snell-server-updater.py --dry-run` | ~5s |
| Run monitor (test) | `snell-monitor/snell-monitor --test-telegram` | ~2s |
| Run monitor (debug) | `snell-monitor/snell-monitor --debug` | varies |

> If commands fail, verify Python version (`python3 --version`) and required system packages.

## Response Style

- Answer first, elaborate only if needed. No sycophantic openers.
- For yes/no or status questions, lead with the answer.
- Skip preamble. Match response length to task complexity.

## Workflow

1. **Before coding**: Read this file + the relevant README (`README.md` or `snell-monitor/README.md`)
2. **After each change**: Run `python3 -m py_compile` on the changed file(s)
3. **Before committing**: Verify both files compile and check for regressions in the logic flow
4. **Before claiming done**: Paste `py_compile` output as evidence

## File Map

```
snell-server-updater.py     — Main CLI: version discovery, semver, download, install, systemd setup
snell-monitor/
├── snell-monitor            — Daemon: journal polling, error parsing, Telegram alerts
├── snell-monitor.service    — systemd unit with security hardening
├── snell-monitor.conf       — Example configuration file
└── README.md                — Component-specific documentation
README.md                    — Project-level documentation
LICENSE                      — MIT
.gitignore                   — Python, IDE, OS, temp files
```

## Architecture

### snell-server-updater.py (643 lines)

Single-file CLI with well-separated sections:

| Section | Lines | Responsibility |
|---------|-------|----------------|
| Constants | 28–83 | URLs, regex patterns, arch map, systemd unit templates, version ordering |
| Helpers | 123–280 | `VersionInfo` dataclass, `parse_version()`, `compare_versions()`, architecture detection, local binary discovery |
| Network | 252–296 | URL fetching, version scraping from release page, HEAD checks |
| Download & install | 298–389 | Download ZIP→extract→verify binary (`-v`)→atomic replace via tmp file + `os.replace()` |
| Systemd setup | 391–477 | `--install` flow: `useradd`, config dir, interactive wizard, write unit files, `daemon-reload` |
| CLI | 479–642 | argparse, `main()` orchestration |

**Key design decisions:**
- **Stdlib-only** for the updater — `urllib`, `zipfile`, `subprocess`, `argparse`. No pip install needed.
- **Semver with pre-release ordering**: `alpha` < `beta` < `rc` < `pre` < stable. Stable sorts higher than any pre-release with the same base.
- **Safe binary replacement**: Downloads to temp dir, runs `snell-server -v` on extracted binary, only replaces existing if verification passes. Uses `os.replace()` for atomicity.
- **Systemd unit templates** embedded as Python f-strings in `SERVICE_UNIT_CONTENT` and `SERVICE_TEMPLATE_CONTENT`.
- **Architecture detection** via `platform.machine()` → `ARCH_MAP` (x86_64→amd64, aarch64→aarch64, etc.)

### snell-monitor/snell-monitor (651 lines)

Single-file daemon with the same pattern:

| Section | Lines | Responsibility |
|---------|-------|----------------|
| Configuration | 66–172 | Env vars + config file parsing, validation |
| Telegram | 175–208 | `requests`-based Bot API client |
| Log parsing | 211–273 | Regex extraction of domain+error from log lines, HTML alert formatting |
| Deduplication | 275–311 | `AlertDeduplicator` class: cooldown-based per-(domain, error_type) suppression |
| Journal Monitor | 312–554 | `JournalMonitor` class: real-time `systemd.journal.Reader` polling, startup lookback, batched flushing |
| CLI | 556–651 | argparse, signal handlers, `main()` |

**Key design decisions:**
- **Native journal access** via `systemd.journal.Reader` — no shelling out to `journalctl`.
- **Batched + deduplicated alerts**: Errors are queued, flushed every 30s (or 5s after first alert), grouped by service unit.
- **Memory guards**: Hard caps on dedup dict (5000 entries) and pending alerts queue (50 items).
- **Graceful shutdown**: SIGTERM/SIGINT flush pending alerts before exit.
- **Startup lookback**: Optionally scan N minutes of history when starting (catch alerts from downtime).

### Dependency requirements

| Tool | Python | System packages | pip packages |
|------|--------|-----------------|--------------|
| `snell-server-updater.py` | ≥3.7 | none | none |
| `snell-monitor/snell-monitor` | ≥3.9 | `python3-systemd` | `requests` |

## Heuristics (quick decisions)

| When | Do |
|------|-----|
| Adding a new CLI flag | Add to `parse_args()` in the relevant file, then handle in `main()` |
| Changing version parsing | Update `SEMVER_RE`, `parse_version()`, and `version_sort_key()` together |
| Modifying systemd units | Edit the `*_CONTENT` string constants in `snell-server-updater.py` |
| Adding a monitor error type | Add to `MONITOR_ERRORS` env/config; the regex in `parse_log_entry()` handles generic patterns |
| Changing alert format | Edit `format_alert_message()` in snell-monitor |
| Both files change | Compile-check both, review each independently — they don't share code |
| User asks about installation | Point to the `README.md` setup sections; the updater is run with `sudo python3 snell-server-updater.py` |

## Setup

Linux system with systemd. Clone and run — no build step:

```bash
git clone https://github.com/love4taylor/snell-server-updater.git
cd snell-server-updater
# Updater: ready to run (Python 3.7+ stdlib only)
sudo python3 snell-server-updater.py --dry-run
# Monitor: install deps first
apt install python3-systemd python3-requests
snell-monitor/snell-monitor --test-telegram
```

## Code Style

- **Python 3.7+** for the updater, **Python 3.9+** for the monitor
- `from __future__ import annotations` in both files
- Type annotations on all function signatures; `@dataclass` for data carriers
- Sections delimited by `# ---` comment blocks matching functional boundaries
- Emoji in user-facing log output (used sparingly and consistently)
- Double-quoted strings for user-facing text, single-quoted for internal
- Regex patterns pre-compiled at module level as constants
- Config via constants at the top; no external config files for the updater

## Security

- **Atomic binary replacement**: `os.replace()` ensures the running service isn't interrupted mid-write (`snell-server-updater.py:373`).
- **Binary verification before install**: Downloaded binary is executed (`snell-server -v`) and checked for exit code + version output before replacing the live binary (`snell-server-updater.py:354-363`).
- **Hardened systemd units**: Both service units include `CapabilityBoundingSet`, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, and restricted `ReadWritePaths`/`ReadOnlyPaths`.
- **Memory bounds**: The monitor caps dedup entries (5000) and pending alerts (50) to prevent OOM under attack/error storms.
- **Secrets in env vars**: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are loaded from env or config file — never hardcoded in the script.

## Checklist

Before committing:

- [ ] Both files compile: `python3 -m py_compile snell-server-updater.py && python3 -m py_compile snell-monitor/snell-monitor`
- [ ] No stale imports or dead code
- [ ] README updated if CLI flags or behavior changed
- [ ] `--dry-run` path verified if download/install logic touched
- [ ] Monitor: `--test-telegram` still works if Telegram code touched

## Examples

### Adding a new CLI flag to the updater

```python
# 1. Add argument in parse_args()
parser.add_argument("--new-flag", action="store_true", help="...")

# 2. Consume in main()
if args.new_flag:
    log("New flag enabled")

# 3. Document in README Options table
```

### Adding a new monitored error type

No code changes needed — add to `MONITOR_ERRORS` in config or env:
```ini
MONITOR_ERRORS="connection refused, connection timed out, dns resolution failed"
```

The regex in `parse_log_entry()` already captures any `(error_type)` pattern from snell-server log lines.

## When Stuck

- **Version parsing issues**: The `SEMVER_RE` regex and `parse_version()` in `snell-server-updater.py:49-56,204-222` handle the full version format. Test with `python3 -c "from snell_server_updater import parse_version; print(parse_version('v6.0.0b1'))"`.
- **Binary verification fails**: The downloaded binary may lack glibc. Check `_verify_binary()` at `snell-server-updater.py:303-326`.
- **Monitor can't find journal**: Verify `python3-systemd` is installed (`apt install python3-systemd`) and `SyslogIdentifier=snell-server` is in the service units.
- **Telegram alerts not sending**: Run `--test-telegram` and check `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in the config file or env.

## Constraints

- **Linux only** — both tools reference systemd, `/usr/local/bin`, `useradd`, and Linux arch names (amd64, aarch64, armv7l, i386).
- **Root required** — `snell-server-updater.py` needs `sudo` for binary install and service setup.
- **No test suite** — verify changes by compile-check and manual dry-run. Be extra cautious with download/install and systemd logic.
- **No type checker** — both files use type annotations but have no mypy/pyright config. The `from __future__ import annotations` is used. The monitor has a `# type: ignore[assignment]` for the `ZoneInfo` fallback.
- **snell-monitor is optional** — the updater works standalone; the monitor is an independent add-on.
