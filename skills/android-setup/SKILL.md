---
name: android-setup
description: Prepare or troubleshoot Android Use after plugin installation, including uv, ADB, USB debugging authorization, device selection and MCP startup. Use when setting up this plugin or its phone connection.
---

# Android Use setup

The installed plugin already declares its MCP server. Do not add a duplicate
global MCP entry, copy skills into global directories, or overwrite existing
client configuration.

Find this plugin's installed root from the path of this skill:
`<plugin-root>/skills/android-setup/SKILL.md`. Read the installation and device
sections of [README.md](../../README.md) only when needed. Use this installed
root, not a developer checkout path, for diagnostic `uv --directory` commands.

Check `uv --version` and `adb version` using local commands. If either is
missing, use its official installation instructions and the user's platform
to install it within the requested setup scope. Prefer user-local setup and
preserve existing versions/configuration. uv uses the bundled `.python-version`
and frozen lockfile to provision Python 3.12 and runtime dependencies; a full
Android SDK, Java and a fixture APK are needed only for development tests.

The MCP launcher automatically runs `uv run --frozen --no-dev android-use-mcp`
with its working directory set to the installed plugin root. For dependency diagnostics, use
`uv --directory <installed-root> sync --frozen --no-dev`. Do not edit files in
the cached plugin to fix startup. If a newly installed executable is not on
the client's PATH, restart the local client before retrying MCP startup.

Check `adb devices -l` or `android_devices`:

- No device: ask the user to connect a data-capable USB cable and enable USB debugging.
- Unauthorized: ask them to accept the debugging authorization on the phone.
- Offline: inspect the connection; do not restart another user's active ADB session blindly.
- Multiple devices: ask which device to control and use `ANDROID_SERIAL` for
  the MCP process through the client's supported plugin/server environment
  configuration. Never modify the packaged manifest or guess a target.

Ask the user to unlock the phone if `screen_off` or a lock screen prevents
inspection. Use `android_ready`, then `android_observe` to verify the
connection. Report hierarchy and screenshot availability separately. Do not
open unrelated apps or enter personal text merely to prove installation.

If MCP tools are not yet visible after installation, start a new client
session and invoke this setup skill again. Installation is complete when the
plugin and both skills are discoverable and its MCP exposes the tools; phone
authorization may require a separate user action. Record any remaining device
step explicitly without claiming phone verification succeeded.
