# TASK: Automate Windows 11 WebAuthn Hybrid/Passkey Flow Disabling and Force Local TPM PIN

## Context & Problem Statement
The Windows 11 (23H2/24H2) WebAuthn subsystem (`webauthn.dll`) aggressively enforces a hybrid cross-device flow (caBLE/Bluetooth QR code) during Passkey creation/authentication in Chromium browsers, completely bypassing the local Windows Hello PIN prompt. 
- If Bluetooth is ON, it forces a QR code.
- If Bluetooth is OFF, it soft-locks on a "Bluetooth is turned off" screen with no fallback to a local PIN.
Legacy GPO (`Use companion devices for authentication`) is deprecated and missing.

We need a Python automation script leveraging `winreg`, `subprocess`, and system API checks to clean up lingering FIDO devices, apply advanced registry overrides, and optionally interface with UI Automation to force local platform authentication.

---

## Technical Requirements (The Contract)

Your Python script must be defensive, perform strict pre-checks, log every action, and implement the following steps:

### 1. Registry Enforcement (System & User hives)
Create a function to apply the following registry modifications. Ensure it checks for administrative privileges first.
* **Disable Companion Devices:** Path: `HKLM\SOFTWARE\Microsoft\PolicyManager\default\Authentication\EnableCompanionDevice`
  Value: `Value` (DWORD) = `0`
* **Force Security Key Focus:**
  Path: `HKLM\SOFTWARE\Microsoft\Policies\Microsoft\PassportForWork\SecurityKey`
  Value: `UseSecurityKeyForSignin` (DWORD) = `1`
* **Disable WebAuthn Bluetooth Probe:**
  Path: `HKLM\SOFTWARE\Microsoft\Cryptography\WebAuthn`
  Value: `DisableBluetoothAuthentication` (DWORD) = `1`

### 2. Purge Linked Hybrid Devices
To prevent the UI from sticking to previously paired phones, the script must scan and purge the FIDO linked devices cache:
* Enumerate all User SIDs under `HKEY_USERS`.
* Locate `Software\Microsoft\Cryptography\FIDO\LinkedDevices`.
* If the subkeys exist, back them up to a `.reg` file in the current directory, then recursively delete them.

### 3. Chromium Flags and Policies Automation
* Generate a `chrome_policy.reg` / `edge_policy.reg` or directly inject into:
  `HKLM\SOFTWARE\Policies\Google\Chrome`
  Set `WebAuthnFactors` or timeout overrides if applicable to suppress browser-side hybrid discovery.

### 4. Optional UI Automation Hook (Fall-back Strategy)
If the registry overrides are insufficient due to hardcoded `webauthn.dll` behavior, write a lightweight helper using `pywinauto` or `uiautomation` that:
* Monitors for the Windows Security window (Executable: `CredentialUIBroker.exe` or Title containing "Windows Security" / "Безопасность Windows").
* Automatically detects if the hybrid/QR view is active and programmatically triggers the "Use a different key" or fallback option to bring up the native local TPM PIN field.

---

## Execution Guidelines for the Agent
1. **Safety First:** Always export/backup any registry key before deleting or modifying it.
2. **Environment:** Assume Python 3.10+, Windows 11, running with elevated Administrator privileges.
3. **Output:** Provide a single, well-documented, clean Python script (`disable_hybrid_webauthn.py`) implementing contract-based programming principles. Do not use placeholders.