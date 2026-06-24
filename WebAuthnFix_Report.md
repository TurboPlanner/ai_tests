# WebAuthn / Passkey Hybrid Flow — Investigation & Remediation Report

**Date:** 2026-06-24
**System:** Windows 10 Pro 25H2 (build 26200.8655)
**Python:** 3.12.10 (64-bit)
**Browsers:** Chrome 149.0.7827.158, Edge 149.0.4022.80

---

## 1. Problem Statement

Windows 25H2 `CredentialUIBroker.exe` always shows a mandatory "Phone" / QR-code option during WebAuthn passkey creation and authentication. The dialog is rendered by Windows' `webauthn.dll` API, which Chromium browsers delegate to by default.

### Symptoms
- Bluetooth ON → shows QR for phone pairing (caBLE hybrid flow)
- Bluetooth OFF → shows "Bluetooth is turned off" dead-end (no fallback to PIN)
- No override exists in Windows Settings or Group Policy to remove the phone option

---

## 2. System State After Intervention

### 2.1 Applied Registry Policies (HKLM)

| Path | Value | Purpose |
|---|---|---|
| `SOFTWARE\Microsoft\PolicyManager\default\Authentication\EnableCompanionDevice` | `Value` = `0` (DWORD) | Disable companion devices via CSP |
| `SOFTWARE\Policies\Microsoft\SecondaryAuthenticationFactor` | `AllowSecondaryAuthenticationDevice` = `0` (DWORD) | Disable secondary auth devices (GP path) |
| `SOFTWARE\Microsoft\Policies\Microsoft\PassportForWork\SecurityKey` | `UseSecurityKeyForSignin` = `1` (DWORD) | Force TPM/security key usage |
| `SOFTWARE\Microsoft\Cryptography\WebAuthn` | `DisableBluetoothAuthentication` = `1` (DWORD) | Disable Bluetooth probe in `webauthn.dll` |
| `SOFTWARE\Policies\Google\Chrome` | `WebAuthenticationHybridEnabled` = `0` (DWORD) | Disable Chrome's own hybrid flow |
| `SOFTWARE\Policies\Microsoft\Edge` | `WebAuthenticationHybridEnabled` = `0` (DWORD) | Disable Edge's own hybrid flow |

### 2.2 Applied Registry Policies (HKCU)

| Path | Value | Purpose |
|---|---|---|
| `SOFTWARE\Microsoft\Cryptography\WebAuthn` | `DisableBluetoothAuthentication` = `1` (DWORD) | User-hive override |

### 2.3 Backup Files

All registry backups in `C:\Projects\AI\reg_backups\` (`.reg` files).

### 2.4 Installed Software

| Software | Path | Notes |
|---|---|---|
| AuthenticatorChooser v0.5.0 | `C:\Program Files\AuthenticatorChooser\` | Downloaded, installed, NOT configured as autostart |
| Kilo MCP: Tavily | `C:\Projects\AI\kilo.json` | Remote MCP via `https://mcp.tavily.com/mcp/` |

---

## 3. What Was Tried and What Worked

### ✅ Registry Policies (all set, idempotent)
All 7 registry keys applied successfully.

### ❌ `WebAuthenticationUseWindowsAPI` as Chrome Policy
**False assumption.** This is NOT a Chrome enterprise policy (no Chrome policy definition exists). It is a runtime feature flag (`chrome://flags` or `--disable-features` command-line switch). Writing it as a REG_DWORD under `SOFTWARE\Policies\Google\Chrome` has no effect.

### ❌ `BrowserState\PasskeySyncEnabled`
**No evidence this registry key exists.** No known Microsoft documentation references it.

### ⚠️ Chrome/Edge `flag_switches` in Local State
Adding `flag_switches.disable-features = "WebAuthenticationUseWindowsAPI"` to `%LOCALAPPDATA%\Google\Chrome\User Data\Local State` worked briefly but Chrome overwrites the file on startup. **Not reliable.** Use command-line flag instead.

### ⚠️ AuthenticatorChooser v0.5.0
Detects Windows Security dialog but **fails on Russian locale** — UI Automation text matching doesn't recognize Russian strings (`"Безопасность Windows"`). Logs show:
```
Window is not a passkey choice prompt because the first TextBlock child of the ScrollViewer has the name [Russian text]
```
v0.5.0 claims to fix this via Automation ID matching, but it still falls back to string comparison on some dialog variants.

### ✅ Microsoft Authenticator (phone app)
Successfully paired with Xiaomi 17T Pro via QR code. Passkeys flow through Microsoft Account sync. This is the working path for cross-device passkey usage.

---

## 4. Architecture Analysis

### Windows WebAuthn Flow (Windows 25H2)

```
Browser → Windows API (webauthn.dll) → CredentialUIBroker.exe (dialog)
                                                            │
                        ┌───────────────────────────────────┼───────────────────┐
                        ▼                                   ▼                   ▼
              Windows Hello PIN                    Phone (QR/BLE)         Security Key
              (platform authenticator)          (hybrid caBLE)         (USB/NFC)
```

