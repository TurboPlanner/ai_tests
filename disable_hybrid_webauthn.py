#!/usr/bin/env python3
"""
disable_hybrid_webauthn.py — Disable Windows 11 WebAuthn Hybrid/Passkey QR Bluetooth Flow
and force local TPM PIN authentication.

Requirements:
  - Windows 11 (23H2+), Python 3.10+
  - Administrative privileges (run as Administrator)
  - System Restore enabled on the system drive (for restore point creation)

Safe to run multiple times; idempotent for registry values.
"""

import argparse
import logging
import os
import subprocess
import sys
import time
import winreg
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGER = logging.getLogger("DisableHybridWebAuthn")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _setup_logging(log_path: Optional[Path] = None, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    LOGGER.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    LOGGER.addHandler(console)

    if log_path:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        LOGGER.addHandler(fh)


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _hive_prefix(hkey: int) -> str:
    if hkey == winreg.HKEY_LOCAL_MACHINE:
        return "HKLM"
    if hkey == winreg.HKEY_CURRENT_USER:
        return "HKCU"
    if hkey == winreg.HKEY_USERS:
        return "HKU"
    return f"HKLM"


def _reg_backup_key(hkey: int, sub_key: str, backup_dir: Path) -> Optional[Path]:
    safe_name = sub_key.replace("\\", "_").replace(" ", "_")
    backup_path = backup_dir / f"{safe_name}.reg"
    prefix = _hive_prefix(hkey)
    try:
        result = subprocess.run(
            ["reg", "export", f"{prefix}\\{sub_key}", str(backup_path), "/y"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            LOGGER.info("Backup saved: %s", backup_path)
            return backup_path
        LOGGER.warning("Backup failed (key may not exist): %s — %s", sub_key, result.stderr.strip())
    except Exception as exc:
        LOGGER.warning("Backup exception for %s: %s", sub_key, exc)
    return None


def _ensure_key(hkey: int, sub_key: str) -> winreg.HKEYType:
    access = winreg.KEY_ALL_ACCESS | winreg.KEY_WOW64_64KEY
    return winreg.CreateKeyEx(hkey, sub_key, 0, access)


def _set_dword(hkey: int, sub_key: str, value_name: str, value: int) -> bool:
    try:
        with _ensure_key(hkey, sub_key) as key:
            current = None
            try:
                current = winreg.QueryValueEx(key, value_name)[0]
            except FileNotFoundError:
                pass
            if current == value:
                LOGGER.info("  [SKIP] %s\\%s already = %d", sub_key, value_name, value)
                return True
            winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value)
            LOGGER.info("  [SET]  %s\\%s = %d (was: %s)", sub_key, value_name, value, current)
            return True
    except PermissionError as exc:
        LOGGER.warning("  [ACCESS DENIED] %s\\%s — %s", sub_key, value_name, exc)
    except Exception as exc:
        LOGGER.warning("  [ERROR] %s\\%s — %s", sub_key, value_name, exc)
    return False


def _delete_key_tree(hkey: int, sub_key: str) -> None:
    prefix = _hive_prefix(hkey)
    try:
        result = subprocess.run(
            ["reg", "delete", f"{prefix}\\{sub_key}", "/f", "/s"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            LOGGER.info("  [DEL]  %s (recursive)", sub_key)
        elif "does not exist" in result.stderr or "cannot find" in result.stderr.lower():
            pass
        else:
            LOGGER.warning("  [WARN] reg delete returned %d for %s: %s",
                           result.returncode, sub_key, result.stderr.strip())
    except Exception as exc:
        LOGGER.warning("  [WARN] Could not delete %s: %s", sub_key, exc)


# ---------------------------------------------------------------------------
# Restore Point
# ---------------------------------------------------------------------------

def create_restore_point(description: str = "Before WebAuthn Hybrid disable script") -> bool:
    LOGGER.info("Creating System Restore Point...")
    ps_script = f"""
$description = '{description}'
try {{
    Checkpoint-Computer -Description $description -RestorePointType MODIFY_SETTINGS -ErrorAction Stop
    Write-Output "OK"
}} catch {{
    Write-Output "FAIL:$($_.Exception.Message)"
}}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=120,
        )
        output = (result.stdout or "").strip()
        if output.startswith("FAIL:"):
            LOGGER.warning("Restore point creation failed: %s", output[5:])
            LOGGER.warning("Ensure System Restore is enabled on drive C: and you run as Admin.")
            return False
        LOGGER.info("Restore point created: %s", output)
        return True
    except subprocess.TimeoutExpired:
        LOGGER.warning("Restore point creation timed out after 120s")
        return False
    except Exception as exc:
        LOGGER.warning("Restore point creation exception: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Core enforcement
# ---------------------------------------------------------------------------

@dataclass
class RegistryAction:
    hive: int = winreg.HKEY_LOCAL_MACHINE
    sub_key: str = ""
    values: dict[str, int] = field(default_factory=dict)
    delete_if_exists: bool = False

    def key_name(self) -> str:
        return f"{_hive_prefix(self.hive)}\\{self.sub_key}"


REGISTRY_CHANGES = [
    # 1) Disable companion devices via CSP (task requirement — Auth.md §1)
    RegistryAction(
        sub_key=r"SOFTWARE\Microsoft\PolicyManager\default\Authentication\EnableCompanionDevice",
        values={"Value": 0},
    ),
    # 2) Disable secondary authentication devices (phones / companion) — GP equivalent
    RegistryAction(
        sub_key=r"SOFTWARE\Policies\Microsoft\SecondaryAuthenticationFactor",
        values={"AllowSecondaryAuthenticationDevice": 0},
    ),
    # 3) Force security key / platform credential usage
    RegistryAction(
        sub_key=r"SOFTWARE\Microsoft\Policies\Microsoft\PassportForWork\SecurityKey",
        values={"UseSecurityKeyForSignin": 1},
    ),
    # 4) Disable Bluetooth probe in WebAuthn
    RegistryAction(
        sub_key=r"SOFTWARE\Microsoft\Cryptography\WebAuthn",
        values={"DisableBluetoothAuthentication": 1},
    ),
    # 5) Chromium policies — disable hybrid flow at the browser level
    RegistryAction(
        sub_key=r"SOFTWARE\Policies\Google\Chrome",
        values={"WebAuthenticationHybridEnabled": 0},
    ),
    RegistryAction(
        sub_key=r"SOFTWARE\Policies\Microsoft\Edge",
        values={"WebAuthenticationHybridEnabled": 0},
    ),
    # 6) User-hive override
    RegistryAction(
        hive=winreg.HKEY_CURRENT_USER,
        sub_key=r"SOFTWARE\Microsoft\Cryptography\WebAuthn",
        values={"DisableBluetoothAuthentication": 1},
    ),
]


def apply_registry_overrides(backup_dir: Path, dry_run: bool = False) -> list[str]:
    changes = []

    for action in REGISTRY_CHANGES:
        LOGGER.info("Processing %s", action.key_name())

        if action.delete_if_exists:
            _reg_backup_key(action.hive, action.sub_key, backup_dir)
            if not dry_run:
                _delete_key_tree(action.hive, action.sub_key)
                changes.append(f"Deleted {action.key_name()}")
            else:
                LOGGER.info("  [DRY-RUN] would delete %s", action.key_name())
                changes.append(f"[DRY-RUN] Would delete {action.key_name()}")
            continue

        for value_name, value in action.values.items():
            if dry_run:
                LOGGER.info("  [DRY-RUN] would set %s\\%s = %d", action.key_name(), value_name, value)
                changes.append(f"[DRY-RUN] Would set {action.key_name()}\\{value_name} = {value}")
            else:
                ok = _set_dword(action.hive, action.sub_key, value_name, value)
                status = "OK" if ok else "FAIL"
                changes.append(f"{status} {action.key_name()}\\{value_name} = {value}")

    return changes


def purge_fido_linked_devices(backup_dir: Path, dry_run: bool = False) -> list[str]:
    purged = []
    linked_path = r"Software\Microsoft\Cryptography\FIDO\LinkedDevices"
    users_key = winreg.OpenKeyEx(winreg.HKEY_USERS, "", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)

    i = 0
    while True:
        try:
            sid = winreg.EnumKey(users_key, i)
            i += 1
        except OSError:
            break
        if not sid.startswith("S-1-") or sid in ("S-1-5-18", "S-1-5-19", "S-1-5-20"):
            continue
        full_path = f"{sid}\\{linked_path}"
        try:
            with winreg.OpenKeyEx(winreg.HKEY_USERS, full_path, 0,
                                  winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as _:
                pass
        except FileNotFoundError:
            continue

        LOGGER.info("Found FIDO LinkedDevices for SID %s", sid)
        _reg_backup_key(winreg.HKEY_USERS, full_path, backup_dir)
        if not dry_run:
            _delete_key_tree(winreg.HKEY_USERS, full_path)
            purged.append(f"Purged LinkedDevices for {sid}")
        else:
            LOGGER.info("  [DRY-RUN] would delete %s", full_path)
            purged.append(f"Would purge LinkedDevices for {sid}")

    winreg.CloseKey(users_key)
    return purged


# ---------------------------------------------------------------------------
# Privilege check
# ---------------------------------------------------------------------------

def is_admin() -> bool:
    import ctypes
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin() -> None:
    if not is_admin():
        LOGGER.critical("This script requires Administrator privileges. Please run as Administrator.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# UI Automation helper (fallback)
# ---------------------------------------------------------------------------

def _install_uia_if_missing() -> bool:
    try:
        import uiautomation  # noqa: F401
        return True
    except ImportError:
        LOGGER.info("uiautomation not installed. Fallback UI hook will be unavailable.")
        LOGGER.info("Install with: pip install uiautomation")
        return False


def spawn_hybrid_watcher() -> Optional[subprocess.Popen]:
    if not _install_uia_if_missing():
        return None
    watcher_code = r"""
import sys, time, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('WebAuthnWatcher')
try:
    import uiautomation as uia
except ImportError:
    log.warning('uiautomation not available')
    sys.exit(1)

def find_windows_security():
    for attempt in range(300):
        for ctrl in uia.GetRootControl().GetChildren():
            name = ctrl.Name or ''
            if 'Windows Security' in name or 'Безопасность Windows' in name or 'безопасность' in name.lower():
                return ctrl
        time.sleep(0.5)
    return None

def dismiss_hybrid(win):
    try:
        qr_view = win.FindFirstControl(searchDepth=5,
            lambda c: 'QR' in (c.Name or '') or 'Bluetooth' in (c.Name or '') or 'hybrid' in (c.Name or '').lower())
        if qr_view:
            log.info('Hybrid/QR view detected — looking for fallback button')
            fallback = win.FindFirstControl(searchDepth=8,
                lambda c: 'different' in (c.Name or '').lower()
                        or 'other' in (c.Name or '').lower()
                        or 'use a different' in (c.Name or '').lower()
                        or 'другой' in (c.Name or '').lower()
                        or 'другое' in (c.Name or '').lower())
            if fallback:
                fallback.Click()
                log.info('Fallback clicked — PIN prompt should appear')
            else:
                log.info('No fallback button found in hybrid view')
    except Exception as e:
        log.debug('UI scan error (non-fatal): %s', e)

if __name__ == '__main__':
    log.info('WebAuthn hybrid watcher started (PID %d)', os.getpid())
    win = find_windows_security()
    if win:
        log.info('Windows Security window detected')
        dismiss_hybrid(win)
    else:
        log.info('No Windows Security window appeared within timeout')
"""
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", watcher_code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        LOGGER.info("UI Automation watcher launched (PID %d)", proc.pid)
        return proc
    except Exception as exc:
        LOGGER.warning("Failed to launch UI watcher: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Disable Windows 11 WebAuthn Hybrid/QR flow and force local TPM PIN.",
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes.")
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    p.add_argument("--no-restore-point", action="store_true", help="Skip System Restore Point creation.")
    p.add_argument("--no-uia-watcher", action="store_true", help="Skip launching the UI Automation fallback watcher.")
    p.add_argument("--log-file", type=str, default=None, help="Path to log file (default: script dir + .log).")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    script_dir = Path(__file__).parent.resolve()
    log_path = Path(args.log_file) if args.log_file else script_dir / "disable_hybrid_webauthn.log"
    _setup_logging(log_path, verbose=args.verbose)

    LOGGER.info("=" * 60)
    LOGGER.info("disable_hybrid_webauthn.py started (dry_run=%s)", args.dry_run)
    LOGGER.info("=" * 60)

    if not args.dry_run:
        ensure_admin()

    if not args.dry_run and not args.no_restore_point:
        rp_ok = create_restore_point()
        if not rp_ok:
            LOGGER.warning("Proceeding without a restore point.")
    else:
        LOGGER.info("Restore point creation skipped (--no-restore-point or --dry-run).")

    backup_dir = script_dir / "reg_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Registry backups directory: %s", backup_dir)

    applied = apply_registry_overrides(backup_dir, dry_run=args.dry_run)
    purged = purge_fido_linked_devices(backup_dir, dry_run=args.dry_run)

    if not args.dry_run and not args.no_uia_watcher:
        spawn_hybrid_watcher()

    LOGGER.info("=" * 60)
    LOGGER.info("Summary:")
    LOGGER.info("  Registry actions: %d", len(applied))
    LOGGER.info("  Linked device actions: %d", len(purged))
    total = len(applied) + len(purged)
    LOGGER.info("  Total changes: %d%s", total, " (dry-run)" if args.dry_run else "")
    LOGGER.info("  Backup dir: %s", backup_dir)
    LOGGER.info("  Log file: %s", log_path)
    LOGGER.info("=" * 60)

    if not args.dry_run:
        LOGGER.info("")
        LOGGER.info("A restart is recommended for the WebAuthn (webauthn.dll) changes to fully take effect.")
        LOGGER.info("After reboot, test with: running 'Test passkey creation in Chromium should prompt for Windows Hello PIN.")


if __name__ == "__main__":
    main()
