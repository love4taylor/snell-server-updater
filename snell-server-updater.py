#!/usr/bin/env python3
"""Update snell-server to the latest version (stable or beta).

Replaces update_snell.sh with proper semver handling so versions like
v6.0.0b1 (beta) are discovered and compared correctly.

With --install: also sets up a systemd service (user, config, units).
"""

from __future__ import annotations

import argparse
import os
import platform
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DL_PAGE = "https://kb.nssurge.com/surge-knowledge-base/release-notes/snell.md"
BASE_URL = "https://dl.nssurge.com/snell"
USER_AGENT = "snell-server-updater/1.0"

# Regex to extract the version portion from a snell-server download URL.
# Captures "v5.0.1", "v6.0.0b1", "v4.1.1", etc.
URL_VERSION_RE = re.compile(
    r"https://dl\.nssurge\.com/snell/snell-server-(v[\w.]+)-linux-(\w+)\.zip"
)

# Regex to extract a version string from binary output (e.g. "snell-server v5.0.1").
BINARY_VERSION_RE = re.compile(r"v(\d+\.\d+\.\d+\w*)")

# Semver parsing (PEP 440 subset):
#   v5.0.1        -> major=5, minor=0, patch=1, pre=None
#   v6.0.0b1      -> major=6, minor=0, patch=0, pre=('b', 1)
#   v6.0.0-beta1  -> major=6, minor=0, patch=0, pre=('beta', 1)
SEMVER_RE = re.compile(
    r"^v?"
    r"(?P<major>\d+)"
    r"\.(?P<minor>\d+)"
    r"\.(?P<patch>\d+)"
    r"(?:[-.]?(?P<pre_type>[a-zA-Z]+)(?P<pre_num>\d*))?"
    r"$"
)

PRE_TYPE_ORDER: dict[str, int] = {
    "alpha": 0,
    "a": 0,
    "beta": 1,
    "b": 1,
    "rc": 2,
    "pre": 3,
}

ARCH_MAP: dict[str, str] = {
    "x86_64": "amd64",
    "i386": "i386",
    "i686": "i386",
    "aarch64": "aarch64",
    "armv7l": "armv7l",
}

# --install paths
INSTALL_PATH = "/usr/local/bin/snell-server"
CONFIG_DIR = "/usr/local/etc/snell-server"
CONFIG_FILE = f"{CONFIG_DIR}/server.conf"
SERVICE_USER = "snell"
SERVICE_SHELL = "/usr/sbin/nologin"
SERVICE_UNIT = "/etc/systemd/system/snell-server.service"
SERVICE_TEMPLATE = "/etc/systemd/system/snell-server@.service"

SERVICE_UNIT_CONTENT = """[Unit]
Description=Snell is a lean encrypted proxy protocol
Documentation=https://kb.nssurge.com/surge-knowledge-base/release-notes/snell
After=network.target nss-lookup.target network-online.target

[Service]
User={user}
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_RAW CAP_NET_ADMIN
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_RAW CAP_NET_ADMIN
NoNewPrivileges=yes
PrivateTmp=yes
SyslogIdentifier=snell-server
ExecStart={binary} -c {config_dir}/server.conf
Restart=on-failure
RestartSec=10s
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
"""

SERVICE_TEMPLATE_CONTENT = """[Unit]
Description=Snell is a lean encrypted proxy protocol
Documentation=https://kb.nssurge.com/surge-knowledge-base/release-notes/snell
After=network.target nss-lookup.target network-online.target

[Service]
User={user}
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_RAW CAP_NET_ADMIN
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_RAW CAP_NET_ADMIN
NoNewPrivileges=yes
PrivateTmp=yes
SyslogIdentifier=snell-server
ExecStart={binary} -c {config_dir}/%i.conf
Restart=on-failure
RestartSec=10s
LimitNOFILE=infinity

[Install]
WantedBy=multi-user.target
"""


@dataclass(frozen=True)
class VersionInfo:
    """Parsed version information for comparison."""

    major: int
    minor: int
    patch: int
    pre_type: str  # e.g. "beta", "b", "" for stable
    pre_num: int  # e.g. 1 for "b1", 0 if none

    @property
    def is_prerelease(self) -> bool:
        return self.pre_type != ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(message: str) -> None:
    print(message, flush=True)


def fail(message: str, exit_code: int = 1) -> NoReturn:
    print(f"\u274c {message}", file=sys.stderr)
    raise SystemExit(exit_code)