- **Chrome default:** delegates to Windows API (no registry policy to disable this)
- **Chrome with `--disable-features=WebAuthenticationUseWindowsAPI`:** uses own WebAuthn (honors `WebAuthenticationHybridEnabled=0`)
- **Firefox:** always uses own WebAuthn (not affected by Windows CredentialUIBroker)

### Key Findings

1. **No official Microsoft registry or GPO disables the phone option.** This is intentional — Microsoft wants phones as authenticators for cross-device passkey sync.
2. The `DisableBluetoothAuthentication=1` only disables Bluetooth **probe** but does NOT remove the phone option from the dialog.
3. `AllowSecondaryAuthenticationDevice=0` affects Windows Hello companion devices, NOT WebAuthn passkey flow.
4. The only reliable override is `--disable-features=WebAuthenticationUseWindowsAPI` on Chromium command line, which makes Chrome bypass Windows API entirely.

---

## 5. Active Services & Processes

| Service/Process | Relevance |
|---|---|
| `CredentialUIBroker.exe` | Renders the WebAuthn dialog (target of the problem) |
| `webauthn.dll` | Windows WebAuthn API implementation |
| `NgcSvc` (Windows Hello service) | Manages PIN/biometrics |
| `FidoAuth` (if present) | FIDO authentication service |

---

## 6. Next Steps for Another Agent

### 6.1 If Goal Is to Force Windows Hello PIN (remove phone)

1. **Add `--disable-features=WebAuthenticationUseWindowsAPI` to Chrome shortcut:**
   - Right-click Chrome shortcut → Properties → Target → append:
     ```
     --disable-features=WebAuthenticationUseWindowsAPI
     ```
   - This makes Chrome bypass Windows CredentialUIBroker and use its own WebAuthn UI
   - With `WebAuthenticationHybridEnabled=0` (already set), hybrid flow is disabled
   - **Trade-off:** may lose TPM platform authenticator in some Chrome versions (unlikely in Chrome 149+)

2. **Or use Firefox** — `about:config` → `security.webauth.webauthn_enable_hybrid = false`

3. **Repair AuthenticatorChooser for Russian locale:**
   - Source: `https://github.com/Aldaviva/AuthenticatorChooser`
   - The debug log shows string comparison failure with Russian text
   - Set up scheduled task: run as admin → `AuthenticatorChooser --autostart-on-logon`

### 6.2 If Goal Is to Work with Phone (Microsoft's design)

- Already working: Xiaomi 17T Pro + QR scan via Microsoft Authenticator
- Passkeys sync via Microsoft Account
- No additional configuration needed

### 6.3 Scripts

| File | Purpose |
|---|---|
| `C:\Projects\AI\disable_hybrid_webauthn.py` | Main script (7 registry policies, dry-run, logging) |
| `C:\Projects\AI\disable_hybrid_webauthn.bat` | Batch launcher for admin execution |
| `C:\Projects\AI\debug_reg_access.py` | Registry write permission diagnostic |
| `C:\Projects\AI\kilo.json` | Kilo config (MCP Tavily search) |

### 6.4 Verification Commands

```powershell
# Check all applied policies
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography\WebAuthn'
Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Google\Chrome'
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Policies\Microsoft\PassportForWork\SecurityKey'

# Check Chrome policy (chrome://policy/ equivalent)
# Open Chrome and navigate to chrome://policy/

# Check if Chrome uses Windows API
# Look for CredentialUIBroker.exe in task manager during passkey creation

# Check AuthenticatorChooser logs
Get-Content "$env:LOCALAPPDATA\AuthenticatorChooser\Logs\*" -Tail 20
```

### 6.5 Tools with Web Search Available

Tavily MCP configured in `C:\Projects\AI\kilo.json` (API key in file). Use `tavily_tavily_search` for:
- Chrome feature flag names in current version
- Microsoft passkey policy changes in upcoming Windows builds
- AuthenticatorChooser locale fixes

---

## 7. Chronology

1. Initial registry policies applied (7 keys)
2. Debug: all keys failed with ACCESS DENIED → fixed `KEY_SET_VALUE` to `KEY_ALL_ACCESS`
3. Browser still showing phone → Tavily search confirmed no registry override exists
4. Attempted `WebAuthenticationUseWindowsAPI=0` as Chrome policy → not a real policy
5. Attempted `BrowserState\PasskeySyncEnabled=0` → not a valid key
6. Tried Chrome Local State `flag_switches` → Chrome overwrites on restart
7. Downloaded/installed AuthenticatorChooser v0.5.0 → fails on Russian locale
8. User paired phone via Microsoft Authenticator → passkey hybrid flow works as designed
9. Conclusion: phone option cannot be removed system-wide; workarounds are Chrome `--disable-features` flag or Firefox