# ---------------------------------------------------------------------------
# Architecture detection
# ---------------------------------------------------------------------------


def detect_arch() -> str:
    """Map `uname -m` to Snell's naming convention."""
    machine = platform.machine()
    arch = ARCH_MAP.get(machine)
    if arch is None:
        fail(f"Unsupported architecture: {machine}")
    return arch


# ---------------------------------------------------------------------------
# Local binary
# ---------------------------------------------------------------------------


def find_snell() -> Path:
    """Locate snell-server in PATH."""
    path = shutil.which("snell-server")
    if not path:
        fail("snell-server not found in PATH")
    return Path(path)


def get_current_version(snell_path: Path) -> str | None:
    """Run `snell-server -v` and extract the version string (e.g. 'v5.0.1')."""
    try:
        result = subprocess.run(
            [str(snell_path), "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
        fail(f"Failed to run snell-server -v: {exc}")
        return None  # unreachable; satisfies type checker

    output = (result.stdout or "") + (result.stderr or "")
    match = BINARY_VERSION_RE.search(output)
    if not match:
        return None
    return "v" + match.group(1)


# ---------------------------------------------------------------------------
# Version parsing & comparison
# ---------------------------------------------------------------------------


def parse_version(raw: str) -> VersionInfo:
    """Parse a version string like 'v5.0.1' or 'v6.0.0b1' into a VersionInfo."""
    m = SEMVER_RE.match(raw)
    if not m:
        nums = re.findall(r"\d+", raw)
        major = int(nums[0]) if len(nums) > 0 else 0
        minor = int(nums[1]) if len(nums) > 1 else 0
        patch = int(nums[2]) if len(nums) > 2 else 0
        return VersionInfo(major, minor, patch, "", 0)

    pre_type = (m.group("pre_type") or "").lower()
    pre_num = int(m.group("pre_num")) if m.group("pre_num") else 0
    return VersionInfo(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        pre_type=pre_type,
        pre_num=pre_num,
    )


def version_sort_key(raw: str) -> tuple[int, int, int, int, int, int]:
    """Return a sortable tuple for a version string.

    Stable releases sort HIGHER than pre-releases with the same base.
    Within pre-releases, ordering follows PRE_TYPE_ORDER then pre_num.
    """
    v = parse_version(raw)
    is_stable = 0 if v.is_prerelease else 1
    type_order = PRE_TYPE_ORDER.get(v.pre_type, 99)
    return (v.major, v.minor, v.patch, is_stable, type_order, v.pre_num)


def compare_versions(left: str, right: str) -> int:
    """Return -1, 0, or 1 (like Python's cmp)."""
    lk = version_sort_key(left)
    rk = version_sort_key(right)
    if lk < rk:
        return -1
    if lk > rk:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Remote version discovery
# ---------------------------------------------------------------------------


def _make_request(url: str, method: str = "GET") -> urllib.request.Request:
    """Build a Request with a User-Agent header (avoids 403 from some servers)."""
    return urllib.request.Request(
        url, method=method, headers={"User-Agent": USER_AGENT}
    )


def fetch_page_text(url: str) -> str:
    """Fetch a URL and return its text content."""
    try:
        req = _make_request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        fail(f"Failed to fetch {url}: {exc}")
        return ""  # unreachable; satisfies type checker


def discover_versions(arch: str) -> dict[str, str]:
    """Scrape the release-notes page for {version: download_url} pairs."""
    content = fetch_page_text(DL_PAGE)
    versions: dict[str, str] = {}
    for m in URL_VERSION_RE.finditer(content):
        ver = m.group(1)
        url_arch = m.group(2)
        if url_arch == arch:
            versions[ver] = m.group(0)
    return versions


def build_url(version: str, arch: str) -> str:
    """Construct a download URL for a specific version and architecture."""
    return f"{BASE_URL}/snell-server-{version}-linux-{arch}.zip"


def url_exists(url: str) -> bool:
    """Check whether a URL is reachable (HEAD request)."""
    req = _make_request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.URLError:
        return False


# ---------------------------------------------------------------------------
# Download & install
# ---------------------------------------------------------------------------


def _verify_binary(binary: Path) -> str | None:
    """Try running `binary -v` and return the version output on success.
    Returns None if the binary fails to execute (missing libraries, etc.)."""
    try:
        result = subprocess.run(
            [str(binary), "-v"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return None

    output = (result.stdout or "") + (result.stderr or "")
    if BINARY_VERSION_RE.search(output):
        return output.strip()

    if result.returncode != 0:
        log(f"   Binary check failed (exit {result.returncode}):")
        for line in output.splitlines():
            log(f"      {line}")
        return None

    return output.strip() or None


def download_and_install(url: str, snell_path: Path) -> bool:
    """Download, extract, verify, and install snell-server.

    The existing binary is only replaced after the new one passes
    a runtime verification (snell-server -v).  Returns True on success.
    """
    log(f"\u2b07\ufe0f  Downloading: {url}")

    tmp_dir = tempfile.mkdtemp(prefix="snell-update-")
    zip_path = os.path.join(tmp_dir, "snell.zip")

    try:
        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        extracted = Path(tmp_dir, "snell-server")
        if not extracted.is_file():
            log("\u274c Error: snell-server not found inside the archive")
            return False

        extracted.chmod(0o755)

        # Verify the new binary runs BEFORE replacing the old one
        log("\U0001f52c Verifying downloaded binary ...")
        ver_output = _verify_binary(extracted)
        if ver_output is None:
            log(
                "\u274c Downloaded binary failed to run (missing libraries or incompatible)."
            )
            log("   The existing snell-server has NOT been touched.")
            return False

        log(f"   Binary OK  -  {ver_output.splitlines()[0]}")

        # Safe to install now (atomic replace to handle running service)
        install_dir = snell_path.parent
        if not install_dir.exists():
            install_dir.mkdir(parents=True, exist_ok=True)
        tmp_target = install_dir / f".{snell_path.name}.new.{os.getpid()}"
        try:
            shutil.copy2(extracted, tmp_target)
            tmp_target.chmod(0o755)
            os.replace(tmp_target, snell_path)
        except PermissionError:
            log("\u274c Permission denied; run with sudo/root")
            return False
        finally:
            try:
                tmp_target.unlink()
            except FileNotFoundError:
                pass
        log(f"\u2728 Update complete!  {ver_output.splitlines()[0]}")
        return True

    except Exception as exc:
        log(f"\u274c Installation failed: {exc}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# System service setup (--install)
# ---------------------------------------------------------------------------


def do_install(snell_path: Path, skip_wizard: bool = False) -> None:
    """Set up snell-server as a systemd service.

    Steps:
      1. Create system user 'snell' (if missing).
      2. Create /usr/local/etc/snell-server/.
      3. Run snell-server --wizard for initial config (interactive).
      4. Install snell-server.service and snell-server@.service.
      5. systemctl daemon-reload.
    """
    if os.geteuid() != 0:
        fail("--install requires root privileges; run with sudo")

    # 1. System user
    try:
        pwd.getpwnam(SERVICE_USER)
        log(f"\U0001f464 User '{SERVICE_USER}' already exists")
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "-r",
                "-s",
                SERVICE_SHELL,
                "-d",
                "/nonexistent",
                "-c",
                "snell server",
                SERVICE_USER,
            ],
            check=True,
        )
        log(f"\U0001f464 Created user '{SERVICE_USER}'")

    # 2. Config directory
    Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    log(f"\U0001f4c1 Config directory: {CONFIG_DIR}")

    # 3. Run wizard (interactive) if config doesn't exist
    config_path = Path(CONFIG_FILE)
    if config_path.is_file():
        log(f"\u26a0\ufe0f  Config already exists: {CONFIG_FILE} -- skipping wizard")
    elif skip_wizard:
        log(f"\u26a0\ufe0f  Skipping wizard (--skip-wizard); config not created.")
    else:
        log("\U0001f52e Running interactive wizard ...")
        log("   ( respond to the prompts below )")
        log("")
        result = subprocess.run(
            [str(snell_path), "--wizard", "-c", CONFIG_FILE],
            check=False,
        )
        if result.returncode != 0:
            log(f"\u26a0\ufe0f  Wizard exited with code {result.returncode}")
        else:
            log(f"\u2705 Config written to {CONFIG_FILE}")

    # 4. Write systemd units
    unit_vars = {
        "user": SERVICE_USER,
        "binary": str(snell_path),
        "config_dir": CONFIG_DIR,
    }

    for path, template in (
        (SERVICE_UNIT, SERVICE_UNIT_CONTENT),
        (SERVICE_TEMPLATE, SERVICE_TEMPLATE_CONTENT),
    ):
        content = template.format(**unit_vars)
        Path(path).write_text(content)
        Path(path).chmod(0o644)
        log(f"\U0001f4c4 Created {path}")

    # 5. Reload systemd
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    log("\U0001f504 systemctl daemon-reload done")
    log("")
    log("Next steps:")
    log(f"  systemctl enable --now snell-server")
    log(f"  # or for multiple instances:")
    log(f"  systemctl enable --now snell-server@myprofile")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update snell-server to the latest version (stable or beta)."
    )
    parser.add_argument(
        "--version",
        "-V",
        metavar="VER",
        help="Install a specific version (e.g. v6.0.0b1, v5.0.1). "
        "Overrides automatic discovery.",
    )
    parser.add_argument(
        "--beta",
        "-b",
        action="store_true",
        help="Include beta / pre-release versions when auto-discovering the latest.",
    )
    parser.add_argument(
        "--arch",
        help=f"Override architecture detection (current: {platform.machine()})",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be done without making changes.",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Install even if the target version is not newer than the current one.",
    )
    parser.add_argument(
        "--install",
        "-i",
        action="store_true",
        help="Set up system service: create user, config dir, wizard, and systemd "
        "units.  Requires root.",
    )
    parser.add_argument(
        "--skip-wizard",
        action="store_true",
        help="Skip the interactive config wizard (use when config already exists).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 1. Architecture
    arch = args.arch or detect_arch()
    log(f"\U0001f5a5\ufe0f  Architecture: {platform.machine()} -> {arch}")

    # 2. Locate local binary (or use install path)
    if args.install:
        snell_path = Path(INSTALL_PATH)
    else:
        snell_path = find_snell()
    log(f"\U0001f4c2 Local: {snell_path}")

    # 3. Current version
    current = get_current_version(snell_path) if snell_path.is_file() else None
    log(f"\U0001f4e6 Current: {current or 'not installed'}")

    # 4. Determine target version & URL
    target_ver: str
    target_url: str

    if args.version:
        target_ver = (
            args.version if args.version.startswith("v") else f"v{args.version}"
        )
        target_url = build_url(target_ver, arch)

        if not url_exists(target_url):
            log(
                f"\u26a0\ufe0f  {target_ver} not found at dl.nssurge.com; trying release page..."
            )
            versions = discover_versions(arch)
            if target_ver in versions:
                target_url = versions[target_ver]
            else:
                fail(f"Version {target_ver} not found for {arch}")
    else:
        log("\U0001f50d Fetching release page...")
        versions = discover_versions(arch)

        if not versions:
            fail(f"No snell-server versions found for {arch} on the release page")

        sorted_vers = sorted(versions.keys(), key=version_sort_key)
        log(f"\U0001f4cb Found: {', '.join(sorted_vers)}")

        if args.beta:
            target_ver = sorted_vers[-1]
        else:
            stables = [v for v in sorted_vers if not parse_version(v).is_prerelease]
            if not stables:
                log(
                    "\u26a0\ufe0f  No stable versions found; falling back to latest pre-release"
                )
                target_ver = sorted_vers[-1]
            else:
                target_ver = stables[-1]

        target_url = versions[target_ver]

    if target_ver is None or target_url is None:
        fail("Failed to determine target version or download URL")
    log(f"\U0001f310 Target: {target_ver}")

    # 5. Version comparison
    needs_download = True
    if current is not None:
        cmp = compare_versions(current, target_ver)
        if cmp == 0:
            log("\u2705 Already at the latest version.")
            needs_download = False
        elif cmp > 0 and not args.force:
            log(
                f"\u26a0\ufe0f  Installed version ({current}) is newer than target ({target_ver})."
            )
            log("   Use --force to install anyway.")
            needs_download = False
    else:
        needs_download = True

    # 6. Download & install binary
    if needs_download or args.force:
        action = "update" if current else "install"
        log(f"\U0001f680 Preparing to {action} -> {target_ver}")

        if args.dry_run:
            log(f"   [DRY RUN] Would download: {target_url}")
            log(f"   [DRY RUN] Would install to: {snell_path}")
        else:
            ok = download_and_install(target_url, snell_path)
            if not ok:
                return 1
    else:
        if args.dry_run:
            log("   [DRY RUN] Binary is up to date, skipping download")

    # 7. System service setup
    if args.install:
        if args.dry_run:
            log("   [DRY RUN] Would set up systemd service (user, config, units)")
        else:
            do_install(snell_path, skip_wizard=args.skip_wizard)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
